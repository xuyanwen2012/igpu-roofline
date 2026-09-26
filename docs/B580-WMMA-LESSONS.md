# Arc B580 WMMA tuning: results and lessons (2026-09-26)

Roofline-guided tuning of the ExecuTorch Vulkan 4w (`linear_q4gsw_coopmat_tsweep_dbuf4`) and
8da4w (`linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpg`) prefill microkernels on an Intel Arc
B580 (BMG G21, Xe2, Mesa 26.2.3). Scope set by the owner: `test_llama_microbench` prefill
microkernels only; no decode, no end-to-end model runs.

- ExecuTorch branch: `yanwen/release14-quant-shaders-b580`, commit `7d47b6ee3` (pushed),
  based on `yanwen/release14-quant-shaders-b70` (`ab9978f16`). Only BMG G21 defaults change.
- Roofs: `results/fleet-fast-20260926/fedora/b580` (fast plan, automatic clocks, all roofs
  confirmed with spread <= 5 %).
- Raw runs, ISA and OA captures: `sarc-acl/.artifacts/roofline-et-study/` (`confirm/`,
  `sweep/`, `isa/`, `oa/`), negative experiments in `b580-8da4w-exploration-negative.patch`.

## Result

Branch defaults (no `ET_VK_*` overrides), Llama 3.2 1B / 3.2 3B / 3.1 8B prefill shapes
(M = 2048), 3 repeats each of `--linear` and `--baseline` (forced tiled), GT0 at 2850 MHz:

| B580 prefill | WMMA | % matrix roof | tiled | WMMA / tiled (geomean, min–max) |
|---|---|---:|---|---|
| 4w texture3d (model path) | 33.8–47.1 TFLOP/s | 30–42 % | 4.9–7.0 | **7.16×** (5.72–8.66) |
| 8da4w texture3d (model path) | 46.1–56.9 TOP/s | 20–25 % | 16.8–24.2 | **2.44×** (2.13–3.14) |
| 4w buffer | 38.2–55.1 TFLOP/s | 34–49 % | 5.2–5.8 | 8.98× |
| 8da4w buffer | 46.7–58.1 TOP/s | 20–25 % | 16.2–22.8 | 2.61× |

Before: the `-b70` branch's Xe2 tiles gave 2.9× / 1.55× on B580, and only with
`ET_VK_TEXTURE_COOPMAT=1`; without it an exported model (texture3d) ran the tiled kernels.
Correctness: `--correctness-only` 10/10 runs with zero failures; `--production-diff` passed
all four Llama 3.1 8B 8da4w shapes with the new kernel dispatched.

## What changed (and why)

| Change | Evidence | Effect (1B, texture3d unless noted) |
|---|---|---|
| Subgroup 16 tiles (`s16`) | ISA: the s32 Xe2 4w kernel compiles to SIMD32 with 11:26 spills:fills and scheduler mode "none"; s16 compiles to SIMD16 with 0 spills | 4w 19.2 → 36.9 TFLOP/s |
| 32×32 subgroup tiles for 4w (8 MMAs per A/B fragment load) | roofline `matrix_feed`: LDS-fed MMA rate scales ~linearly with reuse (B580 fp16: 28 / 54 / 102 / 106 TFLOP/s at 1 / 2 / 4 / 8) | part of the above |
| `WG_TILE_M = 256` for 8da4w | sweep: throughput rises with M because each workgroup's int4 dequant is shared by M rows; N ≤ 32 is slow because A staging is shared by N columns | 8da4w 32.4 → 52.7 TOP/s |
| `FRAG_LAYOUT` (4w): fragment-contiguous LDS, no row padding | the +8 fp16 row padding exists for AMD LDS banks; Xe OA shows zero SLM bank conflicts on BMG, while SLM read was at 83 % of the fp16-granularity SLM roof | buffer +12 % |
| `IMG_A` (4w texture3d): A via `imageLoad` (storage image) instead of `texelFetch` | texture3d ran 30–40 % below buffer with identical math | texture3d +6–29 % (tile dependent) |
| BMG G21 defaults + texture3d coopmat on by default | exported models use `TEXTURE_3D` storage (`vulkan_preprocess.py`), so the opt-in flag meant the model never used WMMA | model path gets WMMA |
| Buffer variants for the Xe2 tiles | the `-b70` branch shipped texture3d-only Xe2 variants, so buffer dispatch on Intel threw "Could not find ShaderInfo" | no crash |

## What did not help (measured, then dropped)

- `IMG_W` (weights via `imageLoad`): −7 to −10 %. The 2D weight access is well served by the
  sampler cache; only the row-streamed A operand benefits from the storage-image path.
- 4w subgroup tiles of 64×32 (16 MMAs): 199:208 spills, 4–5 TFLOP/s.
- 4w `WG_TILE_K = 32`: more LDS, lower occupancy, slower even with `FRAG_LAYOUT`.
- 8da4w with 8 MMAs per subgroup: 134–227 spills. Mesa stays at 128 GRF; there is no
  Vulkan-level way to request Xe2's 256-GRF mode.
- 8da4w single int32 accumulator (measurement-only ablation `ABL_ONE_ACC`, numerically wrong):
  at most +9 % (texture3d), 0 % (buffer). A per-channel int8 weight requant would change
  numerics and double weight bytes for at most that gain, so it was not pursued.
- 8da4w `A_BLOCKS` (larger K per barrier): no gain, so barriers are not its limiter.
- 8da4w `A_KVEC` (wider A staging stores): −12 to −49 %; fewer staging threads each wait
  serially on more global loads, which worsens the dominant SBID stall.
- 8da4w 16×32 subgroup tiles: slower than 32×16 (more B fragments per subgroup).
- fp32 8da4w results in SLM: a 256×64 fp32 tile needs 64 KiB > 48 KiB per workgroup.

## Why the kernels sit at 20–49 % of the matrix roof

The register-resident matrix roof is the wrong ceiling for a quantized GEMM: operands come
from SLM, so the relevant ceiling is the LDS-fed roof at the tile's reuse (≈ 70 TFLOP/s for
the 4w tile, ≈ 136 TOP/s for the 8da4w tile on B580). Xe OA (`VectorEngineStalls`,
`VectorEngineProfile`, `ComputeBasic`) on the tuned kernels:

| counter | 4w | 8da4w |
|---|---:|---:|
| XVE threads occupancy | 95 % | 100 %+ |
| XVE active / stall | 52 % / 39 % | 40 % / 54 % |
| stall: SBID (waiting on SLM/sampler results) | 47 % | 57 % |
| stall: barrier | 31 % | 20 % |
| stall: ALU dependency | 5 % | 20 % |
| SLM read | 2.86 TB/s | 2.28 TB/s |
| XMX / issued instructions | 32 % | 29 % |

Per K iteration the main loop issues ~674 (4w) / ~1194 (8da4w) instructions for 16 DPAS:
SLM staging, scoreboard syncs, address math and (8da4w) int4→int8 unpack and group folds.
The kernels are issue/latency bound on operand staging, not MMA bound. 8da4w is further
capped at 4 MMAs per subgroup because it keeps an int32 and an fp32 accumulator per tile.

## Lessons for the next GPU (B70, other Xe2, other vendors)

1. Put the kernel on the roofline with the matching ceiling first: the LDS/cache-fed
   `matrix_feed` roof at the tile's reuse explains far more than the register-resident peak.
2. Read the ISA before sweeping: SIMD width, spills and scheduler mode predicted the
   biggest single win (s32 → s16) and ruled out large subgroup tiles without timing them.
3. Use hardware counters when static analysis runs out: Xe OA separated SLM latency,
   barriers and ALU chains, and showed zero bank conflicts, which justified removing the
   AMD padding. On Xe2 it needs `dev.xe.observation_paranoid=0` (owner approval, restore to 1
   afterwards) and root for `xe-perf-recorder` (debugfs).
4. Test the storage the model actually uses. Exported models run linear on texture3d; the
   buffer numbers were up to 40 % better and misleading as a deployment metric.
5. Separate dispatch facts from intentions: the microbench's `kernel` field comes from the
   GPU query pool (the same source as ETDump), which exposed the missing buffer variants and
   the texture opt-in.
6. Shader defaults are per device even within a family: B580 (G21) and B70 (G31) preferred
   different tiles; key defaults on the device name and keep other devices untouched.
7. Correctness coverage shrinks as tiles grow: the correctness matrix stops at M = 256, so
   large-M tiles fall back to tiled there. Always add `--production-diff` on real shapes, and
   check which cases actually dispatched the new kernel.
8. Record negative results with numbers, and keep measurement-only switches out of the
   shipped branch (archive the patch instead).
9. Operational: `intel_gpu_top` does not support the xe driver (use sysfs `act_freq` /
   `throttle`); don't let background samplers inherit a `flock` fd; `pkill -f` can match the
   invoking shell.

# Intel Xe2 (Arc B580, Arc Pro B70) WMMA tuning: results and lessons (2026-09-26)

Two Battlemage GPUs, tuned in this order: Arc B580 (BMG G21, 20 Xe cores) first, then
Arc Pro B70 (BMG G31, 32 Xe cores) with the same method. The sections below describe
the B580 work in detail; [Arc Pro B70](#arc-pro-b70-bmg-g31) lists what carried over,
what differed, and its confirmed results.

| Texture3d prefill (model path), WMMA vs forced tiled, geomean | B580 | B70 |
|---|---:|---:|
| 4w | 7.16× | 7.25× |
| 8da4w | 2.44× | 2.70× |

## Arc B580 (BMG G21)

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

### Result

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

### What changed (and why)

| Change | Evidence | Effect (1B, texture3d unless noted) |
|---|---|---|
| Subgroup 16 tiles (`s16`) | ISA: the s32 Xe2 4w kernel compiles to SIMD32 with 11:26 spills:fills and scheduler mode "none"; s16 compiles to SIMD16 with 0 spills | 4w 19.2 → 36.9 TFLOP/s |
| 32×32 subgroup tiles for 4w (8 MMAs per A/B fragment load) | roofline `matrix_feed`: LDS-fed MMA rate scales ~linearly with reuse (B580 fp16: 28 / 54 / 102 / 106 TFLOP/s at 1 / 2 / 4 / 8) | part of the above |
| `WG_TILE_M = 256` for 8da4w | sweep: throughput rises with M because each workgroup's int4 dequant is shared by M rows; N ≤ 32 is slow because A staging is shared by N columns | 8da4w 32.4 → 52.7 TOP/s |
| `FRAG_LAYOUT` (4w): fragment-contiguous LDS, no row padding | the +8 fp16 row padding exists for AMD LDS banks; Xe OA shows zero SLM bank conflicts on BMG, while SLM read was at 83 % of the fp16-granularity SLM roof | buffer +12 % |
| `IMG_A` (4w texture3d): A via `imageLoad` (storage image) instead of `texelFetch` | texture3d ran 30–40 % below buffer with identical math | texture3d +6–29 % (tile dependent) |
| BMG G21 defaults + texture3d coopmat on by default | exported models use `TEXTURE_3D` storage (`vulkan_preprocess.py`), so the opt-in flag meant the model never used WMMA | model path gets WMMA |
| Buffer variants for the Xe2 tiles | the `-b70` branch shipped texture3d-only Xe2 variants, so buffer dispatch on Intel threw "Could not find ShaderInfo" | no crash |

### What did not help (measured, then dropped)

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

### Why the kernels sit at 20–49 % of the matrix roof

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

## Arc Pro B70 (BMG G31)

- ExecuTorch branch `yanwen/release14-quant-shaders-b70`: `9629b3910` (the B580 commit,
  cherry-picked), `7eefbb260` (G31 defaults), `545ccf85c` (sampled reference). Not pushed
  at the time of writing.
- Roofs: `results/fleet-fast-20260926/fedora-gpu-eval/b70-0`. The B70 has 1.55× the B580's
  matrix and FMA roofs, 1.30× its DRAM read, and 1.38× its 32-bit-granularity SLM read.

Round 1 (1B prefill, single runs) re-measured the B580 candidates on the B70: the same
tiles won (4w `t128x128k16g44s16fli`, 8da4w `t256x64k32g48s16`). The previous `-b70`
defaults ran at 36.1 TFLOP/s (4w) and 53.1 TOP/s (8da4w) on texture3d, versus 62.5 and 87.7
with the new tiles. The branch's per-shape 8B 8da4w tile (`t128x128k32g48s32`, G31 only)
was 1.56–1.73× slower than the new default on all four 8B shapes (3 repeats each), so it
was removed.

Confirmed (defaults only, 1B/3B/8B prefill, 3 repeats of WMMA and forced tiled, every cell
within 5 % repeat spread, GT0 at 2800 MHz):

| B70 prefill | WMMA | % matrix roof | tiled | WMMA / tiled (geomean, min–max) | vs previous `-b70` WMMA |
|---|---|---:|---|---|---:|
| 4w texture3d | 46.4–69.4 TFLOP/s | 27–40 % | 7.1–10.4 | **7.25×** (5.14–9.15) | 2.54× |
| 8da4w texture3d | 79.3–93.2 TOP/s | 22–26 % | 26.7–36.0 | **2.70×** (2.49–3.06) | 1.69× |
| 4w buffer | 56.6–81.1 TFLOP/s | 33–47 % | 7.7–8.7 | 9.05× | — |
| 8da4w buffer | 79.2–95.5 TOP/s | 22–27 % | 25.7–34.1 | 2.88× | — |

Correctness: `--correctness-only` 10/10 runs clean; sampled `--production-diff` passed all
four 8B shapes (~8,000 checked elements each, 27 s). Before the change, texture3d WMMA
needed `ET_VK_TEXTURE_COOPMAT=1`, so an exported model ran the tiled kernels.

What differed from the B580:

- `FRAG_LAYOUT` gained only 0–4 % (12 % on B580). Xe OA shows why: the 4w kernel reads SLM
  at 4.17 TB/s on B70, 42 % of the 32-bit-granularity SLM roof, so SLM bandwidth is not
  its limiter there (see lesson 10).
- 4w is healthier on the B70: XVE active 63 % (B580 52 %), stalls spread over SBID 32 %,
  barrier 18 %, instruction fetch 17 %.
- 8da4w's OA profile is nearly identical on both GPUs (SBID ~55 %, ALU dependency ~21 %,
  barrier ~20 %, 1.71 int32 instructions per XMX instruction): its limit is the kernel's
  structure (two accumulators, 4 MMAs per subgroup), not the GPU.
- The B70 host (fedora-gpu-eval) has no igt-gpu-tools; `xe-perf-recorder`/`-reader` were run
  from a private copy with the missing libraries (`LD_LIBRARY_PATH`), leaving the system
  unchanged. `observation_paranoid` was set to 0 only for the capture and restored to 1.

## Sampled reference for production-size correctness

`test_llama_microbench --production-diff` used to compute the full O(M·N·K) CPU reference
(Debug build, single thread): over 40 minutes for the four 8B shapes. `--ref-samples=N`
(default 8192 for `--production-diff`; `--ref-full` restores the full check) computes only
the tile-boundary rows/columns crossed with each other plus seeded random elements; the
comparator skips the rest and prints how many elements it checked. All four shapes now
take about 25 s. Addressing or layout bugs in a tile corrupt whole tiles or tile edges,
which this sample covers.

## Lessons for the next GPU (other Xe2, other vendors)

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
10. Match the roof to the kernel's access granularity (learned on B70). The B70's
    fp16-granularity SLM read roof (3.33 TB/s) is no higher than the B580's, which predicted
    an SLM wall and a large `FRAG_LAYOUT` gain on B70. Xe OA then measured the 4w kernel
    reading SLM at 4.17 TB/s — above that roof — because `coopMatLoad` uses wide
    accesses; against the 32-bit-granularity roof (10.0 TB/s) it is at 42 %, and
    `FRAG_LAYOUT` gained only 0–4 % on B70. A kernel rate above a roof means the wrong
    roof was chosen.

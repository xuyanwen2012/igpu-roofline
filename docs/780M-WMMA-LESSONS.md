# Radeon 780M WMMA tuning: results and lessons (2026-09-26)

Roofline- and profiler-driven tuning of the ExecuTorch Vulkan 4w
(`linear_q4gsw_coopmat_tsweep_dbuf4`) prefill microkernel on the AMD Radeon 780M
(Phoenix, gfx1103, RDNA3, RADV Mesa 25.2.7, host rocky-ryzen). Scope set by the owner:
`test_llama_microbench` prefill microkernels only. 8da4w was analysed but not changed.
See [XE2-WMMA-LESSONS.md](XE2-WMMA-LESSONS.md) for the Intel counterpart.

- ExecuTorch branch `yanwen/release14-quant-shaders-780m`, commit `9178cee44` (on top of
  `eae4d4af4`). Only the 780M selection changes (`device_name_contains("780m")`); other
  AMD devices keep the previous default.
- Roofs: `results/fleet-fast-20260926/rocky-ryzen/780m` (fast plan, automatic clocks).
- Raw runs, ISA dumps, profiles: `sarc-acl/.artifacts/roofline-et-study/`
  (`sweep/780m-*`, `confirm/780m-final`, `prof/780m-clock`). Measurement-only shader
  instrumentation and the negative B-layout experiments are archived as
  `780m-with-prof-and-dump.patch` and `780m-exploration-all-1750.patch`.

## Result

Defaults only (no `ET_VK_*` overrides), Llama 3.2 1B / 3.2 3B / 3.1 8B prefill (M = 2048),
3 repeats each of `--linear` and forced-tiled `--baseline`, every cell within 5 % repeat
spread; `--correctness-only` 10/10 runs clean.

| 780M prefill | WMMA | WMMA / tiled (geomean, min–max) | vs previous 780M default |
|---|---|---|---:|
| 4w texture3d (model path) | 9.7–10.8 TFLOP/s | **5.77×** (5.49–5.92) | **1.30×** |
| 4w buffer | 9.7–10.9 TFLOP/s | 4.68× (4.42–4.85) | 1.32× |
| 8da4w texture3d (unchanged) | 9.4–10.0 TOP/s | 1.34× (1.19–1.42) | 1.00× |

4w now runs at 66–73 % of the fp16→fp32 matrix roof (14.77 TFLOP/s). The previous
fp16-accumulate kernel also showed 1-in-16384 over-tolerance outputs at K = 4096; the
fp32-accumulate kernel has none.

## Profiling without hardware counters

No safe hardware-counter route exists on this iGPU:

- SQTT/RGP is banned in gpu-lab (it hung a machine).
- RADV 25.2.7 exposes no `VK_KHR_performance_query` on GFX11.
- `umr` needs root (sudo requires a password on rocky-ryzen).

What was used instead:

1. **Static ISA** — `RADV_DEBUG=shaders,shaderstats` (VGPRs, LDS, instruction mix per
   loop). Parse only the final `disasm:` block of each shader, not the IR dumps.
2. **`amdgpu_top`** (GRBM/GRBM2 via DRM ioctl, no root; built in a Rocky 10 container).
   Useful only to confirm clocks (2.74–2.80 GHz) and that the GPU is saturated: every
   block reads 97–99 % "busy" whenever a kernel runs, so it cannot locate a bottleneck.
3. **In-kernel phase timing** — the decisive tool:
   - How it works: `VK_KHR_shader_clock` (`clock2x32ARB`, 20-bit SHADER_CYCLES, deltas
     masked). A measurement-only `PROF` variant accumulates per-iteration cycles for four
     phases: barrier wait, prefetch issue, LDS→WMMA, and wait + dequant + LDS store.
   - Output: subgroup 0 of each workgroup writes the mean cycles per iteration into its
     tile's first output elements, which a test-utils hook (`ET_VK_DUMP_OUTPUT_DIR`) dumps.
   - It is safe (ordinary instructions) and gives per-phase time for every workgroup
     (variation across workgroups 1–8 %).
4. **Occupancy arithmetic**:
   - 780M limits: 1024 VGPRs per SIMD, 128 KiB LDS per WGP, 256-thread workgroups
     (2 waves per SIMD per workgroup).
   - Per-wave phase cycles must be read together with waves per SIMD: more resident
     waves make each wave slower but the SIMD busier.
   - Resident waves × 1 / cycles-per-iteration reproduced the measured speedups within
     2–3 %.

## What changed (and why)

| Change | Evidence | Effect |
|---|---|---|
| `ACC_FP32`: fp32 accumulator | ISA: the loop had ~350 `v_mov_b16`/`v_dual_mov_b32` per 32 WMMAs repacking the packed fp16 accumulator (v_wmma_f16 keeps one fp16 per VGPR); roofline fp16→fp32 14.77 vs fp16→fp16 10.96 TFLOP/s | VALU 637 → 330, VGPR 224 → 192/160; buffer 1.32×, texture3d 1.09×; K=4096 outliers gone |
| `CSH_IN_ASH`: texture3d drain staged in Ash (dead after the last MMA) | occupancy: texture3d held 4 waves/SIMD (LDS 45 KiB → 2 WG/WGP; VGPR 192), buffer 6 (37 KiB, 160 VGPRs); predicted 1.08 vs 1.29 relative throughput, measured 1.09 vs 1.32 | LDS 45 → 37 KiB, VGPR 192 → 160 → 6 waves/SIMD; texture3d 1.19× |
| One 780M default (`t128x128k32g42s32f32c`) for all shapes | the 3B-only g24 tile (fp16) measured 8.2 vs 10.8 TFLOP/s for f32c g42 on the 3B shapes | 3B override removed |

## What did not help: B tile stored column-major in LDS

Motivation: the ISA showed 128 `ds_load_u16` per wave per k32 chunk, because RDNA3 WMMA
wants a full 16-k column of B per lane and B was stored [k][n]. Four attempts:

| Attempt | Per-wave cycles/iter (LDS→WMMA / store phase) | vs f32c |
|---|---|---:|
| f32c reference | 2402 / 1112 | 1.00 |
| [n][k] fp16, one fp16 store per element | 2865 / ~4250 (8-way LDS bank conflict: 16 lanes on 2 banks) | 0.60× |
| + per-lane row rotation | 2128 / 2926 | 0.76× |
| one texel per thread (4× fewer fetches) | 1955 / 4118 (rotation became v_cndmask chains, stores stayed 16-bit) | 0.73× |
| uvec2 stores, static order | 2467 / 1438 | 1.00× |
| aliased fp16/uvec2 views (`VK_KHR_workgroup_memory_explicit_layout`) — `ds_load_b128` + `ds_store_b64` as designed | **2398** / 1506 | 1.01× |

The last row settles it: with wide LDS loads the LDS→WMMA phase did not shrink at all, so
that phase is bound by the WMMA instructions themselves, not by LDS reads. The apparent
LDS→WMMA savings in the intermediate rows were an artifact of waves being stuck in the
slow store phase (less WMMA contention). All B-layout code was reverted. The explicit-layout
extension is available on every GPU measured (780M, B580, B70, S24+, Pixel 7a), so the
archived patch stays reusable where LDS reads *are* the limiter.

## Why 4w is near its practical ceiling on the 780M

- WMMA pipe busy: 6 waves × 32 WMMAs × ~16 cycles ≈ 3072 of ~4500 cycles per iteration,
  about 70 %, which matches the kernel's 66–73 % of the fp16→fp32 roof.
- RDNA3 issues WMMA and VALU from the same SIMD, so the remaining time goes to the int4
  dequant and address VALU work plus barriers; it cannot overlap the way Intel's XMX does.
- Amortizing dequant over more rows (larger WG_TILE_M) breaks the occupancy budget:
  - M = 256 needs more LDS than the 3-workgroups-per-WGP limit of 43.7 KiB allows, or
    more VGPRs than the 6-waves limit of 168;
  - the tile is already at the 8-MMAs-per-fragment reuse that the LDS-fed roofline needs
    (14.5 TFLOP/s at reuse 8 vs 9.6 at 4).
- The next step would be a structural rewrite (e.g. producer/consumer waves that separate
  dequant from WMMA), with an expected ≈10 % at high risk; not pursued.
- 8da4w: the int8 matrix roof is only 1.23× the int8 dot roof on the 780M, and the kernel
  already sits at 65–70 % of it, so the theoretical headroom is ≈1.4× and the practical
  headroom is much less.

## Lessons (in addition to the Xe2 lessons)

1. On RDNA3, check the accumulator type against the roofline first: fp16-accumulate WMMA
   is 35 % slower than fp32-accumulate in the roofline itself, and the ISA shows why.
2. When no counters exist, time the kernel's own phases with `shader_clock`; it pinpointed
   every step here. Read per-wave phase time together with resident waves, never alone.
3. Compute occupancy (VGPRs, LDS per workgroup, waves per workgroup) for every candidate:
   the texture3d gap on the 780M was an occupancy cliff, not texture bandwidth.
4. A shrinking phase is only real if it survives when the other phases are fast. The B
   layout looked 20 % better in LDS→WMMA until the store phase was fixed.
5. LDS bank math before layout changes: 16 lanes striding 640 B hit 2 of 64 banks.
6. GLSL arrays of fp16 give 16-bit LDS stores and uvec2 arrays narrow loads. Aliasing needs
   `GL_EXT_shared_memory_block`, which in turn needs:
   - SPIR-V 1.4 (per-variant `VK_VERSION: '1.2'`);
   - `VK_KHR_spirv_1_4` on ExecuTorch's Vulkan 1.1 instance;
   - the feature enabled at device creation.
7. Remove obsolete per-shape overrides when a new default dominates on those shapes (as on
   B70 and here), and measure the override's own shapes before removing it.

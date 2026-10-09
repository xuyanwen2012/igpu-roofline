# Radeon 780M / final 4w and 8da4w linear kernels (780m-final) / matched roofs, no candidate / 2026-10-09

Copied from `docs/templates/SHADER-EXPERIMENT.md` before measuring (commit c7c4a53) and filled in afterwards.
This study measures and inspects; it changes no kernel, so the candidate and negative-result tables hold what
was compared, not a tuning screen. Unknown and untested items are named as such.

## Scope and provenance

- Decision this experiment will inform: whether a third tuning round on the linear kernels is worth starting on
  this device, and which roof each kernel is to be compared with (campaign `et-study-20261010`).
- Scope: kernel level, prefill (M = 2048). Operator and model level: not measured here; the in-model rates are
  cited from the tuning campaign's trace. Decode: out of scope.
- GPU registry ID, execution device/UUID, driver: `780m`; AMD Radeon 780M Graphics (RADV PHOENIX), deviceUUID
  00000000-c400-0000-0000-000000000000; RADV, Mesa 25.2.7 (package `mesa-vulkan-drivers-25.2.7-4.el10`, installed
  2026-05-29: the same under the September roofs and the tuning campaign), Vulkan 1.4.318, kernel 6.12.0-211.
  gpu-lab's checkout is not on the control workstation; the registry entry was taken from the copy in
  `results/fleet-fast-20260926/control/campaign-config.json` and the device verified with `vulkaninfo --summary`.
- Clock policy and observed GPU/memory clocks; power/thermal state: nothing pinned or changed. sclk levels 800 /
  1100 / 2799 MHz, `power_dpm_force_performance_level` auto, mclk up to 2800 MHz; CPU governor powersave, EPP
  balance_performance, tuned profile balanced. Part A: per-row telemetry in the campaign (GPU edge about 64 to 69 C
  during confirmation). Microbench: clock read once before and after each invocation (`et/clock.txt`: 2800 MHz
  after 9 of 9 timed invocations); not sampled during a run; temperature not recorded.
- Roofline campaign, source revision, runner/shader hashes: fast plan, 2026-10-09 19:14 to 19:36 UTC, igpu-roofline
  84361ac (unmodified clone, detached HEAD), runner sha256 f63d4ef143187e42..., shader manifest sha256
  03307d6b4d607bfe... (shaders compiled on the control workstation, copied). `uv run pytest`: 98 passed on both
  machines. A first run (17:49 to 18:12 UTC) is kept in `superseded/foreign-nvtop-part-a-run1/` (see its WHY.md).
- ExecuTorch checkout, commit, dirty patch, build options: final build `head4` of the tuning campaign (export of
  commit c639d4760, branch `topic/780m-prefill-refine`; built by that campaign, not by this study), binary
  `tests/test_llama_microbench` sha256 4d6f6acde6829053...; environment `ET_VK_SARC_UNVERIFIED=1
  ET_VK_SARC_DEV_PROFILE=780m-final`. Read-only: nothing built or written in those trees.
- Artifact paths: `et/linear-r0..r5.json` + `.log` (r0 is a warm-up invocation, unused), `et/sdpa-r1..r3.*`,
  `et/isa-*.stderr` (driver dumps), `et/sdpa-names.log` (fused kernel names + correctness tier `full`),
  `isa/` (split dumps, counts, SPIR-V, types), `et-trace/gemm.csv` (cited in-model trace), device folder
  (part A rows and `report/`), `efficiency.csv`, `summary-tables.txt`, `tools/`.
- Comparison budget and stopping condition: one fast plan, one timing run (6 linear + 3 attention invocations),
  one dump per scheme; no sweep. Stopped when every (model, shape, scheme) had a row. Device time used: 2 x 23
  minutes (part A and its repeat), 6 minutes (timing and dumps), under 1 minute (names).

## Workload and roof contract

- M/N/K, quantization scheme and group size, input rank/layout: the 12 linear shapes of Llama 3.2 1B, 3.2 3B and
  3.1 8B (wq_wo, wk_wv, w1_w3, w2) at M = 2048, schemes 4w and 8da4w, group size 128, rank 3 batch 1.
- Production storage; benchmark storage; any deliberate difference: texture3d I/O with texture2d packed weights in
  both; the buffer cases were also run (in the JSON) and are not in the table.
- Expected kernel and tile/subgroup; **observed dispatched kernel** and evidence: observed, from the `kernel`
  field of every timed case (same in all 5 repeats): 4w `sarc_dev_780m_x_linear_q4gsw_coopmat_` +
  `t128x128k32g24s32f32cbt` (1B wq_wo, wk_wv), `t256x128k32g28s32f32cbt` (1B w1_w3), `t128x256k32g42s32f32cbt`
  (3B wk_wv), `t256x128k32g24s32f32cbt` (3B wq_wo, w1_w3), `t256x128k32g18s32f32cbt` (1B w2, 3B w2, all 8B);
  8da4w `sarc_dev_780m_x_linear_dq8ca_coopmat_zpg_t256x64k64g48s32afmb1` (wq_wo, w1_w3) and
  `sarc_dev_linear_dq8ca_coopmat_zpg_bt_t128x64k32g22s32` (wk_wv, w2). They equal the campaign's dispatch record
  for `780m-final`. Fused attention: `sarc_dev_780m_sdpa_fused3sb_d64_t32x32g11s32rko` (1B),
  `..._d128_t16x64g11s32rko` (3B, 8B), from `et/sdpa-names.log`. Subgroup 32 in every kernel (ISA: wave32).
- Runtime overrides; default-on behavior separately checked: the two environment variables above; behaviour without
  them not measured here (the campaign's `dispatch.txt` has it).
- Operation/byte numerator and units; reload/reuse assumptions: 2 M N K per dispatch, TFLOP/s for 4w and TOP/s for
  8da4w (integer operations; the JSON field `gflops` of 8da4w is an operator-time figure and is not used).
  Operations per loaded operand byte: static, from the SPIR-V, multiply-adds x 8192 over the distinct 16 x 16
  operand tiles loaded (512 B fp16, 256 B int8): 21.33, 25.6 or 32 (4w), 21.33 or 42.67 (8da4w).

| Resource | Selected confirmed roof / source row | Why it matches | Unknowns or mismatch |
|---|---|---|---|
| Matrix | `matrix_fp16_fp32` 14.764 TFLOP/s (3 repeats, spread 0.14 %) for 4w and attention; `matrix_int8` 14.364 TOP/s (0.30 %) for 8da4w | fp16 x fp16 -> fp32 and int8 x int8 -> int32, 16 x 16 x 16, same WMMA opcode in kernel and roof shader (ISA) | roof at subgroup 64 (wave64), kernels at 32: no roof at 32 exists. 8 accumulators in the roof shader, 16 fp32 accumulator tiles per wave in the largest 4w kernel |
| Operand feed | `matrix_fp16_fp32_feed_shared` 14.452, `matrix_int8_feed_shared` 14.121 (CHAINS 8); by-reuse rows CHAINS 1 / 2 / 4 from `matrix_feed_by_reuse` | operands loaded from workgroup memory inside the loop | by-reuse rows at CHAINS 1 and 2 are single sweep rows (flagged); CHAINS 4 has 3 repeats. The roof shader loads B with 16 narrow LDS loads and waits; the kernels use 128-bit loads: the by-reuse row is exceeded by every linear kernel and is context, not a ceiling. Attention loads K and V from the storage buffer: its row is the cache-fed one, the shared-fed roof is context |
| Bandwidth | `texture_rgba16f_tex3d_cache` 82.27 GB/s, `texture_rgba16f_tex3d_dram` 40.80, `global_read` 86.74 (all confirmed) | used only for hypothesis 3 of part D: logical activation fetch M K 2 (N / tile N) bytes per dispatch | logical bytes, not physical traffic; cache residency of the activation slab unknown; the texture roofs' own limit (about 82 GB/s even cache-resident) is not understood |

Confirmation spread, duration, sentinel, conditions: 36 of 36 roofs confirmed, sentinel 3.14 to 3.28 TFLOP/s
against a 2.71 threshold, same sitting as the kernel timing (19:05 to 19:37 UTC), same driver and power state.

## Evidence before the screen

- ISA/pipeline evidence: `isa/README.md`, `isa/counts.csv`, `isa/et-stats.csv`. wave32; VGPRs 128 to 240 (4w),
  64 or 192 (8da4w), 256 (fused attention); 0 spills, 0 scratch; LDS 18432 to 61440 bytes; only
  `v_wmma_f32_16x16x16_f16` (4w, attention) or `v_wmma_i32_16x16x16_iu8` (8da4w); every operand tile loaded with
  `ds_load_b128`. Captured with `RADV_DEBUG=shaders,shaderstats` during real dispatches (1B shapes).
- If ISA is unavailable: not applicable. Not done: RGA offline cross-check; head_dim 128 fused kernel dump.
- Occupancy estimate and limiting resource; workgroup count vs resident slots: the driver's "Subgroups per SIMD"
  is 4, 6 or 8 for the 4w kernels, 5 or 16 for 8da4w, 12 to 18 for the roofline matrix shaders. Resident slots
  per SIMD and the number of SIMDs were not measured: unknown.
- Hypothesis, competing explanation, and observation that would disprove it: three hypotheses with their tests in
  `STUDY.md`, part D. None tested.
- Small candidate set derived from this evidence: none; no candidate was built.

## Measurements and controls

| Candidate / patch | Changed factor | Actual kernel | All repeat timings / spread | Whole-kernel gain | Phase/counter evidence | Verdict |
|---|---|---|---|---|---|---|
| Baseline = final configuration | none | the nine kernels above | per shape in `efficiency.csv`, column `notes` (5 repeat medians, spread 0.06 to 1.02 %) | 1.00x | cited from the tuning campaign, not repeated | 4w 69.3 to 81.7 %, 8da4w 74.1 to 82.6 % of the register roof |
| Candidate | none built | | | | | not applicable |

- Ablation limitations: no ablation run.
- Control preserving work while changing the suspected mechanism: none run; proposed as the tests of part D.
- Phase timing interpreted with occupancy/contention and total kernel time: cited only (campaign `proposal.md`);
  the phase shares are cycles of one wave and do not add up to unit utilisation: the 4w kernel reaches 78 % of
  the roof with 51 to 53 % of a wave's cycles in multiply-adds.
- At least three clean confirmation repeats: 5 timed invocations per case (linear), 3 (attention); one earlier
  invocation was stopped after 1 minute because of a foreign `nvtop` and is kept on the device host as superseded.

## Correctness and coverage

| Shape / rank / storage / scheme | Actual kernel | Full or sampled reference, count/seed/edge coverage | Tolerance / errors | Verdict |
|---|---|---|---|---|
| 24 prefill linear cases, texture3d | as above | not run in this study (`--skip-correctness`) | | untested here; the tuning campaign's gate (`verify.sh`, production-diff 12 of 12) is the evidence |
| attention, production head configurations S = 2048 (1B, 3B, 8B) and 8B S = 1024 pos 1024 | the `fused3sb` pair | tier `full`, full comparison, 4 cases | 0 mismatches in each case | passed (`et/sdpa-names.log`) |

The microbench reports dispatch `unexpected_coopmat` and exit code 1 for the linear suite: the development
kernels are not in its expected-name table. Timing success is not a correctness verdict.

## Negative results and decision

| Rejected candidate | Expected benefit | Measured regression / no gain | Explanation and confidence | Raw data / archived patch |
|---|---|---|---|---|
| by-reuse fed row as the kernel's ceiling (a comparison, not a kernel) | a tighter matched roof | every linear kernel exceeds it, 111 to 294 % | the roof shader's B tile takes 16 narrow LDS loads and a wait per iteration; the kernels' tiles take 2 wide loads. High confidence in the instruction counts, the causal reading is not tested | `isa/roofline/*_lds.isa.txt`, `isa/et/`, `efficiency.csv` |
| first part A run | | an idle `nvtop` attached for its last 9.5 minutes | repeated once; matrix roofs agree within 0.3 % | `superseded/foreign-nvtop-part-a-run1/` |

- Selected change and evidence supporting it: none; no kernel was changed.
- Alternative explanations still open: the three hypotheses of part D.
- Kernel gain / operator gain / model gain: none claimed; operator and model level untested.
- Speedup versus previous WMMA / forced tiled / deployment default: not measured here.
- Correctness failures or missing evidence preventing a deployment recommendation: no recommendation is made.
  Missing: linear correctness in this sitting, clocks during the microbench, a roof at subgroup 32, RGA cross-check,
  GPU-timestamp against wall-clock check.
- Follow-up with the highest expected information value: the matrix family of the roofline at required subgroup
  size 32 (hypothesis 1); a few minutes of device time.

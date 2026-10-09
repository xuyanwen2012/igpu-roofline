# RTX 4070 Ti SUPER / final linear and fused attention kernels / matched roofs, no candidate / 2026-10-09

Copied from `docs/templates/SHADER-EXPERIMENT.md` and committed (`7326bd7`, 17:49:06 UTC) before the first
measurement (17:49:43 UTC). This is a measurement study of the kernels a closed tuning campaign left: there is
no candidate, no kernel was changed and no experiment of part D was run. Sections of the template that need a
candidate say so. Summary for a reader: `STUDY.md`.

## Scope and provenance

- Decision this experiment will inform: whether a third tuning round on the linear (GEMM) kernels is worth
  starting on this device, and on which scheme.
- Scope: kernel, prefill (M = 2048). Operator and model level: not measured here; the tuning campaign's
  in-model trace (gate `s4-c1`) is cited per shape.
- GPU registry ID, execution device/UUID, driver: `4070tis`; NVIDIA GeForce RTX 4070 Ti SUPER, device UUID
  `81a511a2-de7e-c3c8-f641-3562c315ffa7`, host `gpu-dev-4004` (KVM guest, card passed through); proprietary
  driver 615.71.09 (Vulkan driverVersion 2580660800), Vulkan 1.4.351, kernel 7.0.0-38-generic. The gpu-lab
  checkout is not present beside this working copy, so access came from the task file and the host's own
  `gpu-harness --list` (device listed, `busy_pct` 0, no lock holder) plus `vulkaninfo --summary`.
- Clock policy and observed GPU/memory clocks; power/thermal state: nothing pinned or changed. Idle P8, 210 MHz,
  37 C, 8 W. Under load (part A, 463 samples at 90 % utilisation or more): 2490 / 2775 / 2790 MHz (minimum /
  median / maximum), at most 288 W against the 285 W limit, 38 to 69 C. Part B: median 2685 MHz, at most 255 W,
  46 to 68 C. Throttle reasons per 2 s (A) and 0.5 s (B) sample: `sw_thermal_slowdown`, `hw_thermal_slowdown`,
  `hw_slowdown` never active (761 + 759 samples); `sw_power_cap` active in 44 (A) and 218 (B); raw masks 0x1,
  0x4, 0x400, 0x404. Files: `sidecar-part-a/nvidia-smi-samples.csv`, `microbench/nvidia-smi-samples.csv`.
  Memory clock: not readable, unknown.
- Roofline campaign, source revision, runner/shader hashes: `et-study-20261010`, plan `fast`, this branch at
  `7326bd7` (tool sources `runner/`, `shaders/`, `igpu_roofline/` identical to `origin/main` `84361ac`; clean
  tree on the host: `sidecar-part-a/env-fast-*.txt`); runner sha256 `b1180c72e9c5...` (built on the host with
  the tool's own `build --host --no-shaders`), shader manifest sha256 `03307d6b4d60...` (shaders built on the
  control workstation with `build --host`, 98 tests passed; same manifest hash as `fleet-fast-20260926`).
- ExecuTorch checkout, commit, dirty patch, build options: the tuning campaign's final build `topic3`, commit
  `ed8b5af91`, no local patch (its `topic3.src.txt`); read only. `test_llama_microbench` sha256 `61d29fdb...`
  (equal to the campaign's record). Environment `ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=4070ti-fused1
  ETVK_DEVICE_INDEX=0`. Nothing was built or written in those trees (`git status` clean afterwards, no file
  newer than the start of the study).
- Artifact paths: roofs `report/` (REPORT.md, summary.json) and the raw rows beside it; `microbench/` (5 JSON +
  log per suite, sensor samples, GPU client log, `runs.txt`); `efficiency.csv`, `efficiency-detail.json`;
  `isa/` (kernel SPIR-V, disassembly and source, `kernel-coopmat-types.txt`, `raw/` driver statistics,
  `counts.csv`); `sources/` (the cited files of the tuning campaign, copied); `tools/` (every script used).
- Comparison budget and stopping condition: one `fast` plan (25 min of device time), 5 microbench processes per
  suite (6 min), one compile-only statistics pass. No sweep.

## Workload and roof contract

- M/N/K, quantization scheme and group size, input rank/layout: M = 2048; the 12 (model, shape) pairs of
  Llama 3.2 1B, 3.2 3B, 3.1 8B (wq_wo, wk_wv, w1_w3, w2) for 4w and 8da4w; group size 128 (reported by the run);
  rank-3 `[1, M, K]` activations as the microbench builds them.
- Production storage; benchmark storage; any deliberate difference: texture3d in the model; the texture3d rows
  of the microbench are used. Its buffer rows dispatch other tiles (`t128x256k16g42s32ga`,
  `t128x128k16g42s32ga`, the buffer zpgtr kernel) and are not in the table.
- Expected kernel and tile/subgroup; **observed dispatched kernel** and evidence: observed, from the `kernel`
  field of every microbench JSON, identical in all 5 processes and identical to the kernel of the same shape in
  the in-model trace: `sarc_linear_q4gsw_coopmat_t256x128k16g42s32ga_texture3d_texture2d_half` (11 of 12 4w
  shapes), `..._t128x128k16g24s32ga_...` (1B wk_wv), `sarc_linear_dq8ca_coopmat_zpgtr_t128x128k64g44s32mk32ra_
  texture3d_texture2d_half` (all 12 8da4w shapes). Attention: the microbench prints no kernel name for `--sdpa`;
  the names (`sarc_dev_4070ti_sdpa_fused3sb_d64_t32x32g11s32rko`, `..._d128_t16x64g11s32rko`) are from the
  campaign's in-model ETDump of the same build and environment (`sources/attention-kernel-evidence.txt`).
  Subgroup 32.
- Runtime overrides; default-on behavior separately checked: the two environment variables above; default-on
  behaviour not part of this study.
- Operation/byte numerator and units; reload/reuse assumptions: `2*M*N*K` per dispatch, TFLOP/s for 4w and
  TOP/s (integer operations) for 8da4w; unpack, dequantization, scaling and the fp32 group sums are not counted.
  Attention: executed matrix work of QK^T and attention x V over the tiles the kernel runs (formula in
  `tools/build_efficiency.py`; it reproduces the campaign's 1.745e10 / 2.658e10 / 3.543e10 flop per layer).
  Reuse = operations per loaded A/B tile byte for one subgroup and one K step, as the tool's
  `ops_per_load_byte`: derived from the shader source and checked against the static load and multiply-add
  counts of the SPIR-V (per row in the `notes` column).

| Resource | Selected confirmed roof / source row | Why it matches | Unknowns or mismatch |
|---|---|---|---|
| Matrix, 4w | `matrix_fp16` 182.95 TFLOP/s, `confirm/matrix_fp16_16x16x16_c8_*`, 3 repeats 0.05 % | fp16 x fp16 -> fp16 in every multiply-add of both kernels (SPIR-V), 16 x 16 x 16, subgroup 32 | the kernel also converts and adds each group's sum in fp32 (outside the multiply-add); the roof shader does not |
| Matrix, 8da4w | `matrix_int8` 369.24 TOP/s, `confirm/matrix_int8_16x16x32_c4_*`, 0.52 % | int8 x int8 -> int32, 16 x 16 x 32, subgroup 32 | none known |
| Matrix, fused attention | `matrix_fp16_fp32` 92.80 TFLOP/s, `confirm/matrix_fp16_fp32_16x16x16_c4_*`, 0.53 % | fp16 x fp16 -> fp32 in every multiply-add, 16 x 16 x 16, subgroup 32 | none known |
| Operand feed, 4w | `matrix_fp16_feed_shared` 177.94 (64 flop/B, 0.04 %); at reuse: `matrix_fp16_16x16x16_c4_lds` 173.55 (32 flop/B, 3 confirmation repeats, 0.7 %) | operands loaded from shared memory with `coopMatLoad`, as the kernel does | kernel reuse is 25.6 (`g42`) and 21.3 (`g24`) flop/B; no fp16 row below 32 in the `fast` plan |
| Operand feed, 8da4w | `matrix_int8_feed_shared` 367.69 (64 op/B, 0.04 %); at reuse: `matrix_int8_16x16x32_c2_lds` 367.06 (32 op/B) | as above; kernel reuse is exactly 32 op/B | **the 32 op/B row is a single sweep row, not confirmed**; flagged in every 8da4w row |
| Operand feed, attention | `matrix_fp16_fp32_feed_shared` 92.19; at reuse: `c4_lds` 92.15 (**sweep row, not confirmed**, d64) and `c2_lds` 92.65 (confirmed, d128) | nearest available | **not a matched source**: K and V are loaded from global buffers; context only |
| Bandwidth | context only: `texture_rgba32f_tex2d_cache` 1613.7 GB/s, `cache_read_effective` 7129.1, `global_read` 713.5 (all confirmed) | 16 B texel fetches of a cache-resident 2D texture; 16 B buffer loads | the kernel's weight texture is an integer one and each texel is fetched four times; logical bytes, not measured DRAM traffic |

Confirmation spread, duration, sentinel and device conditions: every roof above has 3 repeats within 0.7 %
except the two flagged rows; sentinel 34 probes, none degraded (25.40 to 25.66 TFLOP/s against a limit of
21.67); the roofs and the kernel rates were measured within 35 minutes of each other on the same boot, driver
and clock policy, with no other GPU client.

## Evidence before the screen

- ISA/pipeline evidence: `isa/counts.csv`, raw `isa/raw/*.pipestats.txt`. Subgroup 32 for every pipeline.
  Register Count / Binary Size / Shared Memory / local memory per thread: 4w `g42` 255 / 34688 B / 46592 B / 0;
  4w `g24` 170 / 20864 / 37376 / 0; 8da4w 123 / 15360 / 35328 / 48 B; attention d64 168 / 120704 / 6656 / 0;
  attention d128 204 / 29312 / 3456 / 0; roofline matrix shaders 60 to 95 / 4224 to 10624 / 0 or 4096 / 0.
  Stack Size 0 everywhere. No spill statistic exists. Access width in the source: 16 B (one `uvec4` activation
  load and two 16 B texel fetches per thread per chunk in 8da4w).
- If ISA is unavailable: **not ISA-verified**. The driver returns no internal representation (0 for all 15
  pipelines) and the pipeline cache blob is not readable (7.97 to 7.99 bits of entropy per byte). Substitutes:
  the five pipeline statistics, static SPIR-V counts, and rate against rate at the same shape and subgroup size.
- Occupancy estimate and limiting resource; workgroup count vs resident slots: not measured here. The September
  study's figure (one 512-thread workgroup per SM) is used once, labelled as an assumption, in `STUDY.md`.
- Hypothesis, competing explanation, and observation that would disprove it: three hypotheses with the evidence
  for and against each and the deciding experiment are in `STUDY.md`, part D. None was tested.
- Small candidate set derived from this evidence: none; out of scope.

## Measurements and controls

No candidate. The one measurement of kernel time:

| Candidate / patch | Changed factor | Actual kernel | All repeat timings / spread | Whole-kernel gain | Phase/counter evidence | Verdict |
|---|---|---|---|---|---|---|
| Baseline = final configuration | none | as observed, per shape | 5 processes per shape, every value in `efficiency-detail.json`; spread at most 1.0 % for the linear rows except 1B wk_wv 4w (2.4 %, a 42 us kernel on a 1.024 us timer step); attention 1.0 to 3.1 % | 1.00x | cited from the tuning campaign, not repeated (`sources/prof-parent-*.csv`) | measured |
| Candidate | not applicable | | | | | |

- Ablation limitations: none run. The cited phase timing comes from instrumented twins of the first campaign;
  the September study found that shader clock reads disturb scheduling on this driver, so the shares are read
  as approximate.
- Control preserving work while changing the suspected mechanism: not run; proposed per hypothesis.
- Phase timing interpreted with occupancy/contention and total kernel time: the multiply share of a wave (30 to
  38 %) and the clean kernel's share of the roof (37 to 42 %) agree; nothing else was derived from the phases.
- Confirmation repeats: 5 clean processes per shape, all kept, none excluded.

## Correctness and coverage

| Shape / rank / storage / scheme | Actual kernel | Full or sampled reference, count/seed/edge coverage | Tolerance / errors | Verdict |
|---|---|---|---|---|
| all rows of this study | as observed | **not tested here** (`--skip-correctness`; performance cases skip their reference) | | not tested |
| the final configuration | | the tuning campaign's gate `s4-c1` (its `STATUS.md`): `verify.sh` with production-diff, 192 of 192 attention cases | | cited, not re-run |

The microbench marks the texture3d rows `unexpected_coopmat`: its expectation predates default-on coopmat for
texture3d; the campaign's own runs show the same marker. It is not a correctness verdict.

## Negative results and decision

| Rejected candidate | Expected benefit | Measured regression / no gain | Explanation and confidence | Raw data / archived patch |
|---|---|---|---|---|
| none in this study | | | | |

- Selected change and evidence supporting it: none; the study changes nothing.
- Alternative explanations still open: all three hypotheses of part D.
- Kernel gain / operator gain / model gain: not applicable (no change); operator and model level untested.
- Speedup versus previous WMMA / versus forced tiled / versus deployment default: not measured.
- Correctness failures or missing evidence preventing a deployment recommendation: no recommendation is made.
  Missing: ISA; a confirmed int8 shared-fed row at 32 op/B and fp16 -> fp32 row at 32 flop/B; an fp16
  shared-fed row at the 4w kernels' reuse (21 to 26 flop/B); a texture roof with the kernel's format and fetch
  pattern; timestamps against wall clock.
- Follow-up with the highest expected information value: the roofline texture variant of hypothesis H2 (no
  kernel change, minutes), then the table-free fetch twin of H1.

## Deviations and things that did not go as written

- The copy of the results back to the workstation was restarted once (the share is slow for small files; a
  single archive was used instead). No measurement was affected.
- `--local-name 4070ti` was used so that the results root has the path the task names.
- The first `ssh` that launched part A stayed attached until its client timed out; the run itself was detached
  (`setsid nohup`) and was not affected.

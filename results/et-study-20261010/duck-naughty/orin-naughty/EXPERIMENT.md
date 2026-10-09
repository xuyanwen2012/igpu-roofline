# Jetson Orin Nano / tuned 4w, 8da4w and fused-attention kernels against matched roofs / no kernel change / 2026-10-09

Copied from `docs/templates/SHADER-EXPERIMENT.md` before measuring (commit `5c91538`), filled in afterwards.
This study measures and inspects; it changes no kernel and screens no candidate, so the candidate, correctness
and negative-result tables record what was observed, not a tuning loop. Paths are relative to this directory
unless they start with `/` or `~`.

## Scope and provenance

- Decision this experiment will inform: whether a third tuning round on the linear (GEMM) kernels is worth
  starting on this device, and which of the two older roof sets (16.0 / 32.3 or 9.7 / 19.5) is the valid yardstick.
- Scope: kernel level, prefill (M = 2048). Operator and model level: not measured here; the tuning campaign's
  in-model trace is cited per row. Decode: out of scope.
- GPU registry ID, execution device/UUID, driver: gpu-lab `orin-naughty`, host `duck-naughty`, NVIDIA Tegra Orin
  (nvgpu), Vulkan deviceUUID `b49259c9-868c-5b7c-b6f1-65a2bf4b63be` (returned by the runner's `identity`),
  driver 595.78 (`driver_version` 2496888832), L4T R39.2.1, kernel 6.8.12-1021-tegra, subgroup 32.
- Clock policy and observed GPU/memory clocks; power/thermal state: nothing changed, nothing pinned. `nvpmodel -q`:
  `15W` before and after every run. GPU devfreq governor `nvhost_podgov`, min 306 MHz, max 612 MHz; observed 612 MHz
  in 1787 of 1797 one-second samples with GPU load >= 50 % during part A (`logs-partA/clock-*.txt`); EMC 2133 MHz
  (cap 2133); 53 to 62 C on `gpu-thermal`; `tpc_pg_mask` 240. Snapshot: `device-state/before-partA.txt`. A `jtop`
  monitor of the same user was running (not a GPU job); no known GPU program was seen (`foreign-*.txt` absent).
- Roofline campaign, source revision, runner/shader hashes: this directory; igpu-roofline `84361ac` (origin/main),
  `igpu_roofline/`, `runner/`, `shaders/` unmodified; plan `fast`, 2026-10-09 18:14:15 to 18:53:36 UTC; runner
  SHA-256 `bdc8d65c4c5e8c75f22acb225c9d4069ece69dffe9f2812f141e6a2f711b2e69` (cross-built for aarch64 with
  `tools/cross_build_runner.sh` in the existing `et-jetson-cross:jp7.2.1` image from `runner/CMakeLists.txt`,
  linked against the device's `libvulkan.so.1`); shader manifest SHA-256 `03307d6b...` (identical to the
  2026-09-27 Jetson study's); `artifact-manifest.json`, `shader-shas.json`. The device copy has no `.git`, so the
  report prints `Code: None`; the commit is in `logs-partA/env-*.txt`.
- ExecuTorch checkout, commit, dirty patch, build options: read-only. Final build `topic4` of the tuning campaign
  `sarc-1.5-orin-fused-port` (commit `0bed380905e134c73b56838e4e920e953ee1234a`, staged on the device under
  `~/hmz-sarc-orin-fused/build/topic4/bundle/`; `test_llama_microbench` SHA-256 `72535d0f...`). Environment
  `ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=orin-fused1`. Known limitation accepted by the owner: its shaders
  were compiled by the cross image's `glslc` (shaderc v2026.1), not the pinned one. Nothing was built or written
  in those trees.
- Artifact paths: `report/` (REPORT.md, summary.json, all-configurations.csv), raw rows in the stage directories,
  `reuse-confirm/{shared,cache-c4,cache-c2}/` (focused confirmations), `partB/` (microbench logs and JSON, the
  cited trace), `isa/` (kernel SPIR-V, disassembly, type list, pipeline statistics, `counts.csv`),
  `efficiency.csv`, `tools/` (every script used), `device-state/`.
- Comparison budget and stopping condition: one `fast` plan (39 min), three focused confirmations (2 min), part B
  microbench (4 min) and pipeline statistics (10 s): about 46 minutes of device time against a 3 hour limit.

## Workload and roof contract

- M/N/K, quantization scheme and group size, input rank/layout: M = 2048; the four projection shapes of Llama
  3.2 1B, 3.2 3B and 3.1 8B (N x K in `efficiency.csv`); 4w and 8da4w; group size 128 (runtime header of the
  microbench JSON); rank-3 batch 1.
- Production storage; benchmark storage; any deliberate difference: texture3d activations / output and texture2d
  packed weights in both (`--storage=texture3d`). The 8da4w kernel reads its packed int8 activations from a
  buffer view produced by the activation quantize-and-pack dispatch (kernel source); that dispatch is not in the
  kernel time. The attention kernel is the buffer variant in both.
- Expected kernel and tile/subgroup; **observed dispatched kernel** and evidence: observed, from every run's JSON
  and identical across the 5 runs: 4w `sarc_linear_q4gsw_coopmat_orin_t256x128k16g42s32bt` (11 cells) and
  `sarc_dev_linear_q4gsw_coopmat_bx_t128x128k32g42s32f32c` (8B `w2`, K = 14336); 8da4w
  `sarc_linear_dq8ca_coopmat_zpgtr_orin_bf_t128x128k64g24s32mk32ra` (12 cells); attention
  `sarc_dev_orin_sdpa_fused3sb_d64_t32x32g11s32rko` (1B) and `..._d128_t16x64g11s32rko` (3B, 8B), the latter two
  from the run's `[sarc_dev] orin fused attention` line and the campaign's trace. The microbench labels the
  texture cells `unexpected_coopmat` (its expectation table, exit code 1); the kernel names are what ran.
- Runtime overrides; default-on behavior separately checked: the two environment variables above; default-on
  behavior not checked here (the campaign's gate did).
- Operation/byte numerator and units; reload/reuse assumptions: rate = 2 M N K / kernel time (TFLOP/s for 4w,
  TOP/s for 8da4w; attention 2 S S head_dim heads). Reuse = matrix operations per byte read by `coopMatLoad` for
  A and B, per subgroup and K step, the definition of the tool's fed-matrix rows; derivations in
  `tools/kernel_reuse.json` (from the kernel source of the build, consistent with the static SPIR-V counts).

| Resource | Selected confirmed roof / source row | Why it matches | Unknowns or mismatch |
|---|---|---|---|
| Matrix | 4w: `matrix_fp16` 9.684 TFLOP/s (3 repeats, spread 0.06 %); 8B `w2` and attention: `matrix_fp16_fp32` 9.731 (0.03 %); 8da4w: `matrix_int8` 19.512 TOP/s (0.02 %) | input and accumulator types read from each kernel's SPIR-V (`isa/kernel-coopmat-types.csv`): fp16 x fp16 -> fp16, fp16 x fp16 -> fp32, s8 16x32 x s8 32x16 -> s32; same 16 x 16 x 16 / 16 x 16 x 32 shape, subgroup scope, subgroup size 32 | the roof shader runs 32-thread workgroups, the linear kernels 256-thread ones |
| Operand feed | shared-fed: `matrix_fp16_feed_shared` 9.517, `matrix_fp16_fp32_feed_shared` 8.829, `matrix_int8_feed_shared` 17.411 (all 3 repeats). At the kernel's reuse: int8 at 32 ops/B 9.138 TOP/s, fp16 -> fp32 at 16 ops/B 8.227 TFLOP/s (`reuse-confirm/shared`, 3 repeats); attention, cache-fed: 3.987 at 32 ops/B, 2.223 at 16 ops/B (`reuse-confirm/cache-c4`, `cache-c2`) | all three linear kernels load staged tiles from shared memory with `coopMatLoad`; kernel reuse 25.6 (4w), 21.3 (4w fp32), 42.7 (8da4w) ops/B; attention loads K and V tiles from the storage buffer (32 / 16 ops per buffer byte) | **4w fp16: no matching row.** The only quality-passing fp16 shared-fed row is at 64 ops/B (the 32 ops/B row fails the sample-length gate at 3.8 ms; unqualified value 9.04); it is given as context and labelled so. 8da4w: the row is at 32, the kernel at 42.7; the next row (64 ops/B) reads 15.79. Attention: whether K / V are cache- or DRAM-resident during the kernel is not measured |
| Bandwidth | not used for a percentage. Context: DRAM read / write / copy 62.26 / 58.09 / 64.05 GB/s, shared fp16 read / write 566.4 / 335.1 GB/s (all confirmed) | - | no byte model of the kernels' texture traffic was built; texture roofs differ in format from packed weights |

Confirmation: `fast` plan, top 2 x 3 fresh-process repeats; every roof used has 3 quality repeats within 2 %.
Sustained: one 120 s batch of `alu_fp16`, `global_read`, `matrix_fp16_fp32` (9.729), steady; not a three-batch
sustained roof. Sentinel: 34 probes, 0 degraded (reuse runs: 0 degraded). Conditions of roofs and kernel timings
are the same sitting (18:03 to 18:59 UTC), same clock state.

## Evidence before the screen

- ISA/pipeline evidence: `isa/counts.csv` and `isa/pipeline-stats-kernels/*.stats.txt`
  (`VK_KHR_pipeline_executable_properties`, captured with the `vkpipestats` binary the first Jetson study left on
  the device, specialization constants of the benchmarked shapes: local size 256, `K4_per_group` 32,
  `num_groups` K / 128; attention local size 32). Subgroup 32; registers 128 (4w), 128 (4w fp32), 208 to 209
  (8da4w), 216 / 255 (attention); stack size 0; shared memory 45056 / 43008 / 35328 / 4736 / 3456 bytes. Roofline
  shaders: `pipeline-inspection/` (66 to 130 registers).
- If ISA is unavailable: **not ISA-verified.** The driver returns statistics and no internal representation, for
  the kernels and for the roofline shaders. Substitute: rate against rate at the same matrix shape and subgroup
  size (4w at 3.3 to 3.6 times the scalar fp16 FMA roof, 8da4w at 2.4 to 2.7 times the int8 dot roof), the static
  MulAdd counts of the SPIR-V against the tile arithmetic, and the first Jetson study's Nsight tensor-activity
  counters (cited in `docs/JETSON-WMMA-LESSONS.md`; not repeated).
- Occupancy estimate and limiting resource; workgroup count vs resident slots: not measured. At 209 registers per
  thread a 256-thread workgroup needs about 53.5 K registers, at 128 about 32.8 K; the first Jetson study derived
  two workgroups per SM at about 32 K. SM register capacity is taken from that study, not read from the device.
- Hypothesis, competing explanation, and observation that would disprove it: see STUDY.md part D (three
  hypotheses with evidence for, against and the cheapest deciding experiment). None was run.
- Small candidate set derived from this evidence: none built; a 4 x 4 accumulator tile of the `bf` family is the
  first candidate named.

## Measurements and controls

| Candidate / patch | Changed factor | Actual kernel | All repeat timings / spread | Whole-kernel gain | Phase/counter evidence | Verdict |
|---|---|---|---|---|---|---|
| Baseline = final configuration | none | as listed above | `partB/linear-prefill/run1..5.json`, `partB/sdpa-prefill/run1..5.json`; spread per cell in `efficiency.csv` notes (linear at most 0.72 %, attention 0.82 %) | 1.00x | tuning campaign phase timing, cited (first Orin campaign STATUS, "8da4w linear: phase timing"; "4w linear: phase timing") | measured |
| Candidate | none (compile and inspect study) | - | - | - | - | not applicable |

- Ablation limitations: no ablation was run.
- Control preserving work while changing the suspected mechanism: none run; proposed in part D.
- Phase timing interpreted with occupancy/contention and total kernel time: cited shares are of one wave of an
  instrumented twin (campaign data), used only to check that kernel rate / MMA share lands on the fed roof at the
  kernel's reuse (9.0 to 11.1 against 9.1 to 15.8 TOP/s).
- At least three clean confirmation repeats: 5 fresh processes per suite, all retained. Two earlier trial runs
  (`partB/trial`, `partB/trial2`) are kept: the first stopped at the small correctness gate (below), the second
  checked the invocation on the 1B model.

## Correctness and coverage

| Shape / rank / storage / scheme | Actual kernel | Full or sampled reference, count/seed/edge coverage | Tolerance / errors | Verdict |
|---|---|---|---|---|
| microbench small gate, texture3d, both schemes (`partB/trial/run1.log`) | stock fallback kernels (`q4gsw_linear_gemm...`, `linear_dq8ca_q4gsw_tiled...`), not the kernels of this study | full reference on M = 128 cases | abs 0.5, rel 0.05; `linear_q4gsw_M128_K4096_N128` 6 / 16384 and (rank 3) 2 / 16384 elements outside | **FAILED, pre-existing**, same failure recorded by the tuning campaign; says nothing about the timed kernels |
| the 24 production cells and the attention cells | the timed kernels | not re-run here (`--skip-correctness`); the tuning campaign's gate (production-diff, attention tiers) is its record | - | **untested in this study** |

Timing success is not a correctness verdict. Operator and model validation: outside this study.

## Negative results and decision

| Rejected candidate | Expected benefit | Measured regression / no gain | Explanation and confidence | Raw data / archived patch |
|---|---|---|---|---|
| none (no candidate) | | | | |

Things that did not work and are kept: fp16 shared-fed row at 32 ops/B (`matrix_fp16_16x16x16_c4_lds`) fails the
`short` gate in the `fast` sweep and again in the focused run (`reuse-confirm/shared`), so the 4w kernels have no
matched fed roof at their reuse. `matrix_fp16_fp32_feed_cache` of part A has 2 quality repeats (`repeat_unstable`)
and is not used; its focused re-run confirmed 3.987 with 3 repeats.

- Selected change and evidence supporting it: none; no kernel was changed.
- Alternative explanations still open: operand-load bound against occupancy against staging time for the 8da4w
  kernel (part D); whether the roof at the kernel's exact reuse (42.7 ops/B) is nearer 9.1 or 15.8 TOP/s.
- Kernel gain / operator gain / model gain: none claimed (untested at all three levels).
- Speedup versus previous WMMA / versus forced tiled / versus deployment default: not measured.
- Correctness failures or missing evidence preventing a deployment recommendation: no recommendation is made.
  Missing: ISA, occupancy counters, production correctness in this sitting, the higher clock state.
- Follow-up with the highest expected information value: the 4 x 4 accumulator screen of hypothesis 1 with its
  pipeline statistics; and the owner's decision on one measurement in power mode `MAXN_SUPER` (STUDY.md).

## Which roof set (device-specific question)

- Higher set: `results/fleet-quick-20260925/duck-naughty/orin-naughty` of the main checkout (plan `quick`,
  2026-09-26 05:09 to 05:24 UTC, fleet tree `3bd916f6`). Its controller wrote GPU `min_freq` = `max_freq` =
  1020 MHz and locked the EMC rate (`clock-profile.json`, `clock-original.json`, `clock-restored.json`;
  `clock-before.txt` shows GPU 1020 / 1020 / 1020 MHz, CPU max 1728 MHz, EMC max 3199 MHz, `NV Power Mode: 15W`).
  Copies: `device-state/older-sets/`.
- Lower set: `out/jetson-study/roofline-results/orin-naughty` of the main checkout (plan `fast`, 2026-09-27 05:18
  UTC; `logs/clock-power-readonly.txt`: 15 W, EMC 2133 MHz) and the tuning campaign's run of 2026-10-09 13:59
  UTC (306 to 612 MHz, nothing pinned).
- Between them: reboot on 2026-09-26 21:45 local time (`last -x reboot`, in `device-state/before-partA.txt`).
  Present power-mode table (`/etc/nvpmodel.conf` -> `nvpmodel_p3767_0003_super.conf`): `15W` GPU max 612 MHz, `25W`
  918 MHz, `MAXN_SUPER` uncapped (1020 MHz).
- Roof by roof the higher set is 1.65 to 1.66 times the lower for every compute roof (clock ratio 1.667).
- This run reproduces the lower set (9.684 / 9.731 / 19.512 against 9.696 / 9.736 / 19.519).
- Not established: why the caps before that reboot were those of `MAXN_SUPER` while the label read `15W`.

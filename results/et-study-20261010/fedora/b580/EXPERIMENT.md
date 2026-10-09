# Arc B580 / final linear kernels (4w, 8da4w) and fused attention against matched roofs / 2026-10-09 (campaign `et-study-20261010`)

Copied from `docs/templates/SHADER-EXPERIMENT.md` before the first measurement (commit `f87e89a`), filled in
afterwards. This is a measurement and inspection study: no kernel was changed, no candidate was screened.

## Scope and provenance

- Decision this experiment will inform: whether a third tuning round on the linear kernels is worth starting on
  this card, and where (owner's question in the task file).
- Scope: kernel level, prefill (M = 2048). Operator and model level: not measured here; the tuning campaign's
  in-model trace is cited, not re-run.
- GPU registry ID, execution device/UUID, driver: `b580`, Intel Arc B580 (BMG G21), deviceUUID
  `86800be2-0000-0000-0300-000000000000`, Vulkan device 0, ANV Mesa 26.2.3 (driver version 109060099), Linux
  7.2.9-200.fc44. The gpu-lab checkout is not present beside this clone; the registry entry used is the copy in
  `results/fleet-fast-20260926/control/campaign-config.json` and the device was verified live with
  `vulkaninfo --summary` and the gpu-lab harness `--list`.
- Clock policy and observed GPU/memory clocks; power/thermal state: as found, nothing pinned or changed:
  GT0 `min_freq` 1200, `max_freq` 2850, `rp0` 2850, `rpn` 400 MHz, `power_profile` `[base] power_saving`.
  Observed while measuring (`logs/*.share.jsonl`, 2 s samples): 2850 MHz under load in part A (median), 2767 to
  2850 MHz in the microbench runs; throttle reason `pl2` appears in part A and in the three 4w microbench runs
  (power limit, counted, as in the tuning campaign), no thermal reason; package temperature at most 67 C.
  Memory clocks: unknown (no sensor).
- Desktop: the card drives the display. gpu-lab harness busy level before part A 0 % (threshold 50 as in
  September); foreign DRM engine share during every job 0.00 to 0.02 % (`logs/*.share.jsonl`, column
  `foreign_pct`); no foreign GPU workload seen (`logs/*.foreign` all empty); no run was rejected or repeated.
- Roofline campaign, source revision, runner/shader hashes: this results root, plan `fast`, code `f87e89a`
  (= `origin/main` `84361ac` plus files under this results root only), runner sha256 `784e6acafa0a54e5...`,
  shader hashes in `shader-shas.json` / `artifact-manifest.json`. Tool, shaders and runner unmodified
  (`git diff --stat origin/main -- igpu_roofline runner shaders` is empty). Focused confirmation repeats of four
  shared-fed variants with the same build: `../b580-reuse-<variant>/` (`tools/run_reuse.sh`).
- ExecuTorch checkout, commit, dirty patch, build options: tuning campaign's final build `topic7` =
  `e1e450530f088a576c03d5e7b4af91a2647218a0` (export of that commit, no patch; `topic7.src.txt` of the campaign),
  used read-only; `test_llama_microbench` sha256 `f7f7b5bd5ad094cac21d55d80815de702a5af61f395eb4b325be0dbf4a2a2e4d`
  (`microbench/env.txt`). Configuration `ETVK_DEVICE_INDEX=0 ET_VK_SARC_UNVERIFIED=1
  ET_VK_SARC_DEV_PROFILE=b580-fused1`. Nothing was built or written in the ExecuTorch trees.
- Artifact paths: `report/` (part A), `microbench/*.json|log` (part B raw), `efficiency.csv`, `isa/` (`raw/` dumps,
  `loops/` excerpts, `counts.csv`, `spirv-types.csv`), `cited/` (copies of the two campaign trace tables used),
  `logs/` (status files, desktop share), `tools/` (scripts).
- Comparison budget and stopping condition: one `fast` plan (24 min), 3 microbench processes per scheme, 5 for
  attention, one compile dump per kernel; no experiment of part D is run.

## Workload and roof contract

- M/N/K, quantization scheme and group size, input rank/layout: M = 2048; the 12 (N, K) shapes of Llama 3.2 1B,
  3.2 3B, 3.1 8B that the microbench reports (`wq_wo`, `wk_wv`, `w1_w3`, `w2`); 4w and 8da4w; group size 128
  (JSON field `group_size`); rank 3, batch 1.
- Production storage; benchmark storage; any deliberate difference: texture3d in both (`--storage=texture3d`).
- Expected kernel and tile/subgroup; **observed dispatched kernel** and evidence: observed (JSON field `kernel`,
  identical in all three processes and all 12 shapes per scheme): 4w
  `sarc_linear_q4gsw_coopmat_t128x128k16g44s16m8fli_texture3d_texture2d_half`, 8da4w
  `sarc_dev_linear_dq8ca_coopmat_zpg_xe2bt_t128x128k64g84s16m8_texture3d_texture2d_half`. Both as the campaign
  records. The microbench exits with status 1 because it labels a cooperative-matrix dispatch on texture3d
  `unexpected_coopmat` (an old expectation of the test; the tuning campaign accepts status 0 or 1 for the same
  reason, `tools/screen_rows.py`). Attention: `--sdpa` does not print a kernel name; the profile selects
  `sarc_dev_b580_sdpa_fused_d64_t16x64s16m8g4roj` (head_dim 64) and `..._d128_t16x128s16m8g8oj` (head_dim 128)
  (campaign `proposal.md`, "Result"; named in its `sdpa-correctness` logs); in this run the three separate
  kernels report 0 us and the op total is 0.73 / 1.13 / 1.46 ms, and the compile dump of the same process
  configuration contains exactly two fp16 -> fp32 dpas shaders with 16 and 32 dpas, the multiply-add counts of
  those two SPIR-V modules (`isa/spirv-types.csv`). The name is therefore inferred, not read from the run.
- Runtime overrides; default-on behavior separately checked: the profile above only; default dispatch not
  checked (out of scope).
- Operation/byte numerator and units; reload/reuse assumptions: `2*M*N*K / kernel_time` (TFLOP/s for 4w, TOP/s
  for 8da4w). Reuse as operations per loaded A/B byte per subgroup and K step: 4w 16.0 (8 multiply-adds per
  4 A + 2 B fragments), 8da4w 21.33 (4 multiply-adds per 4 A + 1 B fragments); derivation in
  `tools/efficiency.py`, confirmed by the dpas and shared-memory load counts of `isa/counts.csv`.

| Resource | Selected confirmed roof / source row | Why it matches | Unknowns or mismatch |
|---|---|---|---|
| Matrix, 4w | `matrix_fp16` 111.72 TFLOP/s (3 repeats, spread 0.0 %) | fp16 x fp16 -> fp16 accumulator (SPIR-V: every `OpCooperativeMatrixMulAddKHR` is fp16 8x16 A, fp16 16x16 B, fp16 8x16 Acc), shape 8x16x16 | roof measured at subgroup 32 (SIMD32), kernel requires subgroup 16 (SIMD16); the tool has no subgroup-16 row |
| Matrix, 8da4w | `matrix_int8` 231.37 TOP/s (3 repeats, 0.0 %) | sint8 x sint8 -> sint32, shape 8x16x32 | same subgroup mismatch |
| Matrix, attention | `matrix_fp16_fp32` 115.68 TFLOP/s (3 repeats, 0.0 %) | fp16 x fp16 -> fp32, 8x16x16 | same subgroup mismatch |
| Operand feed, 4w | fed shared (CHAINS 8) `matrix_fp16_feed_shared` 109.76 (0.0 %). **At the kernel's reuse: no matching roof** | | fp16 -> fp16 shared-fed rows at CHAINS 2 and 4 fail the tool's gates (`short; fixed_cost`) in part A and in the focused repeats. Context only (other accumulator): fp16 -> fp32 CHAINS 2 53.51 (confirmed in `../b580-reuse-matrix_fp16_fp32_8x16x16_c2_lds`), CHAINS 4 101.92 (confirmed in part A) |
| Operand feed, 8da4w | fed shared (CHAINS 8) `matrix_int8_feed_shared` 206.36 (0.2 %); at the kernel's reuse: int8 shared-fed CHAINS 2 (21.33 ops per loaded byte, equal to the kernel's) 72.81 TOP/s, 3 repeats, spread 0.4 % (`../b580-reuse-matrix_int8_8x16x32_c2_lds`; part A single sweep row 72.87) | type, shape, source and ops per loaded byte match | **access width does not match**: the roofline shader loads each B tile with 16 byte-wide shared-memory messages (`d8u32`), the kernel with 2 messages of four 32-bit words (`d32x4`); and SIMD32 against SIMD16. Four shapes read 100.1 to 103.4 % of this row: it is not a ceiling for this kernel |
| Operand feed, attention | no matching roof | | K and V tiles come from storage buffers, e from shared memory; mixed reuse |
| Bandwidth | not used for a percentage | | byte model of weights / activations not built in this study |

Sentinel `ok` at all 34 checkpoints of part A (11.680 to 11.681 TFLOP/s); every roof of part A confirmed (36 of
36, largest repeat spread 1.5 %); sustained: one 120 s batch for three roofs, equal to the short-run value (not
three batches, so short-run roofs are used).

## Evidence before the screen

- ISA/pipeline evidence (no screen follows; this is part C): kernels through `INTEL_DEBUG=cs` with
  `MESA_SHADER_CACHE_DISABLE=true` (Mesa 26.2.3 documentation of `INTEL_DEBUG`: "cs: dump shader assembly for
  compute shaders"; the dump carries a statistics line per shader), 1B shapes, `isa/raw/et-*.cs.log`; roofline
  shaders through `VK_KHR_pipeline_executable_properties` (the tool's `pipeline-inspection/`, copies in
  `isa/raw/roofline/`). Counts in `isa/counts.csv`, loop listings in `isa/loops/`.
  - 4w kernel: SIMD16, 960 instructions, 1 loop, 0:0 spills:fills, 128 GRF; loop per K = 16: 8 dpas (= 4 x 2
    tile arithmetic), 48 shared-memory load messages (32 of them 16-bit gathers for the two B tiles, 16 of 32
    bit for the four A tiles), 2 shared stores (4 x 32 bit), 1 sampler, 2 typed-image loads, 1 global load,
    1 barrier, 70 sync.
  - 8da4w kernel: SIMD16, 1370 instructions (1043 in the second compiled variant), 0:0 spills:fills; loop per
    quantization group K = 128: 16 dpas (= 4 x 1 x 4 K steps), 73 shared-memory load messages (65 of 32 bit,
    8 of 4 x 32 bit), 17 shared stores, 2 sampler, 3 global loads, 2 barriers, 196 sync.
  - Fused attention: SIMD16, 927 (head_dim 64) and 1095 (head_dim 128) instructions, 0:0 spills:fills, 16 and
    32 dpas in the block loop.
  - Roofline register roofs: SIMD32, 0 spills, 8 dpas in a 13- or 14-instruction loop with no send.
    Shared-fed: SIMD32, per A/B pair 2 x 32-bit loads for A and 8 x 16-bit (fp16) or 16 x 8-bit (int8) gathers
    for B.
- Occupancy estimate and limiting resource: not estimated (no hardware counter capture in this study).
- Hypothesis, competing explanation, and observation that would disprove it: part D of `STUDY.md`.
- Small candidate set derived from this evidence: none run; three hypotheses listed in `STUDY.md`.

## Measurements and controls

Clean timing only (GPU timestamps of the microbench); no instrumentation. No baseline/candidate comparison.

| Candidate / patch | Changed factor | Actual kernel | All repeat timings / spread | Whole-kernel gain | Phase/counter evidence | Verdict |
|---|---|---|---|---|---|---|
| Final configuration, 4w | none | `sarc_linear_q4gsw_coopmat_t128x128k16g44s16m8fli` | 3 processes x 12 shapes, spread of the process medians per shape in `efficiency.csv` notes (at most 0.6 %) | 1.00x | campaign phase split cited in `STUDY.md` | measured |
| Final configuration, 8da4w | none | `sarc_dev_linear_dq8ca_coopmat_zpg_xe2bt_t128x128k64g84s16m8` | same (at most 2.2 %) | 1.00x | phase split exists only for the previous tile | measured |
| Fused attention | none | inferred, see above | 5 processes, spread at most 0.5 % | 1.00x | | measured |

- Ablation limitations: none run.
- Control preserving work while changing the suspected mechanism: none run.
- Phase timing: not repeated (cited).
- Confirmation repeats: 3 processes per scheme, all kept.

## Correctness and coverage

| Shape / rank / storage / scheme | Actual kernel | Full or sampled reference, count/seed/edge coverage | Tolerance / errors | Verdict |
|---|---|---|---|---|
| all 24 linear cases, 3 attention cases | as above | **not tested in this study** (`--skip-correctness`; the campaign's gate `s6-final` on the same build is `GATE_PASS`) | | not tested here |

Known defect recorded by the campaign and unchanged: cooperative-matrix pipelines are created without
`VK_PIPELINE_SHADER_STAGE_CREATE_REQUIRE_FULL_SUBGROUPS_BIT` (its finding F1); the rates here are of such
pipelines.

## Negative results and decision

| Rejected candidate | Expected benefit | Measured regression / no gain | Explanation and confidence | Raw data / archived patch |
|---|---|---|---|---|
| none (no candidate) | | | | |

- Selected change and evidence supporting it: none; the study recommends where to look (`STUDY.md`, part D).
- Alternative explanations still open: effect of SIMD16 against SIMD32 on the roofs; the true shared-fed ceiling
  at low reuse with 32-bit loads; whether small-N shapes are launch-limited.
- Kernel gain / operator gain / model gain: none claimed; operator and model level untested.
- Correctness failures or missing evidence preventing a deployment recommendation: not applicable (no change).
- Follow-up with the highest expected information value: hypothesis 2 of `STUDY.md` (a shared-fed roof with
  32-bit loads at subgroup 16), because it decides whether the 8da4w kernel has any headroom at its reuse.

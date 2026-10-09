# Arc Pro B70 / final 4w, 8da4w linear and fused attention kernels / how far from the matched roofs / 2026-10-09

Campaign `et-study-20261010`, device key `b70`. Copied from `docs/templates/SHADER-EXPERIMENT.md` before
measuring (commit `56325c9`) and filled in afterwards. This is a measurement and inspection study: no kernel was
changed, no candidate was screened.

## Scope and provenance

- Decision this experiment will inform: whether a third tuning round on the linear kernels is worth starting on
  this card, and with which hypothesis.
- Scope: kernel; prefill (M = 2048). Operator and model level: not measured here; the tuning campaign's in-model
  trace is cited.
- GPU registry ID, execution device/UUID, driver: `b70-0`; Intel(R) Graphics (BMG G31), deviceUUID
  `868023e2-0000-0000-0100-000000000000` (card 0 of two, the second idle); ANV, Mesa 26.2.3 (driverVersion
  109060099); kernel 7.2.9-200.fc44 (the September roofs were measured on the previous kernel).
- Clock policy and observed GPU/memory clocks; power/thermal state: as found, nothing changed: GT `min_freq` 1200,
  `max_freq` / `rp0` 2800, `rpe` / `rpn` 400 MHz, `power_profile` `[base] power_saving`. Observed `act_freq`
  (2 s sysfs samples, `logs/*.samples.tsv`): part A mean 2726 MHz over non-idle samples, part B 2768 to 2794 MHz
  per run (lowest single sample 2000). Throttle: only the power-limit reason `pl2` (16 of 680 samples in part A,
  5 or 6 per part B run), never a thermal reason. Package 56 to 76 C. The tool itself reports the clock state as
  unavailable on Intel.
- Roofline campaign, source revision, runner/shader hashes: this directory; igpu-roofline `84361ac` (branch
  `study/et-20261010-b70`; `runner/`, `shaders/`, `igpu_roofline/` byte-identical to the September source except
  `workload.py`, which no measurement uses). Runner `810e098c8abb...` and inspector `e4b28a2cbe92...`: the
  September binaries copied unchanged (a rebuild with today's compiler gave another hash from the same source and
  was not used, `../build-hashes.txt`). Shader manifest `03307d6b4d60...`, rebuilt here from source, identical
  to September's. Controller: `results/fleet-fast-20260926/control/campaign.py`, unchanged.
- ExecuTorch checkout, commit, dirty patch, build options: the tuning campaign's working copy (branch
  `topic/b70-fused-port`, head `c3d67a821`, clean; commits after the build touch only `openspec/`), build `topic2`
  = export of `6ac44c483`. `test_llama_microbench` sha256 `42c40e60...`, run from a byte-identical copy
  (`raw/binary.sha256`). Environment `ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=b70-fused1
  ETVK_DEVICE_INDEX=0`. Nothing was built or written in the ExecuTorch trees.
- Artifact paths: `report/` (tool report), `raw/` (microbench JSON and logs, 3 processes each), `cited/` (the
  campaign's trace CSVs, copies), `isa/` (driver dumps, roofline listings, kernel SPIR-V and GLSL, `counts.csv`,
  `spirv/types.csv`), `logs/` (guard samples and status per job), `tools/` (scripts), `efficiency.csv`, `STUDY.md`.
  The tool's raw rows (`confirm/`, `sweep-*`, `pipeline-inspection/` ...) are on disk beside these, not committed.
- Comparison budget and stopping condition: one `fast` plan (23 minutes of the card), three microbench processes
  per suite, five dump runs; about 30 minutes of device time in all. Stop after the four parts.

## Workload and roof contract

- M/N/K, quantization scheme and group size, input rank/layout: the twelve linear shapes of Llama 3.2 1B / 3.2 3B /
  3.1 8B (wq_wo, wk_wv, w1_w3, w2) at M = 2048, schemes 4w and 8da4w, group size 128 (the tool's default,
  recorded in the JSON); fused attention at S = 2048, context 3072, head_dim 64 / 128.
- Production storage; benchmark storage; any deliberate difference: texture3d in both (`--storage=texture3d`);
  buffer storage was not measured. The fused attention kernel uses buffers in the model and in the benchmark.
- Expected kernel and tile/subgroup; **observed dispatched kernel** and evidence: observed, from the `kernel`
  field of `raw/linear-r*.json` (GPU query pool): 4w `sarc_linear_q4gsw_coopmat_sweep_t128x128k16g82s16m8flib`
  on eleven shapes and `..._t128x128k32g84s16m8flw` on 1B wk_wv; 8da4w
  `sarc_dev_linear_dq8ca_coopmat_zpg_xe2bt_t128x128k64g84s16m8` on all twelve (all `_texture3d_texture2d_half`).
  The same names appear in the cited in-model trace. The tool prints `dispatch: unexpected_coopmat` and exits 1
  for the linear suite: its expectation table predates cooperative-matrix kernels on texture3d (the campaign
  records the same status for its parent); the kernel names are the evidence. Fused attention: the tool prints no
  kernel name (`dispatch: confirmed`); the variants are those the profile table selects
  (`impl/sarc_dev/Overrides.cpp`: `d64_t16x64s16m8g4roj`, `d128_t16x128s16m8g8oj`) and the driver dump agrees
  (workgroups of 64 and 128 lanes, 16 and 32 `dpas` = the multiply-add counts of those two SPIR-V files).
- Runtime overrides; default-on behavior separately checked: the profile above only. Default-on: not checked
  (the profile is `kUnverified`, by the campaign's design).
- Operation/byte numerator and units; reload/reuse assumptions: rate = 2*M*N*K / kernel time (TFLOP/s for 4w,
  TOP/s integer operations for 8da4w); unpack, scaling, staging are not counted. Attention: only the
  multiply-adds executed (blocks up to the causal limit), derived from the kernel source; the formula is in
  `tools/efficiency.py`. Reuse = matrix operations per byte loaded for them per K step of one subgroup, from the
  tile constants in the kernel's generated GLSL (`isa/glsl/`) and confirmed by the driver listing (4w: 2560
  bytes of shared-memory loads per 8 `dpas`): 4w `flib` 12.8, `flw` 10.67, 8da4w 21.33, attention 10.67 (d = 64)
  and 8.0 (d = 128, exactly between two rows; the higher one is used).

| Resource | Selected confirmed roof / source row | Why it matches | Unknowns or mismatch |
|---|---|---|---|
| Matrix | 4w: `matrix_fp16` 173.3 TFLOP/s (`matrix_fp16_8x16x16_c4`); 8da4w: `matrix_int8` 359.9 TOP/s (`matrix_int8_8x16x32_c8`); attention: `matrix_fp16_fp32` 179.9 TFLOP/s (`..._c8`). All confirmed, 3 repeats, spread <= 0.02 % | component types of A, B and the result of every `OpCooperativeMatrixMulAddKHR` in the kernel's SPIR-V (`isa/spirv/types.csv`): 4w fp16 x fp16 -> fp16, 8da4w int8 x int8 -> int32 (signed), attention fp16 x fp16 -> fp32; shapes 8x16x16 / 8x16x32 are the only ones the driver exposes | roof at subgroup size 32 (SIMD32), kernels at 16 (SIMD16); no roof at 16 |
| Operand feed | fed from shared memory: `matrix_fp16_feed_shared` 168.4, `matrix_int8_feed_shared` 323.3, `matrix_fp16_fp32_feed_shared` 166.6 (confirmed, 8 multiply-adds per loaded pair). At the kernel's reuse: int8 2 chains 113.9 TOP/s, **single run, not a confirmed roof**; fp16 -> fp16 2 chains: **no matching roof** (row gated out: short, fixed cost); attention: fp16 -> fp32 cache-fed 2 chains 54.0 TFLOP/s, **single run** | same types; operand source shared memory for the linear kernels; for the attention kernel K and V come from storage buffers, so the cache-fed row is the one of its source | the 8-chain rows are at 3 to 4 times the kernels' reuse and are context for them, not a ceiling. The int8 2-chain shader loads B in byte-granular 32-byte messages (9 messages per multiply-add) where the kernel issues 4.6 of 64 bytes: the kernel reads 100 to 103 % of it on four shapes, so it is not a ceiling either. fp16 -> fp32 at 2 chains (82.7) is given for 4w as context only: another accumulator type |
| Bandwidth | not used for a percentage. Context: `shared_fp16_read` 3331 GB/s, `shared_fp32_read` 10017 GB/s (confirmed) | | no byte model of the kernels' global traffic was built |

Confirmation, duration, sentinel: confirmation repeats 3 per roof (plan `fast`), 21 samples of about 6 ms each;
sustained 120 s batches for three roofs agree with the short runs within 0.04 %; sentinel 34 readings between
18.349 and 18.351 TFLOP/s, none degraded. One confirmation candidate failed (`matrix_fp16_fp32_feed_dram`, 4 chains,
`repeat_unstable`); that roof is confirmed by its 2-chain candidate and is not used. Missing evidence, recorded
once in `STUDY.md` for the owner: the tool writes no per-run timings, only the per-process median (linear) or
mean (attention). September raw rows for the comparison: `cited/sept-fleet-fast-20260926/` (on disk, recovered
from the device host; not committed).

## Evidence before the screen

- ISA/pipeline evidence (capture: `isa/*.intel_debug_cs.txt`, Mesa `INTEL_DEBUG=cs` with the shader disk cache
  disabled; `isa/roofline/*.GEN_Assembly.txt` from the tool's pipeline inspection; counts in `isa/counts.csv`):
  - 4w `flib` (8B, all four shapes): SIMD16, 1470 instructions, 1 loop, 0:0 spills:fills, 307 sends, 128 GRF,
    workgroup 256 lanes, shared 18432 bytes. Loop (one K chunk): 8 `dpas.8x8 (16)`, 48 shared-memory loads
    (32 of 64 bytes for the 8 A fragments, 16 of 32 bytes for the B fragment; 2560 bytes), 2 shared stores
    (512 bytes), 1 barrier, 2 typed-image loads, 1 sampler fetch, 1 buffer load, 86 `sync.nop`, 302 instructions.
  - 4w `flw` (1B wk_wv): SIMD16, 819 instructions, 0 spills, workgroup 512, shared 40960; loop: 8 `dpas`, 64
    shared loads (3072 bytes), 357 instructions.
  - 8da4w (8B): SIMD16, 1754 (three shapes) / 1043 (one shape) instructions, 0 spills, workgroup 512, shared
    43520; loop (one quantization group = 2 chunks): 16 `dpas.8x8 (16)`, 73 shared loads (6208 bytes), 17 shared
    stores, 2 barriers, 3 buffer loads, 2 sampler fetches, 200 `sync.nop`, 553 instructions.
  - Fused attention: SIMD16, 927 (d = 64) / 1095 (d = 128) instructions, 0 spills; per context block and
    subgroup 16 / 32 `dpas`, 16 / 96 buffer loads, 52 / 85 shared loads, 8 barriers.
  - Roofline shaders: SIMD32, 0 spills; register roofs: 4 or 8 `dpas.8x8 (16)` in a loop of 10 to 14
    instructions; shared-fed 8 chains: 8 `dpas`, 10 load messages of 32 lanes (fp16) or 18 (int8, the B tile as
    16 byte-granular messages), 51 to 76 instructions; shared-fed 2 chains: the same loads for 2 `dpas`.
- If ISA is unavailable: not applicable; the driver prints its assembly.
- Occupancy estimate and limiting resource; workgroup count vs resident slots: not estimated (unknown).
- Hypothesis, competing explanation, and observation that would disprove it: see "Negative results and
  decision"; no hypothesis was tested in this study.
- Small candidate set derived from this evidence: none; part D of `STUDY.md` lists three hypotheses and the
  cheapest experiment for each.

## Measurements and controls

Clean timing only; no instrumented variant was run. All repeat timings are in `raw/linear-r{1,2,3}.json` and
`raw/sdpa-r{1,2,3}.json`; `efficiency.csv` is produced from them by `tools/efficiency.py`.

| Candidate / patch | Changed factor | Actual kernel | All repeat timings / spread | Whole-kernel gain | Phase/counter evidence | Verdict |
|---|---|---|---|---|---|---|
| Baseline = the final configuration | none | as listed above | 3 processes x (3 warm-up + 5 timed) per case; spread of the three process medians 0.0 to 3.9 % (largest: 3B 8da4w wq_wo), 26 of 27 cases under 2 % | 1.00x | cited only (campaign phase timing) | measured |
| Candidate | none | | | | | not applicable |

- Ablation limitations: no ablation.
- Control preserving work while changing the suspected mechanism: none run.
- Phase timing interpreted with occupancy/contention and total kernel time: not done here; the campaign's phase
  split is quoted in `STUDY.md` as a citation.
- At least three clean confirmation repeats: three processes per suite, all kept. Device state during them:
  no foreign engine time in any guard sample, GT clock 2768 to 2794 MHz mean per run, `pl2` only.
- Agreement with the in-model trace (cited, `cited/s3-final-trace-gemm.csv`, median over the dispatches of a
  prefill): in-model rate / microbench rate 0.86 to 1.06 per shape; the three wk_wv shapes of 4w and 1B wk_wv of
  8da4w are 8 to 14 % slower in the model, every other shape is within 5.5 %.

## Correctness and coverage

| Shape / rank / storage / scheme | Actual kernel | Full or sampled reference, count/seed/edge coverage | Tolerance / errors | Verdict |
|---|---|---|---|---|
| all shapes of this study | as above | not run here (`--skip-correctness`, `correctness: SKIPPED` in the JSON) | | not tested in this study |
| the same build and profile | as above | the tuning campaign's gate on build `topic2` (its `STATUS.md`: unmodified `verify.sh` with production-diff, SDPA tiers 12 passes each) | its record | cited, not re-checked |

## Negative results and decision

| Rejected candidate | Expected benefit | Measured regression / no gain | Explanation and confidence | Raw data / archived patch |
|---|---|---|---|---|
| none (no candidate in this study) | | | | |

- Selected change and evidence supporting it: none.
- Findings: the working figures hold (4w 39.3 % geometric mean, 30.9 to 40.9 %; 8da4w 29.6 %, 25.9 to 32.6 % of
  the matched register roofs); 4w accumulates in fp16, so the fp16 -> fp16 roof is its roof; both linear kernels
  compile to one `dpas` per multiply-add with no spills at SIMD16; for 8da4w the register-to-kernel gap is
  10.2 points of feeding at 8 multiply-adds per load, 58.2 points of reuse (2 per load), 2.0 points of
  everything else.
- Alternative explanations still open: whether the kernels are bound by their reuse, by shared-memory message
  count at SIMD16, or by barrier and scoreboard waits (`STUDY.md`, part D); the roof rows at the kernels' reuse
  are single runs or missing, measured at subgroup size 32.
- Kernel gain / operator gain / model gain: none claimed (untested at every level).
- Speedup versus previous WMMA / forced tiled / deployment default: not measured.
- Correctness failures or missing evidence preventing a deployment recommendation: no recommendation is made.
- Follow-up with the highest expected information value: a focused roofline run of the shared-fed 2- and 4-chain
  variants with confirmation, to obtain a gate-passing fp16 -> fp16 row at the 4w kernel's reuse (about 5
  minutes of the card, tool unchanged).

## Rules of the task, as kept

- Tool unmodified for part A (hashes above). ExecuTorch trees read only. No `sudo`, no package, no clock or
  power change, no service change, no reboot.
- Locks: part A held the campaign lock (`lock-868023e2-...`, by the controller) and the tool's device lock;
  parts B and C held both for the whole chain (`tools/partBC.sh`). One measuring process at a time.
- Foreign GPU work was sampled every 2 s in every run (`tools/guard_run.py`). No run was stopped. One sample of
  part A lists a DRM client of the second card with 0 engine cycles whose process had already exited when its
  name was read; it cannot be attributed, it did no GPU work that the counters show, and the sentinel readings
  before and after are equal. It is recorded, and the run was kept.
- Device time: part A 23 min 14 s, parts B and C 6 min 46 s.

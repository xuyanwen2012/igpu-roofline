# P0/P1 implementation verification

Implementation and checks completed. AMD meets the performance target. B580's
default 5 ms replay does **not** meet acceptance: all three discovery samples failed
unchanged quality gates, so there is no confirmed throughput or comparable complete
replay time. These failures are retained, not counted as successful speedups.

## Checks

- 87 Python/native-policy tests passed (`.venv/bin/pytest -q`). These include matrix
  subgroup accounting and capacity, pre/post admission, missing and stale hashes,
  report/insight consistency, incomplete confirmations, unstable/mixed sustained
  cohorts, UUID identity, interprocess locks, targeted cleanup, sentinel expiry,
  cooling, errors, periodic probes, quarantine boundaries and calibration limits.
- Ruff lint, `ty check`, Ruff read-only format checks and clang-format read-only
  checks passed. The native policy test compiles and executes `calibration.h` with
  deterministic timing, including both adjustment directions and nonconvergence.
- All **364** shader variants compiled and passed SPIR-V ledgers. Native `roofline`,
  `roofline_sustained` and `inspect` built successfully. Logs:
  [shader build](../build/p01-build.log), [native build](../build/p01-native-build.log).
  The first native attempt was blocked by the sandbox's read-only ccache; the
  subsequent authorized native build passed.
- Tested runner SHA-256: `1a1b300e44d8f230f93445f7f8e1668407198b6a33c86567bef255846be531b9`.
  Both short and sustained executables have this hash; admission still checks both
  identities independently. Source archives are stored with each campaign.
- B580: **36 matrix configurations passed**, covering FP16 / FP16→FP32 8×16×16 and
  INT8 8×16×32, 1 and 4 subgroups, 1/2/4/8 accumulator chains, plus shared/global
  feed variants at 4 chains. Actual raw streams end `sample_half`, `sample`,
  `validation_post`; sample events contain no copied validation.
  [Matrix evidence](../results/p01-matrix-validation/intel-arc-b580/matrix-validation.json).
- AMD Ryzen 5 9600X integrated GPU: cooperative matrices **unsupported / skipped**,
  not a matrix pass. [Skip evidence](../results/p01-matrix-validation/amd-igpu/matrix-validation.json).
- A real B580 shapes request during the diagnostic run was rejected by the UUID
  lock before deployment, naming controller PID 188498 and UUID
  `86800be2000000000300000000000000`. Cross-directory and distinct-GPU isolation
  are also covered by subprocess tests. ADB cleanup is tested with a fake transport;
  no Android device was used in this campaign.

## Three-round replay comparison

Both builds replayed `alu_fp32_v4_c4`, workgroup 256: AMD groups 2048; B580 groups
8192. Same `quick` plan, 21 samples and three confirmation repeats, `--no-sustain
--no-report`. Default target remains 5 ms. GPUs ran sequentially. Original workspace
changes and previous measurements were preserved; all new data use `results/p01-*`.

Wall time is the recorded interval from deployment start through confirmation end,
including inspection and sentinel probes, excluding Python startup and report
rendering. It is calculated from `timings.jsonl` rather than summing nested stage and
configuration timings. An earlier failed sandbox capability query is excluded from
AMD baseline round 1. The separately saved stage-duration sum agrees within 1 ms.

| GPU | Baseline wall median | New complete-replay wall median | Confirmed throughput change | Verdict |
|---|---:|---:|---:|---|
| AMD iGPU | 26.526 s | 9.210 s | -0.66% | **Pass: 65.28% faster** |
| B580 | 15.182 s | unavailable | unavailable | **Not met: default short samples excluded** |

AMD sample duration fell from about 71.74 ms to 6.21 ms, with loops 128 → 11.
Each new replay made three real stage-boundary probes and one reuse, versus four
real probes in the baseline. Baseline reference medians use the old build's existing
validation/quality rules only; they are not promoted to schema-v2 trusted roofs.

[Machine-readable comparison](../results/p01-verification/summary.json) retains every
round, build hash, confirmation result and source directory. Saved reproduction
scripts are under `results/p01-verification/scripts/` (paths describe this host).

## B580 diagnosis and sustained runs

At default target, the three B580 discovery rows were excluded for:

1. `warmup_unsteady`, `drifting` (37 loops, 6.023 ms).
2. `warmup_unsteady` (36 loops, 5.905 ms).
3. `fixed_cost`: invalid differential with negative fitted fixed fraction
   (33 loops, 5.777 ms).

The incomplete runs' median wall time (9.662 s) is **not a
performance improvement result**, because confirmation did not run. A standard-plan
retry reached steady warmup but still failed sample drift. Another quick diagnostic
attempt in `p01-conflict-must-not-measure` started after the preceding run had ended;
it is retained as an extra failed replay, not evidence of a lock conflict or part of
the three-round comparison.

A separately labelled 20 ms target diagnostic preserved every quality threshold and
three confirmation attempts: two passed, one failed drift, satisfying the existing
at-most-one-failure rule. Its confirmed median is 6.3251 TFLOP/s
(-1.91% against baseline). This supports sensitivity to short-sample variation;
it does not establish the exact cause. Intel frequency telemetry was not added,
and clocks were not pinned. The default target and configuration search are unchanged.

| GPU / campaign | Duration | Post validation | Last-60 stability | GPU duty fraction | Last-60 throughput |
|---|---:|---|---|---:|---:|
| AMD, default target | 60 s | pass | pass | 99.01% | 0.4758 TFLOP/s |
| B580, 20 ms diagnostic | 60 s | pass | pass | 99.55% | 6.4417 TFLOP/s |

One sustained batch per GPU is insufficient to switch roof basis; both reports
correctly remain short-run. Post-validation/readback time is outside sample and duty
measurements. Pre/post checks cannot guarantee catching transient intermediate errors.

- [AMD report](../results/p01-new-amd-3/amd-igpu/report/REPORT.md)
- [B580 diagnostic report](../results/p01-b580-diagnostic-20ms/intel-arc-b580/report/REPORT.md)
- [B580 default-target exclusions](../results/p01-new-b580-3/intel-arc-b580/report/REPORT.md)
- [Historical baseline through new admission](../results/p01-baseline-amd-1/amd-igpu/report/REPORT.md)

The historical report remains readable, identifies pre-only coverage, and has no
current trusted roofs. Raw results remain untouched. Offline ISA tools were
unavailable; SPIR-V checks and available driver inspection are not a claim of full
ISA verification.

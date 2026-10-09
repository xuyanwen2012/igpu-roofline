# S24+ short sampling diagnostic — 2026-09-26

An isolated experiment made three previously problematic configurations repeatable
without rooting, changing clocks, or running another full sweep. This establishes
short-run repeatability for these configurations, not hardware peak or sustained
thermal performance. Production runner and published roofs were not changed.

## Method and provenance

Device: S24+ `R5CY21Y3VEV`, Samsung Xclipse 940. Experimental runner SHA-256:
`f35f2b83b681db9a061d371e162c0599e2b780c02505eb103ce171be778595a4`.

Local artifacts are under `out/s24-sampling-diagnostic/` (ignored by Git):
`source/` contains the actual compiled source, `build/roofline` the binary,
`run.py` and `followup.py` the controllers, `runs/` raw JSONL/configs/process status,
`analysis.json` per-run analysis, `analyze.py` the analysis implementation,
`device-before.txt` and `device-after.txt` device snapshots. `prepare.py` was an
initial one-time transformation; final source additionally contains the native
S24 gpu-lab lock and is authoritative. `runner.patch` preserves the source delta.

Three frozen configurations from `results/fleet-fast-20260926/fedora/R5CY21Y3VEV/confirm`:

- FP16: `alu_fp16_v4_c1`, 62 loops, 8192 groups, workgroup 256.
- INT8: `dot8_c8`, 16 loops, 8192 groups, workgroup 256.
- Cache read: `mem_read_v4`, 1351 loops, 2048 groups, workgroup 128;
  follow-up doubled loops to 2702 to exceed the 4 ms duration threshold.

Both conditions used two seconds of half/full paired priming, 120 formal pairs,
GPU timestamps per dispatch, deferred logging, pre/post CPU-reference validation,
and unchanged shader binaries. Serial submits and waits per dispatch. Grouped
reuses one command buffer containing eight half/full pairs, retaining the original
barriers and individual timestamps, and waits once per group. This comparison
changes recording and submission together; it does not isolate their individual
costs. Serial also differs from the old production campaign in priming/logging.

Three repeats alternated case/mode ordering. Native frequency observation read
`/sys/kernel/gpu/gpu_clock` every 50 ms. One additional unmonitored grouped run per
original configuration checked for an obvious observer effect. Host roofline and
native gpu-lab advisory locks were held. No other GPU was tested.

Main campaign: 80.16 seconds, including three correctness smoke runs, 18 formal
runs, and three observer controls. Three longer cache runs added approximately
12 seconds. This excludes preparation/build time.

## Results

Rates below use logical work divided by the median full-dispatch GPU time.
Repeat spread is `(maximum - minimum) / median` over all three attempts.
Block spread uses all fifteen consecutive eight-sample block medians.

| Configuration | Serial repeat spread | Grouped median rate | Grouped repeat spread | Worst grouped block spread |
|---|---:|---:|---:|---:|
| FP16 | 4.24%, but all runs internally unstable | 2.603 TFLOP/s | 0.0061% | 0.03% |
| INT8 | 10.98% | 2.314 TOP/s | 0.0011% | <0.01% |
| Cache, original loops | 0.0077% | 1605 GB/s | 0.0221% | 0.05% |
| Cache, doubled loops | not tested | 1624 GB/s | 0.0076% | 0.02% |

Original grouped cache time was only 3.53 ms: it failed the duration gate despite
its repeatability. The longer version took 6.98 ms and passed. Do not promote the
short version by relaxing the gate. Cache rates represent shader-logical bytes,
not physical DRAM traffic.

All three repeats of grouped FP16, INT8, and longer cache passed pre/post
validation, the 4 ms duration floor, median-error and differential fixed-cost
checks, first/last-third drift <=5%, and the additional block-spread <=5% check.
Their fixed-cost fractions were approximately 0.4%, 0.9%, and 1.2%, respectively.
This is a diagnostic assessment, not production admission: the normal warmup
schema/admission integration and build provenance would need implementation.

All sampled formal-window grouped GPU clock readings were 1095 MHz. Serial
FP16 switched between 800/900 MHz, INT8 used 900–1095 MHz, and cache stayed at
800 MHz. A 50 ms sampled clock does not prove the frequency between observations,
or expose memory clocks or all hardware state.

Summed per-dispatch GPU timestamp durations / formal host wall time increased
from approximately 71–83% in serial to 96–97% for the three passing grouped cases.
This is a timing-derived duty estimate, not a hardware utilization counter.
The unmonitored controls reproduced the original grouped median rates within
0.01%; one control per configuration is only a limited overhead check.

## Interpretation and next implementation

Submission gaps are a strong, actionable contributor to the unstable measurement
conditions. Grouping makes these short tests highly repeatable. Repetition alone
was insufficient: serial FP16's three-run spread passed 5% even though its
within-run blocks differed by about 12.3–12.6%. Add a within-run stationarity gate.

FP16 needs further investigation before claiming a peak: grouped throughput
(2.603 TFLOP/s) is below both the earlier unconfirmed scan maximum (3.044 TFLOP/s)
and some serial medians despite a higher observed GPU clock. Clock observation
alone cannot explain performance. This experiment does not distinguish power
management, hidden hardware state, or submission/timestamp effects. Do not select
the faster unstable samples or extrapolate throughput from frequency.

A production follow-up should support bounded grouped paired sampling, use that
same schedule for priming and duration calibration, retain per-dispatch queries
and validation, export block stationarity and frequency evidence, and require all
planned repeats. Validate the new timing path before promoting roofs. Measure
ExecuTorch with comparable submission/load and frequency conditions; a continuous
load microbenchmark is not automatically representative of a fragmented workload.

# Jetson Orin: roof-guided Vulkan quantized linear study

Study dates: 2026-09-26–27 (local); device records use UTC.
Target: gpu-lab `orin-naughty`, Orin Nano 8 GB, Vulkan NVIDIA 595.78.
Access and power policy remain owned by [gpu-lab](../../gpu-lab/AGENTS.md).

## Which Jetson was measured

Only **`orin-naughty`**, reached through SSH host
`duck-naughty.tail031559.ts.net` (trusted alias `duck-naughty`), was measured.
It is an **Orin Nano 8 GB, 8 SM**, running the existing **15 W** mode with
GPU min/max **306/612 MHz**. These are the recorded campaign conditions,
not a claim about every Orin's maximum supported clock.

The other Jetson was neither benchmarked nor compared for available memory.
Jetson uses shared system memory: another device with less system occupancy
may have more room for model allocations, but that possibility is unverified.
The 8B stop below was a conservative system-swap guard event, **not OOM or
proof that 8B cannot fit**. Results must not be attributed to the other Jetson.

See the [five-GPU results index](GPU-STUDY-RESULTS.md) for the other studies.

## Scope and provenance

Final source commit: [`0b260ffab`](https://github.com/sarc-acl/executorch/commit/0b260ffab)
on `yanwen/release14-quant-shaders-jetson`. Its tracked source changes match the
validated `final-v2/source.patch`; the commit also includes the restored SDPA
shader prerequisites used by the measured builds.

The isolated ExecuTorch branch `yanwen/release14-quant-shaders-jetson` starts at
`0270403ba53ea4b3c4671b8037d468bdeb0f8d8b` from
`yanwen/release14-quant-shaders-4070ti` ("RTX 4070 Ti SUPER: per-shape 4w
prefill tiles"). "Original WMMA" below means that implementation, explicitly
enabled on Orin, not the first historical WMMA implementation. It uses
`VK_KHR_cooperative_matrix`, not the CUDA WMMA API.

Frozen original variants:

- 4w: `tsweep_dbuf4_t128x128k16g22s32`, FP16 × FP16 → FP16, 16×16×16.
- 8da4w: `tsweep_dbuf4zpgtr_mk32_t128x128k32g44s32`, INT8 × INT8 → INT32,
  16×16×32.

Primary workload: Llama 3.2 1B/3B and Llama 3.1 8B, all four projection
shapes per model, rank-3 batch 1, M=2048, texture3d activations/output,
texture2d packed weights, subgroup32. **Linear group size is 128**; embedding
group32 is a separate parameter. Actual PTE delegate metadata verifies this.

Artifacts: [`out/jetson-study`](../out/jetson-study/), including frozen binaries,
SHA-256 manifests, patches, commands, raw correctness logs, profiler captures,
and clock/memory telemetry. Cross-compilation uses the existing
[Fedora container recipe](../tools/jetson-cross/README.md). Restored SDPA decode
shaders and runner ETDump linkage fixes are shared prerequisites, not tuning
speedups. Clean model timings use the runner without ETDump instrumentation.

## Measured roofs and their limits

No clock or power settings were changed. Read-only queries reported 15 W mode,
EMC 2133 MHz and GPU range 306–612 MHz; load reaches 612 MHz. The roofline
report's generic clock reader does not recognize Tegra: use the accompanying
device-controller telemetry, not the report's empty clock fields.

| Confirmed short-run roof | Median |
|---|---:|
| FP16 matrix, FP16 accumulation | 9.696 TFLOP/s |
| FP16 matrix, FP32 accumulation | 9.736 TFLOP/s |
| INT8 matrix, INT32 accumulation | 19.519 TOP/s |
| FP16 / FP32 scalar FMA | 1.766 / 1.202 TFLOP/s |
| INT8 dot | 2.091 TOP/s |
| DRAM read / write / copy | 62.268 / 58.162 / 64.113 GB/s |
| Effective cache read | 204.059 GB/s |
| FP16 shared read / write | 566.211 / 334.938 GB/s |

The `fast` campaign took 2375 seconds, with fresh-process three-repeat
confirmation and healthy sentinels. Three representative 120-second checks
passed, **one batch each**; this is not a three-batch confirmed sustained roof.
Raw [roof report](../out/jetson-study/roofline-results/orin-naughty/report/REPORT.md)
retains rejected candidates and all quality decisions.

Shared-fed matrix rates are 9.508 TFLOP/s (FP16 accumulator), 8.839 TFLOP/s
(FP32 accumulator), and 17.412 TOP/s (INT8). These are different synthetic
reuse configurations; they are not automatically the matching roof for a
production shader. Texture access also matters: the measured RGBA16F texture2d
DRAM path is 20.737 GB/s versus 40.856 GB/s for texture3d. These formats/access
patterns differ from packed integer weights, so neither value should be
substituted as the workload's measured memory bandwidth.

## What the evidence says to optimize

Original valid 4w projections achieve 5.37–5.85 TFLOP/s, 55–60% of the
matching register-matrix roof. Original 8da4w achieves 1.92–2.16 TOP/s,
only 9.8–11.1% of its matrix roof. The invalid 8B 4w w2 timing is excluded.

Separate Nsight captures of long Vulkan submission windows give:

| Original | Tensor Active | SM Issue | SM Active |
|---|---:|---:|---:|
| 4w | 55.4% | 38.5% | 99.8% |
| 8da4w | 9.86% | 21.4% | 99.9% |

The final 8da4w capture raises Tensor Active to **20.85%** and SM Issue to
**28.82%**. Compute Warps in Flight changes only from 34.30% to 35.65%.
This is consistent with reducing staging overhead at similar occupancy, not
with a register-count reduction. These remain submission-window diagnostics;
the speedup claim comes from separate clean timings.

These are submission-window counters, including operator work, not isolated
instruction attribution. Near-100% SM Active does not imply efficient issue.
Low 8da4w tensor activity makes staging/unpacking/synchronization the first
hypothesis to test. There is no measured DRAM byte counter in this capture,
so the data does **not** prove memory bandwidth is irrelevant.

The [analysis script](../tools/jetson-study/analyze-roofline.py) emits a
[CSV](../out/jetson-study/analysis/original-roofline.csv) and
[roofline figure](../out/jetson-study/analysis/original-roofline.png).
Its x-axis is modeled compulsory tensor traffic, not hardware-observed traffic.
It omits repeated tile fetches, padding, cache effects and the separate dynamic
quantization stage. Kernel timing, complete operator timing and model timing
must stay separate.

For example, ignoring output/metadata traffic, a 128×128 tile has only about
102 ops/byte with half A and packed int4 B, or 171 ops/byte with int8 A, if
every CTA refetches its inputs. Inter-CTA cache reuse changes that traffic.
High whole-tensor arithmetic intensity alone therefore does not establish
that the implementation is compute-bound.

Two actionable conclusions:

1. **8da4w: reduce staging overhead before increasing compute tiling.** Test K64
   to amortize loop barriers, raw 16-byte A transfers, paired B fetches, and
   reuse dead A shared memory for output draining. Together these fit the
   48 KiB workgroup limit. The combined change needs clean timing and production
   correctness; its gain cannot be assigned to one component without ablation.
2. **4w: fix large-K accuracy, then manage resource pressure.** Original FP16
   accumulation fails the unchanged sampled reference on 8B w2, K=14336.
   Orin has essentially equal FP16/FP32 accumulator matrix roofs; the 4070 Ti
   half-rate assumption does not transfer. Changing only the accumulator costs
   255 registers/thread in this shader. K32/g42 FP32 uses 128 registers/thread
   and 46080 shared bytes, offering a better precision/performance compromise.

## Screening and validation record

The bounded screen has ten 4w configurations and eight 8da4w configurations.
At group128, original 4w uses 168 registers/thread; original 8da4w uses 113,
while the K64/raw/paired g44 variant uses 123. Thus its gain is not explained
by a reduced register count. Driver local-memory statistics had implausible
high bits; they are retained as raw evidence, not interpreted as spill bytes.

Initial pipeline inspection mistakenly used group32 specialization. That
inspection is preserved but superseded by `inspect-group128` and
`inspect-candidates-group128`; timings and actual benchmark correctness always
used group128. In particular, the earlier claimed 61-register K64 variant
was not a production-matched statistic.

Initial screening puts K64/raw/paired g44 8da4w at approximately **2.32×** the
original WMMA. Smaller tiles and g42 were slower. This is a provisional screen,
not the final repeated model result.

Two screen controls narrow the staging hypothesis. At fixed 128×64/K32/g42,
enabling raw A + paired B + shared-output reuse gives 2.31×. Keeping those
options and changing only K32→K64 gives another 1.076×. This supports staging
as the principal improvement; raw A, B pairing and shared reuse remain bundled,
and these controls have not received the winner's three-repeat confirmation.

The aligned 4w screen finds M256/g22 approximately 1.06× original, whereas
M256/g42 is 0.88×. Register counts alone would suggest the wrong choice:
255 versus 139 registers/thread must be considered together with 128 versus
256 threads/workgroup and 41472 shared bytes. Final selection uses M256/g22
only where aligned; large K uses the separate FP32 accumulator variant.

The M256 4w tiles initially failed the harness dispatch assertion because its
small M128 test fell back to tiled. That is not a numeric failure. A separate
aligned M2048 production test then found numeric failures on 8B; retain both
facts. K32/g42 FP32 passed the 8B sampled production check without relaxing
tolerances. The final defaults retain M256/g22 on aligned ordinary projections,
K32/g42 FP32 for K>8192, and K64/raw/paired g44 for 8da4w. Orin's default
enablement is limited to group128, texture3d, the measured projection shapes,
and aligned M≤2048. Existing environment overrides remain available for
experiments; unmeasured shapes and storage stay on the existing fallback.

The final default-dispatch build passes all 24 production projections. These
checks use the existing CPU reference, absolute tolerance 0.5 and relative
tolerance 0.05, with 8192 seeded coordinate draws plus a tile-edge grid; duplicate
coordinates mean the unique count differs by shape. This is sampled shader
correctness, not exhaustive output validation or model perplexity evaluation.

## Clean three-repeat microbenchmark confirmation

All 24 tuned cells pass production correctness and three-repeat timing gates.
The baseline/original/tuned order alternates between rounds. No model transfer,
device-side compilation or profiler runs overlap these timing jobs.

| Scheme | Tuned / tiled shader gain | Tuned / original shader gain | Tuned / original whole-operator gain | Maximum tuned repeat spread |
|---|---:|---:|---:|---:|
| 4w | 15.457× (12 cells) | 1.066× (11 valid original cells) | 1.065× (11 cells) | 0.15% |
| 8da4w | 9.281× (12 cells) | 2.324× (12 cells) | 2.235× (12 cells) | 0.18% |

These are equally weighted geometric means across projection shapes, not
model-level speedups. Original 8B 4w w2 is excluded from every valid-original
comparison. Its repaired version takes 45.881 ms versus tiled 619.293 ms;
the original 40.784 ms result is numerically invalid. The precision repair
is not presented as a speedup over that invalid result.

Tuned 8da4w now reaches 4.39–4.86 TOP/s, about 22.5–24.9% of the INT8 matrix
roof. Ordinary tuned 4w reaches 5.75–6.25 TFLOP/s; the FP32 large-K repair
reaches 5.24 TFLOP/s against the matching 9.736 TFLOP/s roof. There remains
substantial room beyond the current staging improvement.

The 24 decode cases use identical original/tuned kernel names. Their single
microbenchmark repeat is a dispatch regression check, not a confirmed decode
speedup claim. Model decode timings are collected separately.

Raw evidence: [confirmation comparison](../out/jetson-study/confirm/comparison.json),
[all repeat times](../out/jetson-study/confirm/summary.json), and
[final build hashes/patch](../out/jetson-study/builds/final-v2/).
Selected SPIR-V is byte-identical to the inspected candidate SPIR-V and passes
`spirv-val`. The unchanged FP16 default shader also matches its frozen original
SPIR-V hash. No unused screen variants remain in the final source.
Three-repeat M2048 confirmation used `final-v1`; `final-v2` changes only the
M256 4w selection below. A final-binary recheck passes all 24 numerical cases,
dispatches the same 24 M2048 kernels, and differs in timing by at most 0.19%.
See [cross-build verification](../out/jetson-study/final-check/cross-build-check.json).

## Short-prompt workload feedback

At 256 prompt tokens, clean three-repeat 8da4w prefill improves from 339 to
208 ms on 1B (**1.630×**), and from 944 to 527 ms on 3B (**1.791×**).
The requested generation length is 32; the observer reports 31 generated tokens
consistently across compared runs. Warmup, prompts, PTEs and tokenizers match.
Decode remains on the existing GEMV path.

The first 4w M256 selection improves 1B from 195 to 188 ms, but leaves 3B at
462 ms versus original 460 ms. A separate pair of instrumented 3B traces
explains why an M2048 microbenchmark gain did not transfer to M256:

| 3B projection | Original median ms | M256 tile median ms | Calls |
|---|---:|---:|---:|
| q/o, K3072 N3072 | 0.888 | 0.933 | 56 |
| k/v, K3072 N1024 | 0.346 | 0.403 | 56 |
| up/gate, K3072 N8192 | 2.325 | 2.195 | 56 |
| down, K8192 N3072 | 2.311 | 2.402 | 28 |

The instrumented linear total changes from 267.69 to 270.05 ms. These are
phase diagnostics, not replacements for the clean model timings. A prior
1B trace also shows the N512 k/v projection regressing with the larger tile.

The resource-derived explanation is consistent with those observations:
M256/g22 needs approximately 32 KiB registers per CTA, allowing at most two
CTAs per SM on the measured 8-SM Nano. At runtime M256 and N3072 it launches
24 CTAs, leaving a partial second 16-CTA wave; N512/1024 underfill even one
wave. The old M128 tile produces more CTAs. The short-prompt refinement
therefore retains M128 when M=256 and N is not divisible by 2048; M2048 and
all 8da4w selections are unchanged. The final trace confirms 140 M128 and
56 M256 prefill projections for 3B, and 32 M128 / 80 M256 for 1B. Fresh clean
three-repeat measurements retain the refinement: 1B takes 186 ms versus
original 196 ms (**1.054×**); 3B takes 454 ms versus 460 ms (**1.013×**).
Maximum tuned repeat spread is 0.54% / 0.44%, respectively.

**Trace labels are not runtime shape evidence by themselves.** These PTEs'
ETDump argument descriptions retain preparation/max M2048, even for a
256-token prompt. `DynamicDispatchNode::trigger_resize` reselects kernels for
the current tensor sizes. Use actual prompt/resize information for M; static
K/N and group128 metadata still describe these fixed weights correctly.

Raw [phase comparison](../out/jetson-study/analysis/short-trace-phases.json),
[model traces](../out/jetson-study/profiles/final-dispatch-summary.json), and
[initial clean short-prompt measurements](../out/jetson-study/model-confirm/comparison.json)
are preserved alongside the later refinement.

## Final whole-model results

Times below are **prefill after warmup**, excluding model loading, initial
pipeline compilation and decode. Each original/tuned cell has three successful
runs with the same PTE, tokenizer, prompt and requested 32-token generation.
Prompts repeat ` the` to obtain exactly 256 or 2048 observed prompt tokens;
this is a reproducible performance fixture, not a language-quality evaluation.
Decode uses unchanged kernels; no decode optimization is claimed.

| Model | Scheme | 256 prompt: original → tuned ms | Speedup | 2048 prompt: original → tuned ms | Speedup |
|---|---|---:|---:|---:|---:|
| 1B | 4w | 196 → 186 | 1.054× | 2339 → 2302 | 1.016× |
| 1B | 8da4w | 339 → 208 | 1.630× | 3551 → 2491 | 1.426× |
| 3B | 4w | 460 → 454 | 1.013× | 5837 → 5724 | 1.020× |
| 3B | 8da4w | 944 → 527 | 1.791× | 9742 → 6440 | 1.513× |

The three-repeat 256-prompt tiled references are 1419 / 1115 ms for 1B
4w / 8da4w, and 4033 / 3146 ms for 3B. The corresponding tuned prefill gains
over tiled are 7.63× / 5.36× and 8.88× / 5.97×. Tiled 2048-prompt references
have only one run each and remain diagnostic.

All M2048 and 8da4w model measurements use `final-v1`; the refined short-prompt
4w comparison uses `final-v2`, with freshly repeated original measurements.
Those unchanged paths have identical shader SPIR-V and final-binary dispatch
verification. [Combined results with per-cell provenance](../out/jetson-study/analysis/final-model-comparison.json)
link back to both campaigns. One last long-prompt attempt hit its campaign time
cap before completion; it is excluded and retained, followed by a successful
fresh attempt in `model-long-retry` to complete the third repetition.

Long-prompt gains are smaller than the microkernel gains and also smaller than
short-prompt 8da4w gains. This is evidence to profile attention and other
remaining operators next; it is not evidence that the measured matrix peak
alone predicts model speed. Initial pipeline compilation can also cost more
when shape-dependent selection creates an additional variant; cold startup is
not covered by the warm-prefill speedup claim.

## Full-model memory findings

Initial clean 256-token prompt / 32 requested decode-token trials completed for
1B and 3B, both quantization schemes. These single runs are discovery evidence.
8B 4w original WMMA completed once (peak process RSS about 5.18 GiB), but its
tiled comparison triggered the swap-growth guard and the original w2 shader
has a known numeric failure. This is not a validated 8B model speedup.
8B 8da4w attempts were cancelled; they do not establish that it intrinsically
cannot fit. Do not use swap or lower memory protections to obtain a comparison.
RSS also does not account for every driver/GPU allocation.

The controller reserves 1 GiB, caps model-scope memory, disallows scope swap,
and stops on additional system swap growth. All attempts, including failed
or cancelled ones, remain in the artifact directory and count toward the
90-minute device-job budget. Compilation and transfer time are separate.

The final tuned 8B 4w **cold capacity probe**, with warmup disabled and 32
requested output tokens, used an even stricter zero-additional-system-swap
threshold. It stopped during loading after 14.91 s on **1 MiB swap growth**,
with about **2.1 GiB still available**. Its cgroup memory limit was about
4.79 GiB, derived from the memory available before launch minus the reserve.
There was no completed observer result and no OOM conclusion. The campaign
stopped immediately, so final 8B 8da4w was not attempted. Do not turn this
conservative guard event into a claim that the hardware cannot fit 8B.
Full 8B model performance remains unestablished; all 8B projection microbenchmarks
and their sampled references are available, including the repaired 4w w2.

## Completion and remaining questions

Recorded device jobs total **5352.69 s (89.21 min)**, including failed attempts,
within the 90-minute cap. The final read-only snapshot reports no active GPU
jobs, an available gpu-lab lock, unchanged 15 W mode and GPU min/max
306/612 MHz (306 MHz idle). See [final device state](../out/jetson-study/final-device-state.json).

The source is maintained on the dedicated Jetson branch. Validation
includes the cross-build, `spirv-val`, production references, clean repetitions,
real-model ETDump dispatch, Python lint, shell syntax checks and 98 passing
roofline repository tests. Other GPUs were not rebenchmarked.

Highest-value follow-ups are a packed-integer texture traffic study, separating
raw-A and paired-B contributions, profiling the remaining long-prompt model
time, and a dedicated 8B loader/memory study that distinguishes cgroup/model
memory from unrelated system swap activity. The selected kernels are the best
among this bounded screen, not a claim of globally optimal tiling.

# <GPU / kernel / hypothesis / date>

Copy this file into the experiment's artifact directory before measuring. Replace
placeholders with evidence or `unknown` / `not tested`; do not mark missing checks
as passed. One record may cover a bounded candidate screen and its confirmation.

## Scope and provenance

- Decision this experiment will inform:
- Scope: kernel / operator / model; prefill / decode:
- GPU registry ID, execution device/UUID, driver:
- Clock policy and observed GPU/memory clocks; power/thermal state:
- Roofline campaign, source revision, runner/shader hashes:
- ExecuTorch checkout, commit, dirty patch, build options:
- Artifact paths: raw JSON, dispatch capture, correctness output, profiles, patches:
- Comparison budget and stopping condition:

## Workload and roof contract

- M/N/K, quantization scheme and group size, input rank/layout:
- Production storage; benchmark storage; any deliberate difference:
- Expected kernel and tile/subgroup; **observed dispatched kernel** and evidence:
- Runtime overrides; default-on behavior separately checked:
- Operation/byte numerator and units; reload/reuse assumptions:

| Resource | Selected confirmed roof / source row | Why it matches | Unknowns or mismatch |
|---|---|---|---|
| Matrix | | input/accumulator types, shape, subgroup | |
| Operand feed | | register/shared/cache/global, MMAs per fragment load | |
| Bandwidth | | storage, access width, layout, working set, logical/physical bytes | |

Do not substitute another accumulator type when the matching roof is missing.
A shared-fed maximum at a different reuse is context, not a matched ceiling.
Record confirmation spread, duration, sentinel and comparable device conditions.

## Evidence before the screen

- ISA/pipeline evidence: SIMD width, registers, spills, shared allocation,
  instruction mix, load/store width; capture path:
- If ISA is unavailable: mark `not ISA-verified`, name the available substitute:
- Occupancy estimate and limiting resource; workgroup count vs resident slots:
- Hypothesis, competing explanation, and observation that would disprove it:
- Small candidate set derived from this evidence:

## Measurements and controls

Use clean timing for before/after gains. Record profiler/instrumentation overhead
separately. Keep workload, storage, correctness tolerance and state comparable.

| Candidate / patch | Changed factor | Actual kernel | All repeat timings / spread | Whole-kernel gain | Phase/counter evidence | Verdict |
|---|---|---|---|---|---|---|
| Baseline | | | | 1.00x | | |
| Candidate | | | | | | |

- Ablation limitations: removed work/dependencies, numerical invalidity:
- Control preserving work while changing the suspected mechanism:
- Phase timing interpreted with occupancy/contention and total kernel time:
- At least three clean confirmation repeats for baseline and selected candidate;
  retain all attempts and explain failures rather than selecting the fastest:

## Correctness and coverage

| Shape / rank / storage / scheme | Actual kernel | Full or sampled reference, count/seed/edge coverage | Tolerance / errors | Verdict |
|---|---|---|---|---|
| | | | | |

Small fallback cases do not validate the candidate. Include production shapes,
large K, tile boundaries/tails where supported, and shapes affected by dispatch
rules. Sampled checks remain sampled; retain known failures, even if pre-existing.
Timing-only ablations must never count as correctness evidence or ship as defaults.

## Negative results and decision

| Rejected candidate | Expected benefit | Measured regression / no gain | Explanation and confidence | Raw data / archived patch |
|---|---|---|---|---|
| | | | | |

- Selected change and evidence supporting it:
- Alternative explanations still open:
- Kernel gain / operator gain / model gain (mark untested levels):
- Speedup versus previous WMMA / versus forced tiled / versus deployment default:
- Correctness failures or missing evidence preventing a deployment recommendation:
- Follow-up with the highest expected information value:

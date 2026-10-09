# Using roofline measurements to optimize ExecuTorch

Project direction agreed on 2026-09-26. This is the working procedure for new
optimization studies. Dated GPU studies below provide the measured evidence;
source-inspection notes describe integration limits, not additional measurements.

## Goal and ownership

The goal is to use measured GPU rooflines to understand real ExecuTorch workloads
and guide optimizations of the Vulkan **8da4w** and **4w** WMMA shaders. Success
means explaining a workload's performance, choosing a testable optimization, and
demonstrating an improvement in the real workload.

| Project | Responsibility |
|---|---|
| `gpu-lab` | The hub for GPU access, queried capabilities and available profiling tools: registry, GPU identity, host/ADB routing, availability, usage coordination, dated capability snapshots and tool restrictions. |
| `igpu-roofline` | The actual microbenchmarks: calibration, validation, quality gates, confirmation, sustained measurements, and reproducible roofline results. |
| ExecuTorch | Real operator/model workloads, shader implementations, correctness checks, and kernel/operator/model performance evaluation. |

Local repositories:

- Access hub: [`../../gpu-lab/`](../../gpu-lab/), especially
  [`gpus.toml`](../../gpu-lab/gpus.toml) and [`AGENTS.md`](../../gpu-lab/AGENTS.md).
- ExecuTorch main: `/home/doremy/Desktop/sarc-acl/main/executorch`.
- WMMA development checkout:
  `/home/doremy/Desktop/sarc-acl/yanwen/release14-quant-shaders/executorch`.

These paths identify the current workspace; record the actual commit and local
changes for every experiment. The two ExecuTorch trees have different shader and
dispatch implementations, so a branch name alone does not identify a workload.

The intended integration lets roofline consume gpu-lab's access information while
retaining its own runner and measurement policy. This is a responsibility boundary,
not a claim that a registry adapter or common execution API already exists.
Host administration facts remain in the HomelabHQ cards referenced by gpu-lab.
Roofline keeps measurement-specific device notes and campaign provenance.

Use [gpu-lab's profiling tool inventory](../../gpu-lab/docs/profiling-tools.md) as
the reference for installed tools, paths, per-GPU support and known restrictions.
Its 2026-09-26 host checks include Pixel 7a Mali counters via Perfetto, NVIDIA
timeline tools, and restrictions after an AMD iGPU SQTT hang. Choose diagnostics
from that inventory for the workload hypothesis; keep captures separate from clean
timing comparisons. [TOOLING.md](TOOLING.md) covers roofline-specific inspection
artifacts and trace handling without maintaining another current tool inventory.

## Available GPU capability queries

gpu-lab has implemented `./gpu caps [SEL] [--json]`, including cooperative-matrix
queries. The saved
[compute-capability snapshot](../../gpu-lab/docs/data/compute-capabilities-2026-09-26.json)
was captured at **2026-09-26T10:21:31-07:00**, uses schema version 1, and records
`status: ok` for all eight registered GPUs. See the
[compute-capability reference](../../gpu-lab/docs/compute-capabilities.md) and
[matrix-shape reference](../../gpu-lab/docs/cooperative-matrices.md) for interpretation.
This workflow's inspection verified the saved files, not a fresh live query.

| Available capability group | Use in roofline / ExecuTorch experiments |
|---|---|
| Subgroup sizes, operations and size control | Select supported subgroup/workgroup configurations and record the size actually requested |
| Dispatch limits and shared-memory limit | Reject invalid launch grids and tile allocations before testing |
| Memory heaps/types, buffer ranges and alignment | Plan buffer placement and sizes within exposed limits; heap capacity is not currently free memory |
| Numeric/storage features, dot-product acceleration, atomics and float controls | Select eligible shader variants and document numerical execution requirements |
| Timestamp properties and compute queues | Check timing support and record queue/timestamp provenance |
| KHR/NV matrix shapes and NV2 flexible dimensions/features | Match input/accumulator types, scope and matrix geometry to supported paths |

Refresh from the gpu-lab checkout with `./gpu caps all --json`. The query may
build/deploy its harness, but does not dispatch shaders or change clocks. Partial
failures retain successful entries and return a nonzero exit status; a missing or
failed entry is unknown, not evidence that the GPU lacks a feature.

Consumers should preserve `schema_version`, `queried_at`, `harness_hash`, registry
ID/host/UUID, device/driver identity and per-device status. The original standalone
matrix snapshot has a different schema; prefer the versioned compute snapshot for
new integration and handle schemas explicitly. Optional groups with
`available: false` do not contain a complete set of false feature flags.

These queries establish driver-advertised capabilities and API limits. They do
not provide measured compute/bandwidth roofs, cache sizes, SM/CU counts, current
clocks or theoretical FLOPS. No new native-hardware query is assumed here.
Roofline must still check the actual execution device and enable required
features; a saved snapshot cannot establish current availability or shader
correctness. The remaining integration work is to consume this existing inventory
for planning and provenance, rather than create another fleet-wide query system.

## Existing connection to the real workload

In the development checkout, inspect:

- `backends/vulkan/test/custom_ops/test_llama_microbench.cpp`
- `backends/vulkan/runtime/graph/ops/impl/QuantizedLinear.cpp`
- `backends/vulkan/runtime/graph/ops/glsl/linear_q4gsw_coopmat_tsweep_dbuf4.glsl`
- `backends/vulkan/runtime/graph/ops/glsl/linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr.glsl`

The Llama microbenchmark already exposes JSON (`test_llama_microbench.v1`) with
model, scheme, regime, storage, M/N/K, variant, actual kernel, dispatch status,
correctness status, kernel median/CV, and operator mean/stdev. It includes Llama
1B/3B/8B linear shapes, prefill at M=2048 and decode at M=1. These are the current
benchmark cases, not exhaustive coverage of all model execution shapes.

Use a forced-tiled baseline with the same storage as the candidate to isolate the
algorithm change. The completed studies include both buffer and texture3d
baselines; verify what the selected checkout supports and retain the production
baseline comparison when evaluating deployment benefit.

At inspection time, the actual default linear quantization group size is **128**
(`g_group`), despite older file-header text mentioning 32. Group size affects tile
eligibility. Record the runtime value and actual dispatched kernel; selecting a
WMMA variant is not proof that the runtime used it.

Large performance cases can skip their CPU reference. The completed tuning
branches added production-shape reference checks, including sampled references;
record which checks the selected checkout actually ran. Separate small-case,
production-shape and sampled coverage in imported reports: successful timing is
not a correctness verdict for that exact large shape.

## Match each workload to the appropriate roof

| Workload path | Relevant measured roofs | Additional work to explain |
|---|---|---|
| 4w WMMA, as in the inspected variant | FP16 matrix roof with matching accumulator type; applicable global/cache/shared bandwidth | INT4 unpack and dequantization, scales, staging, barriers, output epilogue |
| 8da4w WMMA, as in the inspected variant | INT8 x INT8 -> INT32 matrix roof; applicable global/cache/shared bandwidth | INT4-to-INT8 unpack, grouped scaling, zero-point correction, staging, barriers, plus activation quantize/pack at operator level |
| Decode (M=1 in the current benchmark) | Roofs corresponding to the actual GEMV implementation and memory access path | Limited reuse, launch size, reductions, and dispatch overhead |

Match matrix shape, signedness, accumulator type, subgroup configuration, storage
path and device/driver state. Register-resident matrix throughput and fed-matrix
measurements answer different questions. Use the latter to investigate operand
delivery, while accounting for differences from the real kernel's layout and reuse.

Report `2*M*N*K / kernel_time` as **effective matrix-operation throughput**. For
8da4w, distinguish integer matrix operations from floating-point operations even
if an upstream JSON field is named `gflops`. This numerator excludes unpacking,
scaling, conversions, padding and other implementation work; track those costs
separately when explaining performance.

A low fraction of a matrix roof does not by itself identify the bottleneck.
Likewise, a bandwidth comparison needs an explicit byte model: packed weights,
scales, sums/zero points, activations, outputs, tile reloads and shared-memory
traffic where applicable. State the reuse and cache assumptions. Shader-logical
bytes and a large working set are not measurements of physical DRAM traffic.

## Keep three measurement levels

| Level | Question | Evidence |
|---|---|---|
| Kernel | What limits the actual linear shader, and did the change improve it? | GPU timestamps, matching roofs, controlled variants, ISA/counters where available |
| Operator | Does the gain survive all dispatches required by the linear operation? | Include activation quantize/pack for 8da4w and other dispatched preparation/conversion work |
| Model | Does the change improve the workload the user runs? | Actual exported model, prefill latency, decode throughput, correctness and repeatability |

The existing microbenchmark distinguishes kernel and operator timings. Operator
GPU time is not model end-to-end wall time. Preserve the statistic used at each
level: do not subtract a kernel median from an operator mean to infer preparation
cost; use comparable or paired measurements for decomposition.

## Required experiment loop

1. Resolve the GPU through gpu-lab and use its capability snapshot to select
   supported configurations. Verify the execution device's identity, current
   availability, driver and clock/thermal conditions. Coordinate exclusive use
   across tools.
2. Obtain confirmed roofline measurements from the matching device/driver state.
   Retain build identities, validation, quality, sentinel and ISA qualifications.
   Use sustained results when the workload comparison requires sustained behavior.
3. Select representative real 4w and 8da4w cases. Record M/N/K, group size,
   storage, tile/subgroup settings, runtime toggles and actual dispatched kernel.
4. Measure the baseline and candidate at kernel and operator level. Match cases
   explicitly and keep correctness evidence separate from performance evidence.
5. Relate performance to the relevant roofs and traffic model. State one concrete
   hypothesis, such as operand staging or unpack work limiting matrix utilization.
6. Change one relevant factor and repeat the comparison under comparable conditions.
   Use profiling or targeted microbenchmarks to distinguish competing explanations.
7. Validate the winning change in the real ExecuTorch model and record whether
   kernel gains survive at operator and model level, including regressions.

Completed prefill microkernel studies cover [Xe2](XE2-WMMA-LESSONS.md),
[780M](780M-WMMA-LESSONS.md), and [4070 Ti SUPER](4070TI-WMMA-LESSONS.md).
They establish kernel-level gains, not end-to-end model gains. The NVIDIA study
retains a large-K 4w correctness failure; completion of tuning is not evidence
that every candidate is ready for deployment.

### Six practices required for new studies

Start with a copy of the [experiment record](templates/SHADER-EXPERIMENT.md) in the
study's artifact directory. Keep raw data there and link the completed record from
a dated lesson document when a study finishes. The record is the review artifact,
not an additional approval step. A bounded screen can share one record.

1. **Match the roof before interpreting a percentage.** Record input and accumulator
   types, subgroup/matrix shape, operand source, MMAs per fragment load, and memory
   access granularity. Check confirmation and device conditions. Do not replace a
   missing roof with another accumulator type or reuse level. If no match exists,
   mark the comparison unavailable and retain broader roofs as context. A kernel
   exceeding a roof triggers a matching/accounting investigation, not a speedup claim.
2. **Inspect generated code before broad sweeps.** Record SIMD width, register use,
   spills, shared allocation, relevant instructions and access width where available.
   Derive a small candidate set and occupancy budget from this evidence. If ISA is
   unavailable, state `not ISA-verified` and use pipeline statistics, counters or
   controlled experiments; lack of ISA alone does not prevent useful work.
3. **Measure production storage and actual dispatch.** Record input rank/layout,
   shape, quantization group, storage, runtime toggles and observed kernel. Compare
   storage-matched baselines. Separate faster shader execution from enabling WMMA
   in the deployment default. Treat buffer measurements as diagnostic when the
   model uses texture3d, and verify dispatch again after changing selection rules.
4. **Validate the explanation with whole-kernel controls.** Keep instrumented and
   clean timing separate and measure instrumentation overhead. Interpret phase
   cycles with occupancy and contention. Removing a store can remove its load wait;
   confirm with a work-preserving variant. Reject a phase-level improvement that
   disappears when other stages are restored or does not improve total time.
5. **Validate the kernel that actually ran on affected shapes.** Small correctness
   cases may fall back. Check production rank/storage, large K, tile boundaries and
   affected selection rules. Record full versus sampled reference, checked count,
   seed/coverage and tolerance. Preserve failures, including pre-existing ones;
   timing success or fewer failing samples does not make correctness pass. Mark
   operator/model validation as untested when outside the authorized scope.
6. **Keep negative experiments reproducible.** Record the hypothesis, changed factor,
   all repeat results, actual dispatch, correctness, verdict and patch/raw paths.
   Archive incorrect timing-only ablations separately from deployable variants.
   Remove obsolete shape overrides only after testing their affected shapes. Preserve
   raw results and explain rejected candidates so future agents do not repeat them.

Before recommending a change, review the completed record for missing evidence.
Use at least three clean baseline/candidate confirmation repeats, retain all
attempts, and investigate >5% repeat spread or within-run state changes. Do not
infer stability solely from a small standard error or a passing aggregate spread.
Missing evidence limits the claim; it does not become an implicit pass.

## Result association and remaining work

Each comparison must associate results using GPU registry ID plus actual
device identity, driver, campaign conditions, roofline build/shader hashes,
ExecuTorch revision and local changes, actual kernel/variant, shape, quantization
parameters, storage and timing scope. Save the source roofline summary and
ExecuTorch benchmark JSON so conclusions can be reproduced. The experiment record carries these requirements; they are not all fields
guaranteed by existing exports.

Known gaps from source inspection:

- **Automatic roof matching:** `workload.py` uses confirmed roofs and recognizes
  the `f32` tile suffix, but can fall back across accumulator types and selects a
  shared-fed aggregate without proving matching reuse/access granularity. Its
  percentages are provisional until the roof contract above is checked. Strict
  accumulator selection and structured feed matching remain implementation work.

- **Registry/capability integration:** gpu-lab's reusable capability query and
  eight-GPU snapshot are complete; roofline does not yet consume them as a shared
  inventory. Roofline currently has its own device handling and
  historical access snapshots. Those snapshots are retained as provenance, while
  current routes and root status are resolved through gpu-lab. Verify live state
  before running; this documentation session did not connect to devices. Some
  historical roofline devices are absent from gpu-lab's selected registry and need
  an explicit access decision.
- **Cross-tool exclusion:** gpu-lab and roofline use different lock paths and
  conventions. Neither tool's lock provides mutual exclusion with the other.
  Availability/load checks alone do not provide atomic ownership. A shared device
  ownership protocol remains to be designed and implemented.
- **Trusted report inputs:** current roofline reporting can retain unconfirmed
  sweep peaks in short-run plots and ridge calculations, although the confirmation
  table labels them. Use only explicitly confirmed roofs for optimization claims;
  tightening the plot/derived-metric policy remains implementation work.
- **Workload-specific explanation:** roofline already measures compute and memory
  families, including matrix-feed cases. Quantized unpack/scale/staging costs and
  their overlap in the real shader still need controlled experiments; add targeted
  microbenchmarks when an actual workload hypothesis requires them.
- **Capability versus execution:** gpu-lab's cooperative-matrix inventory records
  driver-advertised features. Its current generic harness does not enable those
  matrix extensions/features. Run matrix measurements through a capable runner;
  an inventory entry does not establish shader correctness or performance.

See [METHODOLOGY.md](METHODOLOGY.md) for measurement definitions and
[HOW-TO-RUN.md](HOW-TO-RUN.md) for focused runs, replay and sustained tests.

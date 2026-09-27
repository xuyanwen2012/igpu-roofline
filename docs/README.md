# Documentation

The project measures GPU roofs to explain and optimize real ExecuTorch Vulkan
4w and 8da4w workloads. Start with the document for the task at hand.

| Task | Document |
|---|---|
| Understand project boundaries and the optimization experiment loop | [ExecuTorch workflow](EXECUTORCH-WORKFLOW.md) |
| Start a shader study and record its evidence | [Experiment template](templates/SHADER-EXPERIMENT.md) |
| Build, run, resume, replay or collect sustained measurements | [How to run](HOW-TO-RUN.md) |
| Interpret accounting, validation, quality gates and confirmation | [Methodology](METHODOLOGY.md) |
| Operate this repository as an agent | [Agent guide](../CLAUDE.md) |
| Use roofline's build/inspection workflow | [Developer tooling](TOOLING.md) |
| Find installed profilers, commands and per-GPU restrictions | [gpu-lab profiling tools](../../gpu-lab/docs/profiling-tools.md) |

## GPU access and capabilities

The sibling gpu-lab repository owns the current registry and capability inventory:

- [Registry](../../gpu-lab/gpus.toml) and [operating guide](../../gpu-lab/AGENTS.md):
  GPU identities, SSH/ADB routes, availability and device-use rules.
- [Compute capabilities](../../gpu-lab/docs/compute-capabilities.md): subgroup,
  dispatch, memory, numeric and timing properties; refresh with `./gpu caps` there.
- [Cooperative matrices](../../gpu-lab/docs/cooperative-matrices.md): shapes,
  types, scope and flexible-dimension support.
- [Android phones](../../gpu-lab/docs/android-phones.md): current phone access,
  root and clock-control procedures.

These links assume sibling checkouts. Capability snapshots describe their recorded
driver and query date; they are not measured performance or live availability.
Roofline still verifies its execution device and records campaign-specific caps.

## Completed shader studies

These are measured prefill microkernel studies, not end-to-end model benchmarks.
Use their methods and negative results; recheck device and workload conditions.

- [Xe2: B580 and B70](XE2-WMMA-LESSONS.md): spills, operand reuse, storage paths,
  counters and roof access granularity.
- [Radeon 780M](780M-WMMA-LESSONS.md): accumulator type, occupancy and controlled
  phase timing; reverted LDS-layout experiments.
- [RTX 4070 Ti SUPER](4070TI-WMMA-LESSONS.md): staging, workgroup scheduling,
  instrumentation effects and an unresolved large-K correctness failure.

## Jetson cross-compilation and optimization

- [Orin roof-guided WMMA study](JETSON-WMMA-LESSONS.md): measured roofs,
  staging controls, large-K precision repair, clean kernel confirmation and
  full-model memory constraints.

- [Fedora → Jetson validated build](history/JETSON-CROSS-BUILD-2026-09-26.md):
  Llama 3.2 1B 4w/8da4w generation, correctness checks and actual WMMA traces.
- [Build and validation recipe](../tools/jetson-cross/README.md).

## Historical evidence

Keep these records as provenance, not as the current access registry or a promise
that old measurements pass today's policy:

- [S24+ short sampling diagnostic](history/S24-SAMPLING-DIAGNOSTIC-2026-09-26.md):
  grouped submission improved repeatability; isolated experiment, not published roofs.
- [Roofline fleet history](FLEET.md): devices previously probed, historical driver
  and connection information, and measurement notes.
- [Roofline matrix-shape snapshots](COOPMAT-SHAPES.md): earlier per-driver queries
  and the suite's recorded shape coverage, including devices outside gpu-lab's fleet.
- [P0/P1 validation record](P01-VALIDATION.md): build-specific verification and
  retained performance diagnostics. Artifact links require the original local data.
- [2026-09-25 tooling record](history/TOOLING-2026-09-25.md): earlier installation
  and idle-trace checks, superseded by gpu-lab's profiling inventory.

Use the current runner/shader identities and confirmation policy when choosing
results for a new optimization claim. Never delete raw results during housekeeping.

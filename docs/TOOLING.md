# Roofline developer tooling

Use [gpu-lab's profiling tool inventory](../../gpu-lab/docs/profiling-tools.md)
for per-GPU tools, installation paths, verified support and restrictions. Its
2026-09-26 host checks supersede this repository's older installation inventory.
The [profiling course](../../gpu-lab/docs/profiling-course.md) contains learning
exercises. This page covers the roofline-specific workflow; measurement procedures
are in [HOW-TO-RUN.md](HOW-TO-RUN.md).

## Choose evidence for the optimization question

| Question | Evidence to collect |
|---|---|
| Did the kernel or operator get faster? | Clean GPU-timestamp runs, current confirmed roofs, and ExecuTorch kernel/operator/model measurements |
| Did compilation preserve the intended work? | SPIR-V ledger, driver pipeline statistics/ISA, and offline compiler results where supported |
| Is operand delivery or instruction work limiting performance? | Controlled variants plus the counters or compiler statistics available for that GPU in gpu-lab |
| Is CPU scheduling or device state affecting the result? | A separate timeline/telemetry diagnostic using the tools supported on that host |

Keep diagnostic captures separate from clean benchmark results. Record the tool,
configuration, device/driver, shader/build and workload alongside each capture.
A static compiler estimate is not a measured bandwidth or runtime utilization.

Follow gpu-lab's verified restrictions before profiling. In particular, its current
inventory prohibits SQTT on the desktop and rocky-ryzen AMD iGPUs after a recorded
system hang, and hardware debugging on the display-driving B580. Ordinary timing
and compiler statistics remain the documented alternatives. A listed tool or API
feature does not establish that it can profile this standalone runner.

## Building and editor support

See [host setup](HOW-TO-RUN.md#host-setup) for dependencies and build commands.
`runner/CMakeLists.txt` exports `compile_commands.json` into `build/host` or
`build/android`; the repository `.clangd` uses `build/host`.

```sh
uv run igpu-roofline build --host
clangd --check=runner/src/roofline.cpp
```

Do not rebuild while a campaign is recording: builds change artifact identities.

## Formatting and linting

```sh
uv run pre-commit install             # once per checkout: run the hooks on commit
uv run pre-commit run --all-files     # everything, by hand
uv run pytest                         # offline tests; no GPU needed
```

| Files | Tools | Configuration |
|---|---|---|
| Python | `ruff check`, `ruff format`, `ty check` | `pyproject.toml` |
| Runner C/C++ | system `clang-format` | `.clang-format` |
| Shell | `shellcheck`, `shfmt` (downloaded by pre-commit) | `.editorconfig` |
| YAML, TOML, JSON, whitespace, executable bits | `pre-commit-hooks` | `.pre-commit-config.yaml` |

`results/`, `third_party/`, `shaders/`, `docs/reports/` and `*.patch` are never
reformatted: campaign artifacts stay as they ran, and a shader's SPIR-V hash keys
its results. CI (`.github/workflows/ci.yml`) runs the same hooks except
clang-format, then the tests.
For a separate Ninja build directory, pass `-G Ninja` to CMake; do not replace a
campaign's build directory merely to change generators.

Keep the shader compiler/tool versions explicit. Sourcing another SDK's environment
can change `glslc` and SPIR-V tools on PATH and therefore the generated shader hashes.

## Shader inspection and debugging

Roofline's `inspect` executable collects driver pipeline statistics and internal
representations when exposed; these are saved in `pipeline-inspection/`. Optional
`malioc` and `rga` results go to `offline-isa/`. Configure paths with `MALIOC`/`RGA`
and the AMD target with `RGA_ASIC`; match the target to the measured device.
A target that an offline compiler accepts is not proof of equivalence to that
installed driver's machine code.

For one-off driver dumps, validation layers, RenderDoc and device-specific limits,
use the commands and availability in
[gpu-lab's inventory](../../gpu-lab/docs/profiling-tools.md). In particular, Intel
shader dumps need the documented shader-cache setting. Disable diagnostic layers
and capture settings before collecting clean timing results.

The runner is a standalone executable. Tools requiring a debuggable Android APK
need an additional integration step; their installation alone does not provide
runner coverage. Do not interrupt an active ADB campaign by restarting its server
or switching the device to a WebUSB capture session.

## Perfetto

The checked-in [gpu.pbtx](../tools/perfetto/gpu.pbtx) is a historical system-trace
starting point for frequency, scheduling, thermal and GPU-memory diagnostics.
Its `gpu.counters` stanza has no explicit counter IDs. It is not the verified
Pixel 7a Mali-counter configuration: the newer gpu-lab inventory records 231
counters and requires `counter_ids`. Use its documented configurations and query
available sources on the actual device before selecting counters.

For the system-trace configuration, from this repository:

```sh
adb -s <serial> shell perfetto --txt -c - \
  -o /data/misc/perfetto-traces/gpu.perfetto-trace < tools/perfetto/gpu.pbtx
adb -s <serial> pull /data/misc/perfetto-traces/gpu.perfetto-trace
```

Adjust trace duration to the diagnostic and retain the exact configuration with
its trace. Correlate phone and host clocks explicitly. Missing idle trace events
alone do not establish lack of support. Analyze the trace with the host tools and
SQL examples linked from gpu-lab; treat profiling runs as diagnostic evidence.

## Historical verification

The [2026-09-25 tooling record](history/TOOLING-2026-09-25.md) preserves earlier
installation details, validation checks and idle-phone trace observations. It is
kept for provenance; its availability claims and profiling recommendations are
superseded by gpu-lab's newer inventory.

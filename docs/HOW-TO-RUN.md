# How to run

## Host setup

| need | notes |
|---|---|
| [uv](https://docs.astral.sh/uv/) | `uv sync` creates `.venv` from `uv.lock`; run everything with `uv run ...`. (Plain pip works too: `pip install -e .`) |
| Android NDK r26+ | found via `$ANDROID_NDK_HOME`, `~/Library/Android/sdk/ndk/*`, `~/Android/Sdk/ndk/*` or `~/android-ndk-*` |
| CMake ≥ 3.20 | |
| glslc, spirv-val, spirv-dis, spirv-as | from the Vulkan SDK, or `brew install shaderc spirv-tools` / distro packages |
| adb | Android platform-tools |

```sh
git clone https://github.com/xuyanwen2012/igpu-roofline && cd igpu-roofline
uv sync                      # creates .venv from uv.lock
uv run igpu-roofline build   # shaders + Android runner
```

Every command below is `uv run ...`; with a plain pip install, drop the `uv run` prefix
(or use `.venv/bin/igpu-roofline`).

`build` compiles every shader variant, checks each against its SPIR-V ledger (the build
fails on any mismatch), and cross-compiles the runner for arm64 Android.

## Device setup

1. Enable developer options and USB debugging; accept the host key.
2. `uv run igpu-roofline run` (no `--device`) lists connected devices.
3. Keep the device plugged in, screen allowed to turn off, at room temperature, with
   nothing else running. Results record temperatures and GPU clocks.

The device needs Vulkan 1.3. Features it lacks (fp16 arithmetic, int8 dot product,
cooperative matrix) simply skip the corresponding variants.

## Running

```sh
uv run igpu-roofline run --device <serial>                  # quick
uv run igpu-roofline run --device <serial> --plan standard
uv run igpu-roofline run --device <serial> --plan gold
```

- **Resume**: rerun the same command. Finished configurations are skipped. If a run
  was killed mid-configuration, its unfinished raw file stops the run (it is kept for
  inspection); move that `*.jsonl` aside and rerun.
- **Several devices**: one process per device; each device is locked while measured.
- **Devices on another machine**: run the tool on the machine the device is plugged
  into, or point adb at a forwarded adb server with `ADB_SERVER_SOCKET=tcp:<host>:5037`.
- **Reports**: written at the end of `run`; regenerate any time with
  `uv run igpu-roofline report [--device <serial>]` (no device needed).

## Development workflow

Use a focused run to change the amount of work without relaxing measurement quality:

```sh
# Run just the compute stage for FP32/FP16 FMA, then confirm its candidates.
uv run igpu-roofline run --local --family alu --stage compute

# Run one shared-memory shader across this plan's shared-memory grid.
uv run igpu-roofline run --local --variant sharedbw_fp32_v4_op0 --stage shared

# Keep the standard discovery/confirmation grid, omitting the long sustained runs.
uv run igpu-roofline run --local --plan standard --no-sustain
```

`--family`, `--variant` (exact name), and `--stage` can each be repeated. Values within
one selector are alternatives; different selectors intersect. Stage names are
`validate`, `first_look`, `cache`, `memory`, `compute`, `matrix_feed`, `texture`, `shared`,
`latency`, `ert`, and `memory_type`. Selectors operate on the selected plan's grid:
they do not add variants omitted by that plan. An empty selection is an error.
Setup, state sentinels and applicable confirmation remain automatic. Driver/offline
inspection in focused runs is limited to selected shaders and the sentinel.

Focused runs default to no sustained tests. `--sustain` explicitly enables the
selected plan's sustained portion (`fast`, `standard`, or `gold`); unfiltered runs
retain the original defaults. A latency-only or control-only run can finish without
producing a confirmed roof.

After confirmation, `best-configurations.json` contains the confirmed winners of
that invocation. To reuse prior launch parameters with a new build:

```sh
uv run igpu-roofline --results ./results/new-build run --local \
  --replay /path/to/old-device/best-configurations.json

# Existing campaigns do not need re-running just to create the new export.
uv run igpu-roofline --results ./results/new-build run --local \
  --replay /path/to/old-device/report/summary.json --family alu
```

Replay accepts only confirmed configurations from a report. It requires the same
GPU name and supported variants; a driver change is allowed. It takes launch/data
parameters from the old configuration, but shader metadata, hashes, subgroup size
and runner identity from the current build. Sampling and warm-up use the selected
plan; normal calibration, validation and confirmation still apply. Old executables,
results and reduced validation settings are not reused. `--family` and `--variant`
can narrow a replay; `--stage` cannot be combined with it. Replay tests the exported
points, not a new neighborhood search. Use discovery when the winning point may have
changed. Reusing the same results directory still follows normal resume semantics;
use a fresh results root for independent repeats.
Reports still summarize the campaign directory, including other current results
already present there; a focused invocation does not erase those measurements.

Run sustained tests separately after obtaining current confirmations:

```sh
uv run igpu-roofline --results ./results/new-build sustain --local \
  --roof alu_fp32 --duration 60 --batches 1 --cooldown 90
```

`--roof` is repeatable and uses the keys in `best-configurations.json` (for example,
`alu_fp32`, `memory_fp32_0`, or `cache_read_effective`); omitting it selects all current
confirmed roofs. Default duration is 300 seconds, minimum 60; batches default to 1,
cooldown to 90 seconds. This command deploys/probes the build and performs sustained
preflight/tests without rerunning discovery, confirmation, or ISA inspection. If the
runner or shader changed, first obtain new confirmations with a focused/replay run.

On hosts with multiple GPUs, explicitly choose the intended GPU, for example:

```sh
IGPU_ROOFLINE_GPU=AMD uv run igpu-roofline run --local --family alu --stage compute
```

For an Intel Arc B580, use `IGPU_ROOFLINE_GPU=B580`. Host telemetry is bound to
the Vulkan-selected GPU using vendor/device IDs. Missing or ambiguous matches leave
GPU telemetry unavailable instead of reading another card. Temperature pacing uses
only the selected card's hwmon sensors. Clock reading currently supports amdgpu;
Intel clock readings are unavailable even when Intel GPU measurements succeed.

`run-selection.json` records the most recent short-run scope and configuration counts.
`timings.jsonl` appends stage and configuration durations, recording failures as well
as successes. Stage times include their nested configurations and sentinels: do not
add stage and configuration totals together. Configuration entries also include
resume lookups; cached rows retain their original measurement timings.

Each new result's `phase_seconds` separates resume/thermal guard, config upload,
pre-run telemetry, runner process, post-run telemetry and analysis. The runner
process total includes setup, allocation, pipeline compilation, CPU validation,
warm-up and sampling (and periodic telemetry); these internal components are not
yet separately instrumented. `runner_observed_seconds` gives logged warm-up wall
time and the sum of full/half GPU sample timestamps, which are nested in that total.

## Pinning clocks (optional, rooted devices)

The tool never changes device settings. To measure with fixed clocks, pin them first,
e.g. with [tools/pin_gpu_clock.sh](../tools/pin_gpu_clock.sh) on a rooted device, then
run. The report states whether each GPU clock domain was pinned (min == max) when the
capabilities were captured.

## Device overrides (optional)

Auto-detection covers most devices. For special cases pass `--overrides my-device.yaml`:

```yaml
# explicit GPU clock files to sample (default: kgsl, devfreq, mali0, /sys/kernel/gpu)
gpu_freq_files:
  - /sys/class/devfreq/1f000000.mali/cur_freq
notes: "dev board, GPU clock pinned before the run"
```

## Offline ISA tools (optional)

- **Mali**: install Arm Performance Studio and put `malioc` on `PATH` (or set `$MALIOC`).
- **AMD RDNA (e.g. Samsung Xclipse)**: install Radeon GPU Analyzer and put `rga` on
  `PATH` (or set `$RGA`; `$RGA_ASIC` selects the target, default `gfx1103`).

Missing tools are skipped. Driver-returned ISA and driver statistics are always used.

## Results layout

```
~/igpu-roofline-results/<serial>/
  capabilities.json         Vulkan caps, clock state, device properties
  artifact-manifest.json    SHA-256 of runner, shaders, sources; git commit; runner history
  artifacts/<sha>/          the exact runner binary and a source tarball
  workflow-state.json       current stage
  run-selection.json        latest selected stages, counts, sustained setting
  best-configurations.json confirmed configurations for replay
  timings.jsonl            append-only stage/configuration wall times
  <stage>/<name>_<hash>.json      one result (config, stats, accounting, validation, telemetry refs)
  <stage>/<name>_<hash>.jsonl     raw samples;  .stderr  driver output;  .telemetry.json  temps/clocks
  pipeline-inspection/      driver statistics and ISA text per variant
  offline-isa/              malioc / rga results
  report/                   REPORT.md, TUNING.md, SUPPLEMENT.md, ISA-CHECK.md, figures, CSV
```

Measurement rows are preserved; derived summaries and workflow state describe the
latest invocation. A result row names the runner that produced it; when the runner
changes, earlier runners are kept in `runner_history`, but old rows are excluded from
current roof selection. Start a fresh campaign directory for a rebuilt runner.


## Device ownership and validation coverage

All deployment, measurement, pipeline inspection and shape probing use a host/user
lock in `/tmp/igpu-roofline-locks-<uid>/`. Local keys use the selected Vulkan
[`deviceUUID`](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceIDProperties.html),
not names, ordinal positions or vendor/device IDs. `roofline identity` queries the
selected physical device without creating a logical device or submitting GPU work.
ADB keys use the device serial on the controlling host; cross-host ADB exclusion is
outside this guarantee. Conflicts name the device and owner PID and never kill it.
The campaign's `owner.lock` also prevents two GPUs from writing the same directory.

`IGPU_ROOFLINE_STAGE` is a **parent directory**: local staging appends the full UUID.
Default local result names include a short UUID; explicit `--local-name` stays
compatible. Local subprocesses are pinned to the selected UUID. Timeouts, Ctrl-C and
SIGTERM stop only the invocation owned by this controller, waiting for termination
before releasing ownership. No executable-name-wide `pkill`/`pidof` is used.

New rows use `schema_version=2`, with separate pre/post validation events. The last
real sample is checked after sampling; intermediate transient errors may escape
these checks. Legacy pre-only rows stay on disk but cannot define new trusted roofs.
Their confirmed configurations can still be replayed with current binaries.
`all-configurations.csv` lists exclusions; `REPORT.md` states missing evidence.
Short runs retain the existing quality thresholds and confirmation counts. Sustained
roofs additionally require three different stable batches per current confirmed
configuration and duration. One 60-second batch is useful evidence but is not enough
to switch the report to sustained roofs.

Calibration now shrinks as well as grows workloads toward 5–7.5 ms, records every
round and its stopping reason, and retains fixed-overhead and FP16 bounds. Boundary
sentinel reuse appears in `sentinel-checks.jsonl`; a reused check references its
original probe and does not add a baseline reading.

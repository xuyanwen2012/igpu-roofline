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
uv run igpu-roofline build
```

`build` compiles every shader variant, checks each against its SPIR-V ledger (the build
fails on any mismatch), and cross-compiles the runner for arm64 Android.

## Device setup

1. Enable developer options and USB debugging; accept the host key.
2. `igpu-roofline run` lists connected devices.
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
  <stage>/<name>_<hash>.json      one result (config, stats, accounting, validation, telemetry refs)
  <stage>/<name>_<hash>.jsonl     raw samples;  .stderr  driver output;  .telemetry.json  temps/clocks
  pipeline-inspection/      driver statistics and ISA text per variant
  offline-isa/              malioc / rga results
  report/                   REPORT.md, TUNING.md, SUPPLEMENT.md, ISA-CHECK.md, figures, CSV
```

Results are append-only; nothing is overwritten. A result row names the runner that
produced it; when the runner changes, earlier runners are kept in `runner_history` and
their results stay valid.

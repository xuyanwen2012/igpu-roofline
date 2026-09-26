# Developer tooling

Tools for building, debugging and profiling the runner and its shaders on the fleet
([FLEET.md](FLEET.md)). This page does not cover measurement procedure; for that see
[HOW-TO-RUN.md](HOW-TO-RUN.md) and [CLAUDE.md](../CLAUDE.md).

Status markers: **verified** means it was run on the named device and the result is
quoted; **unverified** means it comes from vendor documentation and has not been run here.

> Debuggers, validation layers and profilers perturb timing. Never leave any of them
> enabled during a recording run; rows measured with a layer loaded are not usable.

## Workstation `fedora`

Owner's desktop, checked 2026-09-25: Fedora 44, kernel 7.2.7, Ryzen 5 9600X + Intel Arc
B580, Mesa 26.2.3, Vulkan loader 1.4.341. The Pixel 7a (`3A021JEHN02756`) and the
Galaxy S24+ (`R5CY21Y3VEV`) are on its USB.

| GPU | Vulkan driver | type |
|---|---|---|
| Intel Arc B580 (BMG G21) | ANV, Mesa 26.2.3 | discrete |
| Ryzen 5 9600X iGPU (RDNA2, Raphael) | RADV, Mesa 26.2.3 | integrated |
| llvmpipe | Mesa | CPU (the runner skips it) |

### Installed

| area | tools |
|---|---|
| Vulkan | `vulkan-headers`, `vulkan-loader`, `vulkan-tools` (`vulkaninfo`, `vkcube`), `vulkan-validation-layers` |
| shaders | `glslc` (shaderc), `glslangValidator` (glslang 16.2), `spirv-tools` (`spirv-val`, `spirv-opt`, `spirv-dis`, `spirv-as`) |
| build | `cmake` 4.3, `ninja` 1.13, `ccache`, clang/clang++, `clangd` |
| debug | `gdb`, `lldb`, `lldb-dap`, RenderDoc 1.45 (`qrenderdoc`, `renderdoccmd`) |
| Android | NDK r30 (`~/android-ndk-r30`), `adb`/`fastboot` (android-tools 37, Fedora package) |
| GPU monitors | `intel_gpu_top`, `radeontop`, `nvtop` |

All from Fedora repositories except the NDK:

```sh
sudo dnf install vulkan-tools vulkan-validation-layers glslc glslang spirv-tools \
    renderdoc ninja-build radeontop clang-tools-extra android-tools
```

`ANDROID_NDK_HOME` is not set; `igpu-roofline build` finds the NDK through its
`~/android-ndk-r*` guess. Other tools will not, so set it (fish:
`set -Ux ANDROID_NDK_HOME ~/android-ndk-r30`).

### Installed under `~/tools` (2026-09-25)

Unpacked release archives; command-line entry points are symlinked into `~/.local/bin`,
GUI tools have launchers in `~/.local/share/applications`. Downloads are kept in
`~/tools/dl`.

| tool | version | location | entry points |
|---|---|---|---|
| Radeon Developer Tool Suite (RGP, RGA, RDP, RMV, RGD) | RGP 2.7, RGA 2.14.2.8 (suite 2026-05-28) | `~/tools/RadeonDeveloperToolSuite-2026-05-28-1806` | `RadeonGPUProfiler`, `RadeonDeveloperPanel`, `rga`, `rgd`, `RadeonMemoryVisualizer` |
| Sokatoa | 1.1.0 (AppImage) | `~/tools/sokatoa` | `sokatoa` |
| Perfetto host tools | v58.2 | `~/tools/perfetto/linux-amd64` | `trace_processor_shell`, `traceconv`, `tracebox`, `perfetto-host` |
| Tracy | 0.14.1 | `~/tools/tracy` | `tracy-profiler` (AppImage), `tracy-capture`, `tracy-csvexport` |
| LunarG Vulkan SDK | 1.4.357.1 | `~/tools/vulkan-sdk/1.4.357.1` | `gfxrecon-*` (GFXReconstruct 1.0.5), `spirv-cross`, `spirv-reflect`, `vkconfig`, `vulkanCapsViewer`, `slangc`, `dxc` |
| GFXReconstruct Android layer | vulkan-sdk-1.4.309.0 (latest Android build on GitHub) | `~/tools/gfxreconstruct/android` | `layer/arm64-v8a`, see `USAGE_android.md` |
| Android Performance Analyzer | 0.9.0 (build 253.31033) | `~/tools/apa/apa-linux` | `apa`, desktop launcher |

APA needs `ANDROID_HOME` with SDK platform-tools. `~/Android/Sdk/platform-tools/adb` is a
symlink to the Fedora `/usr/bin/adb`, so only one adb binary exists on the machine: two
different adb builds restart each other's server, which would drop a running campaign's
connection. `ANDROID_HOME` is set as a fish universal variable and in the APA launcher.

The SDK's own `glslc`, `glslangValidator`, `spirv-val` and `vulkaninfo` are deliberately
**not** linked: the Fedora packages stay first on `PATH`, so the shader toolchain that
builds the SPIR-V does not change. Do not `source` the SDK's `setup-env.sh` in a shell
that builds shaders.

Known issue: the RGA **GUI** (`RadeonGPUAnalyzer`) needs `libicudata.so.70` (Ubuntu
22.04's ICU), which Fedora 44 does not ship; the `rga` command line works. RGP's binary
has no missing libraries.

### Not installed yet

| tool | for | why not |
|---|---|---|
| Snapdragon Profiler | Adreno counters | download needs a Qualcomm account |
| Arm Performance Studio 2026.2 (`malioc`, Streamline) | Mali ISA/cycle estimates, Mali counters (Mali-G1 supported) | licence click-through |
| Android SDK cmdline-tools, JDK 17/21 | APK builds only (the runner is a plain executable) | not needed yet |

## Building

### clangd for the runner

`runner/CMakeLists.txt` sets `CMAKE_EXPORT_COMPILE_COMMANDS`, so every configure writes
`compile_commands.json` into its build directory (`build/host`, `build/android`). The
repository `.clangd` points clangd at `build/host`. Configuring does not change the
runner binaries (checked by SHA-256 on 2026-09-25), but a full build does; do not
rebuild while a campaign is recording.

After a fresh checkout, `uv run igpu-roofline build --host` (or just
`cmake -S runner -B build/host`) creates the database. **Verified**: `clangd
--check=runner/src/roofline.cpp` loads it and reports no compile errors.

### Ninja

`cmake` still uses Make for existing build directories. New ones use Ninja when
`CMAKE_GENERATOR=Ninja` is set. Switching an existing directory requires deleting it and
rebuilding, which changes the runner SHA.

## Debugging

### Validation layers (host)

```sh
VK_LOADER_LAYERS_ENABLE='*validation' ./build/host/roofline ...
```

**Verified**: with `vulkan-validation-layers` 1.4.341, a deliberately invalid
`vkCreateBuffer` (size 0) is reported as `vkCreateBuffer(): pCreateInfo->size is zero`.

On Android, Khronos publishes `libVkLayer_khronos_validation.so` for arm64 in the
Vulkan-ValidationLayers GitHub releases. Android loads debug layers only for debuggable
apps (or from `/data/local/debug/vulkan` with root), so for the runner, a plain
executable, validate on the host instead. **Unverified** on the fleet.

### RenderDoc

`qrenderdoc` captures a host process (launch the runner from its "Launch Application"
tab) and shows buffers, descriptors and pipeline state per dispatch. Timing is limited to
per-event durations, so use it to check correctness, not performance. It can also capture
debuggable APKs on Android. **Unverified** on the fleet.

### Driver ISA and statistics (Mesa)

| driver | environment | output |
|---|---|---|
| RADV | `RADV_DEBUG=shaders` | final RDNA ISA per pipeline, on stderr |
| ANV | `INTEL_DEBUG=cs` | compute-shader ISA |
| ANV | `INTEL_MEASURE=...` | per-dispatch GPU timings to a CSV |

`uv run igpu-roofline` already reads RADV ISA through
`VK_KHR_pipeline_executable_properties` (`inspect`); these variables are for quick
one-off checks.

## Profilers

What exists per GPU in the fleet. None of these is set up in the repository yet.

| GPU | tool | shows | notes |
|---|---|---|---|
| Mali (Pixel 7a G710, vivo G1) | Streamline (Arm Performance Studio) | hardware counters: arithmetic/FMA use, load/store, L2 and external bandwidth, warp occupancy | on non-root phones it normally needs a debuggable APK; whether it can profile the adb-pushed runner is **unverified** |
| Mali | `malioc` | cycles, register count and spilling per shader, offline | the ISA route named in CLAUDE.md |
| Mali, Adreno, Xclipse | Android Performance Analyzer (APA, open beta since 2026-05) | GPU counters, render stages, system trace (built on Perfetto; frame capture on GFXReconstruct) | Google's recommended successor to AGI; aimed at games and Vulkan apps, the profiled app should be debuggable; whether it profiles the adb-pushed runner is **unverified** |
| Mali, Adreno | Android GPU Inspector | GPU frequency, counters, queue timeline | still maintained, superseded by APA |
| Adreno 840 | Snapdragon Profiler | real-time counters (150+) and traces | |
| Xclipse (S24+, M51), also Adreno and Mali | Sokatoa (Samsung with Google and LunarG, 2026-03) | multi-frame GPU profiling, shader editing and on-device replay | frame-oriented; support for compute dispatches is **unverified**. Pipeline dump on the rooted M51 is a CLAUDE.md TODO |
| RDNA (9600X iGPU, 780M) | Radeon GPU Profiler 2.7 | per-dispatch wave occupancy, instruction timing and divergence, cache hit rates | the Developer Panel cannot capture RADV; RADV writes RGP traces itself via `MESA_VK_TRACE=rgp` (`MESA_VK_TRACE_*`); **unverified** here |
| RDNA | `rga` | offline RDNA ISA | cross-check against RADV's returned ISA |
| Intel Arc B580 | `intel_gpu_top`, `INTEL_MEASURE`, Mesa `pps-producer` | engine busy and frequency, per-dispatch timings; `pps-producer` feeds Intel hardware counters into Perfetto (needs root) | Intel GPA is discontinued (2026) and VTune does not profile Vulkan |
| any | `VK_KHR_performance_query` | vendor counters read from inside the application | ANV exposes it; check other drivers with `vulkaninfo` |
| any | Tracy | CPU and Vulkan GPU zones on one timeline | needs instrumenting the runner |
| any | `perf` | host-side CPU cost | |

For tuning the q4gsw / dq8ca kernels: RGP on RADV explains a kernel at the instruction
level; `malioc` plus Streamline give Mali register pressure and bandwidth against the
measured roofs; Snapdragon Profiler does the same on Adreno.

## Perfetto

Perfetto records system traces on Android without root. Use it to line up a roofline run
with GPU frequency, thermal state and scheduling, e.g. to tell a DVFS step from a
thermal limit, or to look for the vivo latched slow state (see CLAUDE.md). Remember the
phone clock may differ from the host clock when correlating.

### Recording from the command line

The config is [`tools/perfetto/gpu.pbtx`](../tools/perfetto/gpu.pbtx). Non-root shells can
read configs only from `/data/misc/perfetto-configs/` and write traces only to
`/data/misc/perfetto-traces/`.

```sh
adb -s <serial> push tools/perfetto/gpu.pbtx /data/misc/perfetto-configs/
adb -s <serial> shell perfetto --txt -c /data/misc/perfetto-configs/gpu.pbtx \
    -o /data/misc/perfetto-traces/gpu.perfetto-trace
adb -s <serial> pull /data/misc/perfetto-traces/gpu.perfetto-trace
```

Set `duration_ms` in the config to cover the stage you are watching. The
`tools/record_android_trace` script in the Perfetto repository automates push, record,
pull and opening the UI.

### Recording from the browser

Run `adb kill-server` first (WebUSB and adb cannot share the device), open
ui.perfetto.dev in Chrome or Brave, choose "Record new trace", and select the GPU, CPU
and power probes.

### Analysing

Open the trace at ui.perfetto.dev; it is processed locally in the browser. For SQL:

```python
# uvx --from perfetto python
from perfetto.trace_processor import TraceProcessor
tp = TraceProcessor(trace="gpu.perfetto-trace")
for r in tp.query("""select t.name, count(*) n, min(c.value) lo, max(c.value) hi
                     from counter c join counter_track t on c.track_id = t.id
                     group by t.name"""):
    print(r.name, r.n, r.lo, r.hi)
```

### What the fleet exposes

Checked 2026-09-25 with `perfetto --query` and `/sys/kernel/tracing/events`.

| | Pixel 7a (Mali-G710, Android 17) | Galaxy S24+ (Xclipse 940, Android 16) |
|---|---|---|
| GPU/CPU frequency, thermal, scheduling tracepoints | yes (`power`, `thermal_exynos_gpu`) | yes (`power`, `thermal_exynos_gpu`) |
| vendor kernel events | `mali/*` | `amdgpu/*`, `gpu_scheduler/*` (per-job scheduling and run times) |
| `android.gpu.memory` | yes | yes |
| `gpu.counters`, `gpu.renderstages` | not registered | not registered |

**Verified** with this config, 5 s traces on idle phones (2026-09-25):

| | recorded | missing |
|---|---|---|
| Pixel 7a | `cpufreq`, `GPU Memory` | GPU frequency, temperatures, `mali/*` events |
| Galaxy S24+ | `cpufreq`, **`gpufreq`**, **`G3D Temperature`** (GPU) and the other thermal zones (BIG, MIDH, MIDL, LITTLE, CP, ISP, NPU), `GPU Memory` | `gpu_scheduler/*`, `amdgpu/*` events |

Frequency and vendor events are emitted on change, so an idle GPU produces few or none.
Whether the missing rows appear under runner load is **unverified**.

Setting `adb shell setprop debug.graphics.gpu.profiler.perfetto 1` (what AGI does) did
not make `gpu.counters` appear on either phone while no Vulkan process was running. The
driver may register it only once a Vulkan process starts, or only through AGI:
**unverified**. The property resets on reboot.

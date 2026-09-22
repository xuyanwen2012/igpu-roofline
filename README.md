# igpu-roofline

Vulkan roofline microbenchmarks for mobile and integrated GPUs. It measures what a GPU
can actually achieve — compute throughput, bandwidth at every memory level, latency —
using textbook methods, verifies the code the GPU really runs, and turns the results
into a roofline and a shader-tuning guide for that device.

Currently runs on **Android** (arm64, Vulkan 1.3) through `adb`. A host backend for
Linux integrated GPUs (e.g. Radeon 780M, Intel Xe) is planned.

## What it measures

| family | method | output |
|---|---|---|
| FMA throughput (fp32, fp16) | independent FMA chains × vector width × launch size (clpeak / ERT style) | compute roofs |
| int8 dot4 | packed dot products, operand recurrence amortized over 8 dots | integer roof |
| cooperative matrix | `coopMatMulAdd` on driver-reported shapes, operands in registers | matrix roofs |
| DRAM bandwidth | BabelStream kernels (copy, mul, add, triad, dot) + read/write, ≥256 MiB | DRAM roof |
| cache bandwidth | read bandwidth vs working set 4 KiB–512 MiB | cache roof |
| shared memory | 8 independent accumulators / pure writes; stride sweep for bank conflicts; accumulator sweep | shared roof |
| latency | pointer chasing: capacity/levels, TLB reach, line size (Saavedra) | latency ladder |
| ERT | one kernel swept from 0.25 to 256 FLOP/byte | measured ridge point |
| memory type | same kernels, DEVICE_LOCAL vs host-visible buffers, A/B repeated | placement advice |
| sustained | each roof held for 300 s, last-60 s median, steadiness and duty cycle | thermal behaviour |

Every result is validated against a CPU reference, timed with GPU timestamps, and
corrected for fixed per-dispatch cost by two-point (differential) timing. Every shader
variant's SPIR-V is checked at build time against its exact designed instruction
counts; on the device, driver pipeline statistics (and ISA text when the driver
offers it) and optional offline compilers (Arm `malioc`, AMD `rga`) confirm what runs.
See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Quick start

```sh
# prerequisites: uv, Android NDK (r26+), CMake, Vulkan SDK tools (glslc, spirv-val/dis/as), adb
uv sync                                    # create .venv and install (uv.lock is committed)
uv run igpu-roofline build                 # shaders (+ ledger checks) and the Android runner
uv run igpu-roofline run                   # list connected devices
uv run igpu-roofline run --device <serial> # quick plan (~10 min), then writes the report
```

Plans:

| plan | contents | time |
|---|---|---|
| `quick` (default) | every family at its most informative settings, 0.25 s warm-up per config | ~10 min |
| `standard` | all sweeps, 1 s warm-up per config, one 300 s sustained run per roof | ~3 h |
| `gold` | as standard with three sustained batches (repeatability) | ~7 h |

`quick` is a screening plan: it samples each axis coarsely, so compute and DRAM roofs
land within a few percent of a full sweep, while shared-memory roofs (very sensitive to
workgroup and allocation size) can read ~20% low. Use `standard` or `gold` for roofs you
will quote.

Runs are resumable: re-run the same command and finished configurations are skipped.
Results go to `~/igpu-roofline-results/<serial>/` (override with `--results` or
`$IGPU_ROOFLINE_RESULTS`); regenerate reports any time with `uv run igpu-roofline report`.
Tests: `uv run --group dev pytest`.

## Output

Per device, in `report/`:

- `REPORT.md` — roof table (short-run median, best, differential; sustained), ridge
  points for every compute roof × memory level, clock state, figures.
- `TUNING.md` — guidance derived from this device's data: independent chains needed
  per thread, register budget and spill limits, vector width and workgroup size for
  DRAM, cache working-set limit for tiling, shared memory vs cache, bank-conflict
  padding, TLB reach, loads in flight, the measured ridge, fp16/int8 trade-offs.
- `SUPPLEMENT.md` — latency ladder, TLB, line size, ERT table, memory-type A/B.
- `ISA-CHECK.md` — SPIR-V ledger, driver statistics and ISA for every roof.
- `summary.json`, `all-configurations.csv`, `sustained-runs.csv`, figures.

## Scope and limits

- Results are **achievable** rates on this device, driver and thermal state; no vendor
  theoretical peaks are used. Clocks are only read, never changed — pin them yourself
  on a rooted device if you want (see [tools/pin_gpu_clock.sh](tools/pin_gpu_clock.sh));
  the report records whether they were pinned.
- Bandwidths are shader-logical bytes. Physical DRAM/L2 traffic needs
  `VK_KHR_performance_query`, which phones generally do not expose.
- One device at a time per process; each device is locked while measured.

More: [docs/HOW-TO-RUN.md](docs/HOW-TO-RUN.md).

## License

Apache-2.0. Third-party code keeps its own license: nlohmann/json (MIT) and the access
pattern adapted from Google uVkCompute (Apache-2.0); see [NOTICE](NOTICE).

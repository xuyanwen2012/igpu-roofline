# igpu-roofline

Vulkan roofline microbenchmarks for mobile and integrated GPUs. It measures what a GPU
can actually achieve — compute throughput, bandwidth at every memory level, latency —
using textbook methods, verifies the code the GPU really runs, and turns the results
into a roofline and a shader-tuning guide for that device.

Runs on **Android** (arm64, Vulkan 1.3) through `adb`, and on the host's own Linux
integrated GPU (`run --local`, e.g. Radeon 780M).

The project uses measured rooflines to study and guide real **ExecuTorch Vulkan
4w and 8da4w WMMA shader optimizations**. `gpu-lab` is the hub for GPU access and
queried driver capabilities; this repository owns the microbenchmarks and measurement
rigor; ExecuTorch owns the actual workloads and kernel, operator and model performance
evaluation.
See [the ExecuTorch workflow](docs/EXECUTORCH-WORKFLOW.md) for responsibilities,
matching workloads to roofs, and the proposed optimization experiment loop.

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
| sustained | plan-selected roofs held for 120 or 300 s, last-60 s median, steadiness and duty cycle | thermal behaviour |

Trusted results require CPU reference checks before and after sampling, GPU timestamp
quality gates, matching build hashes and repeat confirmation. Differential timing
estimates fixed dispatch cost where applicable. SPIR-V ledgers check designed
instruction counts; driver statistics, ISA and optional offline compilers provide
additional evidence when available. See [methodology](docs/METHODOLOGY.md).

## Quick start

```sh
# prerequisites: uv, Android NDK (r26+), CMake, Vulkan SDK tools (glslc, spirv-val/dis/as), adb
uv sync                                    # create .venv and install (uv.lock is committed)
uv run igpu-roofline build                 # shaders (+ ledger checks) and the Android runner
uv run igpu-roofline run                   # list connected devices
uv run igpu-roofline run --device <serial> # quick plan (~15 min), then writes the report
```

Plans:

| plan | contents | time |
|---|---|---|
| `quick` (default) | every family at its most informative settings, 0.25 s warm-up per config; best candidate per roof confirmed 3× | ~15 min (estimate, not yet re-timed) |
| `fast` | shader-tuning roofs: FMA/dot (all widths and chains), WMMA register + fed (shared/cache/DRAM), DRAM, cache, shared, texture vs buffer, latency; top 2 × 3 confirmation; 120 s sustained runs of 3 roofs | ~30 min on a Radeon 780M |
| `standard` | all sweeps, 1 s warm-up per config, top 3 candidates per roof confirmed 5×, one 300 s sustained run per roof | ~3.5 h (estimate) |
| `gold` | as standard with three sustained batches (repeatability) | ~7 h |

`quick` is a screening plan; its coarse grid can miss the best configuration.
Use `standard` or `gold` for a full sweep. Plan durations are device-dependent
estimates; confirmation and quality gates determine which results are usable.

Runs are resumable: re-run the same command and finished configurations are skipped.
Results go to `~/igpu-roofline-results/<serial>/` (override with `--results` or
`$IGPU_ROOFLINE_RESULTS`); regenerate reports any time with `uv run igpu-roofline report`.
Tests: `uv run --group dev pytest`.

For focused runs, replay, standalone sustained tests and timing diagnostics, see
[the development workflow](docs/HOW-TO-RUN.md#development-workflow).

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
- Bandwidths are shader-logical bytes. Physical DRAM/L2 traffic is not measured by
  this suite; it requires separate hardware-counter evidence.
- One device at a time per process; roofline locks its own runs. gpu-lab currently
  uses separate locks, so coordinate use across both tools.
- Only explicitly confirmed roofs support optimization claims. Current plots and
  ridge calculations can include unconfirmed sweep values; check the confirmation
  table or `confirmed` field before using them.

## Documentation

Start with the [documentation index](docs/README.md): running instructions,
measurement methodology, the ExecuTorch optimization workflow, gpu-lab capability
references, and historical campaign notes.

## License

Apache-2.0. Third-party code keeps its own license: nlohmann/json (MIT) and the access
pattern adapted from Google uVkCompute (Apache-2.0); see [NOTICE](NOTICE).

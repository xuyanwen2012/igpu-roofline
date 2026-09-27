# Profiling ExecuTorch Vulkan workloads on the phones

How to get per-shader GPU time, Mali hardware counters and compiler evidence for a real ExecuTorch Llama
prefill on the Pixel 7a and Galaxy S24+, without root on the S24+ and without the Sokatoa UI. Everything
here was run and checked on 2026-09-26. Numbers are from unpinned clocks unless stated.

The tooling lives outside this repository, in the ExecuTorch workspace:
[`sarc-acl/.artifacts/minibench-sokatoa/`](../../sarc-acl/.artifacts/minibench-sokatoa/README.md) (build steps,
patches, scripts and captures). Installed tools and per-GPU restrictions are in
[gpu-lab's profiling tools](../../gpu-lab/docs/profiling-tools.md). Phone access, root and clock pinning are in
[gpu-lab's Android phones](../../gpu-lab/docs/android-phones.md).

> [!NOTE]
> Neither phone exposes `VK_KHR_cooperative_matrix`: both have only `VK_KHR_shader_integer_dot_product` and
> `VK_KHR_shader_float16_int8`, according to `adb shell cmd gpu vkjson`. WMMA studies cannot run on the phones,
> so this document covers the baseline (non-WMMA) ExecuTorch shaders. To repeat the work on a phone that does
> support cooperative matrices, follow
> [Follow-up: phones with cooperative matrices](#follow-up-phones-with-cooperative-matrices-wmma).

## What each phone gives

| Evidence | Pixel 7a (Mali-G710, rooted) | S24+ (Xclipse 940, not rootable) |
|---|---|---|
| Per-dispatch GPU time | Yes: `gpu.renderstages` has one "compute" slice per dispatch | No: render stages cover uploads and transfers only |
| Hardware counters | Yes: 233 Mali counters through Perfetto `gpu.counters` | No public source (see below) |
| GPU frequency and GPU memory | Yes | Yes (`gpufreq`, `GPU Memory`) |
| Vulkan API timeline | Yes | Yes (`Vulkan Events`; plus CPU-side calls with Sokatoa's layer) |
| Real SPIR-V, spec constants, dispatch sizes | Yes (GFXR) | Yes (GFXR) |
| Offline compiler statistics | `malioc` (static only, see caveat) | None public |
| Per-dispatch time from ETDump (`llama_main`) | Yes | Yes |

Sources checked on the S24+, none of which gives hardware counters:
- **Perfetto:** no `gpu.counters` data source, even while a Vulkan app runs.
- **Vulkan:** no `VK_KHR_performance_query`. `VK_SEC_amigo_profiling` is present; per the Khronos registry it
  passes frame timing from the app to the driver, so it does not return counters.
- **sysfs:** `/sys/kernel/gpu/*` holds only busy percentage, clock, DVFS and power-management state.
- **Sokatoa 1.1.0:** its "Vulkan event timing" and "shader ISA" features are "available only through a Samsung
  extension". The [Sokatoa README](https://github.com/sarc-acl/sokatoa) says Samsung will release that
  extension later this year.

Both phones expose `VK_KHR_pipeline_executable_properties`. [Methodology](METHODOLOGY.md) says Xclipse can
return ISA through it. That path has not been tried in this workflow.

## Why an app, not `llama_main`

`gpu.renderstages` data and injected Vulkan layers (GFXR, Sokatoa) need a **debuggable app**. A shell binary
run through `adb shell` gets neither. The workflow therefore runs ExecuTorch's own Minibench app, built
debuggable with the Vulkan backend.

Minibench is patched to take `model_file`, `prompt_file`, `seq_len`, `llm_warmup` and `llm_runs`, and to
record `prefill_ms_runN`. It reproduces `llama_main --max_new_tokens 1`:

| Phone | Model | App prefill (ms) | `llama_main` (ms) |
|---|---|---|---|
| S24+ | 1B 8da4w / 4w | 3501 / 4306 | 3601 / 4401 |
| Pixel 7a | 1B 8da4w / 4w | 7168 / 14131 | 7102 / 14113 |

Pitfalls, all hit during setup:
- **`seq_len` must be 2049.** `LlmModule.generate(prompt, config, …)` forwards only `seqLen`, not
  `maxNewTokens`. With 2049 the runner resolves one new token, which is prefill only.
- **Call `resetContext()` before each run.** Otherwise the second run fails with
  `pos_ + num_prompt_tokens >= max_context_len`.
- **Pass the model path directly with `model_file`.** Apps cannot follow symlinks into `/data/local/tmp`, and
  the shell cannot create hard links there.
- **Copy layers into the app's data directory.** Installing `sokatoa.apk` as the "layer app" fails because of
  Android 11+ package visibility: the log shows `AppsFilter … BLOCKED`. The Vulkan loader searches the
  debuggable app's data directory, so `profile_run.sh` copies the layer `.so` files there.
- **Sokatoa properties take `true`/`false`, not `1`.**
- **Prompts differ between phones.** The S24+'s old `/data/local/tmp/llama/prompt_2048.txt` is ExecuTorch
  README text, not `" the"` × 2048. The canonical prompt is at `/data/local/tmp/minibench/prompt_2048.txt` on
  both phones.

## Workflow

Run from `sarc-acl/.artifacts/minibench-sokatoa/`. The model `.pte`, tokenizer and prompt must already be on
the phone.

### 1. Capture: Perfetto (+ optional GFXR)

```sh
./profile_run.sh <serial> /data/local/tmp/llama/llama3_2-1b_vulkan_8da4w.pte <name> [--gfxr] [--sokatoa-layer]
```

The script:
- records Perfetto with `gpu.renderstages`, `gpu.counters` (with `counter_ids` 1–300 at a 1 ms period),
  `android.gpu.memory`, `track_event` and GPU/CPU/devfreq frequency;
- starts the app for 1 warm-up and 2 measured prefills;
- pulls `trace.pftrace`, `results.json` and `logcat.txt` (and `capture.gfxr` with `--gfxr`) into
  `captures/<name>/`;
- restores every GPU debug setting and property on exit.

`gpu.counters` without `counter_ids` records nothing.

A 1B GFXR capture is about 800 MB, mostly recorded weights. Its last block is incomplete because the app does
not destroy the device.

### 2. Name the GPU slices

Two independent ways, which agree:

- **ETDump order:** `etdump_order.py <run.etdp> 2` lists a run's delegated dispatches in order. A Mali prefill
  is exactly that many compute slices: 700 for 1B 8da4w and 635 for 1B 4w. Slice *i* is ETDump dispatch *i*.
  Per-dispatch correlation between Perfetto and ETDump is 0.9996 (8da4w) and 0.9998 (4w).
- **GFXR:** `gfxrecon-convert` then `gfxr_dispatches.py capture.json shaders/ <build>/vulkan_compute_shaders`.
  It names every pipeline by matching the extracted SPIR-V bytes to the build's generated `.spv` files, and
  lists each `vkCmdDispatch` with its group counts and the specialization constants really passed. The prefill
  is spread over several command buffers (436 + 5 × 128 dispatches for 1B 8da4w).

### 3. Per-shader Mali counters

```sh
python3 mali_counters.py captures/<run>/trace.pftrace etdump_<device>_<model>.txt out.csv
```

**Method:** each 1 ms counter sample is a delta over its period. It is attributed to the dispatch containing
the middle of that period, and results are summed per shader class.

**Columns:**

| Columns | Meaning |
|---|---|
| `dram_read/write_GBs` | External read/write beats × 16 B |
| `L2_hit_%` | LS read beats from L2 ÷ (from L2 + from external) |
| `FMA/CVT/SFU/msg_per_cyc` | Arithmetic and message pipe instructions per core cycle |
| `LS_issue_per_cyc` | Load/store unit issue rate |
| `LS_partial_rd_%` | Share of reads that are not full width |
| `dram_lat_cyc` | Mean of the external read-latency histogram |
| `reads_50%+_inflight_%` | Share of time with at least half the outstanding-read slots in use |
| `warps_>32reg_%` | Warps using more than 32 registers |
| `diverged_per_warp` | Diverged instructions per warp |

**Caveats:**
- **Bytes per beat:** 16 B follows Arm's Valhall counter guides; it is not measured.
- **Per-cycle ratios are per shader core.** `Execution core active cycles` runs at about one core's clock, so
  use these ratios to compare shaders, not as whole-GPU peaks.
- **`core_busy_%` is only the shader-to-top clock ratio** (about 848 ÷ 996 MHz ≈ 84%). Ignore it.
- **`starved_%` exceeds 100%,** so its absolute value is not meaningful. Compare it only between shaders.
- **Short dispatches (under 1 ms) get few samples.** Read them per class, not per dispatch.
- **Clocks were not pinned.** For absolute comparisons against roofs, pin GPU and MIF first, using the
  procedure in gpu-lab.

### 4. Offline compiler with the real specialization constants

```sh
python3 malioc_specialized.py captures/<gfxr run>/dispatches.jsonl <build>/vulkan_compute_shaders <kernel substrings…>
```

The script bakes the captured constants into the SPIR-V with `spirv-opt --set-spec-const-default-value` and
runs `malioc` for Mali-G710.

**Always specialize first.** With default constants, `linear_dq8ca_q4gsw_tiled` compiled to 0 registers and
0.02 cycles, because the main loop disappeared. With the real constants it is 64 registers, LS-bound.

**Use the runtime counters for registers and occupancy.** The bundled `malioc` compiler is r56p1, but the
Pixel's driver is r54p3, and they allocate registers differently:

| Shader | `malioc` | Pixel counter: warps over 32 registers |
|---|---|---|
| `sdpa_compute_out_tiled` | 46 registers, 50% occupancy | 0% |
| `linear_dq8ca_q4gsw_tiled` | 64 registers | 20% |
| `sdpa_compute_attn_weights_tiled` | 59 registers, 50% occupancy | 97.5% (agrees) |

So use `malioc` for pipe balance (A / LS / T) and instruction mix, and the runtime counters for occupancy.

The generated `.glsl` files contain `#include`, which `malioc`'s GLSL front end rejects. Use the `.spv` files.

### 5. Read the source

The templates are in `backends/vulkan/runtime/graph/ops/glsl/<shader>.glsl`, with a `.yaml` of tile
parameters and variants and `.glslh` load/store helpers. Relate the counter evidence to the load width and
the tile size per thread.

## Findings: Pixel 7a, Llama 3.2 1B, 2048-token prefill

| Shader | Share | Evidence | Reading |
|---|---|---|---|
| `linear_dq8ca_q4gsw_tiled` (8da4w) | 46.5% | Highest FMA rate (0.42/cycle); DRAM 8.3 GB/s; 84% partial reads | Closest to compute-bound of the group |
| `q4gsw_linear_gemm` (4w) | 72.5% of 4w | DRAM 0.5 GB/s; CVT pipe 0.25/cycle (unpacking); FMA 0.29/cycle | ALU-bound on unpack plus fp16 FMA: 3.1× slower than the int8-dot GEMM |
| `sdpa_compute_out_tiled` | 30.3% | 26.2 k workgroups (262 k threads), so parallelism is enough; DRAM 1.4 GB/s; L2 hit 93%; FMA 0.09/cycle; 100% partial reads; high starvation | See below |
| `sdpa_compute_attn_weights_tiled` | 13.8% | LS issue 0.94/cycle (near saturation); 100% partial reads; 97.5% of warps over 32 registers; 6.6 diverged instructions per warp | LS-saturated by narrow loads, plus register pressure and divergence |
| `sdpa_attn_weights_softmax` | 4.1% | 38% external read stall | DRAM-latency-bound; small share |

**`sdpa_compute_out_tiled`: narrow loads and low reuse.** The source explains the counter picture:
- **Tile size:** `TILE_M4 = TILE_N4 = TILE_K4 = 1`, so each thread computes a 4×4 tile.
- **Loads:** every loop step loads 4 + 4 `f16vec4` values, which is 8 bytes each. That is 64 B for 64 FMAs, and
  each loaded value is used only 4 times.
- **Access pattern is not the problem:** neighbouring threads read neighbouring V texels, and a warp broadcasts
  the same attention-weight row.

Candidate fixes, not yet measured:
- **Larger tiles:** `TILE_M4 = TILE_N4 = 2` doubles the FMAs per loaded byte. Register cost must be checked.
- **128-bit loads:** read 8 fp16 values as one `uvec4`. That 128 bits is Mali's full load width is an
  inference that has not been checked against Arm documentation.

Test candidates with a patched copy of the shader YAML in an artifact directory, following the
[experiment template](templates/SHADER-EXPERIMENT.md).

## Follow-up: phones with cooperative matrices (WMMA)

For an agent repeating this study on a phone whose GPU exposes `VK_KHR_cooperative_matrix`. The goal is the
same per-shader evidence, baseline versus cooperative-matrix, for the same model and prompt.

### 1. Confirm support and register the phone

- **Query the driver:** `adb -s <serial> shell cmd gpu vkjson` lists device extensions. Look for
  `VK_KHR_cooperative_matrix`. For the supported M×N×K sizes and component types (fp16 and `SINT8`), use
  gpu-lab's `./gpu caps` and [cooperative matrices](../../gpu-lab/docs/cooperative-matrices.md).
- **Register it:** add the phone to gpu-lab (`./gpu devices <host>`, then `gpus.toml`) so ownership and
  busy rules apply. Plug it into the Fedora desktop, which relays adb for the other phones.
- **Record the basics:** the subgroup size and whether the GPU is AMD-based (Xclipse). ExecuTorch's gates
  below depend on both.

### 2. Microkernel level (roofline runner, shell binary)

- **Counters work for shell binaries.** Perfetto `gpu.counters` is system-wide, so a steady-loop
  microkernel run through `adb shell` still gets them. On the Pixel, counters were recorded this way while
  gpu-lab's shell harness ran.
- **Aggregate over the run window.** Sum counter deltas over the window instead of slicing per dispatch;
  `gpu.renderstages` per-dispatch slices need a debuggable app.
- **Use the Perfetto config from `profile_run.sh`** (explicit `counter_ids`). Start it before the run, then
  query counter sums between the run's start and end timestamps.
- **Find the matrix-unit counters.** List every counter name on the new GPU with the query below and pick
  the ones for matrix units or tensor pipes. Names are vendor-specific, and none were seen on Mali-G710. Record
  the names you use in the experiment record.

```sql
SELECT DISTINCT t.name FROM counter c JOIN counter_track t ON c.track_id = t.id ORDER BY t.name;
```

### 3. Workload level: make ExecuTorch actually dispatch the cooperative-matrix shaders

In `main` (checked at `9b91b4309`), quantized linears use `linear_q4gsw_coopmat` (4w) or
`linear_dq8ca_q4gsw_coopmat` (8da4w) only when `can_use_q4gsw_coopmat()` in
`backends/vulkan/runtime/graph/ops/impl/QuantizedLinear.cpp` passes. It requires all of:

- **Device:** `supports_cooperative_matrix()`, **subgroup size 64**, and **`device_is_amd()`**. The comment says
  the shaders are validated only on AMD RDNA (Samsung Xclipse, AMD Radeon). For 8da4w it also requires
  `supports_int8_cooperative_matrix()`.
- **Graph:** no bias; output rank ≤ 2; **output storage buffer**; **dtype half**; M, N, K aligned to the coopmat
  tile (128×64×16 for q4gsw, 128×64×32 for dq8ca). GEMV (decode-shaped) cases stay on the tiled path.

The generic `is_coopmat_eligible()` in `GemmCoopmat.h`, for linear and matmul, additionally rejects
integrated GPUs.

Consequences:
- **Mali and Adreno:** `main` never takes the cooperative-matrix path, even with hardware support. Use a
  checkout that lifts the vendor and subgroup gates; see [ExecuTorch workflow](EXECUTORCH-WORKFLOW.md) for the
  main and development checkouts.
- **Export:** the current `.pte` files use texture3d outputs, which fail the storage gate. Export with buffer
  output storage.
- **Verify before measuring:** read the dispatched kernel names from `gfxr_dispatches.py` (from a `--gfxr`
  capture) or from ETDump. A run that silently fell back to `linear_*_tiled` is a baseline run.

### 4. Profile both paths the same way

Run steps 1–5 of the workflow above for the baseline `.pte` and the cooperative-matrix `.pte`. Compare:
- per-shader GPU time, with the dispatch count per run checked against ETDump;
- counters, including any matrix-unit counters found in step 2;
- specialization constants and workgroup counts, from GFXR;
- the offline compiler's pipe balance, specialized as in step 4.

Keep the prompt (`" the"` × 2048), `seq_len` 2049, warm-up count and clock state identical, and fill in the
[experiment record](templates/SHADER-EXPERIMENT.md).

### 5. Vendor notes

- **Samsung Xclipse:** `main` already allows the cooperative-matrix path on Xclipse (AMD) with subgroup 64, but
  a phone exposing `VK_KHR_cooperative_matrix` is needed; the S24+'s Xclipse 940 does not. Hardware counters
  need the unreleased Samsung Sokatoa extension; ask SARC internally. ISA may be available through
  `VK_KHR_pipeline_executable_properties`, which has not been tried here.
- **Arm Mali:** counter attribution and `malioc` work as above. Prefer the counters for occupancy, because the
  compiler bundled with `malioc` may differ from the phone's driver. Check `malioc --list` for the new GPU.
- **Qualcomm Adreno** (for example the Z Fold7, not yet connected): whether its Perfetto counter producer and
  per-dispatch render stages match Mali's has not been checked. List the registered data sources while a
  Vulkan app runs, with `debug.graphics.gpu.profiler.perfetto` set to 1:
  `adb -s <serial> shell perfetto --query | awk '/DATA SOURCES REGISTERED/{f=1} f' | grep -iE 'gpu|vulkan'`.
  The Pixel shows `gpu.counters` (`gpu_counter_producer`) and per-process `gpu.renderstages`. The S24+ shows
  `gpu.renderstages` but no `gpu.counters`.

## Safety

- **Restore phone settings.** `profile_run.sh` restores `enable_gpu_debug_layers`, `gpu_debug_app`,
  `gpu_debug_layers`, `gpu_debug_layer_app` and the `debug.sokatoa.*` / `debug.gfxrecon.*` properties on exit.
  Verify them afterwards with `settings get global …`.
- **Pixel clocks** are pinned only on request, with gpu-lab's pin and restore procedure.
- **Do not use RGP/SQTT on the AMD iGPUs.** An RGP/SQTT capture on the desktop's 9600X iGPU hung the whole
  machine on 2026-09-26: RLC page faults, then SMU no response, then CPU lockup.
- **Sideloaded APKs:** Play Protect can block a sideloaded APK with an old `targetSdk`. The patched Minibench
  targets SDK 34 to avoid that.

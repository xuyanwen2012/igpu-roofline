# CLAUDE.md — running igpu-roofline as an agent

Read this before measuring anything. It says how to pick the run procedure for the
device in front of you, what "done" means, and what went wrong before. Device-specific
details the owner still has to supply are marked **TODO(owner)**; ask instead of guessing.

## Goal and non-negotiables

The results tune GPU shaders (ExecuTorch Vulkan q4gsw / dq8ca linear kernels, baseline
vs cooperative-matrix). Values are **measured, achievable** rates; theoretical peaks are
optional context only.

- Methods must stay textbook (BabelStream, ERT, pointer chasing, bank-conflict stride,
  differential timing, confirmation repeats). Never trade rigor for speed without
  asking the owner.
- A number is usable only if it passed validation, the quality gates and confirmation,
  and its sentinel was healthy (see "When is a result usable").
- Never delete results. Move bad or interrupted ones to `superseded/<reason>/`.
- Never change the runner, shaders or `igpu_roofline/` while a run is recording on a
  device: rows are keyed by runner and SPIR-V SHA-256.
- One measuring process per device (a lock enforces it). Never start a second run on
  a device another agent or process owns; check `workflow-state.json` and running
  processes first.
- Report to the owner in the owner's language (currently Chinese).

## Setup

```sh
uv sync
uv run igpu-roofline build                 # shaders (glslc, spirv-*) + Android runner (NDK r26+)
uv run igpu-roofline build --host          # Linux iGPU runner instead of Android
uv run igpu-roofline build --host --no-shaders --vulkan-include ~/vulkan-headers/include
                                           # host without glslc/Vulkan dev headers: copy build/shaders
                                           # + build/shader-manifest.json from a build host first
uv run pytest                              # must pass before any device run
```

SPIR-V is portable: compile shaders once and copy `build/shaders/` and
`build/shader-manifest.json` to hosts without shaderc.

## Pick the procedure

1. `adb devices` (phones get swapped) or `vulkaninfo --summary` (host iGPU). Identify
   the device in the table below. Unknown device: run `quick` first and report.
2. Backend: phone → `run --device <serial>`; host GPU → `run --local`.
3. Root? Only then may clocks be pinned (see the device's section). Non-root devices
   run DVFS-governed; the sentinel and thermal pacing handle that.
4. Plan:
   - `quick` (~15–30 min on a phone): smoke test and first confirmed roofs (top 1 × 3
     repeats). Always run this first on a device that has not run the current `main`.
   - `standard` (~4 h): all sweeps, top 3 × 5 confirmation, one 300 s sustained run
     per roof. Use for numbers that will drive shader decisions.
   - `gold`: standard with 3 sustained batches (repeatability).
   - The owner finds 4–5 h too slow for phones; a faster plan is planned. Until it
     exists, ask before starting `standard` on a phone.
5. Results root: pass `--results <dir>`; one directory per campaign. Do not mix
   results of different runner builds in one device folder unless resuming.

## Devices

| device | GPU | access | root | clocks | ISA route | known issues |
|---|---|---|---|---|---|---|
| vivo V2502A `10AFAT2014002UM` | Mali-G1-Ultra MC12 (MT6993), r54p1 | adb on the owner's Mac | no | DVFS, not readable | `malioc` if installed (not yet) | latched ~40 % slow state (below) |
| Samsung S26 Ultra `R3GL10GC1AP` | Adreno 840 | adb on the owner's Mac | no | DVFS, kgsl readable | none offline; driver stats only | stepwise throttling after 40–90 s |
| Samsung M51 `000008354c579c33` | Xclipse 970 (S5E9975) | host `xgpusw-debug06` | **yes** | pinned: GPU 980 MHz (max OPP), MIF 5333, INT 934 | pipeline dump + ISA: **TODO(owner)** | driver/profiler state checks (below) |
| host `rocky-ryzen` (Minisforum UM790 Pro) | Radeon 780M, RADV (Mesa 25.2.7) | `ssh doremy@rocky-ryzen`, `run --local` | no (no sudo) | DVFS, `pp_dpm_*` readable | driver-returned ISA (RADV `Assembly`) | shares DRAM with the CPU |

### Mali-G1 phone (vivo V2502A)
- The GPU can latch into a state ~40 % slower (FP32 sentinel ~3.5 → ~2.2 TFLOP/s)
  after heavy load (GPU reached 61–66 °C), invisible to Android thermal service, logcat,
  battery state and screen state; idling 15 min does not recover it, **a reboot does**.
  The guard stops the run (`workflow-state.json` phase `paused_device_degraded`) and
  moves the affected results to `superseded/degraded-*`. Then: ask the owner to reboot
  and cool the phone, then rerun the same command to resume.
- Thermal pacing: wait above 50 °C until 45 °C (default phone thresholds).
- Coopmat shapes: fp16 4×8×8 / 16×32×32 (fp16 or fp32 acc), int8 4×16×16; subgroup 16.
- The phone clock is ~15 months behind the host; convert with `date -u +%s` on both
  when correlating logcat with results.
- **TODO(owner)**: physical cooling setup (clip-on cooler? case off?), charging policy.

### Adreno 840 phone (S26 Ultra)
- No run with the current `main` yet: start with `quick`.
- Coopmat: M=64 only, N ∈ {16, 32, 64}; fp16 K=16 (fp16 acc), int8 K=32.
- Earlier (v1) data: the FP16 coopmat roof came out below FP16 FMA and the int8 dot
  roof below a real kernel — both measurement artefacts; do not reuse v1 numbers.
- **TODO(owner)**: cooling and whether pacing thresholds should differ from Mali's.

### Xclipse 970 (Samsung M51, rooted)
- Earlier agent procedure (verify with the owner before reuse): check the driver hash
  against the known-good one (`1eea300aa3974ff8974d04808c9ff394`, main-fafb46ae9c0d),
  pin clocks with `just pin-freqs`, move the PAL profiler config aside, run, then
  confirm driver hash and pins unchanged and restore the PAL config.
- Only 16×16×16 coopmat shapes (fp16, fp16→fp32, int8 s8×s8→s32; the int8 shape exists
  in the catalogue since #2).
- Clocks pinned at the max OPP, so results are peak-clock values; say so in reports.
- **TODO(owner)**: how to dump pipelines / get driver ISA on this device, where the
  tools live, and how to feed them into `pipeline-inspection/` or `offline-isa/`.
- **TODO(owner)**: which host drives it and where results must be stored.

### Radeon 780M (rocky-ryzen)
- Work in `~/igpu-roofline-780m` (branch/commit as needed). **Do not touch
  `~/igpu-roofline` or `~/igpu-roofline-results`**: another agent's checkout with
  uncommitted changes.
- No glslc/spirv tools and no Vulkan dev headers: build with
  `build --host --no-shaders --vulkan-include ~/vulkan-headers/include` after syncing
  shaders from a build host. The runner skips llvmpipe automatically.
- Launch detached: `nohup setsid uv run igpu-roofline --results <dir> run --local
  --plan standard > <log> 2>&1 < /dev/null &` (ssh otherwise stays attached).
- Keep the host idle during runs: the iGPU shares DDR5-5600 (89.6 GB/s peak, MCLK 2800)
  with the CPU, and the sentinel only watches GPU compute.
- Reference results: `~/igpu-roofline-results-780m-v2` (standard, all roofs confirmed;
  shared-memory write being re-measured with the redesigned test; the old write rows
  are in `superseded/shared-write-v1/`).

## Running and monitoring

- Launch in the background and poll `workflow-state.json` and the log; do not sit in
  sleep loops in the foreground.
- `paused_device_degraded`: device changed state; follow the device's section (usually
  reboot + cool + rerun). `stopped_by_user` / killed runs: an unfinished `*.jsonl`
  without its `.json` blocks resume; move it to `superseded/interrupted/<stage>/`.
- Resume = rerun the same command. Finished configurations are skipped; only rows of
  the current runner/shader SHAs count.
- If a code change is needed mid-campaign, finish or stop the run first; a changed
  runner SHA invalidates earlier rows for candidate selection (keep runner changes to a
  minimum; a shader-only change re-measures only that shader's configurations).

## When is a result usable

Check all of these before calling a number usable, and state what was not checked:

1. **Validated**: every sample passed the CPU reference (`accepted`).
2. **Quality gates**: median standard error ≤ 3 %, sample ≥ 80 % of the 5 ms target,
   differential fixed cost ≤ 10 %, pre-sampling warm-up steady, sample drift ≤ 5 %.
3. **Confirmed**: REPORT.md "Roof confirmation" shows a confirmed median with a tight
   repeat range; "unconfirmed" roofs are not usable yet.
4. **Sentinel healthy** for the stages that produced the roof (no `degraded` rows).
5. **Physically plausible**: no roof above a known hardware bound; a real kernel above
   a roof means the roof is wrong, not that the hardware was beaten.
6. **Instruction check** where an ISA route exists: the driver/offline ISA must contain
   the intended work (e.g. one LDS store per intended store, FMA counts matching the
   design). Without an ISA route say "not ISA-verified".
7. **Timing sanity** where possible: GPU timestamps vs host wall clock on a long sample
   (780M: 85.0 vs 84.7 GB/s).

## Lessons already paid for (do not relearn)

- Small launch grids under-fill wide GPUs: Mali coopmat roofs were 2.4–2.6× too low at
  ≤ 512 workgroups of one 16-lane subgroup.
- Warm up with the calibrated dispatch size, and again right before sampling: tiny
  dispatches and CPU-side validation let load-based governors drop the clock (780M
  shared read roof was 64 GB/s instead of 3.4 TB/s).
- Compilers remove work SPIR-V `Volatile` was meant to protect: RADV folded
  same-address LDS stores into one `ds_store`. Distinct runtime addresses fixed it.
- The old int8 dot kernel measured a dependency chain; the dot8 kernel shares the
  operand recurrence across 8 dots.
- Per-sample CV is the wrong gate on phones (DRAM samples scatter 6–14 %); gate on the
  median's standard error.
- A max-based sentinel reference trips on noise; use the median reference, 85 %
  threshold and rechecks.
- Phones can change performance state invisibly and persistently; never mix states in
  one roof set.

## Reporting back

Give the owner: device + driver + plan + code commit; the confirmed roof table (median,
repeat range, sustained); cache/latency levels; unconfirmed roofs and why; sentinel
summary; what was not verified (ISA, clocks, timing); and concrete shader implications
(which roof each kernel should be compared with, ridge points). Point to
`report/REPORT.md`, `TUNING.md`, `SUPPLEMENT.md`.

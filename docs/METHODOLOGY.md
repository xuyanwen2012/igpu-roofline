# Methodology

Each microbenchmark isolates one hardware resource, saturates it, prevents the compiler
from removing or folding the work, validates the result, and counts work with a fixed
formula. This page describes each family, why it is built the way it is, and the
pitfalls it guards against.

## Common rules

**Enough independent work (Little's law).** A resource is saturated only when
`independent operations in flight ≥ latency × throughput`. Parallelism comes from many
invocations (TLP) and from independent chains inside an invocation (ILP); sweeps over
chains, vector width, workgroup size and group count find where the device saturates.

**The compiler must not cheat.** Inputs come from buffers (not constants), results are
stored, each chain uses different operands, and workgroup-memory accesses are marked
SPIR-V `Volatile`. Every variant's SPIR-V is checked at build time against exact
designed counts (FMA, dot, cooperative-matrix ops, loads/stores per storage class,
barriers, volatile accesses) — see `igpu_roofline/spirv_audit.py`. Driver statistics
and ISA are checked on the device (see *Verifying the code*). One real failure mode
this caught: a chain of affine FMAs with uniform coefficients (`x = x*a + b`) was
composed into a single FMA by a driver compiler, which inflated the ERT plateau 10×;
the ERT kernel therefore uses the Horner form `y = y*x + a` with per-element `x`.

**Validate.** Schema version 2 records independent `validation_pre` and
`validation_post` events and `validation_scope=pre_and_post`. CPU reference checks
sample output positions (exactly for integer and memory kernels, with relative
tolerance for float reductions). Matrix checks cover every subgroup and accumulator
chain in each sampled workgroup. Each subgroup owns its own output tile, indexed by
`workgroup_id * subgroups_per_workgroup + subgroup_id`; allocation and logical bytes
include all those tiles. Workgroups must contain whole subgroups. Matrix output is
limited by both 256 MiB and the device's storage-buffer range.

Checks bracket continuous formal sampling; they **do not guarantee detection of
transient errors between the two checks**. Sample events contain timing only. The
last differential pair runs half length then full length, so the post check reads
the actual last full dispatch without another dispatch. Sustained runs check their
last actual sample. Post-check CPU time and readback are outside GPU sample timing
and sustained duty-cycle duration. Missing or failed post checks, process failures,
and GPU faults exclude a result; raw output remains available for diagnosis.
Historical rows without this coverage remain readable and are labelled historical,
but cannot define current trusted roofs. Old confirmed configurations may still be
imported for remeasurement.

**Count work with fixed formulas.** FMA = 2 FLOP; int8 dot4 = 8 integer ops; matrix
multiply-add = 2·M·N·K. Address arithmetic, loop control and operand recurrences are
not counted, so rates are conservative. Bytes are shader-logical bytes
(BabelStream conventions), never physical DRAM traffic.

**Time on the GPU.** A timestamp pair brackets each command buffer. The loop count is
calibrated toward a full sample of 5–7.5 ms; short dispatches are batched in one command
buffer (with barriers between them). Reported per configuration: median and minimum
("best", the STREAM/BabelStream convention) of 21 samples.

**Differential timing.** Samples at L and L/2 loop iterations are interleaved; the
median paired difference gives the per-loop cost with fixed per-dispatch cost (launch,
buffer fills, write-back) removed. This matters most for short or latency-bound
kernels, where fixed cost can exceed half of a dispatch.

**Warm-up.** Without pinned clocks, a short run inherits the clock state left by the
previous configuration (observed: the same kernel at 7 GB/s or 33 GB/s depending on
what ran before). Every configuration therefore runs its own dispatch for a fixed time
(0.25 s in `quick`, 1 s otherwise) before sampling, and GPU clocks are recorded.

**Buffers.** Operands live in DEVICE_LOCAL memory that is not host-visible when the
driver offers such a type; data moves through host-visible staging copies outside
timing. (Host-visible coherent+cached memory can be IO-coherent, i.e. snooped, and
slower; the memory-type control measures the difference directly.)

## Families

**FMA (`alu_*`).** Each invocation runs `chains` independent FMA dependency chains,
unrolled 16×, on scalars or vectors. Operands are bounded (|a| < 1) so values neither
overflow nor go denormal; the CPU reference replays the exact FMA sequence, including
fp16 rounding. The chains × width grid shows how much ILP the device needs and where
register pressure (spills, occupancy) starts to hurt.

**int8 dot (`dot8_*`).** `dotPacked4x8EXT` with an operand recurrence (`v = (a + x) &
0x07070707`) so the dot cannot be hoisted out of the loop; the recurrence is shared by
8 independent dots so its cost per counted dot is small.

**Cooperative matrix (`matrix_*`).** One subgroup multiplies A and B loaded once and
kept in registers, accumulating into `chains` independent accumulators. This is the
matrix-unit compute roof, not a GEMM (real GEMMs must also feed operands). Only
shapes and component types the driver reports are run.

**Global memory (`mem_*`).** BabelStream's copy, mul (scale), add, triad and dot
(workgroup tree reduction), plus pure read and pure write; grid-stride, coalesced
accesses; working sets ≥ 256 MiB define the DRAM roof (larger than any on-chip cache).
`_volatile` variants are a control for compiler interference.

**Cache (`sweep-cache`).** The read kernel over working sets from 4 KiB to 512 MiB,
re-reading the same data; small sets use replicated workgroups so parallelism stays
high. Knees move with workgroup size, so they are not capacities — use the pointer
chase for that.

**Shared memory (`sharedbw_*`).** After one fill and one barrier, each invocation reads
with `accumulators` independent accumulators (throughput-bound, not bound by one add
chain), or performs pure writes. Stride sweeps (1, 2, 4, …, 32, 33, 64, 65) expose bank
conflicts (odd strides should recover under a simple modulo bank mapping); the
accumulator sweep (4–32) shows whether shared memory is saturated. The fill uses a
rotated producer so no lane reads its own store. Single-accumulator reads and
read/write with two barriers per step are kept as controls.

**Latency (`pchase`).** One invocation follows a host-built chain `j = next[j]`
(Wong et al. 2010; Mei & Chu 2017; Jia et al. 2018):
- *capacity*: a random single cycle (Sattolo) of 64 B-spaced nodes over 1 KiB–256 MiB;
- *TLB reach*: one node per page, random order;
- *line size* (Saavedra): sequential chains of growing stride over a 1 MiB and a 64 MiB array.
Each dispatch walks the whole chain (≥ 2^16 loads so fixed cost is small, ≤ 2^20 so a
single serial dispatch stays well below the driver's GPU watchdog — 2^25 serial loads
caused `VK_ERROR_DEVICE_LOST`). Latency = differential per-loop time / 16.

**ERT (`ert_f*`).** Empirical Roofline Toolkit form: load 16 B, F dependent FMAs per
component, store 16 B, for F = 1…1024 (AI 0.25–256 FLOP/byte). The measured curve
shows the real transition from bandwidth-bound to compute-bound and cross-checks the
separately measured roofs.

**Memory type (`control-memory-type`).** Read, write, copy and triad at 256 MiB with
DEVICE_LOCAL vs host-visible coherent buffers, arms alternating order, three repeats.

**Sustained.** The confirmed configuration of each roof (see below) runs for 300 s after a cooldown;
the last-60 s median is reported with a steadiness test (halves within 5 %, CV ≤ 10 %)
and the GPU-timestamp duty cycle. Sustained values replace short-run roofs only with
at least three distinct batches (`gold`) for every required roof, all stable and
linked to its current confirmed configuration. Different configurations or sustained
durations never combine toward that count. Both the sustained executable hash and
its reference short-run executable hash must match the deployed manifest.

## Verifying the code

1. **SPIR-V ledger** — exact static counts per variant, asserted at build time.
2. **Driver statistics** — `VK_KHR_pipeline_executable_properties`: registers, spills,
   instruction counts (e.g. Mali reports spills and FMA cycles, Adreno instruction
   classes), plus ISA text when the driver provides it (e.g. Samsung Xclipse).
3. **Offline compilers** (optional) — `malioc` for Mali (registers, spills, occupancy);
   `rga` for AMD RDNA (ISA, VGPRs; an approximation for vendor drivers).

A spilling variant stays in the results (spills only make it slower, so its value is
still achievable) but is marked.

## Reading the roofline

`attainable(AI) = min(compute roof, bandwidth × AI)`, with `AI = ops / bytes of that
memory level`. Each memory level has its own roof (hierarchical roofline); the ridge
point `compute / bandwidth` is the intensity a kernel needs to become compute-bound at
that level. To place your own kernel: count its ops (FMA = 2) and its bytes per level,
compute AI, and compare its measured rate to `min(...)`.

## Roof selection and device state

**Calibrate, warm up at full size, re-calibrate.** Calibration can increase or decrease
loops and dispatch batches. The default full-sample target is 5 ms, with 5–7.5 ms
preferred. Each candidate uses the median of three GPU timings, with at most ten
rounds and adjustment factors bounded to 1/8–8. Excess batches are removed before
shortening loops; differential configurations retain at least two loops. FP16 loop
bounds and the 256-dispatch batch cap remain in force. Fixed overhead takes priority:
if shortening raises its fraction above 10%, calibration increases loop work again.
The target never relaxes quality gates. Each round logs its measurement, decision,
loop/batch counts and stopping reason, including limits or nonconvergence. The usual
quality gates decide whether the final sample is usable. `calibrate=False`, fixed-step
latency and transfer-copy tests retain their original semantics.

The runner then warms up with that
dispatch for `warmup_seconds` and until the last five dispatch times agree within 3 %
(cap 4 x `warmup_seconds`), then re-calibrates. Load-based governors key on GPU busy %:
on a Radeon 780M, 1 s of 0.08 ms dispatches left the clock low and samples ramped from
15 to 4.4 ms. A result whose warm-up never became steady, or whose last-third median
differs from its first-third median by > 5 % (`sample_drift`), cannot define a roof. When a loop count is capped (bounded FP16 accumulation in matrix
and shared-memory tests), calibration raises the dispatches per timed submission
instead; accounting multiplies by the batch the runner actually used. A sample shorter
than 80 % of the target is flagged `below_target_duration`.

**Quality gates.** A result can define a roof only if the standard error of its median
(~1.2533 x CV / sqrt(n)) is <= 3 %, it is not short, and its differential is valid with
fixed cost <= 10 % of the sample. The gate is on the median, not on per-sample CV: phone
DRAM and shared-memory samples scatter 6-14 % while the 21-sample median stays within ~3 %. `roof-candidates.json`
lists faster results that were gated out and why.

**Confirmation (winner's curse).** A sweep runs hundreds of configurations; its maximum
is biased upward by noise. The `confirm` stage re-measures the top candidates of every
roof (quick: 1 x 3, standard/gold: 3 x 5) in fresh processes, round-robin, reversing the
order every repeat. The roof is the median of the best candidate's repeats; REPORT.md
shows the repeat range next to the single-run sweep maximum. First-look results are a
smoke test and never define a roof.

**Launch grids.** Cooperative-matrix variants of every data type sweep 1 and 4
subgroups per workgroup and up to 16384 workgroups (output <= 256 MiB); FMA and dot
sweep up to 8192 workgroups. On Mali-G1 MC12 (16-lane subgroups) one subgroup per
workgroup and <= 512 workgroups left int8 4x16x16 at 2.9 TOP/s; 16384 workgroups gave
5.3 TOP/s. `matrix-coverage.json` lists device-supported shapes that have no compiled
variant, so a missing shape is never skipped silently (int8 16x16x16 was missing).

**ERT ILP.** ERT variants with 4, 8 and 16 independent element chains per thread; with 4
the high-intensity plateau on Mali-G1 was an FMA-latency limit (FP32 needs ~16 chains
there). Bodies with F > 32 run as 32 unrolled steps per loop trip; the fully unrolled
body is kept as a control (same speed on Mali-G1, so code size was not the limit).

**Line size.** Every pointer-chase dispatch walks its chain twice; the L vs L/2
differential is one warm pass. One pass per dispatch measured cold lines.

**Shared-memory FP16.** Accumulators stay FP16; the final sum of the accumulators is
FP32 (outside the timed loop), so results remain exact integers and are validated
exactly.

**Fed cooperative matrix (`matrix_feed` stage).** The `matrix_*` roofs keep A and B in
registers, so they measure the matrix unit alone. Real WMMA kernels load a tile pair
every step, so the `_lds` / `_gmem` variants run `coopMatLoad` for A and B inside the
loop: from workgroup memory (4 staged tile pairs), or from the storage buffer with
~1 MiB of tiles (cache-resident) or >= 256 MiB (DRAM, each tile read once). Each loaded
pair feeds CHAINS multiply-adds, so CHAINS is the reuse per load; comparing the
`matrix_<dtype>_feed_{shared,cache,dram}` roofs with the register-resident roof shows
how much reuse a kernel needs before the loads stop limiting it. DRAM-fed rates grow
with CHAINS until the matrix unit limits them (780M int8: 1.2 / 2.4 / 4.6 / 8.5 TOP/s
at CHAINS 1 / 2 / 4 / 8, all at ~75–79 GB/s), so `matrix_<dtype>_feed_dram` is a
bandwidth roof (GB/s); REPORT.md lists every source × CHAINS with ops per loaded byte
so a kernel's reuse can be looked up directly. Ops count every
subgroup of a workgroup; `matrix_load_bytes` records the A/B bytes loaded. The SPIR-V
ledger asserts two `OpCooperativeMatrixLoadKHR` outside and two inside the loop.

**Texture vs storage buffer (`texture` stage).** ExecuTorch Vulkan kernels read inputs
as `texture3d` / `texture2d` through `texelFetch`. `texture.comp` reads the same texels
in the same order from a storage buffer, a `sampler2D` or a `sampler3D` (RGBA16F and
RGBA32F; 1 MiB cache-resident and 256 MiB DRAM working sets); only the fetch path
differs. Image modes upload through a staging buffer and are not bound by
`maxStorageBufferRange`; extents follow `maxImageDimension2D/3D`. On the Radeon 780M
(RADV) DRAM-sized reads ran ~85 GB/s from a buffer but ~44 GB/s (2D) and ~40 GB/s (3D)
from images; cache-resident reads were close (310–440 GB/s).

**Shared-memory write test.** Every store goes to a distinct address,
`(l*STRIDE + t*step + k*w) % COUNT` with a runtime `step` (push constant), and stores a
runtime-uniform value. The first design stored `ACC x loops` times to one slot per lane;
RADV/ACO folded the whole loop into a single `ds_store` despite SPIR-V `Volatile`
(verified in the driver-returned ISA), which reported 12-20 TB/s on a Radeon 780M. The
new form compiles to `ACC` stores per iteration there. Address arithmetic costs about
two VALU instructions per store, so narrow (scalar) variants can be VALU-bound; the roof
is the fastest width.

**Timing cross-check.** On the 780M a 0.38 s read sample gave 85.0 GB/s by GPU
timestamps and 84.7 GB/s by host wall clock (which includes submit/wait), so the
reported `timestampPeriod` is right; `vkCmdCopyBuffer` gave 74.6 GB/s against 71.4 GB/s
for the shader copy.

**Device-state sentinel.** Without a readable GPU clock, a phone can change state
invisibly: on a Mali-G1 phone the same binary and configuration fell from 3.48 to
2.2 TFLOP/s hours later, at 35 C with the screen on. A fixed FP32 FMA configuration is
measured before and after every stage, every 20 configurations inside a stage, and before
every sustained batch. If it falls below 85 % of the median of the sentinel readings this
runner has seen on this device, it is re-measured twice; if the median of the three is
still below, the run stops (the fast state scatters ~+-6 %, the slow state is ~35 % lower): every result measured since the last good sentinel is moved
to `superseded/degraded-<utc>/`, the workflow state becomes `paused_device_degraded`,
and rerunning the same command after a reboot and cool-down resumes and re-measures
them. REPORT.md still lists every sentinel reading.

**Thermal pacing.** On that phone the slow state began while the GPU was at 61-66 C
under heavy cooperative-matrix load and lasted until reboot. Before every short-run
configuration the GPU temperature is read from the thermal HAL; above 50 C the run
waits (up to 10 min) for 45 C. Waits are logged in `pacing.jsonl`. Sustained stages are
not paced.

## Limits

- No pinned clocks unless you pin them; no hardware counters (physical DRAM/L2 bytes
  unknown); no vendor theoretical peaks. Results are achievable rates.
- Static instruction counts are per loop body; malioc's cycle totals are not
  loop-weighted and are not used to call a bottleneck.

## References

McCalpin, STREAM; Deakin et al., BabelStream; Lo et al., Empirical Roofline Toolkit
(LBNL); Williams, Waterman, Patterson, "Roofline" (CACM 2009); Saavedra & Smith,
"Measuring cache and TLB performance" (1995); Wong et al., "Demystifying GPU
microarchitecture through microbenchmarking" (ISPASS 2010); Mei & Chu, "Dissecting GPU
memory hierarchy through microbenchmarking" (TPDS 2017); Jia et al., "Dissecting the
NVIDIA Volta GPU architecture via microbenchmarking" (2018); Google uVkCompute;
clpeak; vkpeak.


**One admission policy.** Candidate selection, confirmation, reports, tuning advice,
supplements and replay export share validation, build and quality checks. Missing
hashes never match. All planned confirmation repeats must be present; the existing
allowance of at most one failed repeat remains. Rejected/short/noisy/drifting rows
remain in raw files and diagnostic CSV with exclusion reasons. An incomplete report
lists missing evidence instead of implying a sustained or confirmed roof.

**Sentinel boundary reuse.** Only a successful healthy stage-end probe may serve the
immediately following stage-start check, within five seconds in the same process,
device and build. Actual measurement, cooling or errors invalidate reuse. First,
last, every-20-configurations and slowdown rechecks remain actual probes. Reuse logs
reference the original probe and neither add baseline samples nor advance the last
healthy timestamp used for quarantine.

# RTX 4070 Ti SUPER: roofs against the tuned linear kernels (campaign et-study-20261010)

## State

- 2026-10-09 18:55 UTC: review round 2 found one failed check (rule 7: the pipeline-statistics script deleted its
  raw cache blobs). Fixed as described in part C: deletion removed, originals not recoverable, a labelled
  compile-only recapture retains the blobs. No roof or timing was re-run and no number of parts A, B or D
  changed. Nothing is running on the device; locks free.
- 2026-10-09 18:45 UTC (superseded by the entry above as far as part C's cache-blob evidence goes): **all four parts measured and written, branch pushed, one review round passed (four
  checks PASS); nothing is running on the device.** Device locks are free. No decision is needed from the owner
  for this study; two observations for the owner are at the end.
- History: record copied from the template and committed 17:49:06 UTC, before the first measurement started (17:49:43); part A (roofline `fast`) 17:49 to
  18:15 UTC, rc 0; part B (microbench, 5 processes each of `--linear` and `--sdpa`) 18:15 to 18:22 UTC, all rc 0;
  part C (pipeline statistics, compile only) 18:23 UTC, recaptured with retained blobs 18:47 UTC.

## What was measured, in one sitting

NVIDIA GeForce RTX 4070 Ti SUPER, proprietary driver 615.71.09, Vulkan 1.4.351, subgroup 32, clocks as found
(not pinned, power limit 285 W). igpu-roofline at commit `7326bd7` (tool sources identical to `origin/main`
`84361ac`; runner `b1180c72e9c5`, shader manifest `03307d6b4d60`, the same manifest hash as the September
campaign). ExecuTorch final build `topic3` (`ed8b5af91`), read only, with
`ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=4070ti-fused1`; microbench binary sha256 `61d29fdb...`, the one
the tuning campaign gated.

During both measurements only this study's processes were on the GPU (sampled every 2 s / 0.5 s); no thermal
throttle reason and no `hw_slowdown` in any of 761 + 759 sensor samples; the software power cap was active in
44 samples of part A and 218 of part B (the card reaches its 285 W limit under fp16 matrix load, as the tuning
campaign recorded); temperature 37 to 69 C. Sentinel healthy in all 34 probes (25.40 to 25.66 TFLOP/s, limit
21.67).

## Part A: roofs (confirmed, repeat spread at most 0.6 %, except the two rows named below)

| roof | value | repeat range | matrix shape, subgroup |
|---|---:|---|---|
| fp16 -> fp16, operands in registers | 182.95 TFLOP/s | 182.9 to 183.0 | 16 x 16 x 16, 32 |
| fp16 -> fp16, fed from shared memory (best reuse, 64 flop/B) | 177.94 | 177.9 to 177.9 | same |
| fp16 -> fp16, fed from shared memory at 32 flop/B | 173.55 | 2 of 3 confirmation repeats admitted by the tool (one excluded as short), spread 0.1 % | same |
| fp16 -> fp32, operands in registers | 92.80 TFLOP/s | 92.3 to 92.8 | same |
| fp16 -> fp32, fed from shared memory | 92.19 | 92.2 to 92.7 | same |
| int8 -> int32, operands in registers | 369.24 TOP/s | 369.2 to 371.2 | 16 x 16 x 32, 32 |
| int8 -> int32, fed from shared memory (64 op/B) | 367.69 | 367.7 to 367.8 | same |
| int8 -> int32, fed from shared memory at 32 op/B | 367.06 | **one sweep row, not confirmed** | same |

Not confirmed, and used: the int8 shared-fed row at 32 op/B (the 8da4w kernel's reuse) and the fp16 -> fp32
shared-fed row at 32 flop/B (92.15, used for the 1B attention row); both are single sweep rows and are flagged
`(u)` below. Their confirmed neighbours (int8 at 64 op/B: 367.83; fp16 -> fp32 at 16 flop/B: 92.65) differ by
0.2 % and 0.5 %, so no conclusion depends on the flag. The tool reports one more reason line,
`matrix_int8_feed_dram: repeat_unstable`; that roof is not used here. Sustained values exist for three roofs
from one 120 s batch each (fp16 -> fp32 matrix 92.31 TFLOP/s); the tool requires three batches to call a
sustained roof, so the short-run roofs are the basis. Full list: `report/REPORT.md`.

The two roof sets agree with the tuning campaign's of 2026-10-08 (182.8 / 92.3 / 369.2) within 0.5 %.

## Part B: matched efficiency (full table with sources: `efficiency.csv`)

Rate = `2*M*N*K / kernel time`, M = 2048, kernel time = median over 5 processes of the microbench's kernel
median (3 warm-up + 5 timed iterations each), texture3d storage (the model path). Largest spread over the 5
processes: 2.4 % (1B wk_wv 4w, a 42 us kernel on a 1.024 us timer step), otherwise at most 1.0 % for the linear
rows; 1.0 to 3.1 % for the attention rows. The dispatched
kernel is the name the run printed; the same kernel serves the same shape in the tuning campaign's in-model
trace (last column, cited from gate `s4-c1`, not re-run).

| model | shape | scheme | N x K | kernel tile | ms | rate | % register | % fed shared | % fed at reuse | in-model % register |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 1b | wq_wo | 4w | 2048 x 2048 | `t256x128k16g42s32ga` | 0.1444 | 118.99 | 65.0 | 66.9 | 68.6 | 62.6 |
| 1b | wk_wv | 4w | 512 x 2048 | `t128x128k16g24s32ga` | 0.0420 | 102.30 | 55.9 | 57.5 | 58.9 | 50.9 |
| 1b | w1_w3 | 4w | 8192 x 2048 | `t256x128k16g42s32ga` | 0.5847 | 117.53 | 64.2 | 66.0 | 67.7 | 63.9 |
| 1b | w2 | 4w | 2048 x 8192 | `t256x128k16g42s32ga` | 0.5622 | 122.24 | 66.8 | 68.7 | 70.4 | 65.9 |
| 1b | wq_wo | 8da4w | 2048 x 2048 | `t128x128k64g44s32mk32ra` | 0.1178 | 145.89 | 39.5 | 39.7 | 39.7 (u) | 38.2 |
| 1b | wk_wv | 8da4w | 512 x 2048 | `t128x128k64g44s32mk32ra` | 0.0317 | 135.30 | 36.6 | 36.8 | 36.9 (u) | 36.7 |
| 1b | w1_w3 | 8da4w | 8192 x 2048 | `t128x128k64g44s32mk32ra` | 0.4731 | 145.26 | 39.3 | 39.5 | 39.6 (u) | 38.6 |
| 1b | w2 | 8da4w | 2048 x 8192 | `t128x128k64g44s32mk32ra` | 0.4465 | 153.92 | 41.7 | 41.9 | 41.9 (u) | 40.8 |
| 3b | wq_wo | 4w | 3072 x 3072 | `t256x128k16g42s32ga` | 0.3195 | 120.99 | 66.1 | 68.0 | 69.7 | 65.5 |
| 3b | wk_wv | 4w | 1024 x 3072 | `t256x128k16g42s32ga` | 0.1065 | 120.99 | 66.1 | 68.0 | 69.7 | 65.2 |
| 3b | w1_w3 | 4w | 8192 x 3072 | `t256x128k16g42s32ga` | 0.8632 | 119.41 | 65.3 | 67.1 | 68.8 | 65.9 |
| 3b | w2 | 4w | 3072 x 8192 | `t256x128k16g42s32ga` | 0.8468 | 121.72 | 66.5 | 68.4 | 70.1 | 67.0 |
| 3b | wq_wo | 8da4w | 3072 x 3072 | `t128x128k64g44s32mk32ra` | 0.2488 | 155.34 | 42.1 | 42.2 | 42.3 (u) | 42.6 |
| 3b | wk_wv | 8da4w | 1024 x 3072 | `t128x128k64g44s32mk32ra` | 0.0840 | 153.45 | 41.6 | 41.7 | 41.8 (u) | 41.5 |
| 3b | w1_w3 | 8da4w | 8192 x 3072 | `t128x128k64g44s32mk32ra` | 0.6707 | 153.68 | 41.6 | 41.8 | 41.9 (u) | 42.7 |
| 3b | w2 | 8da4w | 3072 x 8192 | `t128x128k64g44s32mk32ra` | 0.6717 | 153.45 | 41.6 | 41.7 | 41.8 (u) | 42.5 |
| 8b | wq_wo | 4w | 4096 x 4096 | `t256x128k16g42s32ga` | 0.5652 | 121.57 | 66.5 | 68.3 | 70.0 | 65.1 |
| 8b | wk_wv | 4w | 1024 x 4096 | `t256x128k16g42s32ga` | 0.1413 | 121.57 | 66.5 | 68.3 | 70.0 | 63.7 |
| 8b | w1_w3 | 4w | 14336 x 4096 | `t256x128k16g42s32ga` | 1.9845 | 121.20 | 66.2 | 68.1 | 69.8 | 65.2 |
| 8b | w2 | 4w | 4096 x 14336 | `t256x128k16g42s32ga` | 1.9523 | 123.20 | 67.3 | 69.2 | 71.0 | 66.3 |
| 8b | wq_wo | 8da4w | 4096 x 4096 | `t128x128k64g44s32mk32ra` | 0.4475 | 153.57 | 41.6 | 41.8 | 41.8 (u) | 42.3 |
| 8b | wk_wv | 8da4w | 1024 x 4096 | `t128x128k64g44s32mk32ra` | 0.1116 | 153.92 | 41.7 | 41.9 | 41.9 (u) | 40.9 |
| 8b | w1_w3 | 8da4w | 14336 x 4096 | `t128x128k64g44s32mk32ra` | 1.5831 | 151.93 | 41.1 | 41.3 | 41.4 (u) | 42.7 |
| 8b | w2 | 8da4w | 4096 x 14336 | `t128x128k64g44s32mk32ra` | 1.5616 | 154.02 | 41.7 | 41.9 | 42.0 (u) | 43.2 |
| 1b | attention, S 2048, d 64, 32 heads | fused | | `fused3sb_d64_t32x32g11s32rko` | 0.3826 | 45.61 | 49.1 | 49.5 | 49.5 (u) | 52.7 / 52.8 |
| 3b | attention, S 2048, d 128, 24 heads | fused | | `fused3sb_d128_t16x64g11s32rko` | 0.5073 | 52.39 | 56.4 | 56.8 | 56.5 | 59.0 / 60.1 |
| 8b | attention, S 2048, d 128, 32 heads | fused | | `fused3sb_d128_t16x64g11s32rko` | 0.6461 | 54.84 | 59.1 | 59.5 | 59.2 | 60.2 / 63.0 |

Rates in TFLOP/s (4w, attention) and TOP/s (8da4w). `(u)`: the reuse row is not a confirmed one (see part A).

Matched roofs, from each kernel's SPIR-V (`isa/kernel-coopmat-types.txt`; every `OpCooperativeMatrixMulAddKHR`
of a kernel has one signature):

| kernel | A, B | accumulator of the multiply-add | shape | matched roof |
|---|---|---|---|---|
| 4w `t256x128k16g42s32ga` (32 multiply-adds in the module) | fp16 | **fp16** | 16 x 16 x 16 | fp16 -> fp16 |
| 4w `t128x128k16g24s32ga` (16) | fp16 | **fp16** | 16 x 16 x 16 | fp16 -> fp16 |
| 8da4w zpgtr `t128x128k64g44s32mk32ra` (8) | int8 | int32 | 16 x 16 x 32 | int8 -> int32 |
| fused attention d64 (32) and d128 (64) | fp16 | **fp32** | 16 x 16 x 16 | fp16 -> fp32 |

**Question 1 of the task, settled.** Both 4w kernels the final configuration dispatches (the only two: 11 shapes
on `g42`, 1B wk_wv on `g24`) accumulate in fp16 inside the matrix instruction, so the fp16 -> fp16 roof
(182.95) is their roof and the working figure of 65 % stands: **64.2 to 67.3 % on the `g42` tile, 55.9 % on the
`g24` tile**. One qualification the SPIR-V shows: after every 128-K quantization group the fp16 accumulator is
converted and added into an fp32 total (`OpFConvert` and `OpFAdd` on fp32 accumulator matrices, 32 / 16 per
module, outside the multiply-add). That is not the half-rate fp16 -> fp32 instruction, but it is work and
register pressure the fp16 roofline shader does not have. The fused attention kernel accumulates in **fp32**
(both variants), so the fp16 -> fp32 roof (92.80) matches it: 49 % (d64) and 56 to 59 % (d128) in the
microbench, 53 to 63 % in the model for the fused kernel alone (the microbench time includes the K/V copy
pass).

**Working figures corrected:** 4w 65 % -> 66.2 % median (55.9 to 67.3); 8da4w 41 % -> 41.6 % median (36.6 to
42.1). Feeding does not change the picture: against the fed roof at the kernel's own reuse the 4w kernels are at
59 to 71 % and 8da4w at 37 to 42 %.

Kernel reuse (operations per loaded A/B tile byte, counted as the tool counts it: one subgroup, one K step):
4w `g42` 16 multiply-adds per 10 tile loads = 25.6 flop/B, `g24` 8 per 6 = 21.3 flop/B (nearest fp16 rows 32;
the fast plan's fp16 shared-fed rows below 32 are excluded by the tool as too short, so for `g24` 32 is the
nearest usable row, not an equal one); 8da4w
4 per 4 = 32 op/B (row 32). The reuse-row values are the tool's best validated median of the admitted
repeats; with the median of the repeats instead they move by at most 0.5 % (fp16 173.44, fp16 -> fp32 at
16 flop/B 92.18); attention 25.6 (d64) and 15.1 (d128) flop/B, but K and V come from global buffers
there, so the shared-fed roofs are context for the attention rows, not a matched operand source.

## Part C: what the driver generated

**Not ISA-verified.** `VK_KHR_pipeline_executable_properties` on this driver returns, for every pipeline, one
executable ("CS", subgroup size 32) with five statistics (Register Count, Binary Size, Stack Size, Local Memory
Size, Shared Memory Size) and **zero internal representations**; the pipeline cache blob has 7.97 to 7.99 bits
of entropy per byte (compressed or encrypted), so there is no disassembly route. Raw output for 5 kernels and 10
roofline shaders: `isa/raw/`, table `isa/counts.csv`.

Evidence gap and how it was closed: the first capture (`isa/raw/`, 18:23 UTC) measured each cache blob's size
and entropy and then deleted the blob, which the campaign's rule against deleting results forbids; those 15
blobs are not recoverable, so the size and entropy figures of `isa/raw/` and `isa/counts.csv` cannot be
recomputed. The deletion is removed from the script and a second, separately labelled compile-only capture
(`isa/recapture-20261009-retained-blobs/`, 18:47 UTC, both device locks, no dispatch) keeps all 15 blobs with
their sha256; table `isa/counts-recapture-20261009-retained-blobs.csv`. Recomputed from the retained blobs:
10.9 to 41.0 kB, 7.966 to 7.986 bits per byte (first capture: 7.965 to 7.986). The five driver statistics are
identical in both captures for all 15 pipelines; the blob is not byte-reproducible (6 of 15 differ by one byte
in size). The entropy claim rests on the second capture. Shapes compiled: 4w 3B wq_wo (`g42`) and 1B wk_wv
(`g24`), 8da4w 3B wq_wo.

1. *Does the kernel compile to the hardware's matrix instructions?* Not shown directly. Indirect evidence: the
   kernels use the same SPIR-V instruction with the same operand types, shape and subgroup size as the roofline
   shaders that reach 183 / 369 T per second, and the 8da4w kernel's own multiply phase runs at the roof: the
   tuning campaign's phase timing gives about 1000 to 1200 clock cycles per K = 64 chunk for 128 multiply-adds
   per 512-thread workgroup, and the int8 roof predicts about 1010 cycles (assuming one such workgroup per SM,
   66 SMs, a 2.7 GHz counter: derived, not measured here). A kernel falling back to scalar code could not do
   that.
2. *How many per loop iteration against the tile arithmetic?* Only the static SPIR-V counts are visible, and
   they equal the tile arithmetic: 4w `g42` 32 = 16 per K = 16 chunk in the loop + 16 in the peeled last chunk;
   4w `g24` 16 = 8 + 8; 8da4w 8 = 2 x 2 tiles x 2 K steps per chunk, loop not peeled. What the driver emits per
   iteration is unknown.
3. *Register spills, SIMD width?* Subgroup 32 in every pipeline, kernels and roofline shaders alike. Stack Size
   is 0 everywhere and there is no spill statistic. Register Count: roofline 60 to 95; 8da4w 123; 4w `g24` 170;
   **4w `g42` 255**, which looks like the top of the counter's range, so that kernel is at or over the register
   budget (16 fp16 accumulators plus 16 fp32 totals per subgroup). Local memory: 48 bytes per thread in the
   8da4w kernel (low 32 bits of the statistic), 0 in every other pipeline.

*What the roofline shader gets that the kernel does not:* operands that are already in shared memory (one
staging before the loop, no barrier inside it), one or two tile loads per 4 to 8 multiply-adds with no
dequantization, 60 to 95 registers, 4 KiB of shared memory against 35 to 47 KiB of the 49 KiB limit, and no
local memory. Rate against rate at the same shape and subgroup size: int8 367.1 (fed, 32 op/B) against 135 to
155; fp16 173.6 (fed, 32 flop/B) against 102 to 123.

## Part D: where the gap is (8da4w, the lowest percentage)

Chain for 3B wq_wo (the 12 shapes differ only in the last step):

| step | rate, TOP/s | loss at this step |
|---|---:|---:|
| int8 matrix roof, operands in registers | 369.24 | |
| fed from shared memory (best reuse) | 367.69 | 0.4 % |
| fed from shared memory at the kernel's reuse, 32 op/B (u) | 367.06 | 0.2 % |
| kernel | 155.34 (135.3 to 155.3 over the shapes) | **57.7 %** (57.7 to 63.1) |

0.996 x 0.998 x 0.423 = 0.421 = 42.1 % of the register roof. **The whole gap is in the last step**: loading
operands from shared memory costs nothing on this card at any reuse (365.9 to 367.8 TOP/s from 16 to 128
op/B), so the question raised in the task (the fed roof equals the register roof, yet the kernel is at 41 %) has
this answer: the kernel loses nothing in the multiply or in the shared-memory loads; it loses the time in
which the matrix unit waits. The tuning campaign's phase timing of this kernel (first campaign, `STATUS.md` /
`proposal.md`, "Phase timing of the shipped linear kernels"; twelve shapes in its `phases/prof-parent-8da4w.csv`)
says where a wave goes: barrier 14 %, weight and activation fetch 34 to 43 %, multiply 30 to 38 %, shared-memory
stores 7 %, prologue and group epilogue 6 to 8 %, write 1 to 5 %. The multiply share (30 to 38 % in the
instrumented twin) and the clean kernel's 37 to 42 % of the roof are the same statement. The campaign also
found: halving the number of weight fetches changes nothing (1.011x, 1.2 % repeat spread), 13 other tiles are
at best 0.84x, and "what the fetch phase is waiting for was not established".

Two numbers from this study's roofs bear on that:

- The kernel issues 1024 texel fetches of 16 B per chunk for 256 distinct texels (each texel four times), i.e.
  `M*N*K/64` bytes per dispatch: **1.06 to 1.21 TB/s of texel fetches, 66 to 75 % of the confirmed
  cache-resident 2D-texture roof** for 16 B texels (1614 GB/s, rgba32f; the kernel's texture is an integer
  one: nearest roof, not a matched one). The activation loads are 8 % of the buffer cache roof.
- The fetch phase is about 930 to 1430 clock cycles per chunk; the confirmed load-to-use latency is 92 to 106 ns
  (about 250 to 290 cycles at 2.7 GHz) for working sets up to 16 MiB. The fetch phase is three to six such
  latencies long.

### Hypotheses for a third round (not run)

| | hypothesis | evidence for | evidence against | cheapest deciding experiment |
|---|---|---|---|---|
| H1 | The fetch phase is a chain of dependent loads, not a number of fetches: each texel coordinate comes from a per-thread table in local memory, then the texel, then the scale, and the warp waits for each in turn. | The phase is 3 to 6 load-to-use latencies long; halving the fetch count did not shorten it; this is the only kernel with local memory (48 B per thread); September: "the A store cost was really exposed global-load latency", nothing saturated (tensor active 30 %). | The loop is built so that the fetch is in flight during the multiply; if that worked the latency would be hidden. The phase timer itself disturbs scheduling on this driver (September). Replacing the table by selects was 0.65x on texture3d. | One timing-only twin of the existing phase-timing kernel whose fetch coordinates are computed from the invocation index with no table read (same fetch count, same texels): if the fetch phase falls towards one latency, H1 holds. One build, minutes. |
| H2 | Texel-fetch throughput is close to a real limit: the kernel's texel traffic is 66 to 75 % of the nearest texture roof. | The number above; the fetch share is the largest of the wave; the texture roof is 4.4 times lower than the buffer cache roof (1614 against 7129 GB/s). | Halving the fetches (to about 37 % of that roof) gained 1.1 %: a binding throughput limit would have paid. September's ablation: removing the weight fetch saved 16 of 301 us. The roof is for another format and for distinct texels. | No kernel change: one roofline texture variant with the kernel's pattern (integer 16 B texels, four fetches per distinct texel, two per thread per barrier). If it reads far above 1.2 TB/s, H2 is dead. A shader variant and a focused `texture` run, minutes. |
| H3 | The limit is the wave structure: all 16 warps of the workgroup fetch, dequantize, store and meet at one barrier per 8 multiply-adds, so the matrix unit idles about 60 % of the time whatever each stage costs. Warps specialised to staging and to multiplying, or more multiply per barrier, would be needed. | Fed roof = register roof at every reuse: once operands are in shared memory nothing else limits the multiply; the multiply phase alone is at the roof; no stage change has moved the total (fetch halving, tiles, staging widths); September's multiply-only ablation reached 272 TOP/s (74 %). | Every structural variant tried so far was slower (256-thread tiles, 8 multiply-adds per warp at 207 to 224 registers, store-first order; 13 tiles at best 0.84x). Shared memory is 35 of 49 KiB, which bounds deeper buffering. Untested on any device. | No kernel change: a roofline shared-fed int8 variant that restages its tiles (global load, shared store, barrier) every R iterations, R swept from 1 to 16, alone and with half of the subgroups doing only the staging. It gives the achievable rate at 8 multiply-adds per barrier and says whether specialisation can pay before any kernel is written. |

Order by cost and information: H2's experiment first (it can only remove a hypothesis), then H1 (one twin
build), then H3.

## For the owner

- A co-tenant image-generation service on the device host is in a restart loop (`activating (auto-restart)`, exit status
  203/EXEC, a few milliseconds of CPU per attempt). It never opened the GPU during this study (no foreign GPU
  client in any sample) and was left as found.
- Left on the device host: this study's own directory `et-study-20261010` (235 MB: the tool build, raw results, microbench and
  statistics outputs). Nothing else was written there; the ExecuTorch trees are unchanged (`git status` clean
  in both campaign checkouts, no file newer than the start of this study).

## Not verified

ISA (no route on this driver); GPU timestamps against wall clock; the SM count and cycle-counter unit used in
part C item 1; sustained behaviour beyond one 120 s batch; correctness (not in scope: the tuning campaign's
gate `s4-c1` stands for the final configuration; the microbench was run with `--skip-correctness` and reports
`unexpected_coopmat` for the texture3d rows, a stale expectation of the test that the campaign's own runs show
as well).

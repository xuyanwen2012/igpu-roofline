# Arc Pro B70: roofs against the tuned kernels (campaign `et-study-20261010`)

## State

2026-10-09, after review round 1: parts A to D are done and nothing is running on the device. The reviewer's
four checks passed. One item waits for the owner (section "Decision needed from the owner" at the end): the
individual timed runs behind each microbenchmark median were never written by the tool. Nothing is re-measured
or recomputed while it is pending. The review artifact is `EXPERIMENT.md`.

Device: Intel Arc Pro B70 (BMG G31), card 0 of two; driver ANV, Mesa 26.2.3 (109060099); kernel 7.2.9-200.fc44.
Clock policy as found, nothing changed: GT `min_freq` 1200, `max_freq` 2800 MHz, profile `[base] power_saving`.
Tool: igpu-roofline `84361ac` (runner `810e098c8abb`, shader manifest `03307d6b4d60`: the September binaries
and SPIR-V, byte for byte). ExecuTorch: the tuning campaign's final build of commit `6ac44c483`, run with
`ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=b70-fused1`, read only.

## Part A: roofs (`report/REPORT.md`, `report/summary.json`)

One `fast` plan, 23 minutes, sentinel healthy at all 34 checkpoints (18.349 to 18.351 TFLOP/s), no stale rows.
GT clock, sampled every 2 s: mean 2726 MHz over the non-idle samples of part A (up to 2800; lower readings fall
between configurations), 2768 to 2794 MHz in the linear runs of part B and 2800 MHz in its attention runs; the power-limit flag `pl2` was set in 16 of 680
samples of part A, no thermal reason, package at most 76 C.

| roof | register | fed from shared memory | unit |
|---|---:|---:|---|
| fp16 -> fp16, 8x16x16 | 173.3 | 168.4 (97.2 %) | TFLOP/s |
| fp16 -> fp32, 8x16x16 | 179.9 | 166.6 (92.6 %) | TFLOP/s |
| int8 -> int32, 8x16x32 | 359.9 | 323.3 (89.8 %) | TOP/s |

All of these are confirmed (3 repeats, spread at most 0.4 %). The tool's only confirmation failure is the 4-chain
candidate of `matrix_fp16_fp32_feed_dram` (`repeat_unstable`, spread 8.2 %); that roof is confirmed by its
2-chain candidate (591.9 GB/s, 1.3 %) and is not used below. No roof of this run is unconfirmed. Against September (previous kernel) no roof moved by more than 3 %: the
largest change is -1.03 % (`matrix_int8_feed_cache`), every matrix register and shared-fed roof is within 0.1 %
(recomputed from the September raw rows, recovered from the device host into `cited/sept-fleet-fast-20260926/`:
the tool's report regenerated from them equals the committed September summary exactly).
The roofs of 2026-10-04 quoted by the tuning campaign (173.3 / 179.9 / 359.9; 168.4 / 166.6 / 323.3) are
reproduced. The roofline shaders run at subgroup size 32 (SIMD32), the kernels at 16: no roof at subgroup size 16
exists in the tool, and every percentage below carries that difference.

## Part B: matched efficiency (`efficiency.csv`, prefill M = 2048, texture3d = the model path)

Linear kernel time: median of three processes, each the median of 5 warm timed runs (process spread at most
3.9 %). Attention: median of three processes, each the tool's mean of 5 warm timed runs of the whole call.
Accumulator types are read from each kernel's SPIR-V (`isa/spirv/types.csv`): **4w accumulates in fp16**
(fp16 x fp16 -> fp16, 8x16x16), 8da4w in int32 (int8 x int8 -> int32, 8x16x32), the fused attention in fp32.

| model | shape (N x K) | scheme | kernel tile | ms | rate | % register | % fed (shared) | % fed at kernel reuse |
|---|---|---|---|---:|---:|---:|---:|---:|
| 1B | wk_wv (512 x 2048) | 4w | `t128x128k32g84s16m8flw` | 0.080 | 53.53 TFLOP/s | 30.9 | 31.8 | no matching roof |
| 1B | wq_wo (2048 x 2048) | 4w | `t128x128k16g82s16m8flib` | 0.247 | 69.58 TFLOP/s | 40.1 | 41.3 | no matching roof |
| 1B | w2 (2048 x 8192) | 4w | `t128x128k16g82s16m8flib` | 0.991 | 69.38 TFLOP/s | 40.0 | 41.2 | no matching roof |
| 1B | w1_w3 (8192 x 2048) | 4w | `t128x128k16g82s16m8flib` | 0.970 | 70.86 TFLOP/s | 40.9 | 42.1 | no matching roof |
| 3B | wk_wv (1024 x 3072) | 4w | `t128x128k16g82s16m8flib` | 0.188 | 68.66 TFLOP/s | 39.6 | 40.8 | no matching roof |
| 3B | wq_wo (3072 x 3072) | 4w | `t128x128k16g82s16m8flib` | 0.554 | 69.8 TFLOP/s | 40.3 | 41.4 | no matching roof |
| 3B | w2 (3072 x 8192) | 4w | `t128x128k16g82s16m8flib` | 1.476 | 69.83 TFLOP/s | 40.3 | 41.5 | no matching roof |
| 3B | w1_w3 (8192 x 3072) | 4w | `t128x128k16g82s16m8flib` | 1.458 | 70.71 TFLOP/s | 40.8 | 42.0 | no matching roof |
| 8B | wk_wv (1024 x 4096) | 4w | `t128x128k16g82s16m8flib` | 0.247 | 69.58 TFLOP/s | 40.1 | 41.3 | no matching roof |
| 8B | wq_wo (4096 x 4096) | 4w | `t128x128k16g82s16m8flib` | 0.969 | 70.91 TFLOP/s | 40.9 | 42.1 | no matching roof |
| 8B | w2 (4096 x 14336) | 4w | `t128x128k16g82s16m8flib` | 3.519 | 68.35 TFLOP/s | 39.4 | 40.6 | no matching roof |
| 8B | w1_w3 (14336 x 4096) | 4w | `t128x128k16g82s16m8flib` | 3.560 | 67.56 TFLOP/s | 39.0 | 40.1 | no matching roof |
| 1B | wk_wv (512 x 2048) | 8da4w | `t128x128k64g84s16m8` | 0.046 | 93.33 TOP/s | 25.9 | 28.9 | 82.0 |
| 1B | wq_wo (2048 x 2048) | 8da4w | `t128x128k64g84s16m8` | 0.150 | 114.4 TOP/s | 31.8 | 35.4 | 100.5 |
| 1B | w2 (2048 x 8192) | 8da4w | `t128x128k64g84s16m8` | 0.660 | 104.2 TOP/s | 28.9 | 32.2 | 91.5 |
| 1B | w1_w3 (8192 x 2048) | 8da4w | `t128x128k64g84s16m8` | 0.632 | 108.7 TOP/s | 30.2 | 33.6 | 95.5 |
| 3B | wk_wv (1024 x 3072) | 8da4w | `t128x128k64g84s16m8` | 0.127 | 101.4 TOP/s | 28.2 | 31.4 | 89.1 |
| 3B | wq_wo (3072 x 3072) | 8da4w | `t128x128k64g84s16m8` | 0.329 | 117.3 TOP/s | 32.6 | 36.3 | 103.1 |
| 3B | w2 (3072 x 8192) | 8da4w | `t128x128k64g84s16m8` | 0.947 | 108.9 TOP/s | 30.3 | 33.7 | 95.6 |
| 3B | w1_w3 (8192 x 3072) | 8da4w | `t128x128k64g84s16m8` | 0.880 | 117.2 TOP/s | 32.6 | 36.2 | 102.9 |
| 8B | wk_wv (1024 x 4096) | 8da4w | `t128x128k64g84s16m8` | 0.167 | 103.2 TOP/s | 28.7 | 31.9 | 90.6 |
| 8B | wq_wo (4096 x 4096) | 8da4w | `t128x128k64g84s16m8` | 0.601 | 114.3 TOP/s | 31.8 | 35.3 | 100.4 |
| 8B | w2 (4096 x 14336) | 8da4w | `t128x128k64g84s16m8` | 2.569 | 93.62 TOP/s | 26.0 | 29.0 | 82.2 |
| 8B | w1_w3 (14336 x 4096) | 8da4w | `t128x128k64g84s16m8` | 2.270 | 106 TOP/s | 29.4 | 32.8 | 93.1 |
| 8B | fused attention (d = 128) | fp16 -> fp32 | `t16x128s16m8g8oj` | 0.967 | 37.75 TFLOP/s | 21.0 | 22.7 | 69.9 |
| 3B | fused attention (d = 128) | fp16 -> fp32 | `t16x128s16m8g8oj` | 0.746 | 36.69 TFLOP/s | 20.4 | 22.0 | 67.9 |
| 1B | fused attention (d = 64) | fp16 -> fp32 | `t16x64s16m8g4roj` | 0.484 | 36.63 TFLOP/s | 20.4 | 22.0 | 67.8 |

- **4w: 39.0 to 40.9 % of the register roof on eleven shapes, 30.9 % on 1B wk/wv; geometric mean 39.3 %.** The
  working figure of 39 % is confirmed. **8da4w: 25.9 to 32.6 %, geometric mean 29.6 %** (working figure 30 %).
  Fused attention: 20.4 to 21.0 % of the fp16 -> fp32 roof, counting only the multiply-adds it executes (the
  causal half); the dense count would read twice that.
- The in-model trace of the tuning campaign (cited, `cited/s3-final-trace-gemm.csv`) gives the same kernels and
  rates within -14 to +6 % per shape (the small wk/wv shapes are slower in the model); values per row in the
  `notes` column.
- Fed roof at the kernel's own reuse. 4w loads 2560 bytes for 8 multiply-adds (12.8 flop per loaded byte; nearest
  row of the tool: 2 chains, 10.67). **For fp16 -> fp16 that row does not exist: the tool gated it out (sample too
  short, fixed cost), so the 4w column says "no matching roof".** Context only, not a matched roof: the
  fp16 -> fp32 row at the same reuse is 82.7 TFLOP/s (single run), of which 4w is 82 to 86 % (65 % for 1B wk/wv).
  8da4w loads 1536 bytes for 4 multiply-adds (21.3 ops per byte = the tool's 2-chain row exactly, 113.9 TOP/s,
  a single run and **not a confirmed roof**).
- 8da4w reads 100 to 103 % of that row on four shapes. That is a mismatch of the roof, not a kernel above the
  hardware: the roof shader loads its B tile in byte-granular 32-byte messages, 9 shared-memory messages per
  multiply-add, where the kernel needs 4.6 messages of 64 bytes (`isa/counts.csv`).

## Part C: what the driver generated (`isa/`, Mesa `INTEL_DEBUG=cs`; roofline shaders from the tool's own inspection)

Inspected: 4w on all four 8B shapes (`flib` tile) and 1B wk/wv (`flw` tile), 8da4w on all four 8B shapes, the fused
attention for 1B and 8B, and the roofline shaders behind every roof above.

1. **Matrix instructions: yes, one `dpas.8x8 (16)` per multiply-add, as the tile arithmetic says.** 4w `flib`: 8 per
   loop iteration (one K chunk of 16: 8 A fragments x 1 B fragment), 16 in the listing because the last chunk is
   a second copy. 4w `flw`: 8 per chunk of K = 32. 8da4w: 16 per loop iteration; the driver unrolled the two
   chunks of a quantization group (2 chunks x 2 K slabs x 4 fragments), the SPIR-V has 8. Fused attention: 16
   (d = 64) and 32 (d = 128) per context block and subgroup.
2. **No spills (0:0 in every kernel), SIMD16, 128 registers.** The kernels require subgroup size 16; the roofline
   shaders compile to SIMD32 with the same 16-wide `dpas`.
3. **What the roofline shader has and the kernel does not.** Its loop is the loads and the multiply-adds and
   nothing else: 53 instructions and 10 shared-memory load messages for 8 `dpas` (fp16, 8 chains), each message
   carrying 32 lanes. The 4w kernel's loop is 302 instructions for 8 `dpas`: 48 shared-memory load messages of
   16 lanes (16 of them 32-byte messages for the one B fragment), 2 staging stores, 2 image loads and 1 sampler
   fetch for the next chunk, 1 barrier, 86 scoreboard `sync.nop`. 8da4w: 553 instructions for 16 `dpas`, 73
   load messages, 17 stores, 2 barriers, 200 `sync.nop`. Per multiply-add: 6.6 instructions in the roof shader,
   37.8 in 4w, 34.6 in 8da4w.

## Part D: where the gap is (8da4w, the lower scheme; geometric mean of the twelve shapes)

| step | TOP/s | share of the register roof | loss at this step |
|---|---:|---:|---:|
| register roof (confirmed) | 359.9 | 100 % | |
| fed from shared memory, 8 multiply-adds per loaded pair (confirmed) | 323.3 | 89.8 % | 10.2 points |
| fed at the kernel's reuse, 2 per pair (single run, not confirmed) | 113.9 | 31.6 % | 58.2 points |
| kernel (93.3 to 117.3) | 106.6 | 29.6 % | 2.0 points (per shape: 5.7 below to 1.0 above the row) |

10.2 + 58.2 + 2.0 = 70.4 = 100 - 29.6. **The gap is the reuse step.** Feeding operands costs 10 % when a loaded
pair serves 8 multiply-adds and 65 % when it serves 2, and the kernel sits within 18 % below to 3 % above the
row of its own reuse. For 4w the same chain is 173.3 -> 168.4 (2.8 points) -> no matching roof -> 68.1
(39.3 %); with the fp16 -> fp32 row as context (82.7, 47.7 %) it would be 49.5 points for reuse and 8.4 for the
kernel. So the statement "the fed roof is 97 % of the register roof, the hardware is not the obstacle" holds only
at 8 multiply-adds per load; at the kernels' reuse the fed rate is a third to a half of the register roof.

What the tuning campaign measured about the last step (cited, not repeated; first campaign `STATUS.md`, "Linear
kernels: phase timing", and `proposal.md`, "Limits"): 4w wave time is MMA 37 to 40 %, barrier 22 to 23 %, fetch 22 to
26 %, shared store 13 to 15 %; 8da4w after its change is fetch 27 to 33 %, MMA 25 to 29 %. More multiply-adds
per subgroup was tried there and collapsed (0.26 to 0.52x), K = 32 chunks for 4w were 0.50x, and 2000 sampled
4w configurations found at most 3 %.

Hypotheses for a third round (none of these experiments was run):

1. **The kernels are at the ceiling of their reuse; only more multiply-adds per loaded byte moves them.**
   For: the chain above; the tool's rows scale almost linearly with reuse (int8 shared-fed 53.9 / 113.9 / 211.0 /
   323.3 TOP/s at 1 / 2 / 4 / 8). Against: the matched row is a single run for int8 and missing for
   fp16 -> fp16, is measured at subgroup size 32 with other message sizes, and 8da4w already exceeds it; the
   phase split gives the multiply-add phase only 25 to 40 % of a wave. Cheapest decision: one focused roofline
   run of the shared-fed 2- and 4-chain variants of all three types with confirmation (about 5 minutes of the
   card, tool unchanged); if a gate-passing fp16 -> fp16 row lands near 80 TFLOP/s, 4w is within 15 % of what
   its structure allows and a third round of tile or staging work is not worth starting.
2. **Shared-memory message count, not bytes, is the limiter, and SIMD16 doubles it.** For: the 4w kernel issues
   6 load messages per multiply-add of 16 lanes, the fp16 -> fp32 roof shader at 2 chains 5 of 32 lanes; at
   their measured rates both issue about 1.0e11 messages per second; a third of the 4w loop's load messages carry the one
   B fragment in 32-byte pieces. Against: the September study's counters (`docs/XE2-WMMA-LESSONS.md`) put the
   4w kernel's shared-memory read at 42 % of the 32-bit read roof on this card, the fragment layout gained 0 to
   4 %, and subgroup size 32 tiles spilled on the sibling card. Cheapest decision: compile only, no timing: dump the existing 4w
   options and tiles of the sweep with `INTEL_DEBUG=cs` and count load messages per `dpas`; if none loads the
   B fragment in 64-byte or wider messages, a kernel that stages B so that it does is the one new kernel worth
   writing, and its message count can be read before it is ever timed.
3. **Barrier and scoreboard waits bound the rest.** For: one barrier per 8 `dpas` in 4w and 22 to 23 % of the
   wave in the cited phase timing; 86 of 302 loop instructions are `sync.nop`. Against: larger K per barrier
   was slower for 4w (0.50x) and gained nothing for 8da4w on the sibling card. Cheapest decision: one Xe
   observation capture of the final 4w kernel (stall reasons split into scoreboard, barrier, dependency). It
   needs `dev.xe.observation_paranoid=0` and root, which this study may not use: an owner decision if wanted.

## Not verified

- GT clock is sampled every 2 s from sysfs, not pinned and not recorded by the tool itself.
- Timing sanity of the GPU timestamps against wall clock was not repeated on this card.
- No roof exists at subgroup size 16, for fp16 -> fp16 at the kernel's reuse, or for int8 with 64-byte loads.
- One sample of the foreign-process watch in part A saw a DRM client of the second card with zero engine time,
  from a process that had already exited when its name was read (`logs/partA-try1.samples.tsv`); no engine time
  of a foreign client was seen in any run, and the sentinel did not move.
- Correctness was not re-run here: the tuning campaign's gate on this build stands (cited).

## Decision needed from the owner

**The five timed runs behind each microbenchmark statistic do not exist as data.** `test_llama_microbench` keeps
them in memory and writes only `kernel_median_us` (linear) and `op_mean_us` (attention) per case; its log has no
per-run line and the final build has no switch to print them. They were never on disk, so they cannot be
recovered. What can be recomputed, and was by the reviewer: every number of `efficiency.csv` from the three
per-process statistics of each case. What cannot: each process's own median or mean from its five runs.

- Option 1, no cost: accept the per-process statistics as the raw level of part B (three processes per case,
  spread at most 3.9 %, in-model trace within -14 to +6 %).
- Option 2, about 10 minutes of the card and no build: repeat the two suites in 5 more processes each, so every
  case has 8 process-level values; still no single-run timings.
- Option 3, a build (forbidden to this study by rule 4, so the owner's to order): a microbenchmark that prints
  its per-run timings, from the same commit, then one repetition of part B; about 30 minutes of build and 10 of
  the card, and the binary would no longer be the one the tuning campaign timed.

Until an answer is appended to the task file nothing is measured, built or recomputed.

# Radeon 780M: roofs against the tuned linear kernels (campaign et-study-20261010)

## State

- 2026-10-09 19:50 UTC: finished. Nothing of this study is running on the device; the locks are released.
- No decision of the owner is open. The one asked (a foreign `nvtop` on the GPU, 18:35 UTC) was answered at
  19:05 UTC (the owner ended it); question and answer are kept at the end of this file.

Device: Radeon 780M, RADV, Mesa 25.2.7 (the package the September roofs and the tuning campaign ran under:
unchanged), subgroup 64, clocks not pinned (idle 800 MHz, 2800 MHz under load), balanced power profile, as found.
Tool: igpu-roofline at commit 84361ac, unmodified, runner built on the device host. Kernels: final build `head4`
of the tuning campaign, `ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=780m-final`, nothing built or written
in the ExecuTorch trees.

## Part A: roofs (fast plan, 19:14 to 19:36 UTC, 0.38 h)

36 of 36 roofs confirmed (3 repeats, spread at most 3.8 %; matrix roofs at most 1.2 %); **no unconfirmed roof**;
sentinel healthy in all 34 readings; no row of another build. Matrix register roofs: fp16 -> fp32 **14.764
TFLOP/s**, int8 **14.364 TOP/s**, fp16 -> fp16 10.935 TFLOP/s; fed from shared memory 14.452 / 14.121 / 10.792
(2 % below the register roofs). They reproduce the tuning campaign's (14.766 / 14.379 on 2026-10-04) and
September's (14.772 / 14.393) within 0.2 %. Sustained (one 120 s run each, so not sustained roofs by the tool's
rule): 14.764 fp16 -> fp32, 86.73 GB/s DRAM read. Not confirmed by repeats: the by-reuse rows at CHAINS 1 and 2
(single validated sweep rows; marked `*` below and `FLAG` in the csv). This is the repeat of a first run (17:49
to 18:12 UTC) that an idle foreign `nvtop` joined at 18:03:05; the first run is kept in `superseded/` and its
matrix roofs differ by at most 0.3 %. Report: `report/` in the device folder of this results root.

## Part B: matched efficiency, prefill M = 2048 (`efficiency.csv`, 24 linear rows + 3 attention rows)

Kernel time: median of 5 repeats of the microbench's kernel median (3 warm-up + 5 timed runs each, repeat
spread at most 1.1 %), production storage texture3d, group size 128. Rate = 2 M N K / time, TFLOP/s (4w) or TOP/s
(8da4w). Every 4w kernel multiplies fp16 x fp16 into an **fp32** accumulator, every 8da4w kernel int8 x int8
into int32, 16 x 16 x 16 (read from the SPIR-V, `isa/spirv-types.csv`): the matched register roofs are
`matrix_fp16_fp32` and `matrix_int8`. Mismatch that the tool cannot close: the roofs are measured at subgroup
64, the kernels run at subgroup 32.

| model | shape (N x K) | scheme | kernel | ms | rate | % register | % fed shared | % of by-reuse row |
|---|---|---|---|---:|---:|---:|---:|---:|
| 1B | wq_wo (2048 x 2048) | 4w | `t128x128k32g24s32f32cbt` | 1.542 | 11.14 | 75.5 | 77.1 | 231.8 (`fp16_fp32_c2_lds`*) |
| 1B | wk_wv (512 x 2048) | 4w | `t128x128k32g24s32f32cbt` | 0.420 | 10.23 | 69.3 | 70.8 | 212.7 (`fp16_fp32_c2_lds`*) |
| 1B | w1_w3 (8192 x 2048) | 4w | `t256x128k32g28s32f32cbt` | 5.919 | 11.61 | 78.6 | 80.3 | 241.5 (`fp16_fp32_c2_lds`*) |
| 1B | w2 (2048 x 8192) | 4w | `t256x128k32g18s32f32cbt` | 5.907 | 11.63 | 78.8 | 80.5 | 120.9 (`fp16_fp32_c4_lds`) |
| 3B | wq_wo (3072 x 3072) | 4w | `t256x128k32g24s32f32cbt` | 3.338 | 11.58 | 78.4 | 80.1 | 120.3 (`fp16_fp32_c4_lds`) |
| 3B | wk_wv (1024 x 3072) | 4w | `t128x256k32g42s32f32cbt` | 1.204 | 10.70 | 72.5 | 74.0 | 111.2 (`fp16_fp32_c4_lds`) |
| 3B | w1_w3 (8192 x 3072) | 4w | `t256x128k32g24s32f32cbt` | 8.972 | 11.49 | 77.8 | 79.5 | 119.4 (`fp16_fp32_c4_lds`) |
| 3B | w2 (3072 x 8192) | 4w | `t256x128k32g18s32f32cbt` | 8.548 | 12.06 | 81.7 | 83.4 | 125.3 (`fp16_fp32_c4_lds`) |
| 8B | wq_wo (4096 x 4096) | 4w | `t256x128k32g18s32f32cbt` | 5.871 | 11.71 | 79.3 | 81.0 | 121.6 (`fp16_fp32_c4_lds`) |
| 8B | wk_wv (1024 x 4096) | 4w | `t256x128k32g18s32f32cbt` | 1.581 | 10.87 | 73.6 | 75.2 | 112.9 (`fp16_fp32_c4_lds`) |
| 8B | w1_w3 (14336 x 4096) | 4w | `t256x128k32g18s32f32cbt` | 20.290 | 11.85 | 80.3 | 82.0 | 123.2 (`fp16_fp32_c4_lds`) |
| 8B | w2 (4096 x 14336) | 4w | `t256x128k32g18s32f32cbt` | 20.395 | 11.79 | 79.9 | 81.6 | 122.5 (`fp16_fp32_c4_lds`) |
| 1B | wq_wo (2048 x 2048) | 8da4w | `zpg_t256x64k64g48s32afmb1` | 1.481 | 11.60 | 80.8 | 82.1 | 287.1 (`int8_c1_lds`*) |
| 1B | wk_wv (512 x 2048) | 8da4w | `zpg_bt_t128x64k32g22s32` | 0.404 | 10.64 | 74.1 | 75.4 | 132.5 (`int8_c2_lds`*) |
| 1B | w1_w3 (8192 x 2048) | 8da4w | `zpg_t256x64k64g48s32afmb1` | 5.851 | 11.75 | 81.8 | 83.2 | 290.7 (`int8_c1_lds`*) |
| 1B | w2 (2048 x 8192) | 8da4w | `zpg_bt_t128x64k32g22s32` | 6.046 | 11.37 | 79.1 | 80.5 | 141.5 (`int8_c2_lds`*) |
| 3B | wq_wo (3072 x 3072) | 8da4w | `zpg_t256x64k64g48s32afmb1` | 3.256 | 11.87 | 82.6 | 84.1 | 293.9 (`int8_c1_lds`*) |
| 3B | wk_wv (1024 x 3072) | 8da4w | `zpg_bt_t128x64k32g22s32` | 1.148 | 11.22 | 78.1 | 79.5 | 139.7 (`int8_c2_lds`*) |
| 3B | w1_w3 (8192 x 3072) | 8da4w | `zpg_t256x64k64g48s32afmb1` | 8.701 | 11.85 | 82.5 | 83.9 | 293.3 (`int8_c1_lds`*) |
| 3B | w2 (3072 x 8192) | 8da4w | `zpg_bt_t128x64k32g22s32` | 8.981 | 11.48 | 79.9 | 81.3 | 142.9 (`int8_c2_lds`*) |
| 8B | wq_wo (4096 x 4096) | 8da4w | `zpg_t256x64k64g48s32afmb1` | 5.892 | 11.66 | 81.2 | 82.6 | 288.7 (`int8_c1_lds`*) |
| 8B | wk_wv (1024 x 4096) | 8da4w | `zpg_bt_t128x64k32g22s32` | 1.525 | 11.26 | 78.4 | 79.8 | 140.2 (`int8_c2_lds`*) |
| 8B | w1_w3 (14336 x 4096) | 8da4w | `zpg_t256x64k64g48s32afmb1` | 20.507 | 11.73 | 81.7 | 83.1 | 290.3 (`int8_c1_lds`*) |
| 8B | w2 (4096 x 14336) | 8da4w | `zpg_bt_t128x64k32g22s32` | 21.045 | 11.43 | 79.6 | 80.9 | 142.3 (`int8_c2_lds`*) |
| 1B | attention (32 heads x 64) | fp16 | `fused3sb_d64_t32x32g11s32rko` | 2.267 | 7.70 | 52.1 | 53.3 | 97.0 (`fp16_fp32_c2_gmem`*) |
| 3B | attention (24 heads x 128) | fp16 | `fused3sb_d128_t16x64g11s32rko` | 3.212 | 8.27 | 56.0 | 57.2 | 104.3 (`fp16_fp32_c2_gmem`*) |
| 8B | attention (32 heads x 128) | fp16 | `fused3sb_d128_t16x64g11s32rko` | 4.055 | 8.74 | 59.2 | 60.5 | 110.1 (`fp16_fp32_c2_gmem`*) |

Time-weighted over a model's linear dispatches, share of the register roof (1B / 3B / 8B): **4w 77.9 / 78.5 /
79.7 %**, **8da4w 80.6 / 81.6 / 80.9 %**; from the tuning campaign's in-model trace (session `s9-final-dev15`,
cited, against today's roofs) 4w 76.3 / 77.0 / 75.3 %, 8da4w 80.8 / 80.4 / 78.0 % (`summary-tables.txt`). The
working figures were 72 % and 78 %: 8da4w is confirmed; 4w is 4 to 6 points better than 72 %, which predates
the per-shape 4w kernels. The attention rows are operator time (copy pass + fused kernel) over the executed
multiply-adds, so they are lower than the campaign's kernel-only 71 %, which also counted a pass this kernel no
longer runs.

The last column is not a ceiling: every linear kernel is above its by-reuse row (111 to 294 %; attention 97
to 110 % of its cache-fed row). The row is chosen by
operations per loaded operand byte as the task defines it (kernel: 21.3 to 42.7, from the SPIR-V: multiply-adds
over distinct loaded tiles), but the roofline shader loads its B tile with 16 narrow shared-memory loads and
waits for them, while the kernels load every tile with 128-bit loads (`isa/README.md`). Counted in load
instructions per multiply-add the kernels (0.75 to 1.56) are beyond the CHAINS 8 row (2.25), where feeding costs
2 %.

## Part C: what the driver generated (`isa/`, ACO disassembly of real dispatches, 1B shapes)

1. Matrix instructions: yes. 4w compiles to `v_wmma_f32_16x16x16_f16` only, 8da4w to `v_wmma_i32_16x16x16_iu8`
   only; per K chunk and subgroup 32 (`t256x128k32g18`), 16 (`t128x128k32g24`, `t256x128k32g28`), 8
   (`zpg_t256x64k64g48`, 16 in a loop body of two chunks) and 16 (`zpg_bt_t128x64k32g22`): each equals the tile
   arithmetic. The roofline shaders behind the matched roofs use the same two instructions, 8 per iteration.
2. Spills: none (0 spilled VGPR / SGPR, 0 scratch, no lane moves). The kernels use 128 to 240 VGPRs (4w), 64 or
   192 (8da4w): the driver reports 4 to 8 (4w) and 5 or 16 (8da4w) waves per SIMD, against 12 to 18 for the
   roofline shaders (56 to 80 VGPRs).
3. Width: the kernels are wave32, the roofline shaders wave64. What the roofline shader gets that the kernel does
   not: operands that stay in registers or come pre-staged, no store and no barrier in the loop, two to four times
   the waves per SIMD. The kernel has one barrier, 6 to 13 shared-memory stores and 3 to 10 image or buffer
   loads per chunk around its multiply-adds.

## Part D: where the gap is (4w, the lower scheme; 8B wq_wo, `t256x128k32g18`, as the example)

| step | rate, TFLOP/s | change |
|---|---:|---:|
| register roof `matrix_fp16_fp32` | 14.764 | |
| fed from shared memory, CHAINS 8 | 14.452 | -2.1 % |
| by-reuse row nearest the kernel (25.6 ops per loaded byte -> CHAINS 4, 3 repeats) | 9.623 | -33.4 % |
| kernel | 11.705 | +21.6 % (79.3 % of the register roof) |

The chain multiplies out (0.979 x 0.666 x 1.216 = 0.793) but its third step is not a loss the kernel pays:
part B shows why. Read by load instructions, feeding costs about 2 points and the other 19 (16 to 29 by shape
for 4w, 16 to 24 for 8da4w) lie outside any roofline row. The tuning campaign's phase timing puts them in staging and
waiting: of one wave's cycles 51 to 53 % are multiply-adds, 22 to 24 % shared-memory stores, 14 to 16 % barrier,
4 to 7 % fetch (its `proposal.md`, "Where the gain comes from"); on the RX 7600 the same 780M tiles spend 32 to
57 % of a wave at the barrier and 27 to 38 % in multiply-adds ("waves wait for staged data", branch
`topic/rx7600-prefill-refine` at c0be2c6c2, `STATUS.md`). A ceiling of "78 %" is not written in that record;
what it has is this phase timing and that no screened 4w kernel is 3 % faster on 6 of 12 shapes. This device
agrees: its kernels sit at 78 to 80 % and no sweep variant moved 4w by more than 2.5 %.

Hypotheses for a third round (none tested here):

1. **The roof is too generous for this kernel form** (wave32, 16 fp32 accumulators a wave). For: roofs exist
   only at subgroup 64 with 8 accumulators; kernel variants at subgroup 64 were 14 % slower, so the two widths do
   differ. Against: same instruction, and fp16 -> fp32 at CHAINS 8 already holds 8 accumulators with no loss.
   Cheapest test: one focused roofline run of the matrix family at required subgroup size 32 (minutes, no kernel
   change). If it reads near 12.5, the kernels are at 93 % and a third round has nothing to win here.
2. **Staging latency is exposed at the barrier** (staging is single-buffered: a wave cannot multiply while the
   next chunk is fetched, unpacked and stored). For: the phase timing above; 1 barrier and 31 wait instructions
   per K = 32 chunk in the ISA; feeding itself costs 2 %. Against: K = 64 chunks and double-buffered staging did
   not win in the campaign's sweeps (4w K 64: 14 % behind; attention `fused2`: no gain). Cheapest test: the
   existing profiling twin with staging and barrier removed (timing only, wrong results): the multiply-add-only
   rate of this exact structure. Near 14.4: the gap is staging; near 12: it is hypothesis 1 or 3.
3. **Activation fetch runs at the texture-fetch rate.** For: the logical activation traffic of the 4w kernels is
   80 to 94 GB/s on 11 of 12 shapes, 97 to 115 % of the confirmed cache-resident texture3d roof (82.3 GB/s) and
   at the DRAM read roof (86.7). Against: the one 256-column tile (3B wk_wv) has half the traffic and is not
   faster; the campaign measured the 256-column tile at +1 to +4 % only; fetch is 4 to 7 % of a wave's cycles;
   logical bytes are not physical traffic. Cheapest test: the 256-column variant of the same tile on the eleven
   shapes (existing sweep variants, kernel timing only).

On this device a third round on the linear kernels looks worth starting only if test 1 leaves the roof where it
is and test 2 shows more than a few points behind staging; that is the owner's decision.

## Not verified, and limits

- GPU clock during the microbench: not sampled (no monitor was to be started). Read once after each invocation:
  2800 MHz in 9 of 9; the campaign's floor is 2700 MHz. Thermal state not recorded for the microbench.
- Correctness of the timed linear cases: not re-run (the campaign's gate stands). The fused kernel passed
  tier `full` here (4 of 4, 0 mismatches), run to read its name from a dispatch.
- The microbench marks every linear case `unexpected_coopmat` (rc 1): development kernels are not in its expected
  table; the campaign's own runs have the same status.
- GPU timestamps against wall clock: not checked in this study. Radeon GPU Analyzer cross-check: not run.
- ExecuTorch trees: no file built, written or changed. I ran `git status` in the campaign's checkout three
  times; that command may refresh the index file under `.git` (the directory's time stamp moved), nothing else.
- Raw rows of part A, the driver dumps and the kernels' SPIR-V are in this results root on the share; git
  tracks the reports, tables, tools and this file.

## Decision asked 2026-10-09 18:35 UTC, answered 19:05 UTC (kept as written)

An interactive `nvtop` (not started by this study) was attached to the 780M from 18:03:05 UTC. Options given:
(a) the owner closes it, then parts B and C and the repeat of part A run (35 minutes of device time); (b)
measure with it attached, every row flagged; (c) close the study without B and C. Answer: (a); the owner ended
it at 19:05 UTC. The timing run that met it (18:17 UTC, stopped after 1 minute) is used for nothing.

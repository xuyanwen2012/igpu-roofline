# Arc B580: roofs against the tuned kernels (campaign `et-study-20261010`)

## State

2026-10-09 18:32 UTC: finished, nothing is running, branch pushed. Parts A to D done; no decision is needed from the owner.

Intel Arc B580 (BMG G21), ANV Mesa 26.2.3, clocks as found (GT 1200 to 2850 MHz, not pinned, `power_saving`
profile), one sitting 17:49 to 18:25 UTC. Roofline tool unmodified (code `f87e89a`, runner `784e6acafa0a`);
ExecuTorch final build `topic7` (`e1e450530`), profile `b580-fused1`, read-only. Desktop share of the card
during every job 0.00 to 0.02 %; no foreign GPU job; nothing rejected. Record: `EXPERIMENT.md`.

## A. Roofs (`report/REPORT.md`)

`fast` plan, 24 minutes. **All 36 roofs confirmed** (3 repeats each, largest spread 1.5 %), sentinel `ok` at all
34 checkpoints. No unconfirmed roof. Sustained: one 120 s batch on three roofs, equal to the short-run values.
Two limits of what the tool measured: every matrix roof is at subgroup 32 (SIMD32) while the kernels require
subgroup 16; and the per-reuse rows of the report at CHAINS 1 and 2 are single sweep runs, so the rows used
below were repeated with the same build (`../b580-reuse-*`, 3 repeats): int8 shared-fed CHAINS 2 72.81 TOP/s
(spread 0.4 %), fp16 -> fp32 CHAINS 2 53.51 TFLOP/s. The fp16 -> fp16 shared-fed rows at CHAINS 2 and 4 fail the
tool's quality gates both times and are not used.

| roof | fp16 -> fp16 (4w) | fp16 -> fp32 (attention) | int8 -> int32 (8da4w) |
|---|---:|---:|---:|
| register | 111.72 TFLOP/s | 115.68 | 231.37 TOP/s |
| fed from shared memory (CHAINS 8) | 109.76 | 106.34 | 206.36 |
| fed from shared memory at the kernel's reuse | no matching roof | no matching roof | 72.81 (CHAINS 2) |

## B. Matched efficiency (`efficiency.csv`; M = 2048, texture3d, warm, median of 3 processes x 5 iterations)

Dispatched kernels (from the runs): 4w `sarc_linear_q4gsw_coopmat_t128x128k16g44s16m8fli`, fp16 accumulator;
8da4w `sarc_dev_linear_dq8ca_coopmat_zpg_xe2bt_t128x128k64g84s16m8`, int32 accumulator (types read from the
SPIR-V, `isa/spirv-types.csv`). Kernel reuse: 4w 16.0, 8da4w 21.33 operations per loaded byte.

| model | shape | N x K | 4w ms | TFLOP/s | % reg | % fed | 8da4w ms | TOP/s | % reg | % fed | % fed at reuse |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1B | wq_wo | 2048 x 2048 | 0.389 | 44.12 | 39.5 | 40.2 | 0.239 | 71.85 | 31.1 | 34.8 | 98.7 |
| 1B | wk_wv | 512 x 2048 | 0.127 | 33.84 | 30.3 | 30.8 | 0.079 | 54.74 | 23.7 | 26.5 | 75.2 |
| 1B | w1_w3 | 8192 x 2048 | 1.455 | 47.23 | 42.3 | 43.0 | 0.927 | 74.11 | 32.0 | 35.9 | 101.8 |
| 1B | w2 | 2048 x 8192 | 1.577 | 43.58 | 39.0 | 39.7 | 1.075 | 63.90 | 27.6 | 31.0 | 87.8 |
| 3B | wq_wo | 3072 x 3072 | 0.855 | 45.19 | 40.5 | 41.2 | 0.530 | 72.86 | 31.5 | 35.3 | 100.1 |
| 3B | wk_wv | 1024 x 3072 | 0.315 | 40.85 | 36.6 | 37.2 | 0.203 | 63.44 | 27.4 | 30.7 | 87.1 |
| 3B | w1_w3 | 8192 x 3072 | 2.275 | 45.32 | 40.6 | 41.3 | 1.442 | 71.50 | 30.9 | 34.6 | 98.2 |
| 3B | w2 | 3072 x 8192 | 2.356 | 43.76 | 39.2 | 39.9 | 1.570 | 65.65 | 28.4 | 31.8 | 90.2 |
| 8B | wq_wo | 4096 x 4096 | 1.474 | 46.63 | 41.7 | 42.5 | 0.912 | 75.32 | 32.6 | 36.5 | 103.4 |
| 8B | wk_wv | 1024 x 4096 | 0.420 | 40.91 | 36.6 | 37.3 | 0.283 | 60.73 | 26.2 | 29.4 | 83.4 |
| 8B | w1_w3 | 14336 x 4096 | 5.428 | 44.31 | 39.7 | 40.4 | 3.544 | 67.87 | 29.3 | 32.9 | 93.2 |
| 8B | w2 | 4096 x 14336 | 5.593 | 43.00 | 38.5 | 39.2 | 4.044 | 59.47 | 25.7 | 28.8 | 81.7 |

- Weighted over a layer's seven linear calls (1B / 3B / 8B): **4w 40.4 / 39.9 / 39.5 %** of the register roof,
  **8da4w 30.2 / 30.1 / 28.6 %**. The working figures (39 % and 30 %) are confirmed. The campaign's in-model
  trace gives the same within 2.5 points per shape (in the CSV notes).
- 4w at its reuse: no matching roof. Context only, other accumulator type: fp16 -> fp32 shared-fed is 53.5 at
  10.7 and 101.9 TFLOP/s at 21.3 operations per loaded byte; the kernel, at 16.0, runs 33.8 to 47.2.
- 8da4w reads 75 to 103 % of the shared-fed roof at its own reuse. Four shapes above 100 % mean that this row is
  not a ceiling for the kernel, and part C shows why (access width).
- Fused attention (`sarc_dev_b580_sdpa_fused_d64_t16x64s16m8g4roj` / `d128_t16x128s16m8g8oj`, fp32 accumulator;
  the name is from the profile's definition, the run does not print it): 0.726 / 1.133 / 1.463 ms per layer,
  24.4 / 24.2 / 25.0 TFLOP/s over the blocks it executes = **21.1 / 20.9 / 21.6 %** of the fp16 -> fp32 register
  roof; no matching fed roof (operands from storage buffers and shared memory).

## C. What the driver generated (`isa/counts.csv`, listings in `isa/loops/`, dumps in `isa/raw/`)

Kernels: `INTEL_DEBUG=cs` with `MESA_SHADER_CACHE_DISABLE=true` on the 1B shapes (one compiled shader serves
all four shapes of a scheme). Roofline shaders: the driver's listing through pipeline executable properties.
One `dpas` (repeat count 8) is one 8-row multiply-add.

| | SIMD | spills : fills | dpas per loop | tile arithmetic | shared-memory loads per loop | other sends per loop | instructions per dpas (with sync) |
|---|---|---|---:|---|---|---|---:|
| 4w kernel (K step 16) | 16 | 0 : 0 | 8 | 4 x 2 = 8 | 48: 32 x 16-bit (B), 16 x 32-bit (A) | 2 shared stores, 1 sampler, 2 image loads, 1 global load, 1 barrier | 39 |
| roofline fp16 register (CHAINS 8) | 32 | 0 : 0 | 8 | 8 | 0 | 0 | 1.8 |
| roofline fp16 shared-fed (CHAINS 8) | 32 | 0 : 0 | 8 | 8 | 10: 8 x 16-bit (B), 2 x 32-bit (A) | 0 | 6.6 |
| 8da4w kernel (group, K = 128) | 16 | 0 : 0 | 16 | 4 x 1 x 4 = 16 | 73: 65 x 32-bit, 8 x (4 x 32-bit) | 17 shared stores, 2 sampler, 3 global loads, 2 barriers | 34 |
| roofline int8 register (CHAINS 8) | 32 | 0 : 0 | 8 | 8 | 0 | 0 | 1.6 |
| roofline int8 shared-fed (CHAINS 2) | 32 | 0 : 0 | 2 | 2 | 18: 16 x 8-bit (B), 2 x 32-bit (A) | 0 | 37 |

1. **Matrix instructions: yes.** Both kernels and the fused attention kernel compile to `dpas`, and the count per
   loop iteration equals the tile arithmetic exactly (8, 16; attention 16 and 32 per block).
2. **Spills: none.** 0 : 0 in all three kernels and in every roofline matrix shader; 128 registers.
3. **Width: the kernels are SIMD16, every roofline matrix shader is SIMD32.** That is what the roofline shader
   gets and the kernel does not: at SIMD32 a tile needs half the shared-memory messages (a 16 x 16 fp16 B tile is
   8 gathers there, 16 in the kernel). The 4w kernel loads B as 16-bit gathers, like the roofline shader. The
   8da4w kernel does the opposite of the roofline shader: it loads B as wide 32-bit messages (2 per tile) where
   the roofline shader uses 16 byte gathers, which is why it reaches and passes that fed row.
   The staging around the products (stores, sampler, image, barrier, sync) is 34 to 39 instructions per `dpas`
   in the kernels against 1.6 to 1.8 in the register roof.

## D. Where the gap is: 8da4w (the lower scheme), 8B weighted

| step | rate, TOP/s | loss in this step | share of register roof left |
|---|---:|---:|---:|
| register roof | 231.37 | | 100 % |
| fed from shared memory (CHAINS 8) | 206.36 | 10.8 % | 89.2 % |
| fed from shared memory at the kernel's reuse (CHAINS 2) | 72.81 | 64.7 % | 31.5 % |
| kernel, 8B weighted (3B 69.64, 1B 69.88) | 66.07 | 9.3 % (3B 4.3 %, 1B 4.0 %) | 28.6 % |

0.892 x 0.353 x 0.907 = 0.286. **Two thirds of the distance is reuse**: the kernel issues 4 multiply-adds per
5 loaded fragments because each subgroup keeps an int32 and an fp32 accumulator set. Against a feed at that
reuse the kernel loses 4 to 9 % (weighted), so better staging of the same structure cannot gain more than that
by this measure, with the caveat of part C that the row is byte-fed and SIMD32. Phase timing from the tuning
campaign exists for the previous tile only (`sarc-1.5-b580-prefill-refine/STATUS.md`, "Linear kernels on this
card": fetch 34 to 39 %, MMA 20 to 23 %, barrier 18 to 20 %, shared store 14 to 16 %); the final tile was chosen
by a screen (1.31x) and has no phase split. That campaign also records that nothing larger of this family fits
the 49152-byte shared memory, and the September lessons record 134 to 227 spills with 8 multiply-adds per
subgroup.

Hypotheses for a third round (none tested here):

1. **More multiply-adds per loaded fragment.** For: the fed roof scales with reuse (34 / 73 / 136 / 206 TOP/s at
   CHAINS 1 / 2 / 4 / 8) and the kernel sits on the CHAINS 2 row. Against: 8 multiply-adds per subgroup spilled
   in September; both accumulator sets already take 64 of 128 registers. Cheapest experiment: compile only
   (`INTEL_DEBUG=cs`, no timing) a 32 x 32 subgroup-tile variant whose fp32 totals leave the registers between
   groups; 0 spills decides whether a timed screen is worth running.
2. **The fed row is not the ceiling at this reuse.** For: four shapes exceed it; the roofline shader loads B by
   bytes at SIMD32, the kernel by 32-bit words at SIMD16. Against: none measured; the size of the effect is
   unknown. Cheapest experiment: one focused roofline run of a shared-fed int8 variant with a 32-bit shared
   array and required subgroup 16 (a new tool variant, about one minute of device time).
3. **Small and long shapes are limited outside the matrix loop.** For: with the same kernel `wk_wv` reads 75 to
   87 % and `w2` 82 to 90 % of the fed row against 93 to 103 % for the others; `wk_wv` has the fewest workgroups
   (64 to 128), `w2` the longest K. Against: these shapes are a minority of the layer time (about a third).
   Cheapest experiment: read the campaign's existing per-shape screen rows (`screen2-8da4w-rows.csv`) for the
   tiles with 64-row or 64-column workgroups on `wk_wv`; no new run.

For 4w (40 %) the same chain cannot be closed: its roof at the kernel's reuse does not exist in this tool run.
The generated code gives the lead: 32 of its 48 shared-memory loads per step are 16-bit gathers for B.

Not verified: memory clocks; hardware counters (none captured); correctness (not run here; the campaign's gate
on this build passed); the subgroup-16 value of any roof.

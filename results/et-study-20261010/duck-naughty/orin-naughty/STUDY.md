# Jetson Orin Nano: roofs against the tuned kernels (campaign et-study-20261010)

## State

- 2026-10-09 19:10 UTC. **Nothing is running** on the device or on the workstation. Parts A to D are done; one
  decision is left to the owner (end of this page). Review record: `EXPERIMENT.md`.

## Result in five lines

1. The device, as found (power mode 15 W, GPU governed 306 to 612 MHz, 612 MHz under load, nvgpu 595.78), reproduces
   the **lower** of the two older roof sets: matrix fp16 9.68 TFLOP/s, fp16 -> fp32 9.73 TFLOP/s, int8 19.51 TOP/s.
2. The higher set (16.0 / 32.3) was measured on 2026-09-26 with the GPU clock pinned at 1020 MHz, before a reboot
   after which the GPU cap is 612 MHz. Every compute roof of the two sets differs by 1.65 to 1.66, the clock ratio
   is 1.667. It is a clock state, not a tool or plan difference.
3. Working figures confirmed: 4w linear 60.0 to 65.6 % of the matching register roof (geomean 63.2 %), 8da4w
   linear 26.0 to 28.5 % (geomean 27.3 %), fused attention 15.3 to 19.4 %.
4. For 8da4w the register roof is the wrong yardstick: fed from shared memory at the kernel's own reuse the matrix
   unit gives 9.14 TOP/s, not 19.5; the kernel is at 55 to 61 % of that.
5. Not ISA-verified (this driver returns pipeline statistics only). The kernels use the matrix unit (rates 2.4 to
   3.6 times the scalar roofs); the 8da4w kernel needs 209 registers per thread against 128 for 4w.

## Part A: fresh roofs

igpu-roofline `fast` plan, tool commit `84361ac` unmodified (runner cross-built for aarch64 from the same commit,
SHA-256 `bdc8d65c...`; shader manifest identical to the September one), 2026-10-09 18:14 to 18:53 UTC, 39 min.
Validation pre and post, 34 sentinel probes, none degraded. The tool's clock reader does not know the Tegra
nodes (report says "clock state unavailable"); a side log sampled the devfreq node every second: 612 MHz in
1787 of 1797 samples under load, 53 to 62 C, power mode unchanged before and after.

| roof | confirmed median | repeat range | repeats | 120 s sustained (1 batch) | unit |
|---|---:|---:|---:|---:|---|
| matrix_fp16 (matrix_fp16_16x16x16_c8) | 9.684 | 9.683 to 9.689 | 3 | - | TFLOP/s |
| matrix_fp16_fp32 (matrix_fp16_fp32_16x16x16_c8) | 9.731 | 9.729 to 9.733 | 3 | 9.729 | TFLOP/s |
| matrix_int8 (matrix_int8_16x16x32_c4) | 19.512 | 19.510 to 19.514 | 3 | - | TOP/s |
| matrix_fp16_feed_shared (matrix_fp16_16x16x16_c8_lds) | 9.517 | 9.516 to 9.517 | 3 | - | TFLOP/s |
| matrix_fp16_fp32_feed_shared (matrix_fp16_fp32_16x16x16_c8_lds) | 8.829 | 8.827 to 8.905 | 3 | - | TFLOP/s |
| matrix_int8_feed_shared (matrix_int8_16x16x32_c8_lds) | 17.411 | 17.402 to 17.411 | 3 | - | TOP/s |
| matrix_fp16_feed_cache (matrix_fp16_16x16x16_c8_gmem) | 7.024 | 7.018 to 7.060 | 3 | - | TFLOP/s |
| matrix_fp16_fp32_feed_cache (matrix_fp16_fp32_16x16x16_c4_gmem) | 3.893 **(not confirmed)** | 3.888 to 3.899 | 2 | - | TFLOP/s |
| matrix_int8_feed_cache (matrix_int8_16x16x32_c8_gmem) | 8.246 | 8.194 to 8.313 | 3 | - | TOP/s |
| alu_fp16 (alu_fp16_v2_c16) | 1.766 | 1.765 to 1.766 | 3 | 1.766 | TFLOP/s |
| alu_fp32 (alu_fp32_v1_c8) | 1.201 | 1.200 to 1.202 | 3 | - | TFLOP/s |
| dot_int8 (dot8_c8) | 2.090 | 2.090 to 2.091 | 3 | - | TOP/s |
| global_read (mem_read_v4) | 62.260 | 62.236 to 62.270 | 3 | 62.231 | GB/s |
| global_write (mem_write_v4) | 58.086 | 58.043 to 58.152 | 3 | - | GB/s |
| global_copy (mem_copy_v4) | 64.046 | 63.972 to 64.095 | 3 | - | GB/s |
| cache_read_effective (mem_read_v4) | 204.059 | 204.025 to 204.107 | 3 | - | GB/s |
| shared_fp16_read (sharedbw_fp16_v2_op0) | 566.369 | 566.284 to 566.433 | 3 | - | GB/s |
| shared_fp16_write (sharedbw_fp16_v4_op2) | 335.146 | 334.881 to 335.162 | 3 | - | GB/s |

Not confirmed: `matrix_fp16_fp32_feed_cache` (2 quality repeats, `repeat_unstable`); not used below. Sustained
values are one 120 s batch each, so they are checks, not confirmed sustained roofs. Fed-matrix rows at lower
reuse are single sweep rows in the `fast` plan; the three this study uses were confirmed by focused runs of the
same tool and runner (`reuse-confirm/`, 3 repeats each, spread below 2 %): int8 from shared at 32 ops per loaded
byte 9.138 TOP/s, fp16 -> fp32 from shared at 16 ops/B 8.227 TFLOP/s, fp16 -> fp32 from cache at 32 and 16 ops/B
3.987 and 2.223 TFLOP/s. The fp16 -> fp16 row at 32 ops/B fails the tool's sample-length gate (3.8 ms sample),
so no quality-passing fp16 row exists below 64 ops/B.

### The two older roof sets

| | higher set | lower set | this run |
|---|---|---|---|
| when (UTC), plan | 2026-09-26 05:09, `quick` (fleet quick campaign) | 2026-09-27 05:18, `fast` (first Jetson study); 2026-10-09 13:59, `fast` (tuning campaign) | 2026-10-09 18:14, `fast` |
| runner | fleet tree `3bd916f6`, built on the device | Jetson-study build / the same fleet tree | commit `84361ac`, cross-built |
| GPU clock | min = max = 1020 MHz: the campaign controller wrote `min_freq` = `max_freq` and locked the EMC rate (its `clock-profile.json`, `clock-before.txt`) | governed 306 to 612 MHz, nothing pinned | governed 306 to 612 MHz, nothing pinned |
| caps read on that day | GPU max 1020 MHz, CPU max 1728 MHz, EMC max 3199 MHz, i.e. the `MAXN_SUPER` row of the power-mode table, although `nvpmodel -q` printed `15W` | GPU max 612 MHz (the `15W` row) | GPU max 612 MHz, CPU max 1498 MHz, EMC max 2133 MHz (the `15W` row) |
| matrix fp16 / fp16 -> fp32 / int8 | 16.03 / 16.17 / 32.33 | 9.70 / 9.74 / 19.52 | 9.68 / 9.73 / 19.51 |
| fp16 FMA, int8 dot | 2.92, 3.47 | 1.77, 2.09 | 1.77, 2.09 |

The device was rebooted between the two (2026-09-26 21:45 local time); since that boot the cap is the 15 W row's.
Why the caps were those of `MAXN_SUPER` under a `15W` label before the reboot is not recorded anywhere I could
read. `summary.json` of both older sets has an empty `clock_state`, which is why the reports themselves do not
show the difference. All tuning-campaign numbers (tok/s, kernel rates) belong to the lower state.

## Part B: matched efficiency (final configuration `orin-fused1`, build `topic4`, M = 2048)

Kernel time: `test_llama_microbench --linear --regime=prefill` on the production storage (texture3d), median of
5 fresh processes (each 3 warm-up + 5 timed dispatches), run-to-run spread at most 0.72 % (attention 0.82 %). Rate = 2 M N K / time.
Types and matrix shapes are read from the kernels' SPIR-V. Roof columns: the confirmed register roof of the same
input and accumulator type and matrix shape (16 x 16 x 16, int8 16 x 16 x 32, subgroup 32), the confirmed
shared-fed roof (best reuse), and the fed row nearest the kernel's operations per loaded byte. Every rate
carries the campaign's accepted limitation: the build's shaders were compiled by the cross image's `glslc`.

| model | shape | scheme | kernel (short) | in -> acc | N x K | ms | rate | of register roof | of shared-fed roof | of fed roof at kernel reuse |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|
| 1B | wq_wo | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 2048 x 2048 | 2.866 | 5.994 TFLOP/s | 61.9 % | 63.0 % | 63.0 % |
| 1B | wk_wv | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 512 x 2048 | 0.7356 | 5.839 TFLOP/s | 60.3 % | 61.4 % | 61.4 % |
| 1B | w1_w3 | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 8192 x 2048 | 11.36 | 6.05 TFLOP/s | 62.5 % | 63.6 % | 63.6 % |
| 1B | w2 | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 2048 x 8192 | 10.87 | 6.32 TFLOP/s | 65.3 % | 66.4 % | 66.4 % |
| 1B | wq_wo | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 2048 x 2048 | 3.388 | 5.071 TOP/s | 26.0 % | 29.1 % | 55.5 % |
| 1B | wk_wv | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 512 x 2048 | 0.8292 | 5.18 TOP/s | 26.5 % | 29.8 % | 56.7 % |
| 1B | w1_w3 | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 8192 x 2048 | 13.5 | 5.088 TOP/s | 26.1 % | 29.2 % | 55.7 % |
| 1B | w2 | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 2048 x 8192 | 12.6 | 5.456 TOP/s | 28.0 % | 31.3 % | 59.7 % |
| 3B | wq_wo | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 3072 x 3072 | 6.292 | 6.144 TFLOP/s | 63.4 % | 64.6 % | 64.6 % |
| 3B | wk_wv | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 1024 x 3072 | 2.124 | 6.066 TFLOP/s | 62.6 % | 63.7 % | 63.7 % |
| 3B | w1_w3 | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 8192 x 3072 | 16.66 | 6.186 TFLOP/s | 63.9 % | 65.0 % | 65.0 % |
| 3B | w2 | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 3072 x 8192 | 16.22 | 6.355 TFLOP/s | 65.6 % | 66.8 % | 66.8 % |
| 3B | wq_wo | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 3072 x 3072 | 7.228 | 5.348 TOP/s | 27.4 % | 30.7 % | 58.5 % |
| 3B | wk_wv | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 1024 x 3072 | 2.411 | 5.344 TOP/s | 27.4 % | 30.7 % | 58.5 % |
| 3B | w1_w3 | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 8192 x 3072 | 19.26 | 5.353 TOP/s | 27.4 % | 30.7 % | 58.6 % |
| 3B | w2 | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 3072 x 8192 | 18.87 | 5.463 TOP/s | 28.0 % | 31.4 % | 59.8 % |
| 8B | wq_wo | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 4096 x 4096 | 11 | 6.249 TFLOP/s | 64.5 % | 65.7 % | 65.7 % |
| 8B | wk_wv | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 1024 x 4096 | 2.797 | 6.142 TFLOP/s | 63.4 % | 64.5 % | 64.5 % |
| 8B | w1_w3 | 4w | `orin_t256x128k16g42s32bt` | fp16 -> fp16 | 14336 x 4096 | 38.36 | 6.27 TFLOP/s | 64.7 % | 65.9 % | 65.9 % |
| 8B | w2 | 4w | `bx_t128x128k32g42s32f32c` | fp16 -> fp32 | 4096 x 14336 | 41.17 | 5.841 TFLOP/s | 60.0 % | 66.2 % | 71.0 % |
| 8B | wq_wo | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 4096 x 4096 | 12.74 | 5.395 TOP/s | 27.6 % | 31.0 % | 59.0 % |
| 8B | wk_wv | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 1024 x 4096 | 3.195 | 5.378 TOP/s | 27.6 % | 30.9 % | 58.9 % |
| 8B | w1_w3 | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 14336 x 4096 | 44.53 | 5.401 TOP/s | 27.7 % | 31.0 % | 59.1 % |
| 8B | w2 | 8da4w | `orin_bf_t128x128k64g24s32mk32ra` | int8 -> int32 | 4096 x 14336 | 43.3 | 5.555 TOP/s | 28.5 % | 31.9 % | 60.8 % |
| 1B | fused_sdpa | - | `fused3sb_d64_t32x32g11s32rko` | fp16 -> fp32 | 2048 x 64 | 11.55 | 1.487 TFLOP/s | 15.3 % | 16.8 % | 37.3 % |
| 3B | fused_sdpa | - | `fused3sb_d128_t16x64g11s32rko` | fp16 -> fp32 | 2048 x 128 | 13.89 | 1.855 TFLOP/s | 19.1 % | 21.0 % | 83.5 % |
| 8B | fused_sdpa | - | `fused3sb_d128_t16x64g11s32rko` | fp16 -> fp32 | 2048 x 128 | 18.24 | 1.884 TFLOP/s | 19.4 % | 21.3 % | 84.7 % |

- Kernel reuse (operations per byte read by `coopMatLoad`, per subgroup and K step; derivations in
  `tools/kernel_reuse.json`): 4w fp16 tile 25.6, 4w fp32-accumulator tile 21.3, 8da4w 42.7, attention 32 / 16
  per buffer-loaded byte. 4w rows: the reuse column repeats the 64 ops/B row because no quality-passing fp16 row
  exists nearer (labelled in the CSV as context, not a matched ceiling). 8da4w: the confirmed row is at 32 ops/B;
  the next one, at 64 ops/B, reads 15.8 TOP/s, so the kernel's own point (42.7) lies between 9.1 and 15.8.
- Attention: K and V tiles come straight from the storage buffer, so the shared-fed roof is context and the
  reuse column is the cache-fed row. Time is the suite's whole attention operator (the suite has no per-kernel
  median); the campaign's in-model trace gives 10.76 / 13.25 / 17.55 ms per layer for the fused kernel alone.
- In-model trace rates (tuning campaign session `s5-c1`, cited per row in the CSV) agree with the microbench
  within 1 % for 23 of the 24 linear cells and within 1.5 % for all (median over the calls of one prefill); the same
  kernels were dispatched in the model.
- The microbench's small correctness gate fails on 2 cases (`linear_q4gsw_M128_K4096_N128`, 6 and 2 of 16384
  elements just outside tolerance). Those cases dispatch the stock fallback kernel, not a kernel of this table;
  the tuning campaign recorded the same failure. Timing therefore ran with `--skip-correctness`, as the
  campaign's own verify step does. Production correctness of the measured kernels was not re-run here.

## Part C: what the driver generated

Evidence: `VK_KHR_pipeline_executable_properties` statistics for the 4w kernel (K = 2048, 4096, 8192), the fp32
4w kernel (K = 14336), the 8da4w kernel (K = 2048, 4096, 14336), both attention kernels, and the tool's own
inspection of every roofline shader behind a roof used above (`isa/counts.csv`, raw files beside it). The driver
returns five statistics and **no internal representation: not ISA-verified**.

| | shader | MulAdd in SPIR-V | MulAdd per K step and subgroup | coopMatLoad in SPIR-V | registers | stack bytes | shared bytes | binary bytes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| kernel | `orin_t256x128k16g42s32bt` 4w-K2048 | 32 | 16 | 20 | 128 | 0 | 45056 | 50688 |
| kernel | `orin_t256x128k16g42s32bt` 4w-K4096 | 32 | 16 | 20 | 128 | 0 | 45056 | 50688 |
| kernel | `orin_t256x128k16g42s32bt` 4w-K8192 | 32 | 16 | 20 | 128 | 0 | 45056 | 50688 |
| kernel | `bx_t128x128k32g42s32f32c` 4w-f32-K14336 | 32 | 16 | 24 | 128 | 0 | 43008 | 30848 |
| kernel | `orin_bf_t128x128k64g24s32mk32ra` 8da4w-K14336 | 16 | 16 | 24 | 208 | 0 | 35328 | 18944 |
| kernel | `orin_bf_t128x128k64g24s32mk32ra` 8da4w-K2048 | 16 | 16 | 24 | 209 | 0 | 35328 | 18688 |
| kernel | `orin_bf_t128x128k64g24s32mk32ra` 8da4w-K4096 | 16 | 16 | 24 | 209 | 0 | 35328 | 22400 |
| kernel | `fused3sb_d128_t16x64g11s32rko` sdpa-d128-8b | 64 | 64 | 78 | 255 | 0 | 3456 | 36480 |
| kernel | `fused3sb_d64_t32x32g11s32rko` sdpa-d64-1b | 32 | 32 | 32 | 216 | 0 | 4736 | 131840 |
| roofline shader | `matrix_fp16_16x16x16_c8`  | 8 | 8 | 2 | 95 | 0 | 0 | 7424 |
| roofline shader | `matrix_fp16_16x16x16_c8_lds`  | 8 | 8 | 4 | 98 | 0 | 4096 | 10752 |
| roofline shader | `matrix_fp16_fp32_16x16x16_c2_gmem`  | 2 | 2 | 4 | 59 | 0 | 0 | 12160 |
| roofline shader | `matrix_fp16_fp32_16x16x16_c2_lds`  | 2 | 2 | 4 | 62 | 0 | 4096 | 6272 |
| roofline shader | `matrix_fp16_fp32_16x16x16_c4_gmem`  | 4 | 4 | 4 | 75 | 0 | 0 | 14720 |
| roofline shader | `matrix_fp16_fp32_16x16x16_c8`  | 8 | 8 | 2 | 130 | 0 | 0 | 8064 |
| roofline shader | `matrix_fp16_fp32_16x16x16_c8_lds`  | 8 | 8 | 4 | 128 | 0 | 4736 | 18816 |
| roofline shader | `matrix_int8_16x16x32_c2_lds`  | 2 | 2 | 4 | 73 | 0 | 4096 | 7936 |
| roofline shader | `matrix_int8_16x16x32_c4`  | 4 | 4 | 2 | 66 | 0 | 0 | 6144 |
| roofline shader | `matrix_int8_16x16x32_c8_lds`  | 8 | 8 | 4 | 128 | 0 | 4736 | 20480 |

1. **Matrix instructions?** Not visible. Rate against rate at the same matrix shape and subgroup size says yes:
   4w runs at 5.84 to 6.36 TFLOP/s, 3.3 to 3.6 times the confirmed scalar fp16 FMA roof (1.766); 8da4w runs at
   5.07 to 5.56 TOP/s, 2.4 to 2.7 times the confirmed int8 dot roof (2.090). Neither is reachable with scalar code.
2. **How many per loop iteration?** By tile arithmetic 16 per K step and subgroup in all three linear kernels
   (4w: 8 x 2 accumulators, K 16; fp32 4w: 4 x 2, two K slabs; 8da4w: 2 x 4, two K = 32 slabs). The SPIR-V holds
   exactly that: 16 for 8da4w, 2 x 16 for the 4w kernels (last K step peeled into a second copy). Whether the
   driver keeps one instruction per MulAdd cannot be checked.
3. **Spills, width.** Stack size 0 in every pipeline, so no spill is reported. Subgroup 32. Registers per thread:
   128 (4w), 128 (fp32 4w), 208 to 209 (8da4w), 216 / 255 (attention), against 66 to 130 for the roofline matrix
   shaders. "Local memory size" comes back as 2^36 (+16 for 8da4w): kept raw, not interpreted.
4. **What the roofline shader has that the kernel does not.** Operands that are already 512-byte tiles (in
   registers, or loaded by one `coopMatLoad` pair per step); one 32-thread workgroup per subgroup with at most
   130 registers; one barrier per step and no other work. The kernel stages its operands first (4-bit weight
   unpack and scaling, activation copy, one barrier per K step), keeps 16 accumulators plus staging values live
   in 256-thread workgroups, and for 8da4w converts int32 to fp32 at every quantization group (every 2 K steps).

## Part D: where the gap is (8da4w, the lowest figure)

| step | from | to | loss |
|---|---:|---:|---:|
| register roof -> fed from shared memory, best reuse (128 ops/B) | 19.51 TOP/s | 17.41 | -10.8 % |
| -> fed from shared memory at the kernel's reuse (confirmed row at 32 ops/B; kernel 42.7) | 17.41 | 9.14 | -47.5 % |
| -> kernel (geomean of the 12 shapes; range 5.07 to 5.56) | 9.14 | 5.33 | -41.6 % |
| whole chain | 19.51 | 5.33 | -72.7 % (0.892 x 0.525 x 0.584 = 0.273) |

- **The largest step is the feed, and it explains why 8da4w is not faster than 4w.** Fed from shared memory at
  low reuse, the matrix unit runs at the shared-memory read rate: 2.8 to 2.9 x 10^11 loaded elements per second
  for fp16 (564 GB/s, the shared fp16 read roof is 566) and for int8 (289 GB/s) alike. An int8 16 x 32 operand has
  twice the elements of an fp16 16 x 16 one and feeds twice the operations, so both types get the same 4.5 to 4.6
  T operations per second and per MulAdd-per-loaded-pair (4.52 fp16 -> fp32, 4.62 int8, single sweep rows), and
  both saturate near 9 at two (8.23, 9.14, confirmed). The int8 unit's doubled register roof only appears above
  four MulAdd per loaded pair (15.8 at 4, 17.4 at 8); the kernel does 16 MulAdd per 12 loaded tiles.
- **Last step (kernel against its fed roof).** The tuning campaign's phase timing of this tile (first Orin
  campaign `STATUS.md`, section "8da4w linear: phase timing and the whole-texel twin"; `proposal.md` of the fused
  port leaves the linear kernels unchanged): MMA 48 to 59 % of a wave, weight fetch 15 to 24 %, barrier 10 %,
  shared-memory store 7 %. Dividing the kernel's 5.33 TOP/s by that MMA share gives 9.0 to 11.1 TOP/s while
  multiplying, which is the fed roof at the kernel's reuse (9.1 at 32 ops/B, 15.8 at 64). The multiply phase is
  already at its fed ceiling; the last step is the staging time around it.
- 4w for comparison: 63 % of the register roof, 65 % of the shared-fed roof; its fp16 operands reach the roof
  at low reuse (measured for fp16 -> fp32: 8.2 of 8.8 at 16 ops/B), so its gap is staging time (campaign, shipped
  4w tile: MMA 45 to 49 % of a wave).

### Hypotheses for a third round (not run)

| | hypothesis | for | against | cheapest deciding experiment |
|---|---|---|---|---|
| 1 | The 8da4w kernel is bound by operand loads from shared memory; more MulAdd per loaded tile raises its ceiling from about 9 to about 16 TOP/s | fed rows above (9.1 / 15.8 / 17.4 at 2 / 4 / 8 MulAdd per pair); MMA-phase rate equals the fed roof at the kernel's reuse | 16 accumulators at 4 x 4 need more than the present 209 registers; the campaign's 512-thread tiles with the same staging were slower (1.019 against 1.158), its smaller subgroup tiles too | kernel-level screen of one existing or generated `bf` tile with 4 x 4 accumulators per subgroup (32 MulAdd per 12 or 16 loads) on the 12 shapes, 2 rounds, with its pipeline statistics: about 15 minutes of device time |
| 2 | Occupancy: at 209 registers per thread a 256-thread workgroup leaves room for one workgroup per SM, where 4w (128) fits two | register counts above; first Jetson study measured 34 to 36 % warps in flight and derived two workgroups per SM at about 32 K registers | that study also found register counts alone predicting the wrong tile; SM register capacity is assumed, not read from the device | pipeline statistics (compile only, no timing) of the `bf` family to find a tile at or below 128 registers, then one kernel screen of it; or one Nsight warps-in-flight capture of the final kernel |
| 3 | The remaining staging time (fetch 15 to 24 %, barrier 10 %, store 7 %, int32 -> fp32 at every group) can still be cut | phase shares; a second barrier per step cost 17 % in the campaign's screen, so barriers are expensive here | round 2 already cut the fetch share from 38 to 47 %; even at zero staging the kernel stops at the fed roof (hypothesis 1) | one timing-only twin with K = 128 steps on two staging slices (half the barriers per K), kernel screen on the 12 shapes |

Decision the table supports: a third linear round on this device is worth starting only for 8da4w and only on
hypothesis 1 (with 2 as its constraint). 4w sits at 63 to 66 % of every roof it can be compared with.

## Decision needed from the owner

**Measure once in the higher clock state?** The higher roof set belongs to GPU 1020 MHz (caps of power mode
`MAXN_SUPER`), a state the device is not in. If the kernels follow the roofs, prefill tok/s there would be up to
1.65 times today's (compute roofs x 1.65 to 1.66, DRAM read / write / copy x 1.5 to 1.7 between the older sets); this is an
expectation, nothing was measured. To find out:

    sudo nvpmodel -m 2      # MAXN_SUPER: GPU max 1020 MHz, EMC max 3199 MHz, CPU max 1728 MHz; may ask for a reboot
    # then the `fast` plan and the part B microbench again (about 45 minutes), optionally one timed model session
    sudo nvpmodel -m 0      # back to 15W

It answers whether the percentages above hold at the higher clock and what the deployment gains from the mode.
Options: (a) leave it, the study stands for the 15 W state [default, no cost]; (b) run it, about 1 hour of device
time plus the mode change and possibly two reboots. I changed nothing and will not without this decision.

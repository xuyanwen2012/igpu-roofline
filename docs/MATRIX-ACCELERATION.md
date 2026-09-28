# Is cooperative matrix hardware-accelerated?

A driver that lists a cooperative-matrix shape is only promising a correct result.
The Vulkan specification says nothing about speed: a driver may lower `coopMatMulAdd`
to ordinary FMA or dot instructions and still conform. The shape query
([COOPMAT-SHAPES.md](COOPMAT-SHAPES.md), gpu-lab's
[cooperative-matrices.md](../../gpu-lab/docs/cooperative-matrices.md)) therefore
answers "which shapes", never "is it fast". This page records how we decide, and the
current verdict for every GPU we tune for.

## How to decide

Use the strongest evidence available, in this order.

1. **ISA or hardware counters.** The compiled shader contains matrix instructions, or
   a matrix-unit counter moves while the kernel runs.

   | Vendor | Matrix instruction / counter | Route |
   |---|---|---|
   | AMD RDNA3 | `v_wmma_f16_16x16x16_f16`, `v_wmma_f32_16x16x16_f16`, `v_wmma_i32_16x16x16_iu8` | RADV shader dump or `rga` ([TOOLING.md](TOOLING.md)) |
   | Intel Xe2 | native `dpas.8x8` (count these; `@dpas_intel` lines are NIR intrinsics, not instructions) | Mesa ANV `MESA_SHADER_CACHE_DISABLE=true INTEL_DEBUG=cs` ([XE2-WMMA-LESSONS.md](XE2-WMMA-LESSONS.md)) |
   | NVIDIA | Nsight `Tensor Active` (SASS `HMMA`/`IMMA`) | `nsys --gpu-metrics-set` ([4070TI-WMMA-LESSONS.md](4070TI-WMMA-LESSONS.md)) |
   | Arm Mali | arithmetic unit split in `malioc` reports | `malioc` |
   | Qualcomm Adreno, Samsung Xclipse | no recorded route yet | ask the device owner |

   Only plain FMA/dot instructions in the loop means the driver emulates the
   operation.

2. **Measured roof ratio.** Compare a register-resident matrix roof with the scalar
   roof of the same input type from a confirmed roofline campaign:
   - fp16: matrix fp16 roof ÷ fp16 FMA roof;
   - int8: matrix int8 roof ÷ int8 dot roof.

   How to read the ratio:
   - **≥ 1.5×**: a dedicated or wider path almost certainly exists.
   - **≈ 1×**: the matrix path runs at scalar speed, which is typical of emulation.
   - **< 1×**: worse than scalar code, or a measurement artefact.

   A low ratio is a question, not a verdict. Before concluding anything, rule out the
   artefacts in CLAUDE.md "Lessons already paid for": under-filled launch grids,
   latency-bound chains, compiler folding and invisible throttling. Also check whether
   the fed (shared, cache, DRAM) roofs can keep the unit busy.

3. **Shape pattern, as a hint only.**
   - Hardware shapes are usually small and fixed, and map to one instruction:
     16×16×16 on AMD, 8×16×16 on Intel, 16×8×16 on NVIDIA.
   - A dimension equal to the subgroup width suggests a per-lane layout: Adreno's
     M = 64 matches its 64-wide wave.
   - An fp16 path that can only accumulate in fp16 suggests register-budget limits.

4. **The device owner's knowledge.** Record it as such. It settles the hardware
   question, but not whether a given driver path uses the hardware.

## Current verdict (2026-09-28)

Ratios use confirmed short-run `fast`-plan roofs (TFLOP/s for fp16, TOP/s for int8).
The sources are the SARC 1.5 e2e benchmark roofline evidence
(`openspec/changes/sarc-1.5-e2e-benchmark/evidence/roofline.md`), `contrib/*/roofline.json`,
and [FLEET.md](FLEET.md) for the M51.

| GPU | fp16 matrix ÷ FMA | int8 matrix ÷ dot | ISA / counter evidence | Verdict |
|---|---|---|---|---|
| Jetson Orin Nano | 9.70 ÷ 1.77 = **5.5×** | 19.52 ÷ 2.09 = **9.3×** | Nsight Tensor Active 9.9 → 20.9 % on the 8da4w kernel ([JETSON-WMMA-LESSONS.md](JETSON-WMMA-LESSONS.md)) | Hardware (Tensor Cores), counter-verified |
| RTX 4070 Ti SUPER | 183.7 ÷ 45.0 = **4.1×** | 369.2 ÷ 78.1 = **4.7×** | Nsight Tensor Active 70–76 % on 4w large shapes ([4070TI-WMMA-LESSONS.md](4070TI-WMMA-LESSONS.md)) | Hardware (Tensor Cores), counter-verified |
| Arc B580 | 111.7 ÷ 27.3 = **4.1×** | 231.4 ÷ 32.1 = **7.2×** | native `dpas.8x8`: 64 (4w, fp16) and 32 (8da4w, int8) in `roofline-et-study/isa/b580/` (older SIMD32 tiles) | Hardware (XMX), ISA-verified |
| Arc Pro B70 | 173.3 ÷ 42.9 = **4.0×** | 359.9 ÷ 50.4 = **7.1×** | native `dpas.8x8`: 16 per compile, 64 per dump, in both the 4w (fp16 → fp16) and 8da4w (s8 × s8 → s32) winners; Mesa 26.2.3, 2026-09-28 (`roofline-et-study/isa/b70/`) | Hardware (XMX), ISA-verified |
| RX 7900 XTX | 136.4 ÷ 63.4 = **2.2×** | 142.6 ÷ 69.2 = **2.1×** | ISA check requested from the device agent | Accelerated by ratio (RDNA3 WMMA) |
| Radeon 780M | 14.77 ÷ 8.14 = **1.8×** (fp32 acc) | 14.39 ÷ 11.72 = 1.2× | `v_wmma_f16/f32_16x16x16_f16` and `v_wmma_i32_16x16x16_iu8` in `roofline-et-study/remote/rocky-ryzen/.../isa/780m/` | Hardware (RDNA3 WMMA), ISA-verified |
| Xclipse (M51) | 7.77 ÷ 7.70 = 1.0× | 15.09 ÷ 3.56 = **4.2×** | **Owner-confirmed real matrix hardware**; ISA check requested | Hardware. The fp16 ratio of 1.0× is unexplained (driver lowering, configuration or measurement), not evidence of emulation |
| Adreno 840 (S26) | 6.95 ÷ 7.76 = **0.9×** | 12.24 ÷ 7.05 = **1.7×** | No ISA route; ISA check requested | int8 accelerated by ratio; the fp16 path runs below scalar FMA |
| Mali-G1-Ultra | unconfirmed | unconfirmed (~9.4 vs ~13.3) | none | Unknown: the old data violates physical limits (matrix < dot; cache-fed > register). Re-measure first |
| Galaxy S24+ (Xclipse 940), Pixel 7a (Mali-G710), Ryzen 9600X iGPU | — | — | driver exposes no cooperative matrix | None available through Vulkan |

Notes:
- **RDNA3 (780M, 7900 XTX).** The ratio is about 2× because RDNA3 executes WMMA on
  its vector SIMDs, not on a separate matrix core. int8 WMMA runs at the fp16 rate,
  which is why 8da4w gains less than 4w on the 780M.
- **M51 and Adreno.** The int8 path is where the matrix gain is today, which matches
  the e2e results: M51 8da4w gains 2.5×, and the S26's fp16 4w row has no releasable
  gain.
- **Limits of this evidence.** All ratios are short-run roofs, not sustained. The M51
  numbers are pinned-clock values from an external summary.

## Keeping this page current

- When an ISA capture arrives, put its path and instruction counts in the evidence
  column.
- Re-derive the ratios from the device's current confirmed campaign after a driver
  update.
- Do not upgrade a verdict from a ratio alone when the ratio is below 1.5×.

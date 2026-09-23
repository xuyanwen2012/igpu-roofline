# Device fleet

Every device the suite runs on or has probed: hardware, driver, where it is connected, and
which roofs it can have. Per-device measurement notes and known issues are in
[CLAUDE.md](../CLAUDE.md#devices). Full cooperative-matrix shape lists are in
[COOPMAT-SHAPES.md](COOPMAT-SHAPES.md).

## Overview

| device | serial | SoC | GPU | driver | Vulkan | subgroup | WMMA | root | connected to |
|---|---|---|---|---|---|---|---|---|---|
| vivo V2502A | `10AFAT2014002UM` | MediaTek MT6993 | Mali-G1-Ultra MC12 | Arm r54p1 | 1.3+ | 16 | **yes** | no | owner's Mac |
| Samsung S26 Ultra | `R3GL10GC1AP` | Snapdragon (Adreno 840) | Adreno 840 | 2150932499 | 1.3+ | 64 | **yes** | no | owner's Mac |
| Samsung M51 | `000008354c579c33` | Exynos S5E9975 | Xclipse 970 | main-fafb46ae9c0d | 1.3+ | **TODO(owner)** | **yes** | **yes** | `xgpusw-debug06` |
| Samsung Galaxy S24+ (SM-S926B) | `R5CY21Y3VEV` | Exynos 2400 (s5e9945) | Xclipse 940 | Samsung 24.0.534 (1900168dcb) | 1.3.279 | 64 (32–64) | **no** | no | `rocky-ryzen` (USB) |
| Google Pixel 7a | `3A021JEHN02756` | Tensor G2 (gs201) | Mali-G710 | Arm r54p3 | 1.4.343 | 16 | **no** | no | `rocky-ryzen` (USB) |
| Minisforum UM790 Pro | host `rocky-ryzen` | Ryzen 9 7940HS | Radeon 780M (RDNA3) | RADV, Mesa 25.2.7 | 1.4.318 | 64 | **yes** | no (no sudo) | local (`run --local`) |

"WMMA" means the driver exposes `VK_KHR_cooperative_matrix` and reports at least one shape
the suite builds. Without it, the suite skips the cooperative-matrix family. FP32/FP16 FMA,
int8 dot4 (`VK_KHR_shader_integer_dot_product`), and all memory and latency families still run.

## WMMA shapes

These are the shapes the suite builds and measures. All are subgroup scope, and A and B
use the same type. The full driver lists (fp32 shapes, unsigned and mixed-sign int8,
saturating accumulation) are in [COOPMAT-SHAPES.md](COOPMAT-SHAPES.md).

| device | GPU | fp16 → fp16 | fp16 → fp32 | int8 → int32 | probed |
|---|---|---|---|---|---|
| rocky-ryzen | Radeon 780M (RADV) | 16×16×16 | 16×16×16 | 16×16×16 | 2026-09-23 |
| vivo V2502A | Mali-G1-Ultra MC12 | 4×8×8, 16×32×32 | 4×8×8, 16×32×32 | 4×16×16 | 2026-09-22 |
| Samsung S26 Ultra | Adreno 840 | 64×{16,32,64}×16 | — | 64×{16,32,64}×32 | 2026-09-21 (v1 tooling) |
| Samsung M51 | Xclipse 970 | 16×16×16 | 16×16×16 | 16×16×16 | transcribed, **TODO(owner)** |
| Samsung Galaxy S24+ | Xclipse 940 | — | — | — | 2026-09-23 (not exposed) |
| Google Pixel 7a | Mali-G710 | — | — | — | 2026-09-23 (not exposed) |

### Radeon 780M (`rocky-ryzen`)

RADV PHOENIX, Mesa 25.2.7 (driver 104865799), Vulkan 1.4.318, subgroup 64, shared memory
65536 B, peak sclk 2799 MHz. Every reported shape is 16×16×16 at subgroup scope:

- fp16 × fp16, accumulating in fp16 or fp32.
- 8-bit int × 8-bit int with every signedness combination (s8/u8 × s8/u8), accumulating in
  s32 or u32. The s32 results are also offered with saturating accumulation.
- No fp32 × fp32, bf16, or fp8 shapes.

## Devices without WMMA

Both devices were probed on 2026-09-23 from `rocky-ryzen` with `igpu-roofline shapes
--device <serial>`. The driver's full extension list (`adb shell cmd gpu vkjson`) confirms
that neither driver exposes any `cooperative_matrix` extension. Both expose
`VK_KHR_shader_float16_int8` and `VK_KHR_shader_integer_dot_product`.

### Google Pixel 7a (`3A021JEHN02756`)

- Android 17 (`google/lynx/lynx:17/CP2A.260705.006/15641320:user/release-keys`), 8 GB RAM.
- Mali-G710, driver `v1.r54p3-00eac0` (226504704), Vulkan 1.4.343, 165 device extensions.
- Subgroup fixed at 16. Shared memory 32768 B.
- The vivo phone's Mali-G1 exposes WMMA on the older r54p1 driver, but this Mali-G710 on
  r54p3 does not. So on Mali, WMMA depends on the GPU, not just on how new the driver is.
- Offline ISA: `malioc` supports Mali-G710.
- Earlier `quick`-plan results from an older checkout exist on `rocky-ryzen`. They predate
  the current runner, so do not reuse them as roofs.

### Samsung Galaxy S24+ SM-S926B (`R5CY21Y3VEV`)

- Android 16 (`samsung/e2sxxx/e2s:16/BP4A.251205.006/S926BXXSGDZG1:user/release-keys`),
  12 GB RAM.
- Xclipse 940 (AMD RDNA3-based), Samsung proprietary driver 24.0.534 (git 1900168dcb,
  100663830), Vulkan 1.3.279, 154 device extensions.
- Subgroup 64 by default; subgroup size control allows 32–64 in compute. Shared memory
  32768 B.
- The Xclipse 970 in the M51 exposes 16×16×16 WMMA, but this Xclipse 940 driver does not,
  even though both GPUs are RDNA3-based.
- The GPU clock is readable without root via `/sys/kernel/gpu/` (`gpu_clock`,
  `gpu_max_clock` = 1095000 kHz).

## Adding a device

```sh
adb devices -l                                        # serial, model
adb -s <serial> shell getprop ro.soc.model            # SoC; also ro.build.fingerprint
uv run igpu-roofline shapes --device <serial>         # GPU, driver, subgroup, WMMA shapes
adb -s <serial> shell cmd gpu vkjson > vk.json        # full Vulkan properties/extensions
```

Add a row to the overview, a section to [COOPMAT-SHAPES.md](COOPMAT-SHAPES.md), and a
row to the device table in [CLAUDE.md](../CLAUDE.md#devices).

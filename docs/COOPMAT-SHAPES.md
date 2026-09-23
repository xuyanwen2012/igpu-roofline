# Cooperative-matrix (WMMA) shapes by device

What each device's driver reports through `vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR`.
The suite only runs exact matches (M, N, K, A, B, C, Result, subgroup scope); see
`matrix-coverage.json` in a results folder for reported shapes that have no compiled
variant. Types: f16/f32 float, s8/u8 8-bit int, s32/u32 32-bit int accumulators.

**Add or refresh a device:** connect it and run

```sh
uv run igpu-roofline shapes --device <serial>   # phone (needs `igpu-roofline build`)
uv run igpu-roofline shapes --local             # this host's GPU (needs `build --host`)
```

and paste the printed table below with the device, driver and date. Shapes change with
drivers: re-probe after a driver update.

## Summary (what the suite measures)

| device | GPU | subgroup | fp16 → fp16 | fp16 → fp32 | int8 → int32 |
|---|---|---:|---|---|---|
| rocky-ryzen | Radeon 780M (RADV) | 64 | 16×16×16 | 16×16×16 | 16×16×16 |
| vivo V2502A | Mali-G1-Ultra MC12 | 16 | 4×8×8, 16×32×32 | 4×8×8, 16×32×32 | 4×16×16 |
| Samsung S26 Ultra | Adreno 840 | 64 | 64×{16,32,64}×16 | — | 64×{16,32,64}×32 |
| Samsung M51 | Xclipse 970 | **TODO(owner)** | 16×16×16 | 16×16×16 | 16×16×16 |
| Samsung Galaxy S24+ | Xclipse 940 | 64 | — | — | — |
| Google Pixel 7a | Mali-G710 | 16 | — | — | — |

Galaxy S24+ and Pixel 7a do not expose `VK_KHR_cooperative_matrix`, so they have no
WMMA shapes. The device list is in [FLEET.md](FLEET.md).

Also reported but not built by the suite: fp32 × fp32 (Mali 4×4×4 and 16×16×16; Adreno
64×{16,32,64}×8), unsigned and mixed-sign int8 variants, and saturating accumulation.

## AMD Radeon 780M — RADV PHOENIX (host `rocky-ryzen`)

Driver 104865799 (Mesa 25.2.7), subgroup 64, shared 65536 B;
probed 2026-09-23.

| M×N×K | A | B | C | Result | scope | saturating |
|---|---|---|---|---|---|---|
| 16×16×16 | f16 | f16 | f16 | f16 | subgroup | no |
| 16×16×16 | f16 | f16 | f32 | f32 | subgroup | no |
| 16×16×16 | u8 | u8 | u32 | u32 | subgroup | no |
| 16×16×16 | u8 | u8 | s32 | s32 | subgroup | no |
| 16×16×16 | u8 | u8 | s32 | s32 | subgroup | yes |
| 16×16×16 | u8 | s8 | u32 | u32 | subgroup | no |
| 16×16×16 | u8 | s8 | s32 | s32 | subgroup | no |
| 16×16×16 | u8 | s8 | s32 | s32 | subgroup | yes |
| 16×16×16 | s8 | u8 | u32 | u32 | subgroup | no |
| 16×16×16 | s8 | u8 | s32 | s32 | subgroup | no |
| 16×16×16 | s8 | u8 | s32 | s32 | subgroup | yes |
| 16×16×16 | s8 | s8 | u32 | u32 | subgroup | no |
| 16×16×16 | s8 | s8 | s32 | s32 | subgroup | no |
| 16×16×16 | s8 | s8 | s32 | s32 | subgroup | yes |

## Mali-G1-Ultra MC12 — vivo V2502A (`10AFAT2014002UM`)

Driver r54p1 (226496512), subgroup 16, shared 32768 B;
probed 2026-09-22. **TODO(owner): re-probe and confirm.**

| M×N×K | A | B | C | Result | scope | saturating |
|---|---|---|---|---|---|---|
| 4×4×4 | f32 | f32 | f32 | f32 | subgroup | no |
| 16×16×16 | f32 | f32 | f32 | f32 | subgroup | no |
| 4×8×8 | f16 | f16 | f32 | f32 | subgroup | no |
| 16×32×32 | f16 | f16 | f32 | f32 | subgroup | no |
| 4×16×16 | s8 | s8 | s32 | s32 | subgroup | no |
| 4×16×16 | u8 | u8 | u32 | u32 | subgroup | no |
| 4×8×8 | f16 | f16 | f16 | f16 | subgroup | no |
| 16×32×32 | f16 | f16 | f16 | f16 | subgroup | no |

## Adreno 840 — Samsung S26 Ultra (`R3GL10GC1AP`)

Driver 2150932499, subgroup 64; captured 2026-09-21 by the older
roofline v1 tooling. **TODO(owner): re-probe with `igpu-roofline shapes`.**

| M×N×K | A | B | C | Result | scope | saturating |
|---|---|---|---|---|---|---|
| 64×64×16 | f16 | f16 | f16 | f16 | subgroup | no |
| 64×64×8 | f32 | f32 | f32 | f32 | subgroup | no |
| 64×64×32 | u8 | u8 | u32 | u32 | subgroup | no |
| 64×64×32 | u8 | s8 | s32 | s32 | subgroup | yes |
| 64×64×32 | s8 | s8 | s32 | s32 | subgroup | no |
| 64×64×32 | s8 | u8 | u32 | u32 | subgroup | yes |
| 64×32×16 | f16 | f16 | f16 | f16 | subgroup | no |
| 64×32×8 | f32 | f32 | f32 | f32 | subgroup | no |
| 64×32×32 | u8 | u8 | u32 | u32 | subgroup | no |
| 64×32×32 | u8 | s8 | s32 | s32 | subgroup | yes |
| 64×32×32 | s8 | s8 | s32 | s32 | subgroup | no |
| 64×32×32 | s8 | u8 | u32 | u32 | subgroup | yes |
| 64×16×16 | f16 | f16 | f16 | f16 | subgroup | no |
| 64×16×8 | f32 | f32 | f32 | f32 | subgroup | no |
| 64×16×32 | u8 | u8 | u32 | u32 | subgroup | no |
| 64×16×32 | u8 | s8 | s32 | s32 | subgroup | yes |
| 64×16×32 | s8 | s8 | s32 | s32 | subgroup | no |
| 64×16×32 | s8 | u8 | u32 | u32 | subgroup | yes |

## Xclipse 970 — Samsung M51 (`000008354c579c33`, rooted)

Transcribed from another agent's report (driver main-fafb46ae9c0d); every entry is
16×16×16, subgroup scope. **TODO(owner): re-probe, add driver version, subgroup size and
shared-memory size.**

| M×N×K | A | B | C | Result | scope | saturating |
|---|---|---|---|---|---|---|
| 16×16×16 | f16 | f16 | f32 | f32 | subgroup | no |
| 16×16×16 | f16 | f16 | f16 | f16 | subgroup | no |
| 16×16×16 | u8 | u8 | u32 | u32 | subgroup | no |
| 16×16×16 | s8 | s8 | s32 | s32 | subgroup | no |
| 16×16×16 | u8 | s8 | s32 | s32 | subgroup | no |
| 16×16×16 | s8 | u8 | s32 | s32 | subgroup | no |
| 16×16×16 | u8 | u8 | u32 | u32 | subgroup | yes |
| 16×16×16 | s8 | s8 | s32 | s32 | subgroup | yes |
| 16×16×16 | u8 | s8 | s32 | s32 | subgroup | yes |
| 16×16×16 | s8 | u8 | s32 | s32 | subgroup | yes |

## Devices without cooperative matrix

Probed 2026-09-23 with `igpu-roofline shapes --device <serial>`: the driver does not expose
`VK_KHR_cooperative_matrix`, and `adb shell cmd gpu vkjson` lists no `cooperative_matrix`
extension at all.

| device | GPU | driver | Vulkan | subgroup | shared |
|---|---|---|---|---:|---:|
| Samsung Galaxy S24+ SM-S926B (`R5CY21Y3VEV`) | Xclipse 940 | Samsung 24.0.534 (100663830) | 1.3.279 | 64 | 32768 B |
| Google Pixel 7a (`3A021JEHN02756`) | Mali-G710 | r54p3 (226504704) | 1.4.343 | 16 | 32768 B |

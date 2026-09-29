# Roofline cooperative-matrix shape snapshots

Historical results from `vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR`, with
driver and query dates below. Current fleet queries and refresh instructions live
in [gpu-lab's matrix inventory](../../gpu-lab/docs/cooperative-matrices.md).
These records also cover devices outside gpu-lab's selected fleet.
A listed shape does not mean the GPU accelerates it; see
[MATRIX-ACCELERATION.md](MATRIX-ACCELERATION.md).
RX 7900 XTX and RX 7600 shapes are in [the extra-devices snapshot](reports/data/cooperative-matrices-extra-2026-09-28.json) and [the atlas](reports/wmma-shape-atlas.html).

The suite only runs exact matches (M, N, K, A, B, C, Result, subgroup scope); see
`matrix-coverage.json` in a results folder for reported shapes that have no compiled
variant. Types: f16/f32 float, s8/u8 8-bit int, s32/u32 32-bit int accumulators.

**Check roofline runner coverage:** on the execution host, run

```sh
uv run igpu-roofline shapes --device <serial>   # phone (needs `igpu-roofline build`)
uv run igpu-roofline shapes --local             # this host's GPU (needs `build --host`)
```

and retain the output with device, driver, date and campaign artifacts. Refresh the
shared inventory through gpu-lab after driver updates; keep historical snapshots
here as provenance rather than maintaining a second current fleet inventory.

## Recorded suite coverage

| device | GPU | subgroup | fp16 → fp16 | fp16 → fp32 | int8 → int32 |
|---|---|---:|---|---|---|
| rocky-ryzen | Radeon 780M (RADV) | 64 | 16×16×16 | 16×16×16 | 16×16×16 |
| vivo V2502A | Mali-G1-Ultra MC12 | 16 | 4×8×8, 16×32×32 | 4×8×8, 16×32×32 | 4×16×16 |
| Samsung S26 Ultra | Adreno 840 | 64 | 64×{16,32,64}×16 | — | 64×{16,32,64}×32 |
| Samsung Xclipse (M51) | Xclipse | — | 16×16×16 | 16×16×16 | 16×16×16 |
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

## Mali-G1-Ultra MC12 — vivo V2502A

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

## Adreno 840 — Samsung S26 Ultra

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

## Samsung Xclipse (M51, internal device)

Owner-provided; every entry is 16×16×16, subgroup scope. Driver details are not published.

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

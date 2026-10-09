# Part C evidence: what RADV (ACO) generated, Radeon 780M, Mesa 25.2.7, 2026-10-09

Raw files: `et/*.isa.txt` (kernels: `RADV_DEBUG=shaders,shaderstats MESA_SHADER_CACHE_DISABLE=true` during a real
dispatch of `test_llama_microbench --linear --scheme=<s> --storage=texture3d --regime=prefill --model=llama-3.2-1b`
and `--sdpa`; split from `../et/isa-*.stderr` by `tools/split_radv_dump.py`, which keeps the `disasm:` section and
the statistics block of every shader that contains a `v_wmma`), `roofline/*.isa.txt` (the roofline matrix shaders:
the driver's own disassembly through `VK_KHR_pipeline_executable_properties`, captured by the tool's inspector at
the start of part A; byte-identical in both part A runs, 10 of 10 files). Counts: `counts.csv`
(`tools/count_isa.py`), statistics: `et-stats.csv`, `roofline-stats.csv`. SPIR-V of the dispatched kernels:
`spirv/` (copied from the final build, sha256 in `spirv/et-study-spv-sha.txt`, identical in the build's two
shader trees), types and static reuse: `spirv-types.csv` (`tools/spirv_coopmat.py`).

Which shader is which shape (order of dispatch, 1B, M = 2048; local size from the run's log):

| file | shape | kernel | local size | VGPRs | spilled VGPR / SGPR | scratch | LDS bytes | waves per SIMD (driver) | v_wmma total / per loop iteration | per iteration: LDS loads, LDS stores, barriers, image + buffer loads |
|---|---|---|---|---:|---|---:|---:|---:|---|---|
| `4w-shader04` | 4w wq_wo | `t128x128k32g24s32f32cbt` | 256 | 160 | 0 / 0 | 0 | 40960 | 6 | 32 / 16 `v_wmma_f32_16x16x16_f16` | 24 `ds_load_b128`, 6, 1, 5 + 1 |
| `4w-shader06` | 4w wk_wv | same kernel | 256 | 160 | 0 / 0 | 0 | 40960 | 6 | 32 / 16 | same |
| `4w-shader07` | 4w w1_w3 | `t256x128k32g28s32f32cbt` | 512 | 128 | 0 / 0 | 0 | 61440 | 8 | 32 / 16 | 24 `ds_load_b128`, 6, 1, 5 + 1 |
| `4w-shader08` | 4w w2 | `t256x128k32g18s32f32cbt` | 256 | 240 | 0 / 0 | 0 | 61440 | 4 | 64 / 32 | 40 `ds_load_b128`, 8, 1, 9 + 1 |
| `8da4w-shader08`, `-shader11` | 8da4w wq_wo, w1_w3 | `zpg_t256x64k64g48s32afmb1` | 1024 | 64 | 0 / 0 | 0 | 60416 | 16 | 16 / 16 `v_wmma_i32_16x16x16_iu8` (two K = 64 chunks per iteration) | 24 `ds_load_b128` + 1 `b32`, 11, 2, 2 + 3 |
| `8da4w-shader10`, `-shader12` | 8da4w wk_wv, w2 | `zpg_bt_t128x64k32g22s32` | 128 | 192 | 0 / 0 | 0 | 18432 | 5 | 16 / 16 | 12 `ds_load_b128`, 13, 1, 1 + 3 |
| `sdpa-shader08` | fused attention, head_dim 64 | `sdpa_fused3sb_d64_t32x32g11s32rko` | (one subgroup) | 256 | 0 / 0 | 0 | 5120 | 4 | 32 / 32 `v_wmma_f32_16x16x16_f16` | 12 `ds_load_b128` + 12 narrow, 37, 0, 0 + 32 `buffer_load_b128` |

All seven are wave32 (`exec_lo` masks; "s32" in the names), no `scratch_*`, no `v_readlane` / `v_writelane`, no
undecoded line. The 4w kernels contain no `v_wmma_f16_16x16x16_f16`; the 8da4w kernels no float WMMA.

Tile arithmetic, per K chunk per subgroup: 4w `t256x128k32g18`, 8 subgroups, each 32 x 128 outputs = 2 x 8
fragments, K 32 = 2 steps: 32 (loop: 32; the last chunk is peeled, total 64; per workgroup 8 x 32 = 256 =
16 x 8 x 2). `t128x128k32g24`: 8 subgroups of 32 x 64 = 2 x 4 fragments x 2 = 16 (loop 16, total 32).
`t256x128k32g28`: 16 subgroups of 32 x 64: 16. 8da4w `t256x64k64g48`: 32 subgroups of 32 x 16 = 2 fragments x 4
slabs of K 16 = 8 per chunk; the loop body holds two chunks (16, with 2 barriers and 24 = 2 x 12 tile loads).
`bt_t128x64k32g22`: 4 subgroups of 64 x 32 = 4 x 2 fragments x 2 slabs = 16. Every count matches.

Roofline matrix shaders (subgroup 64, one subgroup per workgroup, wave64):

| file | roof | VGPRs | spills | waves per SIMD (driver) | per loop iteration |
|---|---|---:|---|---:|---|
| `matrix_fp16_fp32_16x16x16_c8` | `matrix_fp16_fp32` (register) | 80 | 0 | 12 | 8 `v_wmma_f32_16x16x16_f16`, no load |
| `matrix_fp16_fp32_16x16x16_c8_lds` | `matrix_fp16_fp32_feed_shared` | 64 | 0 | 16 | 8 WMMA; A tile 2 `ds_load_b128`, B tile 16 `ds_load_u16_d16[_hi]`; `s_waitcnt lgkmcnt(0)` before the WMMAs |
| `matrix_fp16_fp32_16x16x16_c4_lds`, `_c2_lds`, `_c1_lds` | by-reuse rows | 40 / 32 / 24 | 0 | 16 | 4 / 2 / 1 WMMA, the same 18 LDS loads |
| `matrix_int8_16x16x16_c8` | `matrix_int8` (register) | 64 | 0 | 16 | 8 `v_wmma_i32_16x16x16_iu8`, no load |
| `matrix_int8_16x16x16_c8_lds`, `_c4_lds`, `_c2_lds`, `_c1_lds` | `matrix_int8_feed_shared`, by-reuse rows | 56 / 40 / 24 / 24 | 0 | 18 / 24 / 32 / 32 | 8 / 4 / 2 / 1 WMMA; A tile 1 `ds_load_b128`, B tile 16 `ds_load_u8_d16[_hi]` |

What the roofline shader has that the kernels do not: operands that never change (register) or come from 4
pre-staged tile pairs with no store and no barrier inside the loop; 64 to 80 VGPRs, so 12 to 16 waves fit a
SIMD against 4 to 8 for the 4w kernels; wave64. What the kernels have that the fed roofline shader does not:
every operand tile is read with 128-bit LDS loads (2 per fp16 tile, 1 per int8 tile; B is staged column-major),
while the roofline shader reads its row-major B tile with 16 narrow loads; so the kernels issue 0.75 (8da4w `bt`)
to 1.56 (8da4w `afmb1`; 4w 1.25 to 1.5) LDS load instructions per WMMA where the fp16 roofline shader issues
18 / CHAINS (2.25 at CHAINS 8, 4.5 at 4) and the int8 one 17 / CHAINS.

Not done: Radeon GPU Analyzer offline cross-check (the driver route was available, so the approximation was not
needed); the fused kernel for head_dim 128 was not dumped (one shape per kernel family).

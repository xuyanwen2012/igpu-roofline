# AMD Radeon 780M Graphics (RADV PHOENIX) SPIR-V / driver / ISA check

1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.
2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.
3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler (malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.

| roof | variant | SPIR-V ledger | driver statistics | ISA |
|---|---|---|---|---|
| alu_fp16 | alu_fp16_v2_c1 | fma=16, load_StorageBuffer=2, store_StorageBuffer=2 | VGPRs=8; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=5 | — |
| alu_fp32 | alu_fp32_v1_c8 | fma=128, load_StorageBuffer=2, store_StorageBuffer=8 | VGPRs=24; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=18 | — |
| cache_read_effective | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=11 | — |
| dot_int8 | dot8_c2 | dot=16, load_StorageBuffer=2, store_StorageBuffer=2 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=14 | — |
| global_copy | mem_copy_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | VGPRs=8; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=7 | — |
| global_read | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=11 | — |
| global_triad | mem_triad_v4 | fma=1, load_StorageBuffer=2, store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=11 | — |
| global_write | mem_write_v4 | store_StorageBuffer=1 | VGPRs=8; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=7 | — |
| matrix_fp16 | matrix_fp16_16x16x16_c8 | coopmat_muladd=8 | VGPRs=88; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=106 | — |
| matrix_fp16_feed_cache | matrix_fp16_16x16x16_c8_gmem | coopmat_muladd=8 | VGPRs=72; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=80 | — |
| matrix_fp16_feed_dram | matrix_fp16_16x16x16_c1_gmem | coopmat_muladd=1 | VGPRs=32; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=28 | — |
| matrix_fp16_feed_shared | matrix_fp16_16x16x16_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | VGPRs=72; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=80 | — |
| matrix_fp16_fp32 | matrix_fp16_fp32_16x16x16_c8 | coopmat_muladd=8 | VGPRs=80; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=74 | — |
| matrix_fp16_fp32_feed_cache | matrix_fp16_fp32_16x16x16_c8_gmem | coopmat_muladd=8 | VGPRs=56; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=56 | — |
| matrix_fp16_fp32_feed_dram | matrix_fp16_fp32_16x16x16_c1_gmem | coopmat_muladd=1 | VGPRs=32; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=28 | — |
| matrix_fp16_fp32_feed_shared | matrix_fp16_fp32_16x16x16_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | VGPRs=64; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=56 | — |
| matrix_int8 | matrix_int8_16x16x16_c8 | coopmat_muladd=8 | VGPRs=64; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=58 | — |
| matrix_int8_feed_cache | matrix_int8_16x16x16_c8_gmem | coopmat_muladd=8 | VGPRs=56; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=52 | — |
| matrix_int8_feed_dram | matrix_int8_16x16x16_c1_gmem | coopmat_muladd=1 | VGPRs=32; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=24 | — |
| matrix_int8_feed_shared | matrix_int8_16x16x16_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | VGPRs=56; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=52 | — |
| shared_fp16_read | sharedbw_fp16_v4_op0_acc32 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=32, store_StorageBuffer=1 | VGPRs=104; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=67 | — |
| shared_fp16_write | sharedbw_fp16_v2_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | VGPRs=32; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=3 | — |
| shared_fp32_read | sharedbw_fp32_v2_op0_acc32 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=32, store_StorageBuffer=1 | VGPRs=104; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=67 | — |
| shared_fp32_write | sharedbw_fp32_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=6 | — |
| texture_rgba16f_buffer_cache | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | VGPRs=8; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=8 | — |
| texture_rgba16f_buffer_dram | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | VGPRs=8; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=8 | — |
| texture_rgba16f_tex2d_cache | texture_rgba16f_tex2d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba16f_tex2d_dram | texture_rgba16f_tex2d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba16f_tex3d_cache | texture_rgba16f_tex3d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba16f_tex3d_dram | texture_rgba16f_tex3d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba32f_buffer_cache | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba32f_buffer_dram | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba32f_tex2d_cache | texture_rgba32f_tex2d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba32f_tex2d_dram | texture_rgba32f_tex2d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba32f_tex3d_cache | texture_rgba32f_tex3d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |
| texture_rgba32f_tex3d_dram | texture_rgba32f_tex3d | store_StorageBuffer=1 | VGPRs=16; Spilled SGPRs=0; Spilled VGPRs=0; Pre-Sched VGPRs=10 | — |

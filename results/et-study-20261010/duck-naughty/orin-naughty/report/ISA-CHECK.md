# NVIDIA Tegra Orin (nvgpu) SPIR-V / driver / ISA check

1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.
2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.
3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler (malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.

| roof | variant | SPIR-V ledger | driver statistics | ISA |
|---|---|---|---|---|
| alu_fp16 | alu_fp16_v2_c16 | fma=256, load_StorageBuffer=2, store_StorageBuffer=32 | Register Count=41 | — |
| alu_fp32 | alu_fp32_v1_c8 | fma=128, load_StorageBuffer=2, store_StorageBuffer=8 | Register Count=24 | — |
| cache_read_effective | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Register Count=22 | — |
| dot_int8 | dot8_c8 | dot=64, load_StorageBuffer=2, store_StorageBuffer=8 | Register Count=41 | — |
| global_copy | mem_copy_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Register Count=16 | — |
| global_read | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Register Count=22 | — |
| global_triad | mem_triad_v4 | fma=1, load_StorageBuffer=2, store_StorageBuffer=1 | Register Count=16 | — |
| global_write | mem_write_v4 | store_StorageBuffer=1 | Register Count=16 | — |
| matrix_fp16 | matrix_fp16_16x16x16_c8 | coopmat_muladd=8 | Register Count=95 | — |
| matrix_fp16_feed_cache | matrix_fp16_16x16x16_c8_gmem | coopmat_muladd=8 | Register Count=96 | — |
| matrix_fp16_feed_dram | matrix_fp16_16x16x16_c4_gmem | coopmat_muladd=4 | Register Count=55 | — |
| matrix_fp16_feed_shared | matrix_fp16_16x16x16_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Register Count=98 | — |
| matrix_fp16_fp32 | matrix_fp16_fp32_16x16x16_c8 | coopmat_muladd=8 | Register Count=130 | — |
| matrix_fp16_fp32_feed_cache | matrix_fp16_fp32_16x16x16_c4_gmem | coopmat_muladd=4 | Register Count=75 | — |
| matrix_fp16_fp32_feed_dram | matrix_fp16_fp32_16x16x16_c1_gmem | coopmat_muladd=1 | Register Count=52 | — |
| matrix_fp16_fp32_feed_shared | matrix_fp16_fp32_16x16x16_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Register Count=128 | — |
| matrix_int8 | matrix_int8_16x16x32_c4 | coopmat_muladd=4 | Register Count=66 | — |
| matrix_int8_feed_cache | matrix_int8_16x16x32_c8_gmem | coopmat_muladd=8 | Register Count=130 | — |
| matrix_int8_feed_dram | matrix_int8_16x16x32_c4_gmem | coopmat_muladd=4 | Register Count=95 | — |
| matrix_int8_feed_shared | matrix_int8_16x16x32_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Register Count=128 | — |
| shared_fp16_read | sharedbw_fp16_v2_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | Register Count=21 | — |
| shared_fp16_write | sharedbw_fp16_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | Register Count=24 | — |
| shared_fp32_read | sharedbw_fp32_v2_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | Register Count=38 | — |
| shared_fp32_write | sharedbw_fp32_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | Register Count=32 | — |
| texture_rgba16f_buffer_cache | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Register Count=18 | — |
| texture_rgba16f_buffer_dram | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Register Count=18 | — |
| texture_rgba16f_tex2d_cache | texture_rgba16f_tex2d | store_StorageBuffer=1 | Register Count=18 | — |
| texture_rgba16f_tex2d_dram | texture_rgba16f_tex2d | store_StorageBuffer=1 | Register Count=18 | — |
| texture_rgba16f_tex3d_cache | texture_rgba16f_tex3d | store_StorageBuffer=1 | Register Count=20 | — |
| texture_rgba16f_tex3d_dram | texture_rgba16f_tex3d | store_StorageBuffer=1 | Register Count=20 | — |
| texture_rgba32f_buffer_cache | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Register Count=20 | — |
| texture_rgba32f_buffer_dram | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Register Count=20 | — |
| texture_rgba32f_tex2d_cache | texture_rgba32f_tex2d | store_StorageBuffer=1 | Register Count=18 | — |
| texture_rgba32f_tex2d_dram | texture_rgba32f_tex2d | store_StorageBuffer=1 | Register Count=18 | — |
| texture_rgba32f_tex3d_cache | texture_rgba32f_tex3d | store_StorageBuffer=1 | Register Count=20 | — |
| texture_rgba32f_tex3d_dram | texture_rgba32f_tex3d | store_StorageBuffer=1 | Register Count=20 | — |

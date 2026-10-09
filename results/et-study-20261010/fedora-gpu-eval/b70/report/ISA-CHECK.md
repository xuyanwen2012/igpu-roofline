# Intel(R) Graphics (BMG G31) SPIR-V / driver / ISA check

1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.
2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.
3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler (malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.

| roof | variant | SPIR-V ledger | driver statistics | ISA |
|---|---|---|---|---|
| alu_fp16 | alu_fp16_v4_c1 | fma=16, load_StorageBuffer=2, store_StorageBuffer=4 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=54 | — |
| alu_fp32 | alu_fp32_v2_c16 | fma=256, load_StorageBuffer=2, store_StorageBuffer=32 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=204 | — |
| cache_read_effective | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=59 | — |
| dot_int8 | dot8_c4 | dot=32, load_StorageBuffer=2, store_StorageBuffer=4 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=74 | — |
| global_copy | mem_copy_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=39 | — |
| global_read | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=59 | — |
| global_triad | mem_triad_v4 | fma=1, load_StorageBuffer=2, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=73 | — |
| global_write | mem_write_v4 | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=43 | — |
| matrix_fp16 | matrix_fp16_8x16x16_c4 | coopmat_muladd=4 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=68 | — |
| matrix_fp16_feed_cache | matrix_fp16_8x16x16_c8_gmem | coopmat_muladd=8 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=128 | — |
| matrix_fp16_feed_dram | matrix_fp16_8x16x16_c1_gmem | coopmat_muladd=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=72 | — |
| matrix_fp16_feed_shared | matrix_fp16_8x16x16_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=116 | — |
| matrix_fp16_fp32 | matrix_fp16_fp32_8x16x16_c8 | coopmat_muladd=8 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=164 | — |
| matrix_fp16_fp32_feed_cache | matrix_fp16_fp32_8x16x16_c8_gmem | coopmat_muladd=8 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=196 | — |
| matrix_fp16_fp32_feed_dram | matrix_fp16_fp32_8x16x16_c2_gmem | coopmat_muladd=2 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=100 | — |
| matrix_fp16_fp32_feed_shared | matrix_fp16_fp32_8x16x16_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=184 | — |
| matrix_int8 | matrix_int8_8x16x32_c8 | coopmat_muladd=8 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=164 | — |
| matrix_int8_feed_cache | matrix_int8_8x16x32_c8_gmem | coopmat_muladd=8 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=200 | — |
| matrix_int8_feed_dram | matrix_int8_8x16x32_c2_gmem | coopmat_muladd=2 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=104 | — |
| matrix_int8_feed_shared | matrix_int8_8x16x32_c8_lds | coopmat_muladd=8, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=196 | — |
| shared_fp16_read | sharedbw_fp16_v4_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=98 | — |
| shared_fp16_write | sharedbw_fp16_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=37 | — |
| shared_fp32_read | sharedbw_fp32_v2_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=92 | — |
| shared_fp32_write | sharedbw_fp32_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=44 | — |
| texture_rgba16f_buffer_cache | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=50 | — |
| texture_rgba16f_buffer_dram | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=50 | — |
| texture_rgba16f_tex2d_cache | texture_rgba16f_tex2d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=57 | — |
| texture_rgba16f_tex2d_dram | texture_rgba16f_tex2d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=57 | — |
| texture_rgba16f_tex3d_cache | texture_rgba16f_tex3d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=63 | — |
| texture_rgba16f_tex3d_dram | texture_rgba16f_tex3d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=63 | — |
| texture_rgba32f_buffer_cache | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=50 | — |
| texture_rgba32f_buffer_dram | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=50 | — |
| texture_rgba32f_tex2d_cache | texture_rgba32f_tex2d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=57 | — |
| texture_rgba32f_tex2d_dram | texture_rgba32f_tex2d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=57 | — |
| texture_rgba32f_tex3d_cache | texture_rgba32f_tex3d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=63 | — |
| texture_rgba32f_tex3d_dram | texture_rgba32f_tex3d | store_StorageBuffer=1 | Spills=0; GRF registers=0; Push constant registers=0; Max live registers=63 | — |

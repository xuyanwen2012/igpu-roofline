# Samsung Xclipse 940 SPIR-V / driver / ISA check

1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.
2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.
3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler (malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.

| roof | variant | SPIR-V ledger | driver statistics | ISA |
|---|---|---|---|---|
| alu_fp16 | alu_fp16_v4_c1 | fma=16, load_StorageBuffer=2, store_StorageBuffer=4 | numUsedVgprs=10 | driver ISA: VGPR 12, wave64, FMA 64 ✓, dot 0, LDS ld/st 0/0, scratch 0 |
| alu_fp32 | alu_fp32_v1_c8 | fma=128, load_StorageBuffer=2, store_StorageBuffer=8 | numUsedVgprs=25 | driver ISA: VGPR 28, wave64, FMA 128 ✓, dot 0, LDS ld/st 0/0, scratch 0 |
| cache_read_effective | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | numUsedVgprs=12 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| dot_int8 | dot8_c8 | dot=64, load_StorageBuffer=2, store_StorageBuffer=8 | numUsedVgprs=32 | driver ISA: VGPR 32, wave64, FMA 0, dot 64, LDS ld/st 0/0, scratch 0 |
| global_copy | mem_copy_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | numUsedVgprs=7 | driver ISA: VGPR 8, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| global_read | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | numUsedVgprs=12 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| global_triad | mem_triad_v4 | fma=1, load_StorageBuffer=2, store_StorageBuffer=1 | numUsedVgprs=11 | driver ISA: VGPR 12, wave64, FMA 4, dot 0, LDS ld/st 0/0, scratch 0 |
| global_write | mem_write_v4 | store_StorageBuffer=1 | numUsedVgprs=7 | driver ISA: VGPR 8, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| shared_fp16_read | sharedbw_fp16_v4_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | numUsedVgprs=37 | driver ISA: VGPR 40, wave64, FMA 0, dot 0, LDS ld/st 8/1, scratch 0 |
| shared_fp16_write | sharedbw_fp16_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | numUsedVgprs=21 | driver ISA: VGPR 24, wave64, FMA 0, dot 0, LDS ld/st 1/8, scratch 0 |
| shared_fp32_read | sharedbw_fp32_v2_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | numUsedVgprs=34 | driver ISA: VGPR 36, wave64, FMA 0, dot 0, LDS ld/st 8/1, scratch 0 |
| shared_fp32_write | sharedbw_fp32_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | numUsedVgprs=11 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 1/8, scratch 0 |
| texture_rgba16f_buffer_cache | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | numUsedVgprs=14 | driver ISA: VGPR 16, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| texture_rgba16f_buffer_dram | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | numUsedVgprs=14 | driver ISA: VGPR 16, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| texture_rgba16f_tex2d_dram | texture_rgba16f_tex2d | store_StorageBuffer=1 | numUsedVgprs=10 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| texture_rgba16f_tex3d_dram | texture_rgba16f_tex3d | store_StorageBuffer=1 | numUsedVgprs=10 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| texture_rgba32f_buffer_dram | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | numUsedVgprs=15 | driver ISA: VGPR 16, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| texture_rgba32f_tex2d_dram | texture_rgba32f_tex2d | store_StorageBuffer=1 | numUsedVgprs=10 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| texture_rgba32f_tex3d_cache | texture_rgba32f_tex3d | store_StorageBuffer=1 | numUsedVgprs=10 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |
| texture_rgba32f_tex3d_dram | texture_rgba32f_tex3d | store_StorageBuffer=1 | numUsedVgprs=10 | driver ISA: VGPR 12, wave64, FMA 0, dot 0, LDS ld/st 0/0, scratch 0 |

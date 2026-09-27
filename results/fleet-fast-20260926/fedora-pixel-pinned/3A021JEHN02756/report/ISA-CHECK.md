# Mali-G710 SPIR-V / driver / ISA check

1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.
2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.
3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler (malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.

| roof | variant | SPIR-V ledger | driver statistics | ISA |
|---|---|---|---|---|
| alu_fp16 | alu_fp16_v2_c8 | fma=128, load_StorageBuffer=2, store_StorageBuffer=16 | Registers allocated=32; Registers used=15; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| alu_fp32 | alu_fp32_v2_c4 | fma=64, load_StorageBuffer=2, store_StorageBuffer=8 | Registers allocated=32; Registers used=15; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| cache_read_effective | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=6; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| dot_int8 | dot8_c8 | dot=64, load_StorageBuffer=2, store_StorageBuffer=8 | Registers allocated=32; Registers used=15; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| global_copy | mem_copy_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=13; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| global_read | mem_read_v4 | load_StorageBuffer=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=6; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| global_triad | mem_triad_v4 | fma=1, load_StorageBuffer=2, store_StorageBuffer=1 | Registers allocated=32; Registers used=15; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| global_write | mem_write_v4 | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| shared_fp16_read | sharedbw_fp16_v4_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | Registers allocated=32; Registers used=13; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| shared_fp16_write | sharedbw_fp16_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=12; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| shared_fp32_read | sharedbw_fp32_v2_op0 | control_barrier=1, load_StorageBuffer=1, store_Workgroup=1, load_Workgroup=8, store_StorageBuffer=1 | Registers allocated=32; Registers used=13; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| shared_fp32_write | sharedbw_fp32_v4_op2 | control_barrier=1, store_Workgroup=8, load_Workgroup=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=12; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba16f_buffer_cache | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=6; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba16f_buffer_dram | texture_rgba16f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=6; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba16f_tex2d_cache | texture_rgba16f_tex2d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba16f_tex2d_dram | texture_rgba16f_tex2d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba16f_tex3d_cache | texture_rgba16f_tex3d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba16f_tex3d_dram | texture_rgba16f_tex3d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba32f_buffer_cache | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=6; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba32f_buffer_dram | texture_rgba32f_buffer | load_StorageBuffer=1, store_StorageBuffer=1 | Registers allocated=32; Registers used=6; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba32f_tex2d_cache | texture_rgba32f_tex2d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba32f_tex2d_dram | texture_rgba32f_tex2d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba32f_tex3d_cache | texture_rgba32f_tex3d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |
| texture_rgba32f_tex3d_dram | texture_rgba32f_tex3d | store_StorageBuffer=1 | Registers allocated=32; Registers used=11; Spill size=0; Arithmetic FMA (Valhall only)=0.0 | — |

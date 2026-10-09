# NVIDIA Tegra Orin (nvgpu) SPIR-V / driver / ISA check

1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.
2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.
3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler (malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.

| roof | variant | SPIR-V ledger | driver statistics | ISA |
|---|---|---|---|---|
| matrix_fp16_fp32_feed_shared | matrix_fp16_fp32_16x16x16_c2_lds | coopmat_muladd=2, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Register Count=62 | — |
| matrix_int8_feed_shared | matrix_int8_16x16x32_c2_lds | coopmat_muladd=2, control_barrier=1, load_StorageBuffer=2, store_Workgroup=2 | Register Count=73 | — |

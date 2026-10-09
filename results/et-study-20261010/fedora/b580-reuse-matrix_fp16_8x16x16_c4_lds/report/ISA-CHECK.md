# Intel(R) Arc(tm) B580 Graphics (BMG G21) SPIR-V / driver / ISA check

1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.
2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.
3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler (malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.

| roof | variant | SPIR-V ledger | driver statistics | ISA |
|---|---|---|---|---|

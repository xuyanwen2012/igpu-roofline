#!/usr/bin/env python3
"""build_counts.py <results root>: isa/counts.csv = static SPIR-V counts (spirv-dis) and the driver's
VK_KHR_pipeline_executable_properties statistics (isa/raw/*.pipestats.txt) for the kernels of the final
configuration and the roofline matrix shaders behind the matched roofs. No ISA exists on this driver."""
import csv, re, sys
from pathlib import Path
root = Path(sys.argv[1])
# optional: capture directory under isa/ (default raw, the first capture) and output file name
CAP = sys.argv[2] if len(sys.argv) > 2 else "raw"
OUT = sys.argv[3] if len(sys.argv) > 3 else "counts.csv"
# MMAs per loop iteration expected from the tile arithmetic (shader source) and where the static count sits
TILE = {
 "kernel_4w_t256x128k16g42s32ga_3b_wq_wo": ("isa/kernels/sarc_linear_q4gsw_coopmat_t256x128k16g42s32ga_texture3d_texture2d_half.spvasm", 16, "8 A x 2 B tiles per K=16 chunk; static 32 = 16 in the loop + 16 in the peeled last chunk"),
 "kernel_4w_t128x128k16g24s32ga_1b_wk_wv": ("isa/kernels/sarc_linear_q4gsw_coopmat_t128x128k16g24s32ga_texture3d_texture2d_half.spvasm", 8, "2 A x 4 B tiles per K=16 chunk; static 16 = 8 in the loop + 8 in the peeled last chunk"),
 "kernel_8da4w_zpgtr_t128x128k64g44s32mk32ra_3b_wq_wo": ("isa/kernels/sarc_linear_dq8ca_coopmat_zpgtr_t128x128k64g44s32mk32ra_texture3d_texture2d_half.spvasm", 8, "2 A x 2 B tiles x 2 K=32 steps per K=64 chunk; static 8, loop not peeled"),
 "kernel_sdpa_fused3sb_d64_1b": ("isa/kernels/sarc_dev_4070ti_sdpa_fused3sb_d64_t32x32g11s32rko_buffer_buffer_half.spvasm", 32, "per context block 2x2x4 QK^T + 2x2x4 attention x V"),
 "kernel_sdpa_fused3sb_d128_8b": ("isa/kernels/sarc_dev_4070ti_sdpa_fused3sb_d128_t16x64g11s32rko_buffer_buffer_half.spvasm", 64, "per context block 1x4x8 QK^T + 1x4x8 attention x V"),
}
rows = []
for f in sorted((root / "isa" / CAP).glob("*.pipestats.txt")):
    name = f.name.replace(".pipestats.txt", "")
    text = f.read_text(); err = (root / f"isa/{CAP}/{name}.stderr.txt").read_text()
    stat = {k: int(re.search(k + r"\s+(\d+)", text).group(1)) for k in ("Register Count", "Binary Size", "Stack Size", "Local Memory Size", "Shared Memory Size")}
    sub = int(re.search(r"subgroup (\d+)", text).group(1))
    if name in TILE:
        asm, per_iter, how = TILE[name]
    else:
        asm = f"isa/roofline/{name.replace('roofline_', '')}.spvasm"
        per_iter = int(re.search(r"_c(\d+)", name).group(1)); how = "CHAINS multiply-adds per loop iteration, one A/B pair"
    a = (root / asm).read_text()
    cnt = lambda op: len(re.findall(r"\b" + op + r"\b", a))
    rows.append([name, re.findall(r"^[0-9a-f]{64}$", err, re.M)[0], cnt("OpCooperativeMatrixMulAddKHR"), per_iter, how,
                 cnt("OpCooperativeMatrixLoadKHR"), cnt("OpCooperativeMatrixStoreKHR"), cnt("OpControlBarrier"),
                 cnt("OpImageFetch"), sub, stat["Register Count"], stat["Binary Size"], stat["Stack Size"],
                 stat["Local Memory Size"], stat["Local Memory Size"] & 0xFFFFFFFF, stat["Shared Memory Size"],
                 text.count("--- IR"), re.search(r"cache_blob_bytes=(\d+)", err).group(1), re.search(r"entropy_bits_per_byte=([\d.]+)", err).group(1),
                 "no (driver returns no ISA)"])
with (root / "isa" / OUT).open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow("shader,spirv_sha256,spirv_muladd_static,muladd_per_loop_iteration_tile_arithmetic,tile_arithmetic,spirv_coopmat_load_static,spirv_coopmat_store_static,spirv_control_barrier_static,spirv_image_fetch_static,driver_subgroup_size,driver_register_count,driver_binary_size_bytes,driver_stack_size_bytes,driver_local_memory_size_raw,driver_local_memory_low32_bytes,driver_shared_memory_bytes,driver_internal_representations,pipeline_cache_blob_bytes,pipeline_cache_entropy_bits_per_byte,isa_verified".split(","))
    w.writerows(rows)
for r in rows: print(r[0][:52].ljust(52), "muladd", r[2], "per-iter", r[3], "loads", r[5], "fetch", r[8], "reg", r[10], "bin", r[11], "local", r[14], "shared", r[15], "IR", r[16])

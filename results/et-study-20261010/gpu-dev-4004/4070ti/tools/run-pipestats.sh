#!/bin/bash
# run-pipestats.sh : part C of et-study-20261010. Compiles (never dispatches) the final configuration's kernels and
# the roofline matrix shaders behind the matched roofs with VK_KHR_pipeline_executable_properties capture flags and
# prints what the driver returns: statistics, internal representations (count, text or binary), pipeline cache blob
# size and byte entropy. Under gpu-lab's and the roofline tool's device locks. Driver shader disk cache off.
set -u
S=$HOME/et-study-20261010; O=$S/isa; mkdir -p $O/raw; cd $O
K=$HOME/hmz-sarc-4070ti-fused/.artifacts/build/topic3/backend/vulkan_compute_shaders
R=$S/igpu-roofline/build/shaders
UUID=81a511a2-de7e-c3c8-f641-3562c315ffa7
exec 9>>$HOME/.cache/gpu-lab/lock-$UUID; flock -n 9 || { echo LOCK_BUSY; exit 75; }
exec 8>>/tmp/igpu-roofline-locks-$(id -u)/$(printf 'vulkan:%s' "${UUID//-/}" | sha256sum | cut -d' ' -f1).lock; flock -n 8 || { echo ROOFLINE_LOCK_BUSY; exit 75; }
export __GL_SHADER_DISK_CACHE=0 VKPS_IR=1 VKPS_DEVICE=NVIDIA
one() { local name=$1 spv=$2; shift 2
  VKPS_CACHE=$O/raw/$name.cache.bin $S/tools/vkpipestats $spv "$@" > $O/raw/$name.pipestats.txt 2> $O/raw/$name.stderr.txt 9>&- 8>&-
  echo "rc=$? args=$*" >> $O/raw/$name.stderr.txt; sha256sum $spv | cut -d' ' -f1 >> $O/raw/$name.stderr.txt
  python3 - $O/raw/$name.cache.bin >> $O/raw/$name.stderr.txt <<'PY'
import collections, math, sys
b = open(sys.argv[1], 'rb').read(); c = collections.Counter(b)
print(f"cache_blob_bytes={len(b)} entropy_bits_per_byte={-sum(n/len(b)*math.log2(n/len(b)) for n in c.values()):.3f}")
PY
  rm -f $O/raw/$name.cache.bin; }
# kernels: local size, then spec constants 3.. as the 3B / 1B / 8B dispatches set them (apply_bias, K4_per_group, num_groups, N)
one kernel_4w_t256x128k16g42s32ga_3b_wq_wo $K/sarc_linear_q4gsw_coopmat_t256x128k16g42s32ga_texture3d_texture2d_half.spv 256 1 1 3=0 4=32 5=24 6=3072
one kernel_4w_t128x128k16g24s32ga_1b_wk_wv $K/sarc_linear_q4gsw_coopmat_t128x128k16g24s32ga_texture3d_texture2d_half.spv 256 1 1 3=0 4=32 5=16 6=512
one kernel_8da4w_zpgtr_t128x128k64g44s32mk32ra_3b_wq_wo $K/sarc_linear_dq8ca_coopmat_zpgtr_t128x128k64g44s32mk32ra_texture3d_texture2d_half.spv 512 1 1 3=0 4=32 5=24 6=3072
one kernel_sdpa_fused3sb_d64_1b $K/sarc_dev_4070ti_sdpa_fused3sb_d64_t32x32g11s32rko_buffer_buffer_half.spv 32 1 1 3=1040187392 4=2048 5=512 6=3072
one kernel_sdpa_fused3sb_d128_8b $K/sarc_dev_4070ti_sdpa_fused3sb_d128_t16x64g11s32rko_buffer_buffer_half.spv 32 1 1 3=1035273459 4=4096 5=1024 6=3072
for v in matrix_fp16_16x16x16_c8 matrix_fp16_16x16x16_c4_lds matrix_fp16_16x16x16_c8_lds matrix_fp16_fp32_16x16x16_c4 matrix_fp16_fp32_16x16x16_c1_lds matrix_fp16_fp32_16x16x16_c2_lds matrix_fp16_fp32_16x16x16_c4_lds matrix_int8_16x16x32_c4 matrix_int8_16x16x32_c2_lds matrix_int8_16x16x32_c4_lds; do
  one roofline_$v $R/$v.spv 32 1 1
done
echo PIPESTATS_DONE

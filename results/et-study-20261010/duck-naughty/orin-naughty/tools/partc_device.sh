#!/bin/bash
# partc_device.sh: device side, part C. Driver pipeline statistics (VK_KHR_pipeline_executable_properties) of the
# dispatched ExecuTorch kernels, with the specialization constants of the benchmarked shapes. Uses the
# vkpipestats binary the first Jetson study left on the device (compiles a pipeline, never dispatches); read-only
# there. SPIR-V files are byte copies of the final build's (SHA256SUMS). Under the gpu-lab device lock.
set -u
S=$HOME/roofline-study-20261010; O=$S/partC; V=$HOME/.cache/et-jetson-study/profiles/vkpipestats; mkdir -p $O; cd $O
exec 9>>"$HOME/.cache/gpu-lab/lock-b49259c9-868c-5b7c-b6f1-65a2bf4b63be"; flock -w 1800 9 || { echo LOCK_BUSY > status; exit 75; }
echo "RUNNING $(date -u +%FT%TZ)" > status; sha256sum $V $V.cpp > env.txt; (cd spirv && sha256sum -c SHA256SUMS) >> env.txt 2>&1
run() { n=$1; f=$2; shift 2; VKPS_DEVICE=Tegra VKPS_IR=1 $V spirv/$f.spv "$@" > $n.stats.txt 2> $n.stderr.txt 9>&-; echo "$n rc=$? args=$*" >> status; }
Q=sarc_linear_q4gsw_coopmat_orin_t256x128k16g42s32bt_texture3d_texture2d_half
X=sarc_dev_linear_q4gsw_coopmat_bx_t128x128k32g42s32f32c_texture3d_texture2d_half
D=sarc_linear_dq8ca_coopmat_zpgtr_orin_bf_t128x128k64g24s32mk32ra_texture3d_texture2d_half
# local size 256x1x1; spec 4 = K4_per_group (group 128 -> 32), spec 5 = num_groups (K / 128)
run 4w-K2048   $Q 256 1 1 4=32 5=16
run 4w-K4096   $Q 256 1 1 4=32 5=32
run 4w-K8192   $Q 256 1 1 4=32 5=64
run 4w-f32-K14336 $X 256 1 1 4=32 5=112
run 8da4w-K2048 $D 256 1 1 4=32 5=16
run 8da4w-K4096 $D 256 1 1 4=32 5=32
run 8da4w-K14336 $D 256 1 1 4=32 5=112
# attention: local size 32x1x1; spec 4 = out row stride (heads * head_dim), spec 6 = context capacity
run sdpa-d64-1b  sarc_dev_orin_sdpa_fused3sb_d64_t32x32g11s32rko_buffer_buffer_half 32 1 1 4=2048 6=2048
run sdpa-d128-8b sarc_dev_orin_sdpa_fused3sb_d128_t16x64g11s32rko_buffer_buffer_half 32 1 1 4=4096 6=2048
echo "DONE $(date -u +%FT%TZ)" >> status

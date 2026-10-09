#!/bin/bash
# sweep-4w.sh <binary> <outdir> <tile>...: per tile, 4w correctness (both storages) + 1B prefill perf (both storages).
B=$1; O=$2; shift 2; mkdir -p $O; cd $O
exec 9>>$HOME/.cache/gpu-lab/lock-86800be2-0000-0000-0300-000000000000; flock -n 9 || { echo busy; exit 75; }
export ETVK_DEVICE_INDEX=0 ET_VK_TEXTURE_COOPMAT=1
timeout 3600 intel_gpu_top -d drm:/dev/dri/card0 -J -s 500 -o gpu-top.json >/dev/null 2>&1 & GT=$!
for t in "$@"; do
  export ET_VK_Q4GSW_COOPMAT_VARIANT=tsweep_dbuf4_xe2_$t
  $B --correctness-only --scheme=4w > corr-$t.log 2>&1
  $B --linear --regime=prefill --scheme=4w --model=3.2-1b --skip-correctness --json-out=perf-$t.json > perf-$t.log 2>&1
done
kill $GT

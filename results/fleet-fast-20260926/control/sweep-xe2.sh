#!/bin/bash
# sweep-xe2.sh <binary> <outdir> <scheme 4w|8da4w> <tile>...: per tile, correctness (both storages) + 1B prefill perf (both storages), with sysfs clock sampling.
B=$1; O=$2; S=$3; shift 3; mkdir -p $O; cd $O
exec 9>>$HOME/.cache/gpu-lab/lock-86800be2-0000-0000-0300-000000000000; flock -n 9 || { echo busy; exit 75; }
export ETVK_DEVICE_INDEX=0 ET_VK_TEXTURE_COOPMAT=1
$(dirname $0)/xe-sample.sh clocks-$S.tsv 9>&- & SP=$!
for t in "$@"; do
  if [ $S = 4w ]; then export ET_VK_Q4GSW_COOPMAT_VARIANT=tsweep_dbuf4_xe2_$t; else export ET_VK_DQ8CA_COOPMAT_VARIANT=tsweep_dbuf4zpg_xe2_$t; fi
  $B --correctness-only --scheme=$S > corr-$S-$t.log 2>&1
  $B --linear --regime=prefill --scheme=$S --model=3.2-1b --skip-correctness --json-out=perf-$S-$t.json > perf-$S-$t.log 2>&1
done
kill $SP

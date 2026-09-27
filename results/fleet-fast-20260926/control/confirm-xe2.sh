#!/bin/bash
# confirm-xe2.sh <binary> <outdir> <q4gsw tile> <dq8ca tile>: all-model prefill, both storages, 3 reps WMMA + 3 reps forced tiled; clocks sampled.
B=$1; O=$2; T4=$3; T8=$4; mkdir -p $O; cd $O
exec 9>>$HOME/.cache/gpu-lab/lock-86800be2-0000-0000-0300-000000000000; flock -n 9 || { echo busy; exit 75; }
export ETVK_DEVICE_INDEX=0 ET_VK_TEXTURE_COOPMAT=1 ET_VK_Q4GSW_COOPMAT_VARIANT=tsweep_dbuf4_xe2_$T4 ET_VK_DQ8CA_COOPMAT_VARIANT=tsweep_dbuf4zpg_xe2_$T8
$(dirname $0)/xe-sample.sh clocks.tsv 9>&- & SP=$!
for r in 1 2 3; do
  $B --linear --regime=prefill --skip-correctness --json-out=linear-r$r.json > linear-r$r.log 2>&1
  $B --baseline --regime=prefill --skip-correctness --json-out=baseline-r$r.json > baseline-r$r.log 2>&1
done
kill $SP; echo DONE > done.txt

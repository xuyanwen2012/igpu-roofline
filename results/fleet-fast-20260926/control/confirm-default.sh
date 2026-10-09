#!/bin/bash
# confirm-default.sh <binary> <outdir>: branch defaults only (no ET_VK_* overrides): 10x correctness, 3x --linear, 3x --baseline, all-model prefill.
B=$1; O=$2; mkdir -p $O; cd $O
exec 9>>$HOME/.cache/gpu-lab/lock-86800be2-0000-0000-0300-000000000000; flock -w 900 9 || { echo busy; exit 75; }
export ETVK_DEVICE_INDEX=0
$(dirname $0)/xe-sample.sh clocks.tsv 9>&- & SP=$!
for r in $(seq 1 10); do $B --correctness-only > correctness-r$r.log 2>&1; done
for r in 1 2 3; do
  $B --linear --regime=prefill --skip-correctness --json-out=linear-r$r.json > linear-r$r.log 2>&1
  $B --baseline --regime=prefill --skip-correctness --json-out=baseline-r$r.json > baseline-r$r.log 2>&1
done
kill $SP; echo DONE > done.txt

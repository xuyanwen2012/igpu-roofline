#!/bin/bash
# run-microbench.sh <binary> <outdir> <gpu-lab uuid> <device index> [--with-baseline]
# Holds gpu-lab's device lock; correctness twice (back to back), --linear x3, optional --baseline x3.
set -u
B=$1; O=$2; U=$3; export ETVK_DEVICE_INDEX=$4; WB=${5:-}
mkdir -p $O; cd $O
exec 9>>$HOME/.cache/gpu-lab/lock-$U
flock -n 9 || { echo "gpu-lab lock busy"; exit 75; }
{ date -u +%FT%TZ; uname -a; vulkaninfo --summary 2>/dev/null | grep -E "deviceName|driverInfo|apiVersion"; sha256sum $B; } > env.txt
for r in 1 2; do $B --correctness-only > correctness-r$r.log 2>&1; done
for r in 1 2 3; do $B --linear --regime=prefill --skip-correctness --json-out=linear-r$r.json > linear-r$r.log 2>&1; done
if [ "$WB" = --with-baseline ]; then for r in 1 2 3; do $B --baseline --regime=prefill --skip-correctness --json-out=baseline-r$r.json > baseline-r$r.log 2>&1; done; fi
echo DONE > done.txt

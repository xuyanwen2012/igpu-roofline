#!/bin/bash
# oa-record.sh <outdir> <metric> <scheme> <storage> [env...]: record Xe OA (sudo xe-perf-recorder, 1 ms) while the microbench runs 1B prefill for <scheme>/<storage>.
# Requires dev.xe.observation_paranoid=0 (owner-approved, restored afterwards by the caller).
O=$1; M=$2; S=$3; ST=$4; shift 4; mkdir -p $O; cd $O
B=${BIN:?}
exec 9>>$HOME/.cache/gpu-lab/lock-86800be2-0000-0000-0300-000000000000; flock -w 600 9 || { echo busy; exit 75; }
sudo -n xe-perf-recorder -d 0 -m $M -p 0.001 -o oa-$M-$S-$ST.rec 9>&- > rec-$M-$S-$ST.log 2>&1 & RP=$!
sleep 1
env ETVK_DEVICE_INDEX=0 "$@" $B --linear --regime=prefill --scheme=$S --storage=$ST --model=3.2-1b --skip-correctness > bench-$M-$S-$ST.log 2>&1
sleep 0.5; sudo -n kill -INT $(pgrep -f "xe-perf-recorder -d 0 -m $M") 2>/dev/null; wait $RP 2>/dev/null
sudo -n chown $(id -u):$(id -g) oa-$M-$S-$ST.rec

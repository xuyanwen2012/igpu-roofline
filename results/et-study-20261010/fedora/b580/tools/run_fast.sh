#!/bin/bash
# run_fast.sh: part A. One `fast` plan of igpu-roofline on the Arc B580 as found (nothing pinned or changed),
# detached; status in logs/partA.status. Busy preflight as the September campaign's control/campaign.py:
# gpu-lab harness busy_pct below the device's busy_threshold (50) of control/campaign-config.json.
. "$(dirname "$(readlink -f "$0")")/guard.sh"; REPO=$(cd $ROOT/../../../.. && pwd); cd $REPO
export UV_CACHE_DIR=$REPO/.uv-cache TMPDIR=$REPO/.tmp IGPU_ROOFLINE_GPU=B580 IGPU_ROOFLINE_STAGE=$REPO/.tmp/stage
N=${1:-partA}; S=$LOGS/$N.status
b=$(busy_pct); echo "$(date -u +%FT%TZ) preflight busy_pct=$b threshold=50" > $S
(( ${b%.*} >= 50 )) && { echo "$(date -u +%FT%TZ) BUSY not started" >> $S; exit 77; }
F=/sys/bus/pci/devices/0000:03:00.0/tile0/gt0/freq0
echo "clock policy as found: min $(<$F/min_freq) max $(<$F/max_freq) rp0 $(<$F/rp0_freq) rpn $(<$F/rpn_freq) MHz, power_profile $(<$F/power_profile)" >> $S
echo "$(date -u +%FT%TZ) RUNNING pid $$" >> $S
gpu_job $N uv run igpu-roofline --results results/et-study-20261010/fedora run --local --local-name b580 --plan fast > $LOGS/$N.log 2>&1; rc=$?
echo "$(date -u +%FT%TZ) DONE rc=$rc $(cat $ROOT/workflow-state.json 2>/dev/null | tr -d '\n' | cut -c1-300)" >> $S

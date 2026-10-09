#!/bin/bash
# run-roofline.sh <plan> : part A of et-study-20261010 on the RTX 4070 Ti SUPER host.
# Holds gpu-lab's device lock for the whole run (the roofline tool takes its own lock), samples nvidia-smi
# (clock, temperature, power, throttle reasons) every 2 s and lists every GPU client seen every 2 s.
# Changes no device setting. Status: $S/status.txt (RUNNING / DONE rc=N / LOCK_BUSY / FOREIGN_AT_START).
set -u
PLAN=${1:-fast}
S=$HOME/et-study-20261010; SRC=$S/igpu-roofline; RES=$S/results/gpu-dev-4004; NAME=4070ti
UUID=81a511a2-de7e-c3c8-f641-3562c315ffa7
mkdir -p $RES/$NAME-sidecar; SC=$RES/$NAME-sidecar
exec 9>>$HOME/.cache/gpu-lab/lock-$UUID
flock -n 9 || { echo "LOCK_BUSY $(date -u +%FT%TZ)" > $S/status.txt; exit 75; }
clients() { { nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null
              nvidia-smi pmon -c 1 2>/dev/null | awk '$1 != "#" && $2 ~ /^[0-9]+$/ {print $2}'; } | sort -un |
            while read p; do [ -d /proc/$p ] && echo "$p:$(cat /proc/$p/comm 2>/dev/null)"; done | tr '\n' ';'; }
c=$(clients)
[ -n "$c" ] && { echo "FOREIGN_AT_START $(date -u +%FT%TZ) $c" > $S/status.txt; exit 76; }
{ date -u +%FT%TZ; uname -r; nvidia-smi --query-gpu=name,driver_version,pstate,temperature.gpu,power.draw,power.limit,clocks.gr,clocks_event_reasons.active --format=csv
  vulkaninfo --summary 2>/dev/null | grep -E "deviceName|driverInfo|apiVersion|deviceUUID"
  systemctl is-active zun-flux-pipeline; git -C $SRC rev-parse HEAD; git -C $SRC status --porcelain --untracked-files=no | wc -l
  sha256sum $SRC/build/host/roofline $SRC/build/host/inspect $SRC/build/shader-manifest.json; } > $SC/env-$PLAN-$(date -u +%H%M%S).txt 2>&1
nvidia-smi --query-gpu=timestamp,clocks.gr,temperature.gpu,power.draw,utilization.gpu,pstate,clocks_event_reasons.active,clocks_event_reasons.sw_thermal_slowdown,clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.hw_slowdown,clocks_event_reasons.sw_power_cap \
  --format=csv -lms 2000 >> $SC/nvidia-smi-samples.csv 2>&1 9>&- &
SMI=$!
( while :; do o=$(clients); [ -n "$o" ] && echo "$(date -u +%FT%TZ) $o"; sleep 2; done ) >> $SC/gpu-clients.log 9>&- &
CW=$!
echo "RUNNING $(date -u +%FT%TZ) plan=$PLAN pid=$$" > $S/status.txt
cd $SRC
.venv/bin/igpu-roofline --results $RES run --local --local-name $NAME --plan $PLAN >> $S/roofline-$PLAN.log 2>&1
rc=$?
kill $SMI $CW 2>/dev/null
echo "DONE $(date -u +%FT%TZ) plan=$PLAN rc=$rc" > $S/status.txt

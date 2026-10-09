#!/bin/bash
# parta_device.sh [plan args...]: device side, part A. Runs the unmodified igpu-roofline (tree copied to
# ~/roofline-study-20261010/roofline, runner cross-built from the same commit) with `run --local --plan fast`
# under the campaign's gpu-lab device lock; the tool takes its own lock in addition. Records clock / load /
# temperature every second, the power mode before and after, and any known foreign GPU program seen meanwhile.
# Changes no clock, power mode or service. Resume = run it again (the tool skips finished configurations).
set -u
S=$HOME/roofline-study-20261010; T=$S/roofline; O=$S/partA; mkdir -p $O/logs; N=$(date -u +%Y%m%dT%H%M%SZ)
G=/sys/class/devfreq/17000000.gpu; L=/sys/devices/platform/17000000.gpu/load
for GZ in /sys/class/thermal/thermal_zone*; do [[ $(cat $GZ/type 2>/dev/null) == gpu-thermal ]] && break; done
snap() { echo "$(date -u +%FT%TZ) clk=$(cat $G/cur_freq) min=$(cat $G/min_freq) max=$(cat $G/max_freq) gov=$(cat $G/governor) temp_mC=$(cat $GZ/temp) $(nvpmodel -q 2>/dev/null | tr '\n' ' ')"; }
foreign() { pgrep -a -x 'llama_main|test_llama_micr|logits_dump|llama-server|ollama|vllm' | cut -c1-120; }
echo "RUNNING $(date -u +%FT%TZ) $*" > $O/status
exec 9>>"$HOME/.cache/gpu-lab/lock-b49259c9-868c-5b7c-b6f1-65a2bf4b63be"; flock -w 1800 9 || { echo "LOCK_BUSY $(date -u +%FT%TZ)" >> $O/status; exit 75; }
F=$(foreign); [[ -n $F ]] && { echo "FOREIGN before: $F" >> $O/status; exit 76; }
{ sha256sum $T/build/host/roofline $T/build/host/roofline_sustained $T/build/host/inspect $T/build/shader-manifest.json; cat $T/SOURCE.txt; snap; } > $O/logs/env-$N.txt
( exec 9>&-; while :; do echo "${EPOCHREALTIME} $(cat $G/cur_freq) $(cat $L) $(cat $GZ/temp)"; sleep 1; done > $O/logs/clock-$N.txt ) & MON=$!
( exec 9>&-; while :; do F=$(foreign); [[ -n $F ]] && echo "$(date -u +%FT%TZ) $F" >> $O/logs/foreign-$N.txt; sleep 2; done ) & FW=$!
cd $T; IGPU_ROOFLINE_STAGE=$S/stage python3 -u run.py --results $O/results run --local --local-name orin-naughty "$@" > $O/logs/run-$N.log 2>&1 9>&-; rc=$?
kill $MON $FW 2>/dev/null; snap >> $O/logs/env-$N.txt
echo "DONE rc=$rc $(date -u +%FT%TZ)" >> $O/status

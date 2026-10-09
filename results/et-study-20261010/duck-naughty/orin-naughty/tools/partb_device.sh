#!/bin/bash
# partb_device.sh <name> <reps> <microbench args...>: device side, part B. Runs the final build's
# test_llama_microbench (read-only bundle of the tuning campaign) <reps> times in fresh processes under the
# gpu-lab device lock, from the study's own directory. Records clock / load / temperature every 0.5 s and the
# power mode before and after. Changes no clock, power mode or service; writes nothing into the campaign tree.
set -u
S=$HOME/roofline-study-20261010; NAME=$1; REPS=$2; shift 2
B=$HOME/hmz-sarc-orin-fused/build/topic4/bundle; O=$S/partB/$NAME
[[ -e $O ]] && { echo "$O exists" >&2; exit 2; }
mkdir -p $O; cd $O
G=/sys/class/devfreq/17000000.gpu; L=/sys/devices/platform/17000000.gpu/load
for GZ in /sys/class/thermal/thermal_zone*; do [[ $(cat $GZ/type 2>/dev/null) == gpu-thermal ]] && break; done
snap() { echo "$(date -u +%FT%TZ) clk=$(cat $G/cur_freq) min=$(cat $G/min_freq) max=$(cat $G/max_freq) gov=$(cat $G/governor) temp_mC=$(cat $GZ/temp) $(nvpmodel -q 2>/dev/null | tr '\n' ' ')"; }
others() { pgrep -a -x 'llama_main|test_llama_micr|logits_dump|llama-server|ollama|roofline|roofline_sustai|inspect' | grep -v "^$MYPID " ; }
echo "RUNNING $(date -u +%FT%TZ) $NAME reps=$REPS args=$*" > $O/status
exec 9>>"$HOME/.cache/gpu-lab/lock-b49259c9-868c-5b7c-b6f1-65a2bf4b63be"; flock -w 1800 9 || { echo "LOCK_BUSY" >> $O/status; exit 75; }
MYPID=0; F=$(others); [[ -n $F ]] && { echo "FOREIGN before: $F" >> $O/status; exit 76; }
{ sha256sum $B/test_llama_microbench $B/libllama_runner.so; snap; } > $O/env.txt
( exec 9>&-; while :; do echo "${EPOCHREALTIME} $(cat $G/cur_freq) $(cat $L) $(cat $GZ/temp)"; sleep 0.5; done > $O/clock.txt ) & MON=$!
rc_all=0
for r in $(seq 1 $REPS); do
  env ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=orin-fused1 LD_LIBRARY_PATH=$B $B/test_llama_microbench "$@" --json-out=$O/run$r.json > $O/run$r.log 2>&1 9>&- & MYPID=$!
  while kill -0 $MYPID 2>/dev/null; do F=$(others); [[ -n $F ]] && echo "FOREIGN during run$r: $F" >> $O/status; sleep 1; done
  wait $MYPID; rc=$?; echo "run$r rc=$rc $(date -u +%FT%TZ)" >> $O/status; [[ $rc != 0 ]] && rc_all=$rc
done
kill $MON 2>/dev/null; snap >> $O/env.txt
echo "DONE rc=$rc_all $(date -u +%FT%TZ)" >> $O/status

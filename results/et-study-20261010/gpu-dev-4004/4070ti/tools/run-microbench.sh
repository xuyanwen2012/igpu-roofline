#!/bin/bash
# run-microbench.sh : part B of et-study-20261010 on the RTX 4070 Ti SUPER host. Read-only use of the tuning
# campaign's final build (topic3): 5 processes of test_llama_microbench --linear --regime=prefill (each: 3 warm-up
# + 5 timed iterations per case, kernel median reported) and 5 of --sdpa, final configuration environment.
# Holds gpu-lab's device lock and the roofline tool's device lock; samples nvidia-smi (clock, temperature, power,
# throttle reasons) every 0.5 s and lists GPU clients every 0.5 s. Writes only under ~/et-study-20261010.
set -u
S=$HOME/et-study-20261010; O=$S/microbench; mkdir -p $O $S/tmp; cd $O
B=$HOME/hmz-sarc-4070ti-fused/.artifacts/build/topic3/tests/test_llama_microbench
UUID=81a511a2-de7e-c3c8-f641-3562c315ffa7
exec 9>>$HOME/.cache/gpu-lab/lock-$UUID
flock -n 9 || { echo "LOCK_BUSY $(date -u +%FT%TZ)" > $S/status.txt; exit 75; }
RL=/tmp/igpu-roofline-locks-$(id -u)/$(printf 'vulkan:%s' "${UUID//-/}" | sha256sum | cut -d' ' -f1).lock
exec 8>>$RL
flock -n 8 || { echo "ROOFLINE_LOCK_BUSY $(date -u +%FT%TZ)" > $S/status.txt; exit 75; }
clients() { { nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null
              nvidia-smi pmon -c 1 2>/dev/null | awk '$1 != "#" && $2 ~ /^[0-9]+$/ {print $2}'; } | sort -un |
            while read p; do [ -d /proc/$p ] && echo "$p:$(cat /proc/$p/comm 2>/dev/null)"; done | tr '\n' ';'; }
c=$(clients)
[ -n "$c" ] && { echo "FOREIGN_AT_START $(date -u +%FT%TZ) $c" > $S/status.txt; exit 76; }
export ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=4070ti-fused1 ETVK_DEVICE_INDEX=0 TMPDIR=$S/tmp
{ date -u +%FT%TZ; sha256sum $B; env | grep -E '^ET_?VK'; nvidia-smi --query-gpu=name,driver_version,pstate,temperature.gpu,power.draw,power.limit,clocks.gr,clocks_event_reasons.active --format=csv
  systemctl is-active zun-flux-pipeline; } > env.txt 2>&1
nvidia-smi --query-gpu=timestamp,clocks.gr,temperature.gpu,power.draw,utilization.gpu,pstate,clocks_event_reasons.active,clocks_event_reasons.sw_thermal_slowdown,clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.hw_slowdown,clocks_event_reasons.sw_power_cap \
  --format=csv -lms 500 >> nvidia-smi-samples.csv 2>&1 9>&- 8>&- &
SMI=$!
( while :; do o=$(clients); [ -n "$o" ] && echo "$(date -u +%FT%TZ) $o"; sleep 0.5; done ) >> gpu-clients.log 9>&- 8>&- &
CW=$!
echo "RUNNING $(date -u +%FT%TZ) microbench pid=$$" > $S/status.txt
cool() { local t0=$SECONDS t; while :; do t=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1); (( t > 50 && SECONDS - t0 < 300 )) || break; sleep 5; done; }
: > runs.txt
for r in 1 2 3 4 5; do
  cool; echo "$(date -u +%FT%TZ) start linear-r$r temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)" >> runs.txt
  $B --linear --regime=prefill --skip-correctness --json-out=linear-r$r.json > linear-r$r.log 2>&1 9>&- 8>&-; echo "$(date -u +%FT%TZ) end linear-r$r rc=$?" >> runs.txt
  cool; echo "$(date -u +%FT%TZ) start sdpa-r$r" >> runs.txt
  $B --sdpa --json-out=sdpa-r$r.json > sdpa-r$r.log 2>&1 9>&- 8>&-; echo "$(date -u +%FT%TZ) end sdpa-r$r rc=$?" >> runs.txt
done
kill $SMI $CW 2>/dev/null
echo "DONE $(date -u +%FT%TZ) microbench" > $S/status.txt

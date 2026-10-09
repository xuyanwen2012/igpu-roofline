#!/bin/bash
# partA.sh: one `fast` plan of igpu-roofline on card b70-0, as the September fleet campaign ran it (its
# controller campaign.py, unchanged: it holds the gpu-lab lock of the card and never pins clocks; the tool
# holds its own device lock). Run detached on the device host from ~/et-study-20261010.
# A foreign GPU job invalidates the run: the results move to superseded/foreign-<utc>/, the script waits until
# the cards are clear (at most 30 minutes) and repeats once.
B=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)   # ~/et-study-20261010
T=$B/igpu-roofline; OUT=$B/results/fedora-gpu-eval; L=$B/logs; PY=${STUDY_PYTHON:?python with numpy/matplotlib}
export PYTHONDONTWRITEBYTECODE=1
mkdir -p $OUT $L; cd $T || exit 2
for try in 1 2; do
  echo "$(date -u +%FT%TZ) partA try $try" >> $L/partA.log
  $PY $B/tools/guard_run.py $L/partA-try$try $PY -u campaign.py $OUT fedora-gpu-eval b70 > $L/partA-try$try.controller.log 2>&1; rc=$?
  echo "$(date -u +%FT%TZ) partA try $try rc=$rc" >> $L/partA.log
  [[ $rc != 76 ]] && break
  mkdir -p $OUT/superseded; mv $OUT/b70 $OUT/superseded/foreign-$(date -u +%Y%m%dT%H%M%SZ)
  [[ $try == 2 ]] && break
  t0=$SECONDS; while (( SECONDS - t0 < 1800 )); do
    $PY $B/tools/guard_run.py $L/partA-clearcheck true >/dev/null 2>&1 && break; sleep 30; done
  (( SECONDS - t0 >= 1800 )) && { echo "$(date -u +%FT%TZ) foreign GPU job for 30 minutes: stop" >> $L/partA.log; break; }
done
if [[ $rc == 0 ]]; then $PY -m igpu_roofline.cli --results $OUT report --device b70 > $L/partA-report.log 2>&1; echo "$(date -u +%FT%TZ) report rc=$?" >> $L/partA.log; fi
echo "$(date -u +%FT%TZ) partA done rc=$rc" >> $L/partA.log

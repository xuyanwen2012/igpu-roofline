#!/bin/bash
# Print workflow-state and last log lines for every device of fleet-fast-20260926.
S="ssh -o BatchMode=yes -o ConnectTimeout=8"
q='for f in $(find RES -name workflow-state.json 2>/dev/null); do echo "$f: $(tr -d "\n " < $f | cut -c1-220)"; done; for l in LOGS; do echo "-- $l"; tail -n 3 $l; done'
run() { local h=$1 res=$2 logs=$3; local c=${q//RES/$res}; c=${c//LOGS/$logs}; echo "=== $h"; if [ $h = fedora ]; then bash -c "$c"; else echo "$c" | $S -o HostKeyAlias=$h doremy@$h.tail031559.ts.net bash -s; fi; }
run rocky-ryzen /home/doremy/igpu-roofline/campaigns/780m/2026-09-26-fast-et-study /home/doremy/igpu-roofline/fleet/fleet-fast-20260926/controller-780m.log
run fedora-gpu-eval /home/doremy/.cache/igpu-roofline/fleet-fast-20260926/results /home/doremy/.cache/igpu-roofline/fleet-fast-20260926/controller-b70-0.log
run fedora /home/doremy/.cache/igpu-roofline/fleet-fast-20260926/results "/home/doremy/.cache/igpu-roofline/fleet-fast-20260926/controller-b580.log /home/doremy/.cache/igpu-roofline/fleet-fast-20260926/controller-s24.log /home/doremy/.cache/igpu-roofline/fleet-fast-20260926/controller-pixel-7a.log"

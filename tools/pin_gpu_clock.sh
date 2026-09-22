#!/bin/sh
# Pin (or restore) GPU clocks on a ROOTED Android device before measuring.
# igpu-roofline never runs this; run it yourself. Paths differ by SoC — check first:
#   adb shell 'ls /sys/class/devfreq/; ls /sys/class/kgsl/kgsl-3d0/devfreq 2>/dev/null'
#
# Usage:
#   tools/pin_gpu_clock.sh <serial> list
#   tools/pin_gpu_clock.sh <serial> pin <devfreq-dir> <freq>      # freq as listed in available_frequencies
#   tools/pin_gpu_clock.sh <serial> restore <devfreq-dir> <min> <max> [governor]
# Examples:
#   tools/pin_gpu_clock.sh ABC123 pin /sys/class/kgsl/kgsl-3d0/devfreq 680000000   # Adreno
#   tools/pin_gpu_clock.sh ABC123 pin /sys/class/devfreq/1f000000.mali 848000000   # Mali (Tensor)
set -eu
S=$1; ACTION=$2
sh_root() { adb -s "$S" shell "su -c '$1'"; }
case "$ACTION" in
  list)
    adb -s "$S" shell 'for d in /sys/class/kgsl/kgsl-3d0/devfreq /sys/class/devfreq/*; do
      [ -r $d/cur_freq ] || continue
      echo "$d  governor=$(cat $d/governor 2>/dev/null) min=$(cat $d/min_freq) max=$(cat $d/max_freq) cur=$(cat $d/cur_freq)"
      echo "   available: $(cat $d/available_frequencies 2>/dev/null)"
    done' ;;
  pin)
    D=$3; F=$4
    # Order matters: raise max before min when going up, lower min before max when going down.
    sh_root "echo $F > $D/max_freq; echo $F > $D/min_freq; echo $F > $D/max_freq"
    adb -s "$S" shell "echo now: min=\$(cat $D/min_freq) max=\$(cat $D/max_freq) cur=\$(cat $D/cur_freq)" ;;
  restore)
    D=$3; MIN=$4; MAX=$5; GOV=${6:-}
    sh_root "echo $MAX > $D/max_freq; echo $MIN > $D/min_freq"
    [ -n "$GOV" ] && sh_root "echo $GOV > $D/governor"
    adb -s "$S" shell "echo now: min=\$(cat $D/min_freq) max=\$(cat $D/max_freq)" ;;
  *) echo "unknown action $ACTION"; exit 2 ;;
esac

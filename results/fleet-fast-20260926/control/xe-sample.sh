#!/bin/bash
# xe-sample.sh <out.tsv>: every 0.5 s, B580 GT0 act_freq (MHz), throttle status, hwmon energy (uJ) and temps. Read-only sysfs.
G=/sys/class/drm/card0/device/tile0/gt0/freq0; H=$(ls -d /sys/class/drm/card0/device/hwmon/hwmon* | head -1)
echo -e "t\tact_mhz\tthrottle\tenergy_uj\ttemp_mc" > $1
while :; do echo -e "$(date +%s.%N)\t$(cat $G/act_freq)\t$(cat $G/throttle/status 2>/dev/null)\t$(cat $H/energy1_input 2>/dev/null)\t$(cat $H/temp2_input 2>/dev/null)" >> $1; sleep 0.5; done

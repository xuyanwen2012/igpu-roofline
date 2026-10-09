#!/bin/bash
# partBC.sh: kernel timing (part B) and driver code dumps (part C) of the final configuration on card b70-0,
# with the final build's test_llama_microbench (a byte-identical copy staged under the study directory; the
# ExecuTorch trees are only read). Run detached on the device host. Holds the campaign lock
# (~/.cache/gpu-lab/lock-<uuid>) and the roofline tool's device lock for the whole chain; every GPU job runs
# under tools/guard_run.py. A job stopped by a foreign GPU job (76) is moved to superseded/ and repeated once
# after the cards are clear (waits at most 30 minutes).
B=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd); L=$B/logs; RAW=$B/raw; ISA=$B/isa; ST=$B/stage
PY=${STUDY_PYTHON:?}; U=868023e2-0000-0000-0100-000000000000
SRC=$HOME/hmz-sarc-b70-fused/.artifacts/build/topic2/tests/test_llama_microbench
mkdir -p $L $RAW $ISA $ST; log() { echo "$(date -u +%FT%TZ) $*" >> $L/partBC.log; }
exec 9>>$HOME/.cache/gpu-lab/lock-$U; flock -n 9 || { log "campaign lock busy"; exit 75; }
D=/tmp/igpu-roofline-locks-$(id -u); mkdir -p -m 700 $D
exec 8>>$D/$(printf 'vulkan:%s' "${U//-/}" | sha256sum | cut -d' ' -f1).lock; flock -n 8 || { log "roofline device lock busy"; exit 75; }
[[ -e $ST/test_llama_microbench ]] || cp $SRC $ST/
sha256sum $SRC $ST/test_llama_microbench > $RAW/binary.sha256
MB=$ST/test_llama_microbench
export ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=b70-fused1 ETVK_DEVICE_INDEX=0 PYTHONDONTWRITEBYTECODE=1
T=/sys/bus/pci/devices/0000:01:00.0/hwmon/hwmon*/temp2_input
# job <tag> <stdout file> <stderr file> <command...>
job() { local tag=$1 so=$2 se=$3 rc try; shift 3; cd $B
  for try in 1 2; do
    log "start $tag try $try pkg_temp_mC=$(cat $T)"
    $PY $B/tools/guard_run.py $L/$tag "$@" > $so 2> $se 9>&- 8>&-; rc=$?
    log "end $tag try $try rc=$rc pkg_temp_mC=$(cat $T)"
    [[ $rc != 76 ]] && return $rc
    mkdir -p $B/superseded/foreign-$tag-try$try; mv $so $se $L/$tag.* $B/superseded/foreign-$tag-try$try/ 2>/dev/null
    local t0=$SECONDS; while (( SECONDS - t0 < 1800 )); do $PY $B/tools/guard_run.py $L/clearcheck true > /dev/null 2>&1 9>&- 8>&- && break; sleep 30; done
    (( SECONDS - t0 >= 1800 )) && { log "foreign GPU job for 30 minutes: stop"; exit 76; }
  done; return $rc; }
for r in 1 2 3; do
  job partB-linear-r$r $RAW/linear-r$r.log $RAW/linear-r$r.err timeout 3600 $MB --linear --regime=prefill --storage=texture3d --skip-correctness --json-out=$RAW/linear-r$r.json
  job partB-sdpa-r$r $RAW/sdpa-r$r.log $RAW/sdpa-r$r.err timeout 3600 $MB --sdpa --json-out=$RAW/sdpa-r$r.json
done
log "part B done"
# Part C: the driver's own listing of every compute shader it compiles (Mesa INTEL_DEBUG=cs), disk cache off so
# that the shaders are compiled again. Not a timing run.
export INTEL_DEBUG=cs MESA_SHADER_CACHE_DISABLE=true
dump() { local tag=$1; shift; job partC-$tag $ISA/$tag.stdout.txt $ISA/$tag.intel_debug_cs.txt timeout 3600 $MB "$@"; }
dump 4w-8b    --linear --regime=prefill --storage=texture3d --skip-correctness --scheme=4w    --model=llama-3.1-8b
dump 8da4w-8b --linear --regime=prefill --storage=texture3d --skip-correctness --scheme=8da4w --model=llama-3.1-8b
dump 4w-1b    --linear --regime=prefill --storage=texture3d --skip-correctness --scheme=4w    --model=llama-3.2-1b
dump sdpa-1b  --sdpa --model=llama-3.2-1b
dump sdpa-8b  --sdpa --model=llama-3.1-8b
log "part C dumps done"; log "partBC done"

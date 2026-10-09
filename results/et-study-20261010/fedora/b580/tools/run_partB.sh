#!/bin/bash
# run_partB.sh: part B and the raw captures of part C, detached; status in logs/partB.status.
# Uses the tuning campaign's final build read-only (topic7, binary sha256 recorded in microbench/env.txt) with the
# final configuration ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=b580-fused1 on Vulkan device 0.
#  microbench/<scheme>-r<n>.json : test_llama_microbench --linear --regime=prefill --storage=texture3d (the model
#                                  path), 3 warm-up + 5 timed iterations per shape in each process, 3 processes
#  microbench/sdpa-r<n>.log      : test_llama_microbench --sdpa, 5 processes
#  isa/raw/et-<scheme>.cs.txt    : the same linear run for the 1B model with INTEL_DEBUG=cs and the Mesa on-disk
#                                  shader cache disabled (compile-time dump, timings of these runs are not used)
#  isa/raw/et-sdpa.cs.txt        : likewise for --sdpa
# Every process is one GPU job under the card's campaign lock and the shared desktop-build lock (guard.sh);
# a job during which a foreign GPU workload was seen (status 76) is moved to superseded/foreign/ and repeated once.
. "$(dirname "$(readlink -f "$0")")/guard.sh"; cd $ROOT
BIN=/mnt/linux-share/hmz-campaigns/b580-fused/.artifacts/build/topic7/tests/test_llama_microbench
export TMPDIR=$(cd $ROOT/../../../.. && pwd)/.tmp ETVK_DEVICE_INDEX=0 ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=b580-fused1
S=$LOGS/partB.status; mkdir -p microbench isa/raw superseded/foreign
{ echo "== $(date -u +%FT%TZ)"; sha256sum $BIN; echo "env ETVK_DEVICE_INDEX=0 ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=b580-fused1"; } >> microbench/env.txt
job() { local n=$1 out=$2 try rc; shift 2
  for try in 1 2; do
    [[ -s $out.rc && $(<$out.rc) == 0 ]] && return 0
    gpu_job $n "$@" > $out.log 2>&1; rc=$?; echo $rc > $out.rc
    echo "$(date -u +%FT%TZ) $n try $try rc=$rc" >> $S
    [[ $rc == 76 ]] || return $rc
    mkdir -p superseded/foreign/$n-$try; mv $out.* $LOGS/$n.* superseded/foreign/$n-$try/ 2>/dev/null
  done; return 76; }
echo "$(date -u +%FT%TZ) RUNNING pid $$" > $S
for r in 1 2 3; do for q in 4w 8da4w; do
  job mb-$q-r$r microbench/$q-r$r $BIN --linear --regime=prefill --scheme=$q --storage=texture3d --skip-correctness --json-out=$ROOT/microbench/$q-r$r.json
done; done
for r in 1 2 3 4 5; do job mb-sdpa-r$r microbench/sdpa-r$r $BIN --sdpa; done
export INTEL_DEBUG=cs MESA_SHADER_CACHE_DISABLE=true
for q in 4w 8da4w; do
  job cs-$q isa/raw/et-$q.cs $BIN --linear --regime=prefill --scheme=$q --storage=texture3d --skip-correctness --model=llama-3.2-1b --json-out=$ROOT/isa/raw/et-$q.cs.json
done
job cs-sdpa isa/raw/et-sdpa.cs $BIN --sdpa
echo "$(date -u +%FT%TZ) DONE" >> $S

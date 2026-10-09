#!/bin/bash
# run-et-microbench.sh <microbench binary> <outdir>
# Part B/C of et-study-20261010 on the 780M: timing of the final configuration's linear and fused
# attention kernels, then one RADV shader dump per scheme. Read-only on the ExecuTorch build; all
# output goes to <outdir>. Holds the campaign (gpu-lab) lock for the whole script. No clock change,
# no monitor process: the GPU clock is read once before and after each invocation only.
set -u
B=$1; O=$2
U=00000000-c400-0000-0000-000000000000
mkdir -p "$O" && cd "$O" || exit 1
exec 9>>"$HOME/.cache/gpu-lab/lock-$U"
flock -n 9 || { echo "campaign lock busy" > status.txt; exit 75; }
export ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=780m-final
clk() { echo "$(date -u +%FT%TZ) $1 sclk=$(grep '\*' /sys/class/drm/card*/device/pp_dpm_sclk | tr -d '\n') busy=$(cat /sys/class/drm/card*/device/gpu_busy_percent) load=$(cut -d' ' -f1-3 /proc/loadavg)" >> clock.txt; }
{ date -u +%FT%TZ; uname -r; vulkaninfo --summary 2>/dev/null | grep -E "deviceName|driverInfo|apiVersion" | head -3; sha256sum "$B"; env | grep ET_VK; } > env.txt
echo "running linear" > status.txt
# r0 is a warm-up invocation (kept, not used); r1..r5 are the timed repeats (each: 3 warm + 5 timed runs per case).
for r in 0 1 2 3 4 5; do
  clk "linear-r$r start"
  "$B" --linear --regime=prefill --skip-correctness --json-out=linear-r$r.json > linear-r$r.log 2>&1; echo "linear-r$r rc=$?" >> rc.txt
  clk "linear-r$r end"
done
echo "running sdpa" > status.txt
for r in 1 2 3; do
  clk "sdpa-r$r start"
  ET_VK_SDPA_PERF_RUNS=40,10 "$B" --sdpa --regime=prefill --skip-correctness --json-out=sdpa-r$r.json > sdpa-r$r.log 2>&1; echo "sdpa-r$r rc=$?" >> rc.txt
  clk "sdpa-r$r end"
done
echo "running isa dumps" > status.txt
# Part C: ACO disassembly of the dispatched pipelines (compile and inspect; timings of these runs are not used).
for s in 4w 8da4w; do
  RADV_DEBUG=shaders,shaderstats MESA_SHADER_CACHE_DISABLE=true "$B" --linear --scheme=$s --storage=texture3d --regime=prefill --model=llama-3.2-1b --skip-correctness --json-out=isa-$s.json > isa-$s.stdout 2> isa-$s.stderr; echo "isa-$s rc=$?" >> rc.txt
done
RADV_DEBUG=shaders,shaderstats MESA_SHADER_CACHE_DISABLE=true "$B" --sdpa --regime=prefill --model=llama-3.2-1b --skip-correctness --json-out=isa-sdpa.json > isa-sdpa.stdout 2> isa-sdpa.stderr; echo "isa-sdpa rc=$?" >> rc.txt
clk "end"
echo "finished $(date -u +%FT%TZ)" > status.txt

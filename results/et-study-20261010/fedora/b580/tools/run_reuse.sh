#!/bin/bash
# run_reuse.sh: confirmation repeats for the shared-fed matrix rows at the kernels' reuse. The `fast` plan of
# part A confirms only the two fastest candidates of each roof (CHAINS 8 and 4), so its `matrix_feed_by_reuse`
# rows at CHAINS 1 and 2 are single validated sweep runs. This is a focused run of the unmodified tool
# (same build, same plan, same grid: selectors only narrow the plan) into its own results directory
# ../b580-reuse, where the selected variants are the only candidates and are therefore the ones confirmed.
. "$(dirname "$(readlink -f "$0")")/guard.sh"; REPO=$(cd $ROOT/../../../.. && pwd); cd $REPO
export UV_CACHE_DIR=$REPO/.uv-cache TMPDIR=$REPO/.tmp IGPU_ROOFLINE_GPU=B580 IGPU_ROOFLINE_STAGE=$REPO/.tmp/stage
S=$LOGS/reuse.status; echo "$(date -u +%FT%TZ) RUNNING pid $$ busy_pct=$(busy_pct)" > $S
for v in matrix_int8_8x16x32_c2_lds matrix_fp16_fp32_8x16x16_c2_lds matrix_fp16_8x16x16_c2_lds matrix_fp16_8x16x16_c4_lds; do
  gpu_job reuse-$v uv run igpu-roofline --results results/et-study-20261010/fedora run --local --local-name b580-reuse-$v \
    --plan fast --stage matrix_feed --variant $v > $LOGS/reuse-$v.log 2>&1
  echo "$(date -u +%FT%TZ) $v rc=$?" >> $S
done
echo "$(date -u +%FT%TZ) DONE" >> $S

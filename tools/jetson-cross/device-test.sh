#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/.cache/et-jetson-cross-0270403ba"
export LD_LIBRARY_PATH="$PWD${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# Share gpu-lab's native lock; no clock/power changes.
lock="$HOME/.cache/gpu-lab/lock-b49259c9-868c-5b7c-b6f1-65a2bf4b63be"
mkdir -p "$(dirname "$lock")"
exec 9<>"$lock"
flock -n 9 || { echo 'GPU owned by another job'; exit 75; }
if ps -eo comm= | grep -Eq '^(roofline|roofline_sustai|llama_main|test_llama_micr|llama-server)$'; then
  echo 'Another GPU workload is running'; exit 75
fi
printf '%s\n' "$$" > "$lock"
mode=$1
scheme=$2
case "$scheme" in 4w|8da4w) ;; *) exit 2;; esac
export ET_VK_COOPMAT_ANY_DEVICE=0
if [[ "$mode" != tiled ]]; then
  export ET_VK_COOPMAT_ANY_DEVICE=1
  export ET_VK_TEXTURE_COOPMAT=1
  export ET_VK_Q4GSW_COOPMAT_VARIANT=tsweep_dbuf4_t128x128k16g22s32
  export ET_VK_DQ8CA_COOPMAT_VARIANT=tsweep_dbuf4zpgtr_mk32_t128x128k32g44s32
fi
case "$mode" in
  correctness)
    timeout --signal=TERM --kill-after=10s 120s ./test_llama_microbench \
      --correctness-only --scheme="$scheme" --storage=texture3d ;;
  production)
    timeout --signal=TERM --kill-after=10s 120s ./test_llama_microbench \
      --production-diff --production-diff-model=llama-3.2-1b \
      --production-diff-op="$scheme" --production-diff-storage=texture3d --ref-samples=8192 ;;
  tiled|wmma)
    prompt=(--prompt='Once upon a time, in a small village,')
    tokens=32
    if [[ "$mode" == wmma ]]; then prompt=(--prompt_file=prompt_256.txt); tokens=8; fi
    timeout --signal=TERM --kill-after=10s 180s ./llama_main \
      --model_path="llama3_2-1b_vulkan_${scheme}.pte" \
      --tokenizer_path=tokenizer.model "${prompt[@]}" \
      --max_new_tokens="$tokens" --temperature=0 \
      --etdump_path="${mode}-${scheme}.etdp" ;;
  *) exit 2;;
esac

#!/usr/bin/env bash
set -euo pipefail
version=${1:?usage: build-version.sh VERSION}
[[ "$version" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 2
repo=$(cd "$(dirname "$0")/../.." && pwd)
checkout=/home/doremy/Desktop/sarc-acl/yanwen/release14-quant-shaders-jetson/executorch
work=$repo/out/jetson-cross
output=$repo/out/jetson-study/builds/$version
[[ ! -e "$output" ]] || { echo "Preserving existing build: $output"; exit 2; }
mkdir -p "$output"
# Sync only the isolated branch's study changes into the disposable build snapshot.
while IFS= read -r -d '' path; do
  [[ -f "$checkout/$path" ]] || { echo "Unsupported deleted source: $path"; exit 2; }
  mkdir -p "$work/source/executorch/$(dirname "$path")"
  cp "$checkout/$path" "$work/source/executorch/$path"
done < <(git -C "$checkout" diff --name-only -z)
git -C "$checkout" diff > "$output/source.patch"
git -C "$checkout" rev-parse HEAD > "$output/source-head.txt"
"$repo/tools/jetson-cross/container.sh" > "$output/build.log" 2>&1
cp "$work/bundle/llama_main" "$output/llama_main-trace"
cp "$work/bundle/test_llama_microbench" "$work/bundle/libllama_runner.so" "$output/"
podman run --rm --userns=keep-id \
  -v "$repo/tools/jetson-cross:/recipe:ro,Z" -v "$work:/work:Z" \
  localhost/et-jetson-cross:jp7.2.1 bash -c '
    cmake -S /work/source/executorch/examples/models/llama \
      -B /work/build/examples/models/llama -DEXECUTORCH_ENABLE_EVENT_TRACER=OFF
    cmake --build /work/build/examples/models/llama --target llama_main -j8
    cp /work/build/examples/models/llama/llama_main /work/bundle/llama_main-clean
  ' > "$output/clean-runner-build.log" 2>&1
cp "$work/bundle/llama_main-clean" "$output/llama_main"
sha256sum "$output/llama_main" "$output/llama_main-trace" \
  "$output/libllama_runner.so" "$output/test_llama_microbench" > "$output/sha256.txt"

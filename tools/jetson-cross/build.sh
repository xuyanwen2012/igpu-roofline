#!/usr/bin/env bash
set -euo pipefail
cd /work/source/executorch
export PYTHONPATH=/work/source
common=(-DCMAKE_TOOLCHAIN_FILE=/recipe/aarch64.cmake -DCMAKE_BUILD_TYPE=Release -DPYTHON_EXECUTABLE=/opt/venv/bin/python)
mkdir -p /work/bundle
# Headers are architecture-neutral; do not add the host's /usr/include to ARM search paths.
aarch64-linux-gnu-g++ -O2 -std=c++17 /recipe/smoke.cpp \
  -I/work/source/executorch/backends/vulkan/third-party/Vulkan-Headers/include \
  -ldl -o /work/bundle/vulkan-smoke
if [[ ${1:-} == smoke ]]; then exit 0; fi
cmake --preset llm-release -B /work/build -G Ninja "${common[@]}" \
  -DCMAKE_INSTALL_PREFIX=/work/build \
  -DEXECUTORCH_BUILD_VULKAN=ON -DEXECUTORCH_BUILD_DEVTOOLS=ON \
  -DEXECUTORCH_ENABLE_EVENT_TRACER=ON -DEXECUTORCH_BUILD_XNNPACK=OFF \
  -DEXECUTORCH_BUILD_EXTENSION_ASR_RUNNER=OFF \
  -DEXECUTORCH_BUILD_TESTS=OFF -DEXECUTORCH_BUILD_CUDA=OFF \
  -DEXECUTORCH_VULKAN_SHADER_COMPILE_NTHREADS=8
cmake --build /work/build --target install -j8
cmake -S examples/models/llama -B /work/build/examples/models/llama -G Ninja "${common[@]}" \
  -DCMAKE_PREFIX_PATH=/work/build -DCMAKE_FIND_ROOT_PATH='/work/build;/usr/aarch64-linux-gnu' \
  -DEXECUTORCH_BUILD_VULKAN=ON -DEXECUTORCH_ENABLE_EVENT_TRACER=ON
cmake --build /work/build/examples/models/llama --target llama_main -j8
cmake -S backends/vulkan/test/custom_ops -B /work/microbench -G Ninja "${common[@]}" \
  -DCMAKE_PREFIX_PATH=/work/build -DCMAKE_FIND_ROOT_PATH='/work/build;/usr/aarch64-linux-gnu' \
  -DEXECUTORCH_BUILD_VULKAN=ON -DEXECUTORCH_VULKAN_SHADER_COMPILE_NTHREADS=8
cmake --build /work/microbench --target test_llama_microbench -j8
cp /work/build/examples/models/llama/llama_main /work/bundle/
cp /work/build/examples/models/llama/runner/libllama_runner.so /work/bundle/
cp /work/microbench/test_llama_microbench /work/bundle/
file /work/bundle/*

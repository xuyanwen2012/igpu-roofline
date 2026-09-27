#!/bin/bash
# Usage (inside et-vk-build:rocky10): build-microbench-host.sh <executorch dir> <out prefix>
# Host-only variant of build-microbench.sh (main: default build type, tests: Debug, as build_and_run.sh).
set -eux
ET=$1; OUT=$2
cd $ET; export PYTHONPATH=$(dirname $ET)
GL=$(which glslc)
cmake . -DCMAKE_INSTALL_PREFIX=$OUT-host -DEXECUTORCH_BUILD_VULKAN=ON -DPYTHON_EXECUTABLE=/usr/bin/python3 -DGLSLC_PATH=$GL -B$OUT-host
cmake --build $OUT-host -j12 --target install
cmake backends/vulkan/test/custom_ops/ -DCMAKE_INSTALL_PREFIX=$OUT-host -DCMAKE_BUILD_TYPE=Debug -DGLSLC_PATH=$GL -B$OUT-host/backends/vulkan/test/custom_ops
cmake --build $OUT-host/backends/vulkan/test/custom_ops -j12 --target test_llama_microbench
echo BUILD_OK

#!/bin/bash
# Usage (inside et-vk-build:rocky10): build-microbench.sh <executorch dir> <out prefix>
# Mirrors backends/vulkan/test/custom_ops/build_and_run.sh (main: default build type, tests: Debug).
set -eux
ET=$1; OUT=$2; NDK=/home/doremy/android-ndk-r30
cd $ET; export PYTHONPATH=$(dirname $ET)
GL=$(which glslc)
cmake . -DCMAKE_INSTALL_PREFIX=$OUT-host -DEXECUTORCH_BUILD_VULKAN=ON -DPYTHON_EXECUTABLE=/usr/bin/python3 -DGLSLC_PATH=$GL -B$OUT-host
cmake --build $OUT-host -j12 --target install
cmake backends/vulkan/test/custom_ops/ -DCMAKE_INSTALL_PREFIX=$OUT-host -DCMAKE_BUILD_TYPE=Debug -DGLSLC_PATH=$GL -B$OUT-host/backends/vulkan/test/custom_ops
cmake --build $OUT-host/backends/vulkan/test/custom_ops -j12 --target test_llama_microbench
A="-DCMAKE_TOOLCHAIN_FILE=$NDK/build/cmake/android.toolchain.cmake -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-28"
cmake . -DCMAKE_INSTALL_PREFIX=$OUT-android -DEXECUTORCH_BUILD_VULKAN=ON -DPYTHON_EXECUTABLE=/usr/bin/python3 $A -DGLSLC_PATH=$GL -B$OUT-android
cmake --build $OUT-android -j12 --target install
cmake backends/vulkan/test/custom_ops/ -DCMAKE_INSTALL_PREFIX=$OUT-android -DCMAKE_BUILD_TYPE=Debug $A -DGLSLC_PATH=$GL -B$OUT-android/backends/vulkan/test/custom_ops
cmake --build $OUT-android/backends/vulkan/test/custom_ops -j12 --target test_llama_microbench
echo BUILD_OK

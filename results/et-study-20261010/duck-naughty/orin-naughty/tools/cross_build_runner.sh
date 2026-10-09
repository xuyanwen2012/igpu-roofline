#!/bin/bash
# Cross-build of the unmodified runner for aarch64 (waits for the workstation build lock).
cd /mnt/linux-share/hmz-campaigns/roofline-study/orin/igpu-roofline
echo "WAITING $(date -u +%FT%TZ)" > out/orin-cross/status
exec 9> ~/.cache/gpu-lab/lock-desktop-build; flock 9
echo "RUNNING $(date -u +%FT%TZ)" > out/orin-cross/status
podman run --rm --userns=keep-id --security-opt label=disable -v "$PWD:/src:ro" -v "$PWD/out/orin-cross:/work" localhost/et-jetson-cross:jp7.2.1 bash -c 'set -e; cmake -S /src/runner -B /work/build -DCMAKE_TOOLCHAIN_FILE=/src/tools/jetson-cross/aarch64.cmake -DVULKAN_LINK=/work/sysroot/libvulkan.so.1 -DVULKAN_INCLUDE=/opt/vulkan/1.4.341.1/x86_64/include; cmake --build /work/build -j8; aarch64-linux-gnu-g++ --version | head -1'
echo "DONE rc=$? $(date -u +%FT%TZ)" > out/orin-cross/status

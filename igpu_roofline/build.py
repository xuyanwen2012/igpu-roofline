"""Build the shaders (with ledger checks) and the Android runner."""

import glob
import os
import shutil
import subprocess
from pathlib import Path

from . import paths, shaders

REQUIRED_TOOLS = ("glslc", "spirv-val", "spirv-dis", "spirv-as", "cmake")
NDK_GUESSES = [
    "~/Library/Android/sdk/ndk/*",
    "~/Android/Sdk/ndk/*",
    "~/android-ndk-r*",
    "/opt/android-ndk*",
]


def find_ndk() -> Path:
    env = os.environ.get("ANDROID_NDK_HOME") or os.environ.get("ANDROID_NDK_ROOT")
    candidates = [env] if env else []
    for pattern in NDK_GUESSES:
        candidates += sorted(glob.glob(os.path.expanduser(pattern)), reverse=True)
    for c in candidates:
        if c and (Path(c) / "build/cmake/android.toolchain.cmake").exists():
            return Path(c)
    raise SystemExit("Android NDK not found: set ANDROID_NDK_HOME (NDK r26 or newer).")


def build_host(jobs: int = 8, vulkan_include: str | None = None):
    """Native runner for the host's own GPU (Linux iGPU). SPIR-V is portable, so the
    shaders may be compiled elsewhere and copied into build/shaders."""
    paths.use_target("host")
    paths.HOST_BUILD.mkdir(parents=True, exist_ok=True)
    cmd = [
        "cmake",
        "-S",
        str(paths.REPO / "runner"),
        "-B",
        str(paths.HOST_BUILD),
        "-DCMAKE_BUILD_TYPE=Release",
    ]
    if vulkan_include:
        cmd.append(f"-DVULKAN_INCLUDE={Path(vulkan_include).expanduser().resolve()}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["cmake", "--build", str(paths.HOST_BUILD), "-j", str(jobs)], check=True
    )
    for binary in (paths.RUNNER, paths.RUNNER_SUSTAINED, paths.INSPECT):
        print(f"  {binary.relative_to(paths.REPO)}  sha256 {paths.digest(binary)[:16]}")


def build(
    jobs: int = 8,
    host: bool = False,
    shaders_too: bool = True,
    vulkan_include: str | None = None,
):
    needed = (REQUIRED_TOOLS if shaders_too else ()) + ("cmake",)
    missing = sorted({t for t in needed if not shutil.which(t)})
    if missing:
        raise SystemExit(
            f"Missing tools: {', '.join(missing)} (install the Vulkan SDK / shaderc / SPIRV-Tools and CMake)."
        )
    if shaders_too:
        print("Compiling shaders and checking SPIR-V ledgers ...", flush=True)
        variants = shaders.build_all()
        print(f"  {len(variants)} variants OK")
    elif not paths.SHADER_MANIFEST.exists():
        raise SystemExit(
            "--no-shaders needs an existing build/shaders + build/shader-manifest.json (copy them from a build host)."
        )
    if host:
        print("Building host runner ...", flush=True)
        build_host(jobs, vulkan_include)
        return

    ndk = find_ndk()
    print(f"Building runner with NDK {ndk} ...", flush=True)
    paths.ANDROID_BUILD.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "cmake",
            "-S",
            str(paths.REPO / "runner"),
            "-B",
            str(paths.ANDROID_BUILD),
            f"-DCMAKE_TOOLCHAIN_FILE={ndk}/build/cmake/android.toolchain.cmake",
            "-DANDROID_ABI=arm64-v8a",
            "-DANDROID_PLATFORM=android-29",
            "-DANDROID_STL=c++_static",
            "-DCMAKE_BUILD_TYPE=Release",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["cmake", "--build", str(paths.ANDROID_BUILD), "-j", str(jobs)], check=True
    )
    for binary in (paths.RUNNER, paths.RUNNER_SUSTAINED, paths.INSPECT):
        print(f"  {binary.relative_to(paths.REPO)}  sha256 {paths.digest(binary)[:16]}")

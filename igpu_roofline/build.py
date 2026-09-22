"""Build the shaders (with ledger checks) and the Android runner."""
import glob
import os
import shutil
import subprocess
from pathlib import Path

from . import paths, shaders

REQUIRED_TOOLS = ("glslc", "spirv-val", "spirv-dis", "spirv-as", "cmake")
NDK_GUESSES = ["~/Library/Android/sdk/ndk/*", "~/Android/Sdk/ndk/*", "~/android-ndk-r*", "/opt/android-ndk*"]


def find_ndk() -> Path:
    env = os.environ.get("ANDROID_NDK_HOME") or os.environ.get("ANDROID_NDK_ROOT")
    candidates = [env] if env else []
    for pattern in NDK_GUESSES:
        candidates += sorted(glob.glob(os.path.expanduser(pattern)), reverse=True)
    for c in candidates:
        if c and (Path(c) / "build/cmake/android.toolchain.cmake").exists():
            return Path(c)
    raise SystemExit("Android NDK not found: set ANDROID_NDK_HOME (NDK r26 or newer).")


def build(jobs: int = 8):
    missing = [t for t in REQUIRED_TOOLS if not shutil.which(t)]
    if missing:
        raise SystemExit(f"Missing tools: {', '.join(missing)} (install the Vulkan SDK / shaderc / SPIRV-Tools and CMake).")
    print("Compiling shaders and checking SPIR-V ledgers ...", flush=True)
    variants = shaders.build_all()
    print(f"  {len(variants)} variants OK")

    ndk = find_ndk()
    print(f"Building runner with NDK {ndk} ...", flush=True)
    paths.ANDROID_BUILD.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cmake", "-S", str(paths.REPO / "runner"), "-B", str(paths.ANDROID_BUILD),
                    f"-DCMAKE_TOOLCHAIN_FILE={ndk}/build/cmake/android.toolchain.cmake",
                    "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-29", "-DANDROID_STL=c++_static",
                    "-DCMAKE_BUILD_TYPE=Release"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["cmake", "--build", str(paths.ANDROID_BUILD), "-j", str(jobs)], check=True)
    for binary in (paths.RUNNER, paths.RUNNER_SUSTAINED, paths.INSPECT):
        print(f"  {binary.relative_to(paths.REPO)}  sha256 {paths.digest(binary)[:16]}")

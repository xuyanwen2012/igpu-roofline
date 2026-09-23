"""Filesystem layout. Code lives in the repo; results live outside it."""
import hashlib
import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parent.parent
BUILD = REPO / "build"
SHADER_SRC = REPO / "shaders"
SHADER_OUT = BUILD / "shaders"
SHADER_MANIFEST = BUILD / "shader-manifest.json"
ANDROID_BUILD = BUILD / "android"
RUNNER = ANDROID_BUILD / "roofline"
RUNNER_SUSTAINED = ANDROID_BUILD / "roofline_sustained"
INSPECT = ANDROID_BUILD / "inspect"

# Where the runner lives on an Android device.
REMOTE_DIR = "/data/local/tmp/igpu-roofline"

HOST_BUILD = BUILD / "host"


def manifest_runner(manifest: dict) -> str | None:
    """Runner SHA-256 of an artifact manifest, for Android or host builds (older
    manifests only have the Android path key)."""
    return (manifest.get("runner_sha256") or manifest.get("build/android/roofline")
            or manifest.get("build/host/roofline"))


def use_target(target: str) -> None:
    """Point RUNNER/RUNNER_SUSTAINED/INSPECT at the Android or host (Linux iGPU) build."""
    global RUNNER, RUNNER_SUSTAINED, INSPECT
    build = HOST_BUILD if target == "host" else ANDROID_BUILD
    RUNNER, RUNNER_SUSTAINED, INSPECT = build / "roofline", build / "roofline_sustained", build / "inspect"


def results_root(override: str | None = None) -> pathlib.Path:
    path = override or os.environ.get("IGPU_ROOFLINE_RESULTS") or "~/igpu-roofline-results"
    return pathlib.Path(path).expanduser().resolve()


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str | None:
    """Commit of the repo that produced a result ('+dirty' if uncommitted edits)."""
    try:
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
        return head + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None

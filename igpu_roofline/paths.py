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

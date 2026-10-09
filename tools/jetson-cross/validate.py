"""Bounded Jetson validation. Uses the device-side gpu-lab lock and preserves logs."""

import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "out/jetson-cross"
HOST = "doremy@duck-naughty.tail031559.ts.net"
SSH = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "HostKeyAlias=duck-naughty",
    "-o",
    "UpdateHostKeys=no",
    HOST,
]
REMOTE = ".cache/et-jetson-cross-0270403ba"
parser = argparse.ArgumentParser()
parser.add_argument("--campaign", default="validation")
parser.add_argument(
    "--modes",
    nargs="+",
    choices=("tiled", "correctness", "production", "wmma"),
    default=("tiled", "correctness", "production", "wmma"),
)
args = parser.parse_args()
if Path(args.campaign).name != args.campaign:
    parser.error("campaign must be a directory name")
LOGS = WORK / "logs" / args.campaign
LOGS.mkdir(exist_ok=True)
start = time.monotonic()
for mode in args.modes:
    for scheme in ("4w", "8da4w"):
        name = f"{mode}-{scheme}"
        meta = LOGS / f"{name}.json"
        if meta.exists():
            old = json.loads(meta.read_text())
            if old["rc"] == 0:
                print(name, "already completed", flush=True)
                continue
            raise SystemExit(
                f"Previous failure preserved: {meta}; use a new campaign for retries"
            )
        remaining = 600 - (time.monotonic() - start)
        if remaining < 1:
            raise SystemExit("600 second validation budget exhausted")
        # timeout on the remote side also bounds work if the SSH connection drops.
        command = f"timeout --kill-after=10s {max(1, int(remaining))}s bash {REMOTE}/device-test.sh {shlex.quote(mode)} {shlex.quote(scheme)}"
        before = time.monotonic()
        with (LOGS / f"{name}.log").open("w") as out:
            p = subprocess.run([*SSH, command], stdout=out, stderr=subprocess.STDOUT)
        result = {
            "rc": p.returncode,
            "wall_seconds": time.monotonic() - before,
            "command": command,
        }
        meta.write_text(json.dumps(result, indent=2))
        print(name, result, flush=True)
        if p.returncode:
            raise SystemExit(
                f"{name} failed; inspect preserved log before further GPU work"
            )

"""Snapshot a fixed ExecuTorch revision and initialized submodules, without dirty files."""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("checkout", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--revision", default="0270403ba53ea4b3c4671b8037d468bdeb0f8d8b")
a = p.parse_args()
dst = a.output / "source/executorch"
if dst.exists():
    raise SystemExit(f"Refusing to overwrite {dst}")


def archive(repo, ref, target):
    target.mkdir(parents=True, exist_ok=True)
    data = subprocess.check_output(["git", "-C", str(repo), "archive", ref])
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        t.extractall(target, filter="data")


# Submodule statuses belong to HEAD; require it to match the requested revision.
head = subprocess.check_output(
    ["git", "-C", str(a.checkout), "rev-parse", "HEAD"], text=True
).strip()
if head != a.revision:
    raise SystemExit("Use a checkout at the requested revision")
subs = subprocess.check_output(
    ["git", "-C", str(a.checkout), "submodule", "status", "--recursive"], text=True
)
if any(line[0] != " " for line in subs.splitlines()):
    raise SystemExit("Initialize all submodules at their recorded revisions first")
archive(a.checkout, a.revision, dst)
for line in subs.splitlines():
    sha, path = line[1:].split()[:2]
    archive(a.checkout / path, sha, dst / path)
patches = sorted((Path(__file__).resolve().parent / "patches").glob("*.patch"))
for patch in patches:
    subprocess.run(["patch", "-p1", "-i", str(patch)], cwd=dst, check=True)
(a.output / "source-manifest.json").write_text(
    json.dumps(
        {
            "revision": a.revision,
            "patches": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in patches
            },
            "submodules": subs,
            "source": "clean git archives; working-tree changes excluded",
        },
        indent=2,
    )
)

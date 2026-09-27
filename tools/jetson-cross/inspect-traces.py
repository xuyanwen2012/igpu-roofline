"""Decode size-prefixed ETDump files and count actual Vulkan kernel events."""

import argparse
import collections
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("workspace", type=Path, nargs="?", default=Path("out/jetson-cross"))
a = parser.parse_args()
w = a.workspace.resolve()
traces = sorted((w / "traces").glob("*.etdp"))
if not traces:
    raise SystemExit("No ETDump traces found")
subprocess.run(
    [
        str(w / "build/third-party/flatc_ep/bin/flatc"),
        "-t",
        "--strict-json",
        "--raw-binary",
        "--size-prefixed",
        "-o",
        str(w / "traces"),
        "-I",
        str(w / "source/executorch/schema"),
        str(w / "source/executorch/devtools/etdump/etdump_schema_flatcc.fbs"),
        "--",
        *map(str, traces),
    ],
    check=True,
)
summary = {}
for trace in traces:
    counts = collections.Counter()
    data = json.loads(trace.with_suffix(".json").read_text())
    for run in data["run_data"]:
        for event in run.get("events", []):
            label = event.get("profile_event", {}).get("delegate_debug_id_str", "")
            if label.startswith("{"):
                kernel = json.loads(label).get("kernel_name")
                if kernel:
                    counts[kernel] += 1
    summary[trace.stem] = dict(counts)
    print(trace.stem, {k: v for k, v in counts.items() if "coopmat" in k})
(w / "dispatch-summary.json").write_text(json.dumps(summary, indent=2))

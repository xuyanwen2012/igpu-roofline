"""Compare instrumented 3B 4w projection phases, separately from clean timing."""

import argparse
import collections
import json
import statistics
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("study", type=Path)
a = p.parse_args()
sources = {
    "original": "profiles/trace-short/trace-original-3b-4w/capture.json",
    "initial_tuned": "profiles/nsys-final/trace-3b-4w/capture.json",
    "final_tuned": "profiles/trace-short-final/trace-3b-4w/capture.json",
}
summary = {}
for mode, relative in sources.items():
    path = a.study / relative
    if not path.exists():
        continue
    groups = collections.defaultdict(list)
    kernels = collections.defaultdict(set)
    for run in json.loads(path.read_text())["run_data"]:
        for e in run.get("events", []):
            event = e.get("profile_event", {})
            label = event.get("delegate_debug_id_str", "")
            if not label.startswith("{"):
                continue
            label = json.loads(label)
            kernel = label.get("kernel_name", "")
            if not kernel.startswith("linear_q4gsw_coopmat"):
                continue
            args = label["operator"]["args"]
            k = args[0]["sizes"][-1]
            n = args[1]["sizes"][0]
            # Labels retain preparation/max M=2048, while these runner jobs use
            # 256 prompt tokens. Do not infer runtime M from that static label.
            key = f"K{k}_N{n}"
            # VulkanBackend.cpp logs QueryPool's start_time_ns/end_time_ns.
            groups[key].append((event["end_time"] - event["start_time"]) / 1e6)
            kernels[key].add(kernel)
    summary[mode] = {
        key: {
            "count": len(times),
            "median_ms": statistics.median(times),
            "sum_ms": sum(times),
            "kernels": sorted(kernels[key]),
        }
        for key, times in groups.items()
    }
    print(mode, "instrumented projection sum ms", sum(sum(x) for x in groups.values()))
(a.study / "analysis/short-trace-phases.json").write_text(json.dumps(summary, indent=2))

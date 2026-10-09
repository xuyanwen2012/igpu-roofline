"""Compare matched microbenchmark rows; preserve repeat spread and dispatch evidence."""

import argparse
import collections
import json
import math
import statistics
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("campaign", type=Path)
a = p.parse_args()
groups = collections.defaultdict(lambda: collections.defaultdict(list))
for path in sorted(a.campaign.glob("*/perf.json")):
    metadata = path.parent / "result.json"
    if not metadata.exists() or json.loads(metadata.read_text())["rc"] != 0:
        continue
    mode = path.parent.name.rsplit("-r", 1)[0]
    for row in json.loads(path.read_text())["cases"]:
        key = (
            row["model"],
            row["scheme"],
            row["regime"],
            row["op"],
            row["storage"],
            row["M"],
            row["K"],
            row["N"],
        )
        groups[mode][key].append(row)
result = {}
for mode, rows in groups.items():
    result[mode] = []
    for key, repeat in rows.items():
        times = [r["kernel_median_us"] for r in repeat]
        if any(x is None for x in times):
            continue
        median = statistics.median(times)
        result[mode].append(
            {
                "key": key,
                "median_us": median,
                "spread": (max(times) - min(times)) / median,
                "repeats": len(times),
                "times_us": times,
                "op_mean_us": statistics.median(r["op_mean_us"] for r in repeat),
                "dispatch": list({r["dispatch"] for r in repeat}),
                "max_kernel_cov": max(r["kernel_cov"] or 0 for r in repeat),
            }
        )
(a.campaign / "summary.json").write_text(json.dumps(result, indent=2))
base = {tuple(r["key"]): r for r in result.get("baseline", [])}
for mode, rows in result.items():
    for scheme in ("4w", "8da4w"):
        r = [x for x in rows if x["key"][1] == scheme]
        speed = [
            base[tuple(x["key"])]["median_us"] / x["median_us"]
            for x in r
            if tuple(x["key"]) in base
        ]
        print(
            mode,
            scheme,
            "cells",
            len(r),
            "max spread",
            round(max((x["spread"] for x in r), default=0) * 100, 2),
            "%",
            "vs baseline",
            round(math.exp(statistics.mean(map(math.log, speed))), 3)
            if speed
            else None,
        )

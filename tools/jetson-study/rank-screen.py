"""Rank bounded-screen candidates against the frozen original by matching shape."""

import argparse
import json
import math
import statistics
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("screen", type=Path)
p.add_argument("baseline", type=Path)
a = p.parse_args()


def key(r):
    return (r["model"], r["scheme"], r["op"], r["M"], r["K"], r["N"], r["storage"])


base = {}
for f in a.baseline.glob("linear-r*/perf.json"):
    for r in json.loads(f.read_text())["cases"]:
        base.setdefault(key(r), []).append(r["kernel_median_us"])
base = {k: statistics.median(v) for k, v in base.items()}
rank = []
for f in a.screen.glob("*/perf.json"):
    meta = f.parent / "result.json"
    if not meta.exists() or json.loads(meta.read_text())["rc"] != 0:
        continue
    data = json.loads(f.read_text())["cases"]
    if not data:
        continue
    # Prefill must really use the requested matrix shader, not a fallback.
    if any(r["variant"] != "coopmat" or not r["ok"] for r in data):
        print("REJECT dispatch/failure", f.parent.name)
        continue
    gains = [base[key(r)] / r["kernel_median_us"] for r in data if key(r) in base]
    rank.append(
        {
            "candidate": f.parent.name,
            "geomean": math.exp(statistics.mean(map(math.log, gains))),
            "gains": {
                r["model"] + "/" + r["op"]: base[key(r)] / r["kernel_median_us"]
                for r in data
            },
            "dispatches": sorted({r["kernel"] for r in data}),
        }
    )
rank.sort(key=lambda r: r["geomean"], reverse=True)
(a.screen / "ranking.json").write_text(json.dumps(rank, indent=2))
for r in rank:
    print(f"{r['geomean']:.3f}x {r['candidate']}")
print(
    "Screen ranking is provisional: requires production correctness and clean repeats."
)

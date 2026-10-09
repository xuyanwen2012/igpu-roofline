"""Summarize matched successful model repeats without hiding missing attempts."""

import argparse
import collections
import json
import statistics
from pathlib import Path
from typing import Any

p = argparse.ArgumentParser()
p.add_argument("campaign", type=Path)
a = p.parse_args()
rows = json.loads((a.campaign / "summary.json").read_text())
groups = collections.defaultdict(list)
for row in rows:
    if row["rc"] == 0 and row.get("stop_reason") is None and "prefill_ms" in row:
        groups[row["job"].rsplit("-r", 1)[0]].append(row)
summary: dict[str, dict[str, Any]] = {}
for key, repeat in sorted(groups.items()):
    prefill = [r["prefill_ms"] for r in repeat]
    decode = [r["decode_token_per_sec"] for r in repeat]
    median = statistics.median(prefill)
    summary[key] = {
        "repeats": len(repeat),
        "prompt_tokens": sorted({r["prompt_tokens"] for r in repeat}),
        "generated_tokens": sorted({r["generated_tokens"] for r in repeat}),
        "prefill_ms": median,
        "prefill_times_ms": prefill,
        "prefill_spread": (max(prefill) - min(prefill)) / median,
        "decode_tps": statistics.median(decode),
        "decode_spread": (max(decode) - min(decode)) / statistics.median(decode),
        "peak_rss_kb": max(r.get("max_rss_kb", 0) for r in repeat),
        "load_ms": statistics.median(r["load_ms"] for r in repeat),
    }
for key, value in summary.items():
    if "-tuned-" not in key:
        continue
    for comparison in ("baseline", "original"):
        baseline = summary.get(key.replace("-tuned-", "-" + comparison + "-"))
        if baseline:
            if (baseline["prompt_tokens"], baseline["generated_tokens"]) != (
                value["prompt_tokens"],
                value["generated_tokens"],
            ):
                raise SystemExit("Mismatched token counts: " + key)
            value["prefill_speedup_vs_" + comparison] = (
                baseline["prefill_ms"] / value["prefill_ms"]
            )
    print(key, json.dumps(value))
(a.campaign / "comparison.json").write_text(json.dumps(summary, indent=2))

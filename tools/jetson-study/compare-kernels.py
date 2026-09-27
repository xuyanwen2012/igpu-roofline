"""Publish only confirmed, numerically checked tuned projection comparisons."""

import argparse
import json
import math
import statistics
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("campaign", type=Path)
a = p.parse_args()
summary = json.loads((a.campaign / "summary.json").read_text())
modes = {
    mode: {tuple(row["key"]): row for row in summary[mode]}
    for mode in ("baseline", "original", "tuned")
}
rows = []
for key, tuned in modes["tuned"].items():
    model, scheme, regime, op, storage, m, k, n = key
    correctness = a.campaign / f"pdiff-{scheme}-{model}/result.json"
    checked = correctness.exists() and json.loads(correctness.read_text())["rc"] == 0
    baseline = modes["baseline"][key]
    original = modes["original"][key]
    stable = all(
        x["repeats"] >= 3 and x["spread"] <= 0.05 and x["max_kernel_cov"] <= 0.03
        for x in (baseline, original, tuned)
    )
    valid = checked and stable and tuned["dispatch"] == ["confirmed"]
    old_invalid = (model, scheme, op) == ("llama-3.1-8b", "4w", "w2")
    rows.append(
        {
            "key": key,
            "validated": valid,
            "sampled_production_check_passed": checked,
            "stable_three_repeats": stable,
            "baseline_us": baseline["median_us"],
            "original_us": original["median_us"],
            "tuned_us": tuned["median_us"],
            "tuned_tops": 2 * m * n * k / tuned["median_us"] / 1e6,
            "tuned_repeat_spread": tuned["spread"],
            "original_numerically_valid": not old_invalid,
            "kernel_speedup_vs_baseline": baseline["median_us"] / tuned["median_us"]
            if valid
            else None,
            "kernel_speedup_vs_original": original["median_us"] / tuned["median_us"]
            if valid and not old_invalid
            else None,
            "operator_speedup_vs_original": original["op_mean_us"] / tuned["op_mean_us"]
            if valid and not old_invalid
            else None,
        }
    )
for scheme in ("4w", "8da4w"):
    selected = [r for r in rows if r["key"][1] == scheme]
    print(
        scheme,
        "validated cells",
        sum(r["validated"] for r in selected),
        "/",
        len(selected),
    )
    for field in (
        "kernel_speedup_vs_baseline",
        "kernel_speedup_vs_original",
        "operator_speedup_vs_original",
    ):
        values = [r[field] for r in selected if r[field] is not None]
        print(
            field,
            math.exp(statistics.mean(map(math.log, values))) if values else None,
            "cells",
            len(values),
        )
(a.campaign / "comparison.json").write_text(json.dumps(rows, indent=2))

"""Relate matched operator timings to measured roofs; traffic is explicitly modeled."""

import argparse
import csv
import json
import statistics
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

p = argparse.ArgumentParser()
p.add_argument("study", type=Path)
a = p.parse_args()
roofs = json.loads(
    (a.study / "roofline-results/orin-naughty/report/summary.json").read_text()
)["short_run"]
groups = {}
confirmed = (a.study / "confirm/comparison.json").exists()
campaign = a.study / ("confirm" if confirmed else "baseline-runs")
pattern = "original-r*/perf.json" if confirmed else "linear-r*/perf.json"
for path in campaign.glob(pattern):
    if json.loads((path.parent / "result.json").read_text())["rc"] != 0:
        continue
    for r in json.loads(path.read_text())["cases"]:
        key = (r["scheme"], r["model"], r["op"], r["M"], r["K"], r["N"])
        groups.setdefault(key, []).append(r["kernel_median_us"])
rows = []
for (scheme, model, op, m, k, n), times in sorted(groups.items()):
    # Ideal compulsory tensor traffic, NOT measured DRAM traffic. Count one read
    # of each input/weight/scale/zero and one output write; ignore layout padding,
    # repeated tile fetches, caches, and intermediate dynamic quantization.
    # 4w: half activations; 8da4w matrix stage: already-quantized int8 activations.
    # Symmetric int4 weights have one half scale per group (no weight zero).
    # 8da4w also reads int32 weight sums and per-row half scales/int8 zeros.
    traffic = (
        m * k * (2 if scheme == "4w" else 1) + k * n / 2 + k * n / 128 * 2 + m * n * 2
    )
    if scheme == "8da4w":
        traffic += k * n / 128 * 4 + m * 3
    ops = 2 * m * k * n
    us = statistics.median(times)
    roof_name = "matrix_fp16" if scheme == "4w" else "matrix_int8"
    roof = roofs[roof_name]["value"]
    rows.append(
        {
            "scheme": scheme,
            "model": model,
            "op": op,
            "M": m,
            "K": k,
            "N": n,
            "kernel_us": us,
            "tops": ops / us / 1e6,
            "matrix_roof_tops": roof,
            "matrix_roof_fraction": ops / us / 1e6 / roof,
            "ideal_tensor_bytes": traffic,
            "ideal_ops_per_byte": ops / traffic,
            "numerical_status": "FAILED"
            if (scheme, model, op) == ("4w", "llama-3.1-8b", "w2")
            else "sampled_pass",
        }
    )
out = a.study / "analysis"
out.mkdir(exist_ok=True)
with (out / "original-roofline.csv").open("w") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
for scheme in ("4w", "8da4w"):
    valid = [
        r for r in rows if r["scheme"] == scheme and r["numerical_status"] != "FAILED"
    ]
    print(
        scheme,
        "throughput range",
        min(r["tops"] for r in valid),
        max(r["tops"] for r in valid),
        "roof fraction",
        min(r["matrix_roof_fraction"] for r in valid),
        max(r["matrix_roof_fraction"] for r in valid),
    )

fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), constrained_layout=True)
confirmation = a.study / "confirm/comparison.json"
tuned_rows = json.loads(confirmation.read_text()) if confirmation.exists() else []
for ax, scheme in zip(axes, ("4w", "8da4w")):
    selected = [r for r in rows if r["scheme"] == scheme]
    roof = selected[0]["matrix_roof_tops"]
    x = np.geomspace(1, 10000, 200)
    ax.loglog(
        x,
        np.minimum(roof, x * roofs["global_read"]["value"] / 1000),
        color="gray",
        linestyle="--",
        label="Ideal read-BW / matrix envelope",
    )
    for model, marker, color in (
        ("llama-3.2-1b", "o", "tab:blue"),
        ("llama-3.2-3b", "s", "tab:orange"),
        ("llama-3.1-8b", "^", "tab:green"),
    ):
        good = [
            r
            for r in selected
            if r["model"] == model and r["numerical_status"] != "FAILED"
        ]
        ax.scatter(
            [r["ideal_ops_per_byte"] for r in good],
            [r["tops"] for r in good],
            marker=marker,
            color=color,
            label=model,
        )
        tuned = [
            r for r in tuned_rows if r["key"][:2] == [model, scheme] and r["validated"]
        ]
        intensities = {
            r["op"]: r["ideal_ops_per_byte"] for r in selected if r["model"] == model
        }
        ax.scatter(
            [intensities[r["key"][3]] for r in tuned],
            [r["tuned_tops"] for r in tuned],
            marker=marker,
            facecolors="none",
            edgecolors=color,
            s=75,
        )
    if tuned_rows:
        ax.scatter(
            [],
            [],
            facecolors="none",
            edgecolors="black",
            label="Tuned = hollow markers",
        )
    bad = [r for r in selected if r["numerical_status"] == "FAILED"]
    if bad:
        ax.scatter(
            [r["ideal_ops_per_byte"] for r in bad],
            [r["tops"] for r in bad],
            marker="x",
            color="red",
            label="Numerically invalid (excluded)",
        )
    ax.set(
        title=scheme + " WMMA, M=2048",
        xlabel="Ideal tensor operations/byte (modeled)",
        ylabel="Effective matrix TOP/s",
        ylim=(0.05, 30),
    )
    ax.grid(True, alpha=0.2)
    ax.legend(fontsize=7, loc="lower right")
fig.suptitle("Orin: modeled compulsory traffic, not hardware-measured DRAM traffic")
fig.savefig(out / "original-roofline.png", dpi=180)

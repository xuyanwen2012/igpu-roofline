#!/usr/bin/env python3
"""Publication figures for the 2026-09-26 end-to-end prefill study (ExecuTorch Vulkan, Llama 1B/3B/8B).

Input: e2e_summary.json (analyze.py), next to this script.
Output: figures/{e2e_overview,e2e_linear_share}.{pdf,png}

Run: uv run python results/e2e-20260926/plot_e2e.py
"""

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"

GPUS = [("4070tis", "RTX 4070 Ti SUPER"), ("b70-0", "Arc Pro B70"), ("b580", "Arc B580"),
        ("780m", "Radeon 780M")]
SIZES = [("1b", "1B"), ("3b", "3B"), ("8b", "8B")]
SCHEMES = [("4w", "4w (int4 weight, fp16 act.)"), ("8da4w", "8da4w (int4 weight, int8 act.)")]
# Okabe-Ito (colour-blind safe)
C_TUNED = {"4w": "#0072B2", "8da4w": "#D55E00"}
C_TILED = "#BBBBBB"
C_GPU = {"4070tis": "#009E73", "b70-0": "#0072B2", "b580": "#56B4E9", "780m": "#E69F00"}
MARK = {"1b": "o", "3b": "s", "8b": "^"}

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Liberation Sans", "Arial", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "legend.fontsize": 7, "axes.linewidth": 0.6,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5,
    "ytick.major.size": 2.5, "axes.spines.top": False, "axes.spines.right": False,
    "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def load():
    rows = json.loads((HERE / "e2e_summary.json").read_text())
    return {(r["gpu"], r["size"], r["quant"]): r for r in rows}


def throughput_panel(ax, d, quant, letter):
    """Grouped bars: per GPU, 1B/3B/8B; tiled (grey) vs tuned (colour), log y, speedup labels."""
    w, gap = 0.36, 0.25
    x0 = 0.0
    centers, labels = [], []
    for gi, (g, gname) in enumerate(GPUS):
        for si, (s, sname) in enumerate(SIZES):
            r = d[(g, s, quant)]
            xc = x0 + si
            for off, mode, col in ((-w / 2, "tiled", C_TILED), (w / 2, "tuned", C_TUNED[quant])):
                m = r[mode]
                ax.bar(xc + off, m["tok_s"], w, color=col, edgecolor="black", linewidth=0.4, zorder=2)
                ax.errorbar(xc + off, m["tok_s"], yerr=[[m["tok_s"] - m["lo"]], [m["hi"] - m["tok_s"]]],
                            fmt="none", ecolor="black", elinewidth=0.5, capsize=1.2, zorder=3)
            ax.text(xc + w / 2, r["tuned"]["hi"] * 1.12, f"{r['speedup']:.1f}×", ha="center",
                    va="bottom", fontsize=6.3, rotation=90, zorder=4)
            ax.text(xc, -0.025, sname, ha="center", va="top", fontsize=6.5,
                    transform=ax.get_xaxis_transform())
        centers.append(x0 + 1)
        labels.append(gname)
        x0 += len(SIZES) + gap
        if gi < len(GPUS) - 1:
            ax.axvline(x0 - gap / 2 - 0.5, color="0.85", linewidth=0.5, zorder=1)
    ax.set_yscale("log")
    ax.set_ylim(60, 80000)
    ax.set_xlim(-0.6, x0 - gap - 0.4)
    ax.set_xticks(centers)
    ax.set_xticklabels(labels)
    ax.tick_params(axis="x", length=0, pad=12)
    ax.set_ylabel("Prefill throughput (tokens/s)")
    ax.grid(axis="y", which="major", color="0.9", linewidth=0.5, zorder=0)
    ax.set_title(f"({letter}) End-to-end prefill, {dict(SCHEMES)[quant]}", loc="left")
    ax.legend(handles=[Patch(facecolor=C_TILED, edgecolor="black", linewidth=0.4, label="tiled (baseline)"),
                       Patch(facecolor=C_TUNED[quant], edgecolor="black", linewidth=0.4,
                             label="tuned coopmat (this work)")],
              loc="upper right", frameon=False, ncol=2, handlelength=1.2, columnspacing=1.0)


def heatmap_panel(fig, ax, d):
    cols = [(q, s) for q, _ in SCHEMES for s, _ in SIZES]
    M = np.array([[d[(g, s, q)]["speedup"] for q, s in cols] for g, _ in GPUS])
    cmap = LinearSegmentedColormap.from_list("sp", ["#F7F7F7", "#9ECAE1", "#2171B5", "#08306B"])
    im = ax.imshow(M, cmap=cmap, vmin=1, vmax=5.5, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.2f}×", ha="center", va="center", fontsize=6.8,
                    color="white" if M[i, j] > 3.3 else "black")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([s.upper() for _, s in cols])
    ax.set_yticks(range(len(GPUS)))
    ax.set_yticklabels([n for _, n in GPUS])
    for j0, (q, _) in zip((1, 4), SCHEMES):
        ax.text(j0, -0.62, q, ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    ax.axvline(2.5, color="white", linewidth=1.5)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.02)
    cb.set_label("Speedup over tiled", fontsize=7)
    cb.ax.tick_params(labelsize=6.5, width=0.5, length=2)
    cb.outline.set_linewidth(0.5)
    ax.set_title("(c) End-to-end prefill speedup (tuned / tiled)", loc="left", pad=16)


def amdahl_panel(ax, d):
    lim = (0.9, 6.0)
    ax.plot(lim, lim, color="0.6", linewidth=0.7, linestyle="--", zorder=1)
    ax.fill_between(lim, [v * 0.9 for v in lim], [v * 1.1 for v in lim], color="0.93", zorder=0)
    skipped = []
    for g, gname in GPUS:
        for s, _ in SIZES:
            for q, _ in SCHEMES:
                r = d[(g, s, q)]
                p = r.get("predicted_speedup")
                if p is None or not (0 < r.get("linear_share_tiled", 2) < 1):
                    skipped.append(f"{gname} {s.upper()} {q}")
                    continue
                ax.scatter(p, r["speedup"], s=18, marker=MARK[s], facecolor=C_GPU[g] if q == "4w" else "white",
                           edgecolor=C_GPU[g], linewidth=0.9, zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ticks = [1, 1.5, 2, 3, 4, 5]
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(mpl.ticker.FixedLocator(ticks))
        axis.set_major_formatter(mpl.ticker.FixedFormatter([f"{t:g}×" for t in ticks]))
        axis.set_minor_locator(mpl.ticker.NullLocator())
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_aspect("equal")
    ax.set_xlabel("Predicted from microbenchmarks (Amdahl)")
    ax.set_ylabel("Measured end-to-end")
    ax.set_title("(d) Microkernel gains vs. model-level gains", loc="left")
    h = [plt.Line2D([], [], marker="o", linestyle="", markerfacecolor=c, markeredgecolor=c, markersize=4,
                    label=n) for (g, n), c in zip(GPUS, (C_GPU[g] for g, _ in GPUS))]
    h += [plt.Line2D([], [], marker=MARK[s], linestyle="", color="0.3", markerfacecolor="0.3", markersize=4,
                     label=n) for s, n in SIZES]
    h += [plt.Line2D([], [], marker="o", linestyle="", color="0.3", markerfacecolor="0.3", markersize=4,
                     label="4w (filled)"),
          plt.Line2D([], [], marker="o", linestyle="", color="0.3", markerfacecolor="white", markersize=4,
                     label="8da4w (open)")]
    ax.legend(handles=h, loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False, fontsize=6,
              handletextpad=0.2, borderaxespad=0.0, ncol=1, labelspacing=0.45)
    note = "Shaded: ±10 %."
    if skipped:
        note += " Excluded: " + "; ".join(skipped) + " (noisy tiled microbenchmark)."
    ax.text(1.02, 0.0, note, transform=ax.transAxes, ha="left", va="bottom", fontsize=5.3, color="0.4",
            wrap=True)


def kfmt(v, _):
    return f"{v / 1000:g}k" if v >= 1000 else f"{v:g}"


def throughput_small_multiples(fig, gs_rows, d):
    """Rows = scheme, columns = GPU; linear tokens/s with each panel on its own scale, so the gap between
    tiled and tuned is shown at full height; speedup printed above every tuned bar."""
    w = 0.38
    xs = np.arange(len(SIZES))
    axes = []
    for ri, (q, qname) in enumerate(SCHEMES):
        for ci, (g, gname) in enumerate(GPUS):
            ax = fig.add_subplot(gs_rows[ri, ci])
            axes.append(ax)
            tiled = [d[(g, s, q)]["tiled"]["tok_s"] for s, _ in SIZES]
            tuned = [d[(g, s, q)]["tuned"]["tok_s"] for s, _ in SIZES]
            ax.bar(xs - w / 2, tiled, w, color=C_TILED, edgecolor="black", linewidth=0.4, zorder=2)
            ax.bar(xs + w / 2, tuned, w, color=C_TUNED[q], edgecolor="black", linewidth=0.4, zorder=2)
            top = max(tuned) * 1.22
            ax.set_ylim(0, top)
            for x, t, u in zip(xs, tiled, tuned):
                ax.text(x + w / 2, u + top * 0.015, f"{u / t:.1f}×", ha="center", va="bottom",
                        fontsize=7.5, fontweight="bold", color=C_TUNED[q])
            ax.set_xticks(xs)
            ax.set_xticklabels([n for _, n in SIZES])
            ax.tick_params(axis="x", length=0)
            ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(kfmt))
            ax.yaxis.set_major_locator(mpl.ticker.MaxNLocator(4))
            ax.grid(axis="y", color="0.92", linewidth=0.5, zorder=0)
            if ri == 0:
                ax.set_title(gname, fontsize=8.5, fontweight="bold")
            if ci == 0:
                ax.set_ylabel(f"{q}\ntokens/s", fontsize=8)
    return axes


def speedup_bars(ax, d):
    """All GPUs x models, 4w and 8da4w side by side, linear speedup axis from 0 with the 1x baseline."""
    w, gap = 0.38, 0.9
    x0 = 0.0
    centers = []
    ymax = max(d[(g, s, q)]["speedup"] for g, _ in GPUS for s, _ in SIZES for q, _ in SCHEMES)
    for g, gname in GPUS:
        for si, (s, sname) in enumerate(SIZES):
            xc = x0 + si
            for off, (q, _) in ((-w / 2, SCHEMES[0]), (w / 2, SCHEMES[1])):
                v = d[(g, s, q)]["speedup"]
                ax.bar(xc + off, v, w, color=C_TUNED[q], edgecolor="black", linewidth=0.4, zorder=2)
                ax.text(xc + off, v + 0.06, f"{v:.1f}", ha="center", va="bottom", fontsize=6.3)
            ax.text(xc, -0.05, sname, ha="center", va="top", fontsize=6.8, transform=ax.get_xaxis_transform())
        centers.append(x0 + 1)
        x0 += len(SIZES) + gap
    ax.axhline(1, color="black", linewidth=0.8, linestyle="--", zorder=3)
    ax.text(1.005, 1, "1× = tiled\nbaseline", ha="left", va="center", fontsize=6.3,
            transform=mpl.transforms.blended_transform_factory(ax.transAxes, ax.transData))
    ax.set_ylim(0, ymax * 1.15)
    ax.set_xlim(-0.6, x0 - gap - 0.4)
    ax.set_xticks(centers)
    ax.set_xticklabels([n for _, n in GPUS], fontsize=8, fontweight="bold")
    ax.tick_params(axis="x", length=0, pad=13)
    ax.set_ylabel("Prefill speedup (×)")
    ax.yaxis.set_major_locator(mpl.ticker.MultipleLocator(1))
    ax.grid(axis="y", color="0.92", linewidth=0.5, zorder=0)
    ax.legend(handles=[Patch(facecolor=C_TUNED[q], edgecolor="black", linewidth=0.4, label=n)
                       for q, n in SCHEMES], loc="lower right", bbox_to_anchor=(1.0, 1.0), frameon=False,
              ncol=2, borderaxespad=0.2)


def overview(d):
    """Main figure: linear throughput small multiples (a, b) and the speedup summary (c)."""
    fig = plt.figure(figsize=(7.2, 6.4))
    gs = fig.add_gridspec(3, 4, height_ratios=[1, 1, 1.15], hspace=0.5, wspace=0.42, top=0.9)
    throughput_small_multiples(fig, gs, d)
    fig.text(0.005, 0.995, "(a) End-to-end prefill throughput, 2048-token prompt (linear scale; each panel "
             "on its own axis)", fontsize=9, va="top")
    fig.legend(handles=[Patch(facecolor=C_TILED, edgecolor="black", linewidth=0.4, label="tiled (baseline)"),
                        Patch(facecolor=C_TUNED["4w"], edgecolor="black", linewidth=0.4, label="tuned, 4w"),
                        Patch(facecolor=C_TUNED["8da4w"], edgecolor="black", linewidth=0.4,
                              label="tuned, 8da4w")],
               loc="upper left", bbox_to_anchor=(0.0, 0.965), ncol=3, frameon=False)
    ax = fig.add_subplot(gs[2, :])
    speedup_bars(ax, d)
    ax.set_title("(b) End-to-end prefill speedup over tiled", loc="left", pad=8)
    return fig


def supplement(d):
    fig = plt.figure(figsize=(7.2, 7.4))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.25], width_ratios=[1.15, 1], hspace=0.62,
                          wspace=0.32)
    throughput_panel(fig.add_subplot(gs[0, :]), d, "4w", "a")
    throughput_panel(fig.add_subplot(gs[1, :]), d, "8da4w", "b")
    heatmap_panel(fig, fig.add_subplot(gs[2, 0]), d)
    amdahl_panel(fig.add_subplot(gs[2, 1]), d)
    return fig


def linear_share(d):
    """Fraction of prefill time in the quantized linears, tiled -> tuned (microbench linear / e2e time)."""
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.3), sharey=True)
    for ax, (q, qname) in zip(axes, SCHEMES):
        y = 0
        yt, yl = [], []
        for g, gname in GPUS:
            for s, sname in SIZES:
                r = d[(g, s, q)]
                t, w = r.get("linear_share_tiled"), r.get("linear_share_tuned")
                if t is None:
                    continue
                ok = 0 < t < 1
                ax.annotate("", xy=(w * 100, y), xytext=(min(t, 1) * 100, y),
                            arrowprops=dict(arrowstyle="-|>", color=C_GPU[g], lw=1.0, mutation_scale=6,
                                            linestyle="-" if ok else ":"))
                ax.scatter([min(t, 1) * 100], [y], s=10, color=C_TILED, edgecolor="black", linewidth=0.4, zorder=3)
                ax.scatter([w * 100], [y], s=12, color=C_GPU[g], edgecolor="black", linewidth=0.4, zorder=3)
                if not ok:
                    ax.text(100, y - 0.3, "tiled share >100 %*", fontsize=5, color="0.4", ha="right")
                yt.append(y)
                yl.append(f"{gname}  {sname}")
                y += 1
            y += 0.6
        ax.set_yticks(yt)
        ax.set_yticklabels(yl, fontsize=6)
        ax.set_xlim(20, 102)
        ax.set_xlabel("Share of prefill time in quantized linears (%)")
        ax.grid(axis="x", color="0.92", linewidth=0.5)
        ax.set_title(qname, loc="left")
    axes[0].invert_yaxis()  # shared y: invert once, first GPU on top
    fig.legend(handles=[plt.Line2D([], [], marker="o", linestyle="", markerfacecolor=C_TILED,
                                   markeredgecolor="black", markersize=4, label="tiled baseline"),
                        plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="0.3",
                                   markeredgecolor="black", markersize=4, label="tuned coopmat (this work)")],
               loc="lower center", bbox_to_anchor=(0.5, 0.98), ncol=2, frameon=False)
    fig.text(0.99, -0.1, "* microbenchmark tiled time for this shape was noisy; share clipped at 100 %.",
             ha="right", fontsize=5.5, color="0.4")
    return fig


def main():
    OUT.mkdir(exist_ok=True)
    d = load()
    for name, fig in (("e2e_overview", overview(d)), ("e2e_supplement", supplement(d)),
                      ("e2e_linear_share", linear_share(d))):
        for ext in ("pdf", "png"):
            fig.savefig(OUT / f"{name}.{ext}", dpi=300)
        plt.close(fig)
        print("wrote", OUT / f"{name}.pdf", OUT / f"{name}.png")


if __name__ == "__main__":
    main()

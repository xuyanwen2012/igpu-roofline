"""WMMA (branch default, --linear) vs forced-tiled (--baseline) prefill microkernels, on confirmed roofs.

usage: compare_et.py <roofline device folder> <microbench run dir> <out.md>
Each cell is the median over repeats of the per-run kernel median (GPU timestamps); a cell is
flagged when its repeat spread exceeds 5 % or when repeats dispatched different kernels.
"""

import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from igpu_roofline.workload import place, usable_roofs  # noqa: E402

MAX_SPREAD = 0.05


def load(run: pathlib.Path, suite: str):
    cells, meta = {}, None
    for f in sorted(run.glob(f"{suite}-r*.json")):
        d = json.loads(f.read_text())
        meta = meta or d
        for c in d["cases"]:
            if c["regime"] != "prefill" or not c["ok"] or not c.get("kernel_median_us"):
                continue
            key = (c["model"], c["op"], c["scheme"], c["storage"])
            cells.setdefault(key, []).append(c)
    return meta, cells


def summarize(cases):
    t = [c["kernel_median_us"] for c in cases]
    med = statistics.median(t)
    kernels = sorted({c["kernel"] for c in cases})
    return {
        "us": med,
        "spread": (max(t) - min(t)) / med,
        "n": len(t),
        "kernels": kernels,
        "case": dict(cases[0], kernel_median_us=med, kernel=kernels[0]),
    }


def main(roof_dir, run_dir, out):
    roof_dir, run_dir = pathlib.Path(roof_dir), pathlib.Path(run_dir)
    summary = json.loads((roof_dir / "report" / "summary.json").read_text())
    roofs, _ = usable_roofs(summary)
    meta, wmma = load(run_dir, "linear")
    _, tiled = load(run_dir, "baseline")
    g = meta["group_size"]
    lines = [
        f"# {summary['device']}: WMMA vs tiled prefill microkernels",
        "",
        f"Run: `{run_dir}` · ET device `{meta['device']}` · subgroup {meta['subgroup_size']} · group {g}. "
        "Times are medians of per-run kernel medians (GPU timestamps); `!` = repeat spread > 5 % "
        "or mixed kernels across repeats. % roof = achieved / matching confirmed roof "
        "(WMMA: matrix fp16 or int8; tiled: fp16 FMA or int8 dot).",
        "",
        "| model | layer | scheme | storage | WMMA kernel | WMMA µs | WMMA TOP/s | % matrix roof "
        "| tiled µs | tiled TOP/s | % FMA/dot roof | speedup |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    rows = []
    for key in sorted(set(wmma) | set(tiled), key=lambda k: (k[2], k[3], k[0], k[1])):
        w = summarize(wmma[key]) if key in wmma else None
        t = summarize(tiled[key]) if key in tiled else None
        pw = place(w["case"], g, roofs) if w else None
        pt = place(t["case"], g, roofs) if t else None
        flag = lambda s: "!" if s and (s["spread"] > MAX_SPREAD or len(s["kernels"]) > 1) else ""  # noqa: E731
        pct = lambda p: f"{p['compute_fraction']:.0%}" if p and "compute_fraction" in p else "—"  # noqa: E731
        is_wmma = bool(w) and "coopmat" in w["kernels"][0]
        speed = t["us"] / w["us"] if (w and t) else None
        rows.append(
            {
                "key": key,
                "wmma": w and {k: w[k] for k in ("us", "spread", "n", "kernels")},
                "tiled": t and {k: t[k] for k in ("us", "spread", "n", "kernels")},
                "wmma_place": pw,
                "tiled_place": pt,
                "speedup": speed,
                "wmma_dispatched": is_wmma,
            }
        )
        lines.append(
            f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | "
            f"`{w['kernels'][0] if w else '—'}`{'' if is_wmma or not w else ' (NOT coopmat)'} | "
            f"{w['us']:.0f}{flag(w)} | {pw['achieved_tops']:.2f} | {pct(pw)} | "
            if w
            else f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | — | — | — | — | "
        )
        lines[-1] += (
            f"{t['us']:.0f}{flag(t)} | {pt['achieved_tops']:.2f} | {pct(pt)} | "
            if t
            else "— | — | — | "
        )
        lines[-1] += f"{speed:.2f}× |" if speed else "— |"
    geo = [r["speedup"] for r in rows if r["speedup"] and r["wmma_dispatched"]]
    for scheme in ("4w", "8da4w"):
        s = [r["speedup"] for r in rows if r["speedup"] and r["wmma_dispatched"] and r["key"][2] == scheme]
        if s:
            lines.append("")
            lines.append(
                f"- {scheme}: geomean WMMA speedup over tiled {statistics.geometric_mean(s):.2f}× "
                f"over {len(s)} cells (min {min(s):.2f}×, max {max(s):.2f}×)"
            )
    if geo:
        lines.append(f"- all: geomean {statistics.geometric_mean(geo):.2f}× over {len(geo)} cells")
    lines += ["", "Roofs used: " + ", ".join(f"{k} {v['value']:.2f} {v['unit']}" for k, v in sorted(roofs.items()) if k in (
        "matrix_fp16", "matrix_fp16_fp32", "matrix_int8", "alu_fp16", "dot_int8", "global_read"))]
    pathlib.Path(out).write_text("\n".join(lines) + "\n")
    pathlib.Path(out).with_suffix(".json").write_text(json.dumps(rows, indent=1, default=str))
    print("\n".join(lines[-6:]))


if __name__ == "__main__":
    main(*sys.argv[1:4])

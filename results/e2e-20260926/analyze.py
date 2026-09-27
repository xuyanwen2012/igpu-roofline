#!/usr/bin/env python3
"""Summarize e2e prefill runs (out/runs.jsonl) and compare with a microbench Amdahl prediction.

Measured: median prefill tok/s per (gpu, model, scheme, mode) over ok, uncontended repeats.
Predicted: the final microbench confirmation of each GPU gives per-shape linear kernel times
(texture3d, prefill M=2048) for the tuned kernel (--linear) and the tiled kernel (--baseline).
One prefill runs, per layer, 2 x wq_wo-shaped (wq, wo), 2 x wk_wv, 2 x w1_w3, 1 x w2 linears.
  L_tiled, L_tuned = layers * sum(count * kernel time)
  other            = e2e tiled prefill ms - L_tiled        (everything that is not a linear)
  predicted tuned  = other + L_tuned ; predicted speedup = e2e tiled / predicted tuned
Writes E2E.md and e2e_summary.json next to this script.
"""

import json
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE.parent
MICRO = {"4070tis": ART / "runs/4070ti-final3", "b580": ART / "confirm/b580-default-v1",
         "b70-0": ART / "confirm/b70-default-v1", "780m": ART / "confirm/780m-final"}
MODEL = {"1b": ("llama-3.2-1b", 16), "3b": ("llama-3.2-3b", 28), "8b": ("llama-3.1-8b", 32)}
PER_LAYER = {"wq_wo": 2, "wk_wv": 2, "w1_w3": 2, "w2": 1}
GPU_NAME = {"4070tis": "RTX 4070 Ti SUPER", "b70-0": "Arc Pro B70", "b580": "Arc B580", "780m": "Radeon 780M"}


def micro_times(d):
    """(model, scheme, suite) -> {op: median kernel us} for texture3d prefill cases."""
    acc = defaultdict(list)
    for suite in ("linear", "baseline"):
        for f in sorted(d.glob(f"{suite}-r*.json")):
            for c in json.loads(f.read_text())["cases"]:
                if c["regime"] == "prefill" and c["storage"] == "texture3d" and c.get("kernel_median_us"):
                    acc[(c["model"], c["scheme"], suite, c["op"])].append(c["kernel_median_us"])
    out = defaultdict(dict)
    for (m, s, suite, op), v in acc.items():
        out[(m, s, suite)][op] = st.median(v)
    return out


def main():
    runs = [json.loads(l) for l in (HERE / "out/runs.jsonl").read_text().splitlines() if l.strip()]
    groups = defaultdict(list)
    bad = defaultdict(int)
    for r in runs:
        key = (r["gpu"], r["size"], r["quant"], r["mode"])
        if r["status"] == "ok":
            groups[key].append(r)
        else:
            bad[key] += 1
    rows = []
    for gpu in GPU_NAME:
        micro = micro_times(MICRO[gpu]) if MICRO[gpu].exists() else {}
        for size in MODEL:
            for quant in ("4w", "8da4w"):
                t, w = groups.get((gpu, size, quant, "tiled")), groups.get((gpu, size, quant, "tuned"))
                if not t or not w:
                    continue
                row = dict(gpu=gpu, size=size, quant=quant, n=(len(t), len(w)),
                           bad=(bad[(gpu, size, quant, "tiled")], bad[(gpu, size, quant, "tuned")]))
                for mode, rs in (("tiled", t), ("tuned", w)):
                    tok = [r["tok_s"] for r in rs]
                    ms = [r["prefill_ms"] for r in rs]
                    row[mode] = dict(tok_s=st.median(tok), lo=min(tok), hi=max(tok),
                                     spread=(max(tok) - min(tok)) / st.median(tok), prefill_ms=st.median(ms))
                row["speedup"] = row["tuned"]["tok_s"] / row["tiled"]["tok_s"]
                model, layers = MODEL[size]
                lt, lw = micro.get((model, quant, "baseline")), micro.get((model, quant, "linear"))
                if lt and lw and set(PER_LAYER) <= set(lt) and set(PER_LAYER) <= set(lw):
                    L_t = layers * sum(PER_LAYER[o] * lt[o] for o in PER_LAYER) / 1000.0
                    L_w = layers * sum(PER_LAYER[o] * lw[o] for o in PER_LAYER) / 1000.0
                    P_t = row["tiled"]["prefill_ms"]
                    other = P_t - L_t
                    row.update(linear_ms_tiled=L_t, linear_ms_tuned=L_w, other_ms=other,
                               linear_share_tiled=L_t / P_t, predicted_speedup=P_t / (other + L_w),
                               linear_share_tuned=L_w / row["tuned"]["prefill_ms"])
                rows.append(row)
    (HERE / "e2e_summary.json").write_text(json.dumps(rows, indent=1))
    L = ["# End-to-end prefill (2048 tokens): tiled vs tuned linear kernels", "",
         "llama_main, --warmup, --max_new_tokens 1, same binary per GPU (tiled = ET_VK_FORCE_TILED_LINEAR=1). "
         "Median of ok, uncontended repeats (range in brackets). Predicted = Amdahl from the final "
         "microbench kernel times (texture3d) and the e2e tiled prefill time. Linear share = microbench "
         "linear time / e2e prefill time.", "",
         "| GPU | model | scheme | tiled tok/s | tuned tok/s | e2e speedup | predicted | linear share tiled -> tuned | n |",
         "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        f = lambda m: f"{r[m]['tok_s']:.0f} [{r[m]['lo']:.0f}-{r[m]['hi']:.0f}]"  # noqa: E731
        pred = f"{r['predicted_speedup']:.2f}x" if "predicted_speedup" in r else "-"
        share = (f"{r['linear_share_tiled']:.0%} -> {r['linear_share_tuned']:.0%}"
                 if "linear_share_tiled" in r else "-")
        L.append(f"| {GPU_NAME[r['gpu']]} | {r['size'].upper()} | {r['quant']} | {f('tiled')} | {f('tuned')} | "
                 f"**{r['speedup']:.2f}x** | {pred} | {share} | {r['n'][0]}+{r['n'][1]}"
                 + (f" (failed/contended {r['bad'][0]}+{r['bad'][1]})" if any(r['bad']) else "") + " |")
    spread = [(r["gpu"], r["size"], r["quant"], m, r[m]["spread"]) for r in rows for m in ("tiled", "tuned")
              if r[m]["spread"] > 0.05]
    L += ["", "Repeat spread > 5 %: " + (", ".join(f"{g} {s} {q} {m} {x:.0%}" for g, s, q, m, x in spread)
                                          if spread else "none")]
    (HERE / "E2E.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Tiled vs tuned correctness sanity: the token generated after the 1973-token real-text prompt."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
tail = (HERE / "prompt_check.txt").read_text().rstrip()[-60:]


def generated(logf):
    txt = logf.read_text()
    head = txt.split("PyTorchObserver", 1)[0]
    i = head.rfind(tail)
    return None if i < 0 else head[i + len(tail):].strip("\n")


rows = {}
for l in (HERE / "out/checks.jsonl").read_text().splitlines():
    r = json.loads(l)
    g = generated(HERE / "out" / r["gpu"] / f"{r['size']}_{r['quant']}_{r['mode']}_check.log") if r["status"] == "ok" else None
    rows[(r["gpu"], r["size"], r["quant"], r["mode"])] = (r["status"], g)
out = ["| GPU | model | scheme | tiled token | tuned token | match |", "|---|---|---|---|---|---|"]
for (gpu, s, q, m) in sorted(rows):
    if m != "tiled":
        continue
    t, w = rows[(gpu, s, q, "tiled")], rows.get((gpu, s, q, "tuned"), ("missing", None))
    out.append(f"| {gpu} | {s} | {q} | {t[1]!r} ({t[0]}) | {w[1]!r} ({w[0]}) | {'yes' if t[1] == w[1] and t[1] else 'NO'} |")
(HERE / "CHECKS.md").write_text("\n".join(out) + "\n")
print("\n".join(out))

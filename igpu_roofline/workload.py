"""Place ExecuTorch quantized-linear kernels on this device's measured roofline.

Input: a `test_llama_microbench.v1` JSON from ExecuTorch's Vulkan custom_ops test
and the device's `report/summary.json`. Only confirmed roofs with a tight repeat
spread are used as ceilings; anything else is listed but never compared against.

The byte count is the compulsory traffic of one linear (each operand read once,
output written once), so arithmetic intensity is an upper bound and the memory
ceiling a lower bound on time. Ops are 2*M*N*K (integer ops for 8da4w).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

SCHEMA = "test_llama_microbench.v1"
MAX_SPREAD = 0.05  # CLAUDE.md "Confirmed": repeat spread <= 5 %
MEMORY_ROOF = "global_read"

# Which compute roof a kernel is held to: (scheme, uses WMMA) -> roof keys, most
# specific first. 4w coopmat accumulates in fp16 (linear_q4gsw_coopmat_*); the
# 8da4w coopmat uses int8 x int8 -> int32; the 8da4w tiled kernel uses
# dotPacked4x8AccSatEXT; the 4w tiled kernel is fp16 FMA.
COMPUTE_ROOFS = {
    ("4w", True): ["matrix_fp16", "matrix_fp16_fp32"],
    ("8da4w", True): ["matrix_int8"],
    ("4w", False): ["alu_fp16"],
    ("8da4w", False): ["dot_int8"],
}
# The same MMA fed through shared memory: what a tiled WMMA kernel can reach.
FEED_ROOFS = {"4w": "matrix_fp16_feed_shared", "8da4w": "matrix_int8_feed_shared"}


def usable_roofs(summary: dict) -> tuple[dict, dict]:
    """Split short-run roofs into usable (confirmed, spread <= 5 %) and the rest."""
    usable, rejected = {}, {}
    for key, roof in summary.get("short_run", {}).items():
        if not roof.get("confirmed"):
            rejected[key] = "unconfirmed"
        elif roof.get("repeat_spread", 1.0) > MAX_SPREAD:
            rejected[key] = f"repeat spread {roof['repeat_spread']:.1%} > 5%"
        else:
            usable[key] = roof
    return usable, rejected


def roof_scale(roof: dict) -> float:
    """Roof value in ops/s or bytes/s."""
    unit = roof["unit"]
    for prefix, scale in (("T", 1e12), ("G", 1e9), ("M", 1e6)):
        if unit.startswith(prefix):
            return roof["value"] * scale
    raise ValueError(f"unknown roof unit {unit!r}")


def compulsory_bytes(case: dict, group_size: int) -> int:
    """Minimum DRAM traffic of one linear: int4 weights, fp16 scales, inputs, output."""
    m, k, n = case["M"], case["K"], case["N"]
    weights = k * n // 2 + (k // group_size) * n * 2
    # 8da4w: int8 activations + per-row fp32 scale / int32 zero point, int32 weight sums.
    inputs = m * k + m * 8 + n * 4 if case["scheme"] == "8da4w" else m * k * 2
    return weights + inputs + m * n * 2


def uses_wmma(kernel: str) -> bool:
    return "coopmat" in kernel


def place(case: dict, group_size: int, roofs: dict) -> dict:
    """One kernel: achieved rate, intensity, attainable ceiling and fraction of it."""
    wmma = uses_wmma(case["kernel"])
    ops = 2 * case["M"] * case["N"] * case["K"]
    nbytes = compulsory_bytes(case, group_size)
    seconds = case["kernel_median_us"] * 1e-6
    row = {
        "model": case.get("model"),
        "scheme": case["scheme"],
        "regime": case.get("regime"),
        "storage": case.get("storage"),
        "suite": case.get("suite"),
        "kernel": case["kernel"],
        "M": case["M"],
        "K": case["K"],
        "N": case["N"],
        "kernel_median_us": case["kernel_median_us"],
        "achieved_tops": ops / seconds / 1e12,
        "achieved_gbps": nbytes / seconds / 1e9,
        "intensity_ops_per_byte": ops / nbytes,
        "compute_roof": None,
        "memory_roof": None,
        "feed_roof": None,
    }
    compute = next(
        (k for k in COMPUTE_ROOFS[(case["scheme"], wmma)] if k in roofs), None
    )
    ceilings = {}
    if compute:
        row["compute_roof"] = compute
        ceilings["compute"] = roof_scale(roofs[compute])
    if MEMORY_ROOF in roofs:
        row["memory_roof"] = MEMORY_ROOF
        ceilings["memory"] = (
            roof_scale(roofs[MEMORY_ROOF]) * row["intensity_ops_per_byte"]
        )
    feed = FEED_ROOFS[case["scheme"]] if wmma else None
    if feed in roofs:
        row["feed_roof"] = feed
        row["feed_fraction"] = ops / seconds / roof_scale(roofs[feed])
    if ceilings:
        bound = min(ceilings, key=ceilings.get)
        row["bound"] = bound
        row["attainable_tops"] = ceilings[bound] / 1e12
        row["roof_fraction"] = ops / seconds / ceilings[bound]
        if "compute" in ceilings:
            row["compute_fraction"] = ops / seconds / ceilings["compute"]
        if "memory" in ceilings:
            row["memory_fraction"] = ops / seconds / ceilings["memory"]
    return row


def load_cases(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(Path(path).read_text())
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: expected schema {SCHEMA}, got {data.get('schema')}")
    cases = [
        c
        for c in data["cases"]
        if c.get("ok")
        and c.get("suite") != "correctness"
        and c.get("op") == "linear"
        and c.get("scheme") in ("4w", "8da4w")
        and (c.get("kernel_median_us") or 0) > 0
        and c.get("kernel")
    ]
    return data, cases


def analyze(folder: Path, et_json: Path) -> dict:
    summary = json.loads((folder / "report" / "summary.json").read_text())
    usable, rejected = usable_roofs(summary)
    meta, cases = load_cases(et_json)
    rows = [place(c, meta["group_size"], usable) for c in cases]
    result = {
        "device": summary.get("device"),
        "et_device": meta.get("device"),
        "et_json": str(et_json),
        "group_size": meta["group_size"],
        "roofs_used": {
            k: usable[k]
            for k in sorted(
                {
                    r[f]
                    for r in rows
                    for f in ("compute_roof", "memory_roof", "feed_roof")
                }
                - {None}
            )
        },
        "roofs_rejected": rejected,
        "rows": rows,
    }
    write(folder / "report", result)
    return result


def _pct(v):
    return f"{v:.0%}" if v is not None else "—"


def write(report: Path, result: dict):
    report.mkdir(parents=True, exist_ok=True)
    stem = Path(result["et_json"]).stem
    (report / f"workload-{stem}.json").write_text(json.dumps(result, indent=2))
    rows = result["rows"]
    if rows:
        with open(report / f"workload-{stem}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
            w.writeheader()
            w.writerows(rows)
    lines = [
        f"# ExecuTorch kernels on the {result['device']} roofline",
        "",
        f"Source: `{result['et_json']}` (ExecuTorch device: {result['et_device']}, "
        f"group size {result['group_size']}).",
        "",
        "Ops = 2·M·N·K (integer ops for 8da4w). Bytes = compulsory traffic "
        "(int4 weights + fp16 scales + inputs + fp16 output, each once), so intensity is an "
        "upper bound. Attainable = min(compute roof, intensity × DRAM read roof). "
        "Only confirmed roofs with repeat spread ≤ 5 % are used.",
        "",
        "## Roofs used",
        "",
        "| roof | confirmed median | unit | repeat spread |",
        "|---|---:|---|---:|",
    ]
    for k, v in result["roofs_used"].items():
        lines.append(
            f"| {k} | {v['value']:.3f} | {v['unit']} | {v['repeat_spread']:.1%} |"
        )
    lines += [
        "",
        "## Kernels",
        "",
        "| model | scheme | regime | storage | kernel | M×K×N | µs | TOP/s | ops/B | bound | "
        "% attainable | % compute roof | % shared-fed MMA |",
        "|---|---|---|---|---|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['model']} | {r['scheme']} | {r['regime']} | {r['storage']} | "
            f"`{r['kernel']}` | {r['M']}×{r['K']}×{r['N']} | {r['kernel_median_us']:.1f} | "
            f"{r['achieved_tops']:.2f} | {r['intensity_ops_per_byte']:.0f} | "
            f"{r.get('bound', 'no usable roof')} | {_pct(r.get('roof_fraction'))} | "
            f"{_pct(r.get('compute_fraction'))} | {_pct(r.get('feed_fraction'))} |"
        )
    missing = sorted(
        {
            k
            for r in rows
            for k in COMPUTE_ROOFS[(r["scheme"], uses_wmma(r["kernel"]))]
            + [MEMORY_ROOF]
            if k in result["roofs_rejected"]
        }
    )
    if missing:
        lines += ["", "## Roofs not usable", ""]
        lines += [f"- {k}: {result['roofs_rejected'][k]}" for k in missing]
    (report / f"WORKLOAD-{stem}.md").write_text("\n".join(lines) + "\n")

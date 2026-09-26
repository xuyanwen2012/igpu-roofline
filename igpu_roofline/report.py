"""Offline analysis: roof tables, hierarchical rooflines and figures.

Never talks to a device. Physical DRAM/cache traffic is never inferred from
logical bytes; all bandwidths are shader-logical.
"""

import csv
import json
import os
import statistics
from pathlib import Path

from . import admission, paths
from .planning import config_identity
from .stages import matrix_feed_key, quality, rate

os.environ.setdefault("MPLCONFIGDIR", str(paths.BUILD / "matplotlib-cache"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10, "figure.dpi": 140})
MiB = 1024**2
CONTROL_SUFFIXES = ("_volatile", "_hostcoherent", "_1acc", "_read_write_sync")
GLOBAL_OPS = ["read", "write", "copy", "scale", "add", "triad", "dot"]


# --- loading ---------------------------------------------------------------------------
def load_rows(folder: Path) -> list[dict]:
    """Every result row directly under <device>/<stage>/ (superseded/ is one level deeper)."""
    out = []
    for p in folder.glob("*/*.json"):
        if p.name.endswith((".config.json", ".telemetry.json")):
            continue
        try:
            r = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        if isinstance(r, dict) and "accepted" in r and "config" in r:
            r["source"] = str(p.relative_to(folder))
            out.append(r)
    return out


def metric(r: dict):
    """(roof key, work, unit, scale) of a result, or None for non-roof families."""
    c, a, f = r["config"], r["accounting"], r["config"]["family"]
    if f in ("latency", "ert"):
        return None
    if f in ("alu", "matrix", "dot"):
        integer = bool(a["integer_ops"])
        key = f + "_" + c["dtype"]
        if f == "matrix" and c.get("feed"):
            key = matrix_feed_key(c, a)
            if key.endswith(
                "_dram"
            ):  # streaming-bound: a bandwidth roof (see stages.rate)
                return key, a["logical_global_bytes"], "GB/s", 1e9
        return (
            key,
            a["float_ops"] + a["integer_ops"],
            "TOP/s" if integer else "TFLOP/s",
            1e12,
        )
    if f == "texture":
        from .stages import texture_key

        key = texture_key(c, a)
        return (key, a["logical_global_bytes"], "GB/s", 1e9) if key else None
    if c.get("role") == "cache":
        return "cache_read_effective", a["logical_global_bytes"], "GB/s", 1e9
    if f == "copy":
        return "vulkan_transfer_copy", a["logical_global_bytes"], "GB/s", 1e9
    if f == "shared":
        if c.get("kind") == "bw":
            suffix = "_read" if c["op"] == 0 else "_write"
        else:
            suffix = "_read_1acc" if c["op"] == 0 else "_read_write_sync"
        return "shared_" + c["dtype"] + suffix, a["logical_shared_bytes"], "GB/s", 1e9
    name = "global_" + GLOBAL_OPS[c["op"]]
    if c.get("volatile_global"):
        name += "_volatile"
    if c.get("memory_mode", "device_local") != "device_local":
        name += "_hostcoherent"
    return name, a["logical_global_bytes"], "GB/s", 1e9


def is_control(key: str) -> bool:
    return key.endswith(CONTROL_SUFFIXES)


def driver_reports_spill(folder: Path, name: str) -> bool:
    p = folder / "pipeline-inspection" / f"{name}.json"
    if not p.exists():
        return False
    for rec in json.loads(p.read_text()).get("records", []):
        for ex in rec.get("executables", []):
            for st in ex.get("statistics", []):
                if "spill" in st["name"].lower() and float(st.get("value") or 0) > 0:
                    return True
    return False


def choose_roofs(short: dict, sustained: dict) -> tuple[dict, str]:
    """Use sustained roofs only when every roof has >= 3 sustained batches."""
    needed = {k for k in short if k != "vulkan_transfer_copy" and not is_control(k)}
    complete = (
        bool(needed)
        and needed <= set(sustained)
        and all(
            sustained[k].get("batches", 0) >= 3
            and sustained[k].get("all_steady")
            and short[k].get("confirmed")
            for k in needed
        )
    )
    return (sustained, "sustained") if complete else (short, "short-run")


def hierarchical_ridges(roofs: dict) -> dict:
    """Ridge point (ops/byte) of every compute roof against every memory level."""
    result = {}
    for prefix in ("global_", "cache_", "shared_fp32_", "shared_fp16_"):
        bandwidth = max(
            (
                v["value"]
                for k, v in roofs.items()
                if k.startswith(prefix) and not is_control(k)
            ),
            default=0,
        )
        if bandwidth:
            result[prefix.rstrip("_")] = {
                k: v["value"] * 1000 / bandwidth
                for k, v in roofs.items()
                if v["unit"] in ("TFLOP/s", "TOP/s")
            }
    return result


# --- analysis ----------------------------------------------------------------------------
def analyze(folder: Path) -> dict:
    caps = json.loads((folder / "capabilities.json").read_text())
    manifest = json.loads((folder / "artifact-manifest.json").read_text())
    # Only rows of the current runner and the current build of each shader define roofs;
    # runner_history is provenance, not a licence to mix builds (an older, faster
    # confirmation could otherwise win under the current runner's name).
    runner = paths.manifest_runner(manifest)
    _, shader_shas, sustained_runner = admission.build_context(folder)
    all_rows = load_rows(folder)

    def current(r):
        return not admission.build_reasons(r, runner, shader_shas, sustained_runner)

    for r in all_rows:
        r["exclusion_reasons"] = admission.reasons(
            r, runner, shader_shas, sustained_runner
        )
    stale = [r["source"] for r in all_rows if not current(r)]
    valid = [
        r
        for r in all_rows
        if not r["exclusion_reasons"]
        and "accounting" in r
        and not r["source"].startswith(("validate/", "sustain-preflight-"))
    ]
    confirmations = admission.confirmed_groups(
        [r for r in all_rows if r["source"].startswith("confirm/") and current(r)],
        lambda r: not r["exclusion_reasons"],
        rate,
    )
    confirmed_sources = {v["row"]["source"]: v for v in confirmations.values()}
    # Unstable batches remain in their cohort so they cannot disappear from all_steady.
    sustained_rows = [
        r
        for r in all_rows
        if r["config"].get("duration_seconds", 0) > 0
        and not (set(r["exclusion_reasons"]) - {"sustained_unsteady"})
    ]
    valid_short = [r for r in valid if not r["config"].get("duration_seconds")]
    peak, sustained, sweep_peak = {}, {}, {}
    for r in valid_short + sustained_rows:
        if r["source"].startswith(("first-look/", "probe/")):
            continue  # smoke test and device-state sentinel never define roofs
        c = r["config"]
        if c["family"] == "memory" and c.get("role") != "cache":
            ws = r["accounting"].get("working_set_bytes", 0)
            if r["source"].startswith("sweep-cache/"):
                if not 32768 <= ws <= 4 * MiB:
                    continue
                r = dict(r)
                r["config"] = dict(c, role="cache")
            elif ws < 256 * MiB:
                continue
        m = metric(r)
        if m is None:
            continue
        key, work, unit, scale = m
        item = {
            "value": work / r["median_seconds"] / scale,
            "best": work / r["min_seconds"] / scale,
            "unit": unit,
            "source": r["source"],
            "config": r["config"],
            "cv": r["cv"],
            "samples": r["n"],
            "driver_reports_spill": driver_reports_spill(folder, r["config"]["name"]),
            "memory": (r.get("allocation") or {}).get("memory_mode"),
        }
        d = r.get("differential")
        if d and d.get("valid"):
            item["differential"] = work / d["incremental_seconds_for_L"] / scale
            item["fixed_fraction"] = d["fixed_fraction"]
        if r["source"].startswith("confirm/"):
            winner = confirmed_sources.get(r["source"])
            if not winner:
                continue
            values = [rate(x) / scale for x in winner["rows"]]
            med = winner["median"] / scale
            item.update(
                value=med,
                best=max(
                    metric(x)[1] / x["min_seconds"] / scale for x in winner["rows"]
                ),
                confirmed=True,
                repeats=len(values),
                repeat_min=min(values),
                repeat_max=max(values),
                repeat_spread=(max(values) - min(values)) / med,
            )
            peak[key] = item
            continue
        if r["source"].startswith("sustain-"):
            item.update(
                value=work / r["last60"]["median_seconds"] / scale,
                steady=r["steady_last60"],
                gpu_duty_fraction=r.get("gpu_timestamp_duty_fraction"),
                duration_seconds=r["config"].get("duration_seconds"),
            )
            winner = confirmations.get(c.get("sustained_roof"))
            if not winner or not admission.sustained_reference_matches(
                c, winner["row"]["config"]
            ):
                r["exclusion_reasons"].append("unlinked_sustained_configuration")
                continue
            sustained.setdefault((key, config_identity(c)), []).append(item)
        else:
            sweep_peak[key] = max(sweep_peak.get(key, 0), item["value"])
            if key not in peak or (
                not peak[key].get("confirmed") and item["value"] > peak[key]["value"]
            ):
                peak[key] = item
    for key, item in peak.items():
        if item.get("confirmed") and key in sweep_peak:
            item["sweep_best_unconfirmed"] = sweep_peak[key]

    # Sentinel timeline (clock proxy measured before/after every stage).
    probes = sorted(
        (
            r["config"].get("probe_utc", ""),
            r["config"].get("probe", ""),
            r["accounting"]["float_ops"] / r["median_seconds"] / 1e12,
        )
        for r in all_rows
        if r["source"].startswith("probe/")
        and r.get("accepted")
        and current(r)
        and not admission.validation_reasons(r)
        and r.get("accounting")
    )
    ref = statistics.median(x[2] for x in probes) if probes else 0
    sentinel = {
        "config": "alu_fp32_v4_c16 wg256 groups512",
        "unit": "TFLOP/s",
        "median": ref,
        "degraded_below": 0.85 * ref,
        "timeline": [
            {"utc": u, "label": lab, "value": v, "degraded": v < 0.85 * ref}
            for u, lab, v in probes
        ],
    }
    sustained_summary: dict[str, dict] = {}
    for (key, _), items in sorted(sustained.items()):
        duration = items[0]["duration_seconds"]
        # Distinct batch directories, never repeated files within one batch.
        batches = {}
        for item in items:
            batches.setdefault(item["source"].split("/")[0], []).append(item)
        vs = [items[0] for items in batches.values()]
        candidate = {
            "value": statistics.median(x["value"] for x in vs),
            "unit": vs[0]["unit"],
            "batches": len(vs),
            "all_steady": all(x["steady"] for x in items),
            "duration_seconds": duration,
            "values": [x["value"] for x in vs],
            "gpu_duty_fractions": [x["gpu_duty_fraction"] for x in vs],
            "sources": [x["source"] for x in vs],
        }
        if (
            key not in sustained_summary
            or candidate["batches"] >= sustained_summary[key]["batches"]
        ):
            sustained_summary[key] = candidate
    valid = [r for r in valid if not r["exclusion_reasons"]]
    roofs, basis = choose_roofs(peak, sustained_summary)
    feed = matrix_feed_by_reuse(valid)
    plans = sorted({str(r["plan"]) for r in all_rows if r.get("plan")})
    summary = {
        "device": caps["gpu"],
        "serial": caps["serial"],
        "plans": plans,
        "roof_basis": basis,
        "sentinel": sentinel,
        "stale_rows_excluded": len(stale),
        "excluded_rows": {
            r["source"]: r["exclusion_reasons"]
            for r in all_rows
            if r["exclusion_reasons"]
        },
        "validation_scope": "pre_and_post",
        "missing_reasons": (["No current confirmed roofs"] if not confirmations else [])
        + (
            [
                "Sustained roofs require three distinct stable batches per current confirmed configuration and duration"
            ]
            if basis != "sustained"
            else []
        ),
        "clock_state": caps.get("clock_state"),
        "short_run": peak,
        "sustained": sustained_summary,
        "ridges": {
            "short_run": hierarchical_ridges(peak),
            "roofs": hierarchical_ridges(roofs),
        },
        "physical_dram_bandwidth": None,
        "physical_cache_bandwidth": None,
        "matrix_feed_by_reuse": feed,
        "git_commit": manifest.get("git_commit"),
        "runner_sha256": paths.manifest_runner(manifest),
    }
    report = folder / "report"
    report.mkdir(exist_ok=True)
    (report / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    with (report / "all-configurations.csv").open("w") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "source",
                "accepted",
                "exclusion_reasons",
                "validation_scope",
                "name",
                "family",
                "median_seconds",
                "min_seconds",
                "cv",
                "n",
                "float_ops",
                "integer_ops",
                "logical_global_bytes",
                "logical_shared_bytes",
            ]
        )
        for r in all_rows:
            a = r.get("accounting", {})
            w.writerow(
                [
                    r["source"],
                    r["accepted"],
                    ";".join(r["exclusion_reasons"]),
                    r.get("validation_scope", "historical_pre_only"),
                    r["config"]["name"],
                    r["config"]["family"],
                ]
                + [r.get(x) for x in ("median_seconds", "min_seconds", "cv", "n")]
                + [
                    a.get(x)
                    for x in (
                        "float_ops",
                        "integer_ops",
                        "logical_global_bytes",
                        "logical_shared_bytes",
                    )
                ]
            )

    write_report_md(report, caps, summary, peak, sustained_summary, roofs, basis)
    plot_rooflines(report, caps, roofs, basis, valid)
    plot_working_set(report, caps, valid)
    plot_shared_stride(report, caps, valid)
    write_sustained(report, folder, caps, valid)
    from . import insights

    insights.write_all(folder, report, valid, caps, summary)
    return summary


def matrix_feed_by_reuse(valid: list) -> list[dict]:
    """Fed cooperative matrix per (dtype, source, CHAINS): the best validated median, with
    ops per loaded A/B byte, so a kernel's reuse can be looked up directly. DRAM-fed rates
    grow with CHAINS until the matrix unit limits them; their roof is a bandwidth."""
    best = {}
    for r in valid:
        c, a = r["config"], r["accounting"]
        if (
            c["family"] != "matrix"
            or not c.get("feed")
            or r["source"].startswith(("first-look/", "probe/", "sustain-"))
        ):
            continue
        level = matrix_feed_key(c, a).rsplit("_", 1)[1]
        ops = a["float_ops"] + a["integer_ops"]
        item = {
            "dtype": c["dtype"],
            "level": level,
            "chains": c["chains"],
            "rate": ops / r["median_seconds"] / 1e12,
            "unit": "TOP/s" if a["integer_ops"] else "TFLOP/s",
            "load_gbps": a["matrix_load_bytes"] / r["median_seconds"] / 1e9,
            "ops_per_load_byte": ops / a["matrix_load_bytes"],
            "gates": quality(r),
            "source": r["source"],
        }
        k = (c["dtype"], level, c["chains"])
        if k not in best or item["rate"] > best[k]["rate"]:
            best[k] = item
    order = {"shared": 0, "cache": 1, "mid": 2, "dram": 3}
    return [
        best[k] for k in sorted(best, key=lambda k: (k[0], order.get(k[1], 9), k[2]))
    ]


# --- REPORT.md ---------------------------------------------------------------------------
def _clock_line(caps: dict) -> str:
    cs = caps.get("clock_state") or {}
    if not cs.get("domains"):
        return "GPU clock state **unavailable** (frequency and pinning not verified)."
    pinned = cs.get("pinned_domains") or []
    if pinned:
        dom = cs["domains"][pinned[0]]
        return (
            f"GPU clock **pinned** ({pinned[0]}: {int(dom['min']) / 1e6:g} MHz)."
            if dom["min"].isdigit()
            else f"GPU clock pinned ({pinned[0]})."
        )
    return "GPU clock **DVFS-governed** (not pinned); results depend on the governor and thermal state."


def write_report_md(
    report: Path,
    caps: dict,
    summary: dict,
    peak: dict,
    sustained: dict,
    roofs: dict,
    basis: str,
):
    props = caps.get("device_properties", {})
    lines = [
        f"# {caps['gpu']} roofline report",
        "",
        f"Device: {props.get('ro.product.manufacturer', '')} {props.get('ro.product.model', '')} "
        f"(SoC {props.get('ro.soc.model', '?')}), {'' if caps.get('backend') == 'local' else 'Android '}"
        f"{props.get('ro.build.version.release', '?')}, "
        f"driver {caps['driver_version']}, subgroup {caps['subgroup']}.",
        f"Plan(s): {', '.join(summary['plans']) or '?'}. {_clock_line(caps)}",
        f"Code: {summary['git_commit']}, runner {(summary['runner_sha256'] or 'missing')[:16]}. "
        f"Rows from other runner or shader builds excluded: {summary.get('stale_rows_excluded', 0)}.",
        "",
        "Validation policy: **pre_and_post**; checks bracket continuous sampling and do not guarantee detection of transient errors between checks. Historical pre-only rows are diagnostic only.",
        f"Excluded rows: {len(summary.get('excluded_rows', {}))}; reasons are in all-configurations.csv.",
        *summary.get("missing_reasons", []),
        "",
        "Short-run columns are the best validated configuration: median and best (minimum time, the STREAM/"
        "BabelStream convention) of the samples, and the differential rate (paired L vs L/2 runs, removing fixed "
        "per-dispatch cost). Sustained is the median of the last 60 s of each sustained run "
        "(durations are recorded in sustained-runs.csv). Controls never define a "
        "roof. `spill` marks variants whose driver statistics report register spilling: spills only slow a "
        "kernel, so the value is still an achievable lower bound.",
        "",
        "| roof | short median | short best | differential | sustained | unit |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for k in sorted(peak, key=lambda k: (is_control(k), k)):
        v, sv = peak[k], sustained.get(k)
        tags = (" (control)" if is_control(k) else "") + (
            " (spill)" if v.get("driver_reports_spill") else ""
        )
        diff = (
            f"{v['differential']:.3f} (fixed {v['fixed_fraction']:.0%})"
            if "differential" in v
            else "—"
        )
        sus = (
            (
                f"{sv['value']:.3f} ({sv['batches']}×"
                + ("" if sv["all_steady"] else ", not steady")
                + ")"
            )
            if sv
            else "—"
        )
        lines.append(
            f"| {k}{tags} | {v['value']:.3f} | {v['best']:.3f} | {diff} | {sus} | {v['unit']} |"
        )
    lines += [
        "",
        "## Roof confirmation",
        "",
        "Each roof's top candidates were re-measured in fresh processes, round-robin with alternating order. "
        "The roof is the median of the best candidate's repeats; the sweep maximum (a single run) is shown for "
        "comparison. Roofs without a quality-passing candidate (standard error of the median <= 3 %, not short, fixed cost <= 10 %) are "
        "marked unconfirmed.",
        "",
        "| roof | confirmed median | repeat range | repeats | sweep max (unconfirmed) |",
        "|---|---:|---:|---:|---:|",
    ]
    for k in sorted(peak):
        v = peak[k]
        if v.get("confirmed"):
            sweep = (
                f"{v['sweep_best_unconfirmed']:.3f}"
                if "sweep_best_unconfirmed" in v
                else "—"
            )
            lines.append(
                f"| {k} | {v['value']:.3f} | {v['repeat_min']:.3f}–{v['repeat_max']:.3f} ({v['repeat_spread']:.1%}) "
                f"| {v['repeats']} | {sweep} |"
            )
        elif not is_control(k):
            lines.append(f"| {k} | unconfirmed | — | — | {v['value']:.3f} |")
    if summary.get("matrix_feed_by_reuse"):
        lines += [
            "",
            "## Cooperative matrix fed from memory, by reuse",
            "",
            "Best validated median per source and CHAINS (multiply-adds per loaded A/B tile pair). "
            "`load GB/s` counts the A/B tile bytes loaded. DRAM-fed rates grow with reuse until the matrix unit "
            "limits them, so the `matrix_*_feed_dram` roof above is a bandwidth; look a kernel's ops per loaded "
            "byte up here instead. `gates` lists quality gates the row failed (such rows never define a roof).",
            "",
            "| dtype | source | CHAINS | ops / loaded byte | rate | load GB/s | gates |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        lines += [
            f"| {x['dtype']} | {x['level']} | {x['chains']} | {x['ops_per_load_byte']:.1f} | {x['rate']:.3f} {x['unit']} "
            f"| {x['load_gbps']:.1f} | {', '.join(x['gates']) or '—'} |"
            for x in summary["matrix_feed_by_reuse"]
        ]
    sen = summary["sentinel"]
    lines += [
        "",
        "## Device-state sentinel",
        "",
        f"`{sen['config']}` measured before and after every stage and every 20 configurations. Values below 85 % "
        f"of the median reading ({sen['median']:.3f} TFLOP/s) mark a stage that ran on a throttled or otherwise degraded device; "
        "re-measure those stages.",
        "",
        "| UTC | label | TFLOP/s | state |",
        "|---|---|---:|---|",
    ]
    lines += [
        f"| {x['utc'][:19]} | {x['label']} | {x['value']:.3f} | {'**degraded**' if x['degraded'] else 'ok'} |"
        for x in sen["timeline"]
    ]
    lines += [
        "",
        f"## Ridge points ({basis} roofs)",
        "",
        "Arithmetic intensity (ops per byte of that level) at which each compute roof meets each memory roof.",
        "",
        "| compute roof | " + " | ".join(summary["ridges"]["roofs"]) + " |",
        "|---|" + "---:|" * len(summary["ridges"]["roofs"]),
    ]
    computes = sorted(
        {k for level in summary["ridges"]["roofs"].values() for k in level}
    )
    for k in computes:
        lines.append(
            f"| {k} | "
            + " | ".join(
                f"{summary['ridges']['roofs'][lvl].get(k, 0):.2f}"
                for lvl in summary["ridges"]["roofs"]
            )
            + " |"
        )
    lines += [
        "",
        "## Figures",
        "",
        "![roofline](roofline.png)",
        "",
        "![working set](working-set.png)",
        "",
        "![shared stride](shared-stride.png)",
        "",
        "![sustained](sustained-trends.png)",
        "",
        "See also [TUNING.md](TUNING.md), [SUPPLEMENT.md](SUPPLEMENT.md) (latency, TLB, line size, ERT, "
        "memory type) and [ISA-CHECK.md](ISA-CHECK.md).",
        "",
        "## Limits",
        "",
        "- Bandwidths are shader-logical bytes; physical DRAM/L2 traffic is not measurable without "
        "`VK_KHR_performance_query` (exposed: "
        + str(caps.get("performance_query_exposed"))
        + ").",
        "- No vendor theoretical peaks are used; values are achievable rates on this device and driver.",
        "- Cache knees move with workgroup size and are not cache capacities; see the pointer-chase results.",
        "- Sustained values need 3 batches (plan `gold`) before they replace short-run roofs.",
    ]
    (report / "REPORT.md").write_text("\n".join(lines) + "\n")


# --- figures -----------------------------------------------------------------------------
def plot_rooflines(report: Path, caps: dict, roofs: dict, basis: str, valid: list):
    x = np.logspace(-2, 4, 300)
    panels = [
        ("global_", "DRAM (>=256 MiB working set)"),
        ("cache_", "Cache reuse (<=4 MiB, not an identified L2)"),
        ("shared_", "Workgroup (shared) memory"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    ert = {}
    for r in valid:
        if r["source"].startswith("ert/"):
            ai = r["config"]["flops_per_element"] * 8 / 32
            ert[ai] = max(
                ert.get(ai, 0), r["accounting"]["float_ops"] / r["median_seconds"] / 1e9
            )
    for ax, (prefix, title) in zip(axes, panels):
        bws = [
            v["value"]
            for k, v in roofs.items()
            if k.startswith(prefix) and not is_control(k)
        ]
        bandwidth = max(bws, default=0)
        for k, v in sorted(roofs.items()):
            if v["unit"] in ("TFLOP/s", "TOP/s") and bandwidth:
                ax.loglog(
                    x,
                    np.minimum(v["value"] * 1e3, x * bandwidth),
                    label=f"{k} ({v['value']:.2f} {v['unit']})",
                )
        if prefix == "global_" and ert:
            xs = sorted(ert)
            ax.loglog(
                xs, [ert[a] for a in xs], "ko-", ms=3, label="ERT measured (fp32)"
            )
        ax.set(
            xlabel="ops / byte of this level",
            ylabel="GFLOP/s or GOP/s",
            title=f"{title}\n{bandwidth:.0f} GB/s",
        )
        ax.grid(True, which="both", alpha=0.2)
        if ax.lines:
            ax.legend(fontsize=6)
    fig.suptitle(f"{caps['gpu']} — hierarchical roofline ({basis} roofs)")
    fig.tight_layout()
    fig.savefig(report / "roofline.png")
    plt.close(fig)


def plot_working_set(report: Path, caps: dict, valid: list):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=True)
    for ax, width in zip(axes, (1, 2, 4)):
        series = {}
        for r in valid:
            c = r["config"]
            if r["source"].startswith("sweep-cache/") and c["width"] == width:
                a = r["accounting"]
                series.setdefault(c["wg"], []).append(
                    (
                        a["working_set_bytes"],
                        a["logical_global_bytes"] / r["median_seconds"] / 1e9,
                    )
                )
        for wg, pts in sorted(series.items()):
            pts.sort()
            ax.plot([p[0] for p in pts], [p[1] for p in pts], ".-", label=f"WG {wg}")
        ax.set(
            xscale="log",
            yscale="log",
            xlabel="working set (bytes)",
            title=f"read, vec{width}",
        )
        ax.grid(True, which="both", alpha=0.2)
        if series:
            ax.legend(fontsize=8)
    axes[0].set_ylabel("GB/s (shader-logical)")
    fig.suptitle(f"{caps['gpu']} — read bandwidth vs working set")
    fig.tight_layout()
    fig.savefig(report / "working-set.png")
    plt.close(fig)


def plot_shared_stride(report: Path, caps: dict, valid: list):
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), sharex=True)
    series_defs = [
        ("bw", 0, 8, "read, 8 accumulators", "o-"),
        ("bw", 2, 8, "pure write", "s-"),
        ("", 0, None, "read, 1 accumulator (control)", ".--"),
        ("", 1, None, "read/write + barriers (control)", ".:"),
    ]
    for row, dtype in enumerate(("fp32", "fp16")):
        scalar = 2 if dtype == "fp16" else 4
        for col, width in enumerate((1, 2, 4)):
            ax = axes[row, col]
            for kind, op, acc, label, style in series_defs:
                pts = []
                for r in valid:
                    c = r["config"]
                    if (
                        not r["source"].startswith("sweep-shared/")
                        or c.get("kind", "") != kind
                        or c["dtype"] != dtype
                        or c["width"] != width
                        or c["op"] != op
                        or c["wg"] != 64
                        or (acc and c.get("accumulators") != acc)
                        or c["shared_count"] * width * scalar
                        != caps["max_shared_bytes"]
                    ):
                        continue
                    pts.append(
                        (
                            c["stride"],
                            r["accounting"]["logical_shared_bytes"]
                            / r["median_seconds"]
                            / 1e9,
                        )
                    )
                pts.sort()
                if pts:
                    ax.plot(
                        [p[0] for p in pts], [p[1] for p in pts], style, label=label
                    )
            ax.set(
                xscale="log",
                xlabel="element stride",
                ylabel="GB/s",
                title=f"{dtype} vec{width}",
            )
            ax.grid(True, alpha=0.2)
            if ax.lines:
                ax.legend(fontsize=6)
    fig.suptitle(f"{caps['gpu']} — shared memory vs stride (WG 64, max allocation)")
    fig.tight_layout()
    fig.savefig(report / "shared-stride.png")
    plt.close(fig)


def write_sustained(report: Path, folder: Path, caps: dict, valid: list):
    rows = []
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))
    shown = [
        "alu_fp32",
        "alu_fp16",
        "dot_int8",
        "global_copy",
        "cache_read_effective",
        "shared_fp32_read",
    ]
    for r in valid:
        if not r["source"].startswith("sustain-"):
            continue
        m = metric(r)  # the cache roof's config carries role="cache"
        if m is None:
            continue
        key, work, unit, scale = m
        samples = [
            json.loads(x)
            for x in (folder / r["raw"]).read_text().splitlines()
            if x.startswith("{")
        ]
        samples = [s for s in samples if s.get("event") == "sample"]
        if not samples:
            continue
        first = [s["seconds"] for s in samples if s["elapsed_seconds"] <= 60]
        tele_path = (folder / r["raw"]).with_suffix(".telemetry.json")
        tele = json.loads(tele_path.read_text()) if tele_path.exists() else []
        gpu_t = [
            next(v for k, v in t["temperatures_c"].items() if "gpu" in k.lower())
            for t in tele
            if any("gpu" in k.lower() for k in (t.get("temperatures_c") or {}))
        ]
        freqs = []
        for t in tele:
            vals = [
                int(v)
                for v in (t.get("gpu_freq") or {}).values()
                if str(v).strip().isdigit()
            ]
            if vals:
                freqs.append(vals[0])
        rows.append(
            {
                "metric": key,
                "source": r["source"],
                "samples": len(samples),
                "unit": unit,
                "first60_rate": work / statistics.median(first) / scale,
                "last60_rate": work / r["last60"]["median_seconds"] / scale,
                "last60_cv": r["last60"]["cv"],
                "steady_last60": r["steady_last60"],
                "gpu_duty_fraction": r.get("gpu_timestamp_duty_fraction"),
                "gpu_temp_start_c": gpu_t[0] if gpu_t else None,
                "gpu_temp_max_c": max(gpu_t) if gpu_t else None,
                "gpu_freq_min": min(freqs) if freqs else None,
                "gpu_freq_max": max(freqs) if freqs else None,
            }
        )
        if key in shown:
            ax = axes.flat[shown.index(key)]
            bins = {}
            for s in samples:
                bins.setdefault(int(s["elapsed_seconds"] // 10), []).append(
                    s["seconds"]
                )
            xs = sorted(bins)
            ax.plot(
                [i * 10 + 5 for i in xs],
                [work / statistics.median(bins[i]) / scale for i in xs],
                label=r["source"].split("/")[0],
            )
    for ax, key in zip(axes.flat, shown):
        ax.set(title=key, xlabel="elapsed (s)")
        ax.grid(True, alpha=0.2)
        if ax.lines:
            ax.legend(fontsize=7)
        else:
            ax.text(0.5, 0.5, "no sustained run", ha="center", transform=ax.transAxes)
    fig.suptitle(f"{caps['gpu']} — sustained runs, 10 s median bins")
    fig.tight_layout()
    fig.savefig(report / "sustained-trends.png")
    plt.close(fig)
    if rows:
        with (report / "sustained-runs.csv").open("w") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def analyze_all(root: Path) -> list[dict]:
    out = []
    for folder in sorted(root.iterdir()):
        if (
            folder.is_dir()
            and (folder / "capabilities.json").exists()
            and (folder / "artifact-manifest.json").exists()
        ):
            s = analyze(folder)
            print(
                f"{s['device']} ({s['serial']}): {len(s['short_run'])} roofs, {len(s['sustained'])} sustained -> {folder / 'report'}"
            )
            out.append(s)
    return out

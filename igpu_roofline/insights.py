"""Supplementary results and the shader-tuning guide.

SUPPLEMENT.md  latency / TLB / line size, ERT, memory-type control
ISA-CHECK.md   SPIR-V ledger + driver statistics + ISA (driver or offline) per roof
TUNING.md      actionable guidance derived only from this device's measurements
"""

import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

from . import admission, paths
from .isa_offline import isa_summary

MiB = 1024**2


def _rate(r: dict) -> float:
    a, f = r["accounting"], r["config"]["family"]
    if f in ("alu", "dot", "matrix", "ert"):
        return (a["float_ops"] + a["integer_ops"]) / r["median_seconds"] / 1e9
    if f == "shared":
        return a["logical_shared_bytes"] / r["median_seconds"] / 1e9
    return a["logical_global_bytes"] / r["median_seconds"] / 1e9


def latency_ns(r: dict) -> float:
    """Per-load latency, from the differential per-loop time when valid (16 loads per loop)."""
    d = r.get("differential") or {}
    if d.get("valid"):
        return d["seconds_per_loop"] / 16 * 1e9
    loads = 16 * r["effective_loops"] * r["config"].get("batch_dispatches", 1)
    return r["median_seconds"] / loads * 1e9


def _stage(rows, prefix):
    return [r for r in rows if r["source"].startswith(prefix + "/")]


def write_all(folder: Path, report: Path, all_rows: list, caps: dict, summary: dict):
    context = admission.build_context(folder)
    ok = [
        r
        for r in all_rows
        if not admission.reasons(r, *context)
        and not r.get("exclusion_reasons")
        and "accounting" in r
    ]
    write_supplement(report, ok, caps)
    write_isa_check(folder, report, caps, summary)
    write_tuning(folder, report, ok, caps)


# --- SUPPLEMENT.md ---------------------------------------------------------------------
def write_supplement(report: Path, ok: list, caps: dict):
    L = [f"# {caps['gpu']} supplementary measurements", ""]
    capacity = sorted(
        _stage(ok, "latency-capacity"),
        key=lambda r: r["accounting"]["working_set_bytes"],
    )
    tlb = sorted(
        _stage(ok, "latency-tlb"), key=lambda r: r["accounting"]["working_set_bytes"]
    )
    stride = sorted(
        _stage(ok, "latency-stride"),
        key=lambda r: (
            r["accounting"]["working_set_bytes"],
            r["accounting"]["chain_stride_bytes"],
        ),
    )
    L += [
        "## Load-to-use latency (pointer chasing)",
        "",
        "One invocation follows a host-built chain `j = next[j]`; every load depends on the previous one. "
        "Each dispatch walks the whole chain (2^16..2^20 loads); latency is the differential per-load time "
        "(fixed dispatch cost removed), in ns (clocks are not pinned unless the report says so).",
        "",
        "| working set (random, 64 B nodes) | latency ns |",
        "|---:|---:|",
    ]
    L += [
        f"| {r['accounting']['working_set_bytes'] / 1024:g} KiB | {latency_ns(r):.1f} |"
        for r in capacity
    ]
    if tlb:
        page = tlb[0]["config"].get("page_size")
        L += [
            "",
            f"| TLB test: pages touched (one node per {page} B page) | span | latency ns |",
            "|---:|---:|---:|",
        ]
        L += [
            f"| {r['accounting']['working_set_bytes'] // page} | {r['accounting']['working_set_bytes'] / MiB:g} MiB | {latency_ns(r):.1f} |"
            for r in tlb
        ]
    if stride:
        L += [
            "",
            "Line size (Saavedra): sequential chains over an array larger than the level under test. Below the "
            "line size several loads share a line; at the line size every load is a new line.",
            "",
            "| array | stride | avg latency ns |",
            "|---:|---:|---:|",
        ]
        L += [
            f"| {r['accounting']['working_set_bytes'] / MiB:g} MiB | {r['accounting']['chain_stride_bytes']} B | {latency_ns(r):.1f} |"
            for r in stride
        ]
    if capacity or stride:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
        if capacity:
            axes[0].plot(
                [r["accounting"]["working_set_bytes"] for r in capacity],
                [latency_ns(r) for r in capacity],
                ".-",
                label="64 B random",
            )
        if tlb:
            axes[0].plot(
                [r["accounting"]["working_set_bytes"] for r in tlb],
                [latency_ns(r) for r in tlb],
                "x--",
                label="1 per page (TLB)",
            )
        axes[0].set(
            xscale="log",
            xlabel="working set (bytes)",
            ylabel="latency (ns)",
            title="capacity / TLB",
        )
        axes[0].legend(fontsize=8)
        for size in sorted({r["accounting"]["working_set_bytes"] for r in stride}):
            pts = [
                (r["accounting"]["chain_stride_bytes"], latency_ns(r))
                for r in stride
                if r["accounting"]["working_set_bytes"] == size
            ]
            axes[1].plot(
                [p[0] for p in pts],
                [p[1] for p in pts],
                ".-",
                label=f"{size / MiB:g} MiB array",
            )
        axes[1].set(
            xscale="log",
            xlabel="stride (bytes)",
            ylabel="avg latency (ns)",
            title="line size",
        )
        if stride:
            axes[1].legend(fontsize=8)
        for ax in axes:
            ax.grid(True, which="both", alpha=0.2)
        fig.suptitle(f"{caps['gpu']} — pointer chasing")
        fig.tight_layout()
        fig.savefig(report / "latency.png")
        plt.close(fig)
        L += ["", "![latency](latency.png)"]

    ert = _stage(ok, "ert")
    if ert:
        L += [
            "",
            "## ERT (Empirical Roofline Toolkit) sweep",
            "",
            "Each element: load 16 B, F dependent FMAs per component in ERT's Horner form (`y = y*x + a`, which a "
            "compiler cannot collapse), store 16 B. AI = F*8/32 FLOP/byte.",
            "",
            "| F | AI | WG | GFLOP/s | GB/s |",
            "|---:|---:|---:|---:|---:|",
        ]
        for r in sorted(
            ert, key=lambda r: (r["config"]["flops_per_element"], r["config"]["wg"])
        ):
            a, f = r["accounting"], r["config"]["flops_per_element"]
            L.append(
                f"| {f} | {f * 8 / 32:g} | {r['config']['wg']} | {a['float_ops'] / r['median_seconds'] / 1e9:.1f} | "
                f"{a['logical_global_bytes'] / r['median_seconds'] / 1e9:.1f} |"
            )

    control = _stage(ok, "control-memory-type")
    if control:
        by = {}
        for r in control:
            by.setdefault(r["config"]["name"], {}).setdefault(
                r["config"].get("memory_mode", "device_local"), []
            ).append(_rate(r))
        L += [
            "",
            "## Memory type (A/B)",
            "",
            "Same kernel and 256 MiB working set; only the buffer memory type changes. Arms alternate order each "
            "repeat; medians (range).",
            "",
            "| kernel | DEVICE_LOCAL GB/s | host-visible coherent GB/s | ratio |",
            "|---|---:|---:|---:|",
        ]
        for name, v in sorted(by.items()):
            d, h = v.get("device_local"), v.get("host_coherent")
            if d and h:
                L.append(
                    f"| {name} | {statistics.median(d):.1f} ({min(d):.1f}–{max(d):.1f}) | "
                    f"{statistics.median(h):.1f} ({min(h):.1f}–{max(h):.1f}) | {statistics.median(d) / statistics.median(h):.2f}× |"
                )
        fallback = any(
            b.get("fallback_host_visible")
            for r in control
            for b in (r.get("allocation") or {}).get("buffers", [])
        )
        if fallback:
            L.append(
                "\nThis driver exposes no DEVICE_LOCAL-only type for storage buffers; the runner used its host-visible fallback."
            )
    (report / "SUPPLEMENT.md").write_text("\n".join(L) + "\n")


# --- ISA-CHECK.md ----------------------------------------------------------------------
def _driver_stats(folder: Path, name: str):
    p = folder / "pipeline-inspection" / f"{name}.json"
    if not p.exists():
        return None
    stats = {}
    for rec in json.loads(p.read_text()).get("records", []):
        for ex in rec.get("executables", []):
            for st in ex.get("statistics", []):
                stats[st["name"]] = st.get("value")
    return stats


def write_isa_check(folder: Path, report: Path, caps: dict, summary: dict):
    manifest = {m["name"]: m for m in json.loads(paths.SHADER_MANIFEST.read_text())}
    keep = (
        "fma",
        "dot",
        "coopmat_muladd",
        "load_StorageBuffer",
        "store_StorageBuffer",
        "load_Workgroup",
        "store_Workgroup",
        "control_barrier",
    )
    L = [
        f"# {caps['gpu']} SPIR-V / driver / ISA check",
        "",
        "1. **SPIR-V ledger**: exact static counts asserted at build time for every variant.",
        "2. **Driver statistics** (`VK_KHR_pipeline_executable_properties`): registers, spills, instruction counts.",
        "3. **ISA**: text returned by the driver when it offers one; otherwise an offline vendor compiler "
        "(malioc for Mali, RGA for AMD RDNA as an approximation). All static, not runtime counters.",
        "",
        "| roof | variant | SPIR-V ledger | driver statistics | ISA |",
        "|---|---|---|---|---|",
    ]
    for key, item in sorted(summary["short_run"].items()):
        name = item["config"]["name"]
        m = manifest.get(name, {})
        ledger = ", ".join(
            f"{k}={v}" for k, v in m.get("spirv_ledger", {}).items() if k in keep and v
        )
        stats = _driver_stats(folder, name)
        driver = (
            "not inspected"
            if stats is None
            else "; ".join(
                f"{k}={v}"
                for k, v in stats.items()
                if any(
                    t in k.lower()
                    for t in (
                        "register",
                        "spill",
                        "instruction count all",
                        "alu instruction",
                        "arithmetic fma",
                        "vgpr",
                    )
                )
            )
            or "none reported"
        )
        isa_files = sorted((folder / "pipeline-inspection").glob(f"{name}.*ISA*.txt"))
        if isa_files and m:
            s = isa_summary(isa_files[0].read_text(), m)
            check = (
                ""
                if s["expected_scalar_fma"] is None
                else (
                    " ✓"
                    if s["fma_matches_design"]
                    else f" ✗ (design {s['expected_scalar_fma']})"
                )
            )
            isa = (
                f"driver ISA: VGPR {s['header'].get('vgpr_count', '?')}, wave{s['header'].get('wave_size', '?')}, "
                f"FMA {s['fma_scalar_equivalent']}{check}, dot {s['dot']}, LDS ld/st {s['lds_load']}/{s['lds_store']}, scratch {s['scratch']}"
            )
        else:
            off = folder / "offline-isa" / f"{name}.json"
            isa = (
                json.loads(off.read_text()).get("summary", "see file")
                if off.exists()
                else "—"
            )
        L.append(f"| {key} | {name} | {ledger} | {driver} | {isa} |")
    (report / "ISA-CHECK.md").write_text("\n".join(L) + "\n")


# --- TUNING.md -------------------------------------------------------------------------
def _offline(folder: Path, name: str) -> dict:
    p = folder / "offline-isa" / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def write_tuning(folder: Path, report: Path, ok: list, caps: dict):
    L = [
        f"# {caps['gpu']} shader tuning guide",
        "",
        f"Generated from this device's measurements (subgroup {caps['subgroup']}, max shared {caps['max_shared_bytes']} B). "
        "Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.",
        "",
    ]

    # ALU: vector width x independent chains
    for dtype in ("fp32", "fp16"):
        rows = [
            r
            for r in _stage(ok, "sweep-compute")
            if r["config"]["family"] == "alu" and r["config"]["dtype"] == dtype
        ]
        if not rows:
            continue
        grid = {}
        for r in rows:
            k = (r["config"]["width"], r["config"]["chains"])
            if k not in grid or _rate(r) > grid[k][0]:
                grid[k] = (_rate(r), r["config"]["wg"])
        top = max(v[0] for v in grid.values())
        (bw, bc), (_, bwg) = max(grid.items(), key=lambda x: x[1][0])
        L += [
            f"## {dtype} FMA: vector width × independent chains (GFLOP/s, best WG)",
            "",
            "| width \\ chains | 1 | 2 | 4 | 8 | 16 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for w in (1, 2, 4):
            cells = []
            for ch in (1, 2, 4, 8, 16):
                v = grid.get((w, ch))
                spill = (
                    " ⚠spill"
                    if _offline(folder, f"alu_{dtype}_v{w}_c{ch}").get("spills")
                    else ""
                )
                cells.append(f"{v[0]:.0f}{spill}" if v else "—")
            L.append(f"| vec{w} | " + " | ".join(cells) + " |")
        need = {
            w: min(
                (
                    ch
                    for ch in (1, 2, 4, 8, 16)
                    if grid.get((w, ch), (0,))[0] >= 0.9 * top
                ),
                default=None,
            )
            for w in (1, 2, 4)
        }
        L += [
            "",
            f"- Fastest: vec{bw} × {bc} chains, WG {bwg}: {top:.0f} GFLOP/s.",
            "- Independent chains per invocation needed for 90% of that: "
            + ", ".join(f"vec{w} → {n if n else 'never'}" for w, n in need.items())
            + ". Keep at least this many independent accumulators per thread (vector components count as chains).",
            "",
        ]

    regs = (
        [
            (p.stem, json.loads(p.read_text()))
            for p in sorted((folder / "offline-isa").glob("alu_*.json"))
        ]
        if (folder / "offline-isa").exists()
        else []
    )
    regs = [(n, o) for n, o in regs if o.get("ok")]
    if regs:
        spill = sorted(n for n, o in regs if o.get("spills"))
        low = sorted(
            n
            for n, o in regs
            if (o.get("properties") or {}).get("thread_occupancy", 100) < 100
        )
        L += [
            "## Register budget (offline compiler)",
            "",
            f"- Variants that spill: {', '.join(spill) or 'none'}.",
            f"- Variants below full occupancy: {', '.join(low) or 'none'}.",
            "- Live values per thread (width × chains) beyond these cause spills or lower occupancy; size "
            "accumulator counts and unroll factors below them.",
            "",
        ]

    # DRAM: vector width and WG
    dram = [
        r
        for r in _stage(ok, "sweep-cache")
        if r["config"]["op"] == 0
        and r["accounting"].get("working_set_bytes", 0) >= 256 * MiB
    ]
    ops = {}
    for r in _stage(ok, "sweep-memory"):
        c = r["config"]
        if (
            not c.get("volatile_global")
            and r["accounting"].get("working_set_bytes", 0) >= 256 * MiB
        ):
            k = ["read", "write", "copy", "scale", "add", "triad", "dot"][c["op"]]
            ops[k] = max(ops.get(k, 0), _rate(r))
    if dram:
        g = {}
        for r in dram:
            k = (r["config"]["width"], r["config"]["wg"])
            g[k] = max(g.get(k, 0), _rate(r))
        (bw, bwg), bv = max(g.items(), key=lambda x: x[1])
        v1 = max((v for (w, _), v in g.items() if w == 1), default=0)
        L += [
            "## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)",
            "",
            "| width | WG 64 | WG 128 | WG 256 |",
            "|---|---:|---:|---:|",
        ]
        L += [
            f"| vec{w} | "
            + " | ".join(
                f"{g[(w, wg)]:.1f}" if (w, wg) in g else "—" for wg in (64, 128, 256)
            )
            + " |"
            for w in (1, 2, 4)
        ]
        L += [
            "",
            f"- Best: vec{bw} ({bw * 4} B per access), WG {bwg}: {bv:.1f} GB/s; scalar reads reach {v1 / bv:.0%} of it.",
        ]
    if ops:
        L.append(
            "- DRAM bandwidth by kernel (GB/s): "
            + ", ".join(f"{k} {v:.1f}" for k, v in ops.items())
            + "."
            + (
                f" Writes reach only {ops['write'] / ops['read']:.0%} of reads: coalesce output into wide stores."
                if "read" in ops
                and "write" in ops
                and ops["write"] < 0.85 * ops["read"]
                else ""
            )
        )
    L.append("")

    # cache working set
    cache_rows = [
        r
        for r in _stage(ok, "sweep-cache")
        if r["config"]["op"] == 0 and r["config"]["width"] == 4
    ]
    by_ws = {}
    for r in cache_rows:
        ws = r["accounting"]["working_set_bytes"]
        by_ws[ws] = max(by_ws.get(ws, 0), _rate(r))
    cache_best = max(by_ws.values(), default=None)
    if by_ws:
        dram_bw = min(
            (v for ws, v in by_ws.items() if ws >= 256 * MiB),
            default=min(by_ws.values()),
        )
        fast = [ws for ws, v in sorted(by_ws.items()) if v >= 2 * dram_bw]
        if fast:
            L += [
                "## Cache working set",
                f"- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to {max(fast) / MiB:g} MiB "
                f"(best {cache_best:.0f} GB/s vs DRAM {dram_bw:.0f} GB/s). Size tiles so the reused set fits in this.",
                "",
            ]

    # shared memory
    sh = [
        r
        for r in _stage(ok, "sweep-shared")
        if r["config"].get("kind") == "bw" and r["config"]["op"] == 0
    ]
    if sh:
        best = max(sh, key=_rate)
        sv = _rate(best)
        L += [
            "## Shared (workgroup) memory",
            f"- Best shared read {sv:.0f} GB/s ({best['config']['name']}, WG {best['config']['wg']})"
            + (
                f"; cache-reuse read {cache_best:.0f} GB/s; ratio {sv / cache_best:.2f}×."
                if cache_best
                else "."
            ),
        ]
        if cache_best:
            L.append(
                "- "
                + (
                    "Shared memory is clearly faster than the cache: staging reused data in shared memory pays off."
                    if sv > 1.3 * cache_best
                    else "Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, "
                    "contiguous access) rather than explicit shared-memory staging."
                )
            )
        accs = {}
        for r in sh:
            k = r["config"].get("accumulators", 8)
            accs[k] = max(accs.get(k, 0), _rate(r))
        if len(accs) > 1:
            peak_acc = max(accs, key=lambda k: accs[k])
            L.append(
                "- Independent accumulators vs shared read bandwidth: "
                + ", ".join(f"{k}: {v:.0f}" for k, v in sorted(accs.items()))
                + " GB/s. "
                + (
                    "More accumulators no longer help: shared reads are saturated."
                    if accs[peak_acc] <= 1.1 * accs.get(8, 0)
                    else f"Up to {peak_acc} independent reads in flight still help: issue enough independent shared loads per thread."
                )
            )
        for dtype in ("fp32", "fp16"):
            scalar = 2 if dtype == "fp16" else 4
            st = {
                r["config"]["stride"]: _rate(r)
                for r in sh
                if r["config"]["dtype"] == dtype
                and r["config"]["width"] == 1
                and r["config"]["wg"] == 64
                and r["config"].get("accumulators") == 8
                and r["config"]["shared_count"] * scalar == caps["max_shared_bytes"]
            }
            if 1 in st and len(st) > 2:
                L.append(
                    f"- {dtype} scalar stride sensitivity (vs stride 1): "
                    + ", ".join(f"s{k} {v / st[1]:.2f}" for k, v in sorted(st.items()))
                    + "."
                )
                bad = [k for k, v in st.items() if v < 0.7 * st[1]]
                if bad:
                    recovered = any(st.get(k, 0) >= 0.9 * st[1] for k in (33, 65))
                    L.append(
                        f"  - Strides {bad} are slow (bank conflicts): pad 2-D shared arrays by one element per row "
                        f"(32→33, 64→65)."
                        + (
                            " Measured 33/65 recover."
                            if recovered
                            else " Odd strides do not recover either: not a simple modulo bank mapping; verify padding by measurement."
                        )
                    )
                else:
                    L.append("  - No stride penalty: no bank conflicts to pad around.")
        L.append("")

    # latency / TLB / loads in flight
    cap_rows = sorted(
        _stage(ok, "latency-capacity"),
        key=lambda r: r["accounting"]["working_set_bytes"],
    )
    if cap_rows:
        small, big = latency_ns(cap_rows[0]), latency_ns(cap_rows[-1])
        L += [
            "## Latency and loads in flight",
            f"- Dependent-load latency: ~{small:.0f} ns for small working sets, ~{big:.0f} ns at "
            f"{cap_rows[-1]['accounting']['working_set_bytes'] / MiB:g} MiB.",
        ]
        if ops.get("read"):
            L.append(
                f"- Little's law: saturating DRAM needs ~{ops['read'] * big / 1e3:.0f} KB of reads in flight GPU-wide "
                "(bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; "
                "issue independent loads together."
            )
        tlb = sorted(
            _stage(ok, "latency-tlb"),
            key=lambda r: r["accounting"]["working_set_bytes"],
        )
        if tlb:
            base = min(latency_ns(r) for r in tlb)
            reach = [
                r["accounting"]["working_set_bytes"]
                for r in tlb
                if latency_ns(r) <= 1.3 * base
            ]
            if reach:
                L.append(
                    f"- TLB reach ~{max(reach) / MiB:g} MiB (largest span with one access per page within 1.3× of the "
                    "minimum). Keep randomly accessed data (gathers, lookup tables) within it."
                )
        L.append("")

    # ERT ridge
    ert = _stage(ok, "ert")
    if ert:
        b = {}
        for r in ert:
            ai = r["config"]["flops_per_element"] * 8 / 32
            b[ai] = max(b.get(ai, 0), _rate(r))
        top = max(b.values())
        ridge = min(ai for ai, v in b.items() if v >= 0.8 * top)
        L += [
            "## Measured ridge (ERT, fp32)",
            f"- At >= {ridge:g} FLOP per DRAM byte a kernel reaches 80% of the compute plateau ({top:.0f} GFLOP/s). "
            "Below that it is bandwidth-bound: cut bytes (quantize, reuse, fuse) before cutting math.",
            "",
        ]

    # precision choice
    pk = {}
    for r in _stage(ok, "sweep-compute"):
        c = r["config"]
        if c["family"] in ("alu", "dot", "matrix"):
            k = c["family"] + "_" + c["dtype"]
            pk[k] = max(pk.get(k, 0), _rate(r))
    if pk:
        L += [
            "## Precision and data type",
            "- Peaks (G ops/s): "
            + ", ".join(f"{k} {v:.0f}" for k, v in sorted(pk.items()))
            + ".",
        ]
        if "alu_fp16" in pk and "alu_fp32" in pk:
            ratio = pk["alu_fp16"] / pk["alu_fp32"]
            L.append(
                f"- fp16 is {ratio:.2f}× fp32"
                + (
                    ": worth it for compute-bound kernels."
                    if ratio > 1.5
                    else ": little compute gain; the main benefit of fp16 is halving bytes."
                )
            )
        if "dot_int8" in pk and "alu_fp16" in pk:
            L.append(
                f"- int8 dot4 (8 ops each) runs at {pk['dot_int8'] / pk['alu_fp16']:.2f}× fp16 FMA throughput."
            )
        L.append("")

    # memory type
    ctl = {}
    for r in _stage(ok, "control-memory-type"):
        ctl.setdefault(r["config"]["name"], {}).setdefault(
            r["config"].get("memory_mode", "device_local"), []
        ).append(_rate(r))
    if ctl:
        L.append("## Buffer memory type")
        for name, v in sorted(ctl.items()):
            if "device_local" in v and "host_coherent" in v:
                d, h = (
                    statistics.median(v["device_local"]),
                    statistics.median(v["host_coherent"]),
                )
                L.append(
                    f"- {name}: DEVICE_LOCAL {d:.1f} GB/s vs host-visible coherent {h:.1f} GB/s ({d / h:.2f}×)."
                )
        L.append(
            "- Keep large GPU-only buffers in DEVICE_LOCAL memory; move data to/from the CPU through staging copies."
        )
    (report / "TUNING.md").write_text("\n".join(L) + "\n")

import hashlib
import html
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

src = Path("../gpu-lab/docs/data/cooperative-matrices-2026-09-26.json")
extra_src = Path("docs/reports/data/cooperative-matrices-extra-2026-09-28.json")
raw = src.read_text()
data = json.loads(raw)
extra_raw = extra_src.read_text()
extra = json.loads(extra_raw)
data["gpus"] += extra["gpus"]
data["extra_sources"] = {g["id"]: g["source"] for g in extra["gpus"]}
raw = json.dumps(data)
ids = [
    "4070tis",
    "b70-0",
    "b580",
    "780m",
    "orin-naughty",
    "7900xtx",
    "s26",
    "m51",
    "mali-g1",
]
gpus = [next(g for g in data["gpus"] if g["id"] == i) for i in ids]
names = [
    "RTX 4070 Ti SUPER",
    "Arc Pro B70",
    "Arc B580",
    "Radeon 780M",
    "Jetson Orin Nano",
    "RX 7900 XTX",
    "Adreno 840 (S26)",
    "Xclipse (M51)",
    "Mali-G1-Ultra",
]
NG = len(ids)
shapes = sorted({(r["m"], r["n"], r["k"]) for g in gpus for r in g["khr"]})
types = {
    0: "FP16",
    1: "FP32",
    3: "INT8",
    5: "INT32",
    7: "UINT8",
    9: "UINT32",
    1000141000: "BF16",
    1000491002: "FP8 E4M3",
    1000491003: "FP8 E5M2",
}
plt.rcParams.update(
    {"font.family": "DejaVu Sans", "svg.fonttype": "none", "font.size": 11}
)
fig, ax = plt.subplots(figsize=(15, 5.6))
fig.patch.set_facecolor("#fbfaf6")
ax.set_facecolor("#fbfaf6")
vals = [
    [int(s in {(r["m"], r["n"], r["k"]) for r in g["khr"]}) for s in shapes]
    for g in gpus
]
ax.imshow(
    vals, cmap=ListedColormap(["#ebeae4", "#17685f"]), vmin=0, vmax=1, aspect="auto"
)
ax.set_xticks(range(len(shapes)), [" × ".join(map(str, s)) for s in shapes])
ax.xaxis.tick_top()
plt.setp(ax.get_xticklabels(), rotation=45, ha="left", rotation_mode="anchor")
ax.set_yticks(range(NG), names)
ax.tick_params(length=0, pad=12)
for y, row in enumerate(vals):
    for x, v in enumerate(row):
        ax.text(
            x,
            y,
            "YES" if v else "—",
            ha="center",
            va="center",
            color="white" if v else "#777b7a",
            fontsize=9,
            fontweight="bold",
        )
ax.set_xticks([i - 0.5 for i in range(len(shapes) + 1)], minor=True)
ax.set_yticks([i - 0.5 for i in range(NG + 1)], minor=True)
ax.grid(which="minor", color="#fbfaf6", linewidth=4)
ax.tick_params(which="minor", length=0)
for s in ax.spines.values():
    s.set_visible(False)
fig.tight_layout()
buf = io.StringIO()
fig.savefig(buf, format="svg", facecolor=fig.get_facecolor())
chart = buf.getvalue()[buf.getvalue().index("<svg") :]
chart = chart.replace(
    "<svg ",
    '<svg role="img" aria-label="Fixed shape support across nine GPU models." ',
    1,
)
# Is the matrix path really hardware-accelerated? See docs/MATRIX-ACCELERATION.md.
# Per GPU and input class: (ratio vs scalar roof or None, verdict class, label, evidence).
ACCEL = {
    "4070tis": {
        "fp16": (4.1, "yes", "Yes", "Nsight Tensor Active"),
        "int8": (4.7, "yes", "Yes", "Nsight Tensor Active"),
    },
    "b70-0": {
        "fp16": (4.0, "yes", "Yes", "ISA: dpas"),
        "int8": (7.1, "yes", "Yes", "ISA: dpas"),
    },
    "b580": {
        "fp16": (4.1, "yes", "Yes", "ISA: dpas"),
        "int8": (7.2, "yes", "Yes", "ISA: dpas"),
    },
    "780m": {
        "fp16": (1.8, "yes", "Yes", "ISA: v_wmma_f32/f16"),
        "int8": (1.2, "yes", "Yes, small gain", "ISA: v_wmma_i32_iu8"),
    },
    "orin-naughty": {
        "fp16": (5.5, "yes", "Yes", "Nsight Tensor Active"),
        "int8": (9.3, "yes", "Yes", "Nsight Tensor Active"),
    },
    "7900xtx": {
        "fp16": (2.2, "yes", "Yes", "ratio; ISA pending"),
        "int8": (2.1, "yes", "Yes", "ratio; ISA pending"),
    },
    "s26": {
        "fp16": (0.9, "no", "No gain measured", "ratio below FMA; ISA pending"),
        "int8": (1.7, "yes", "Yes", "ratio; ISA pending"),
    },
    "m51": {
        "fp16": (
            1.0,
            "own",
            "Hardware (owner); ratio unexplained",
            "owner-confirmed; ISA pending",
        ),
        "int8": (4.2, "yes", "Yes", "ratio + owner-confirmed"),
    },
    "mali-g1": {
        "fp16": (None, "unk", "Unknown", "data invalid; re-measure"),
        "int8": (None, "unk", "Unknown", "data invalid; re-measure"),
    },
}
TYPE_CLASS = {0: "fp16", 3: "int8", 7: "int8"}


def badge(gid, a_type):
    cls = TYPE_CLASS.get(a_type)
    if cls is None:
        return '<span class="acc acc-unk">Not measured</span>'
    ratio, kind, label, ev = ACCEL[gid][cls]
    r = f" · {ratio:.1f}×" if ratio is not None else ""
    return f'<span class="acc acc-{kind}" title="{html.escape(ev)}">{html.escape(label)}{r}</span>'


def accel_table():
    body = ""
    for gid, name in zip(ids, names):
        cells = ""
        for cls in ("fp16", "int8"):
            ratio, kind, label, ev = ACCEL[gid][cls]
            r = f"{ratio:.1f}×" if ratio is not None else "—"
            cells += f'<td class="num">{r}</td><td><span class="acc acc-{kind}">{html.escape(label)}</span><br><small class="notes">{html.escape(ev)}</small></td>'
        body += f'<tr><th scope="row">{name}</th>{cells}</tr>'
    return (
        '<h3 style="margin-top:34px">Is the matrix path really accelerated?</h3>'
        '<p class="notes">A listed shape only promises a correct result; a driver may lower it to ordinary FMA. '
        "The ratio divides the measured register-resident matrix roof by the scalar roof of the same input type "
        "(fp16 FMA, int8 dot) from confirmed short-run roofline campaigns. ISA or hardware-counter evidence outranks the ratio. "
        "The Xclipse (M51) has real matrix hardware per its owner; its fp16 ratio of 1.0× is unexplained. "
        "Method and sources: igpu-roofline/docs/MATRIX-ACCELERATION.md.</p>"
        '<div class="table-scroll"><table><thead><tr><th>GPU</th><th>fp16 matrix ÷ FMA</th><th>fp16 verdict</th>'
        "<th>int8 matrix ÷ dot</th><th>int8 verdict</th></tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


rows = ""
cards = ""
for g, name in zip(gpus, names):
    grouped = {}
    for r in g["khr"]:
        key = (r["a"], r["b"], r["c"], r["result"], r["saturating"])
        grouped.setdefault(key, []).append("×".join(str(r[k]) for k in ["m", "n", "k"]))
    for key, ss in grouped.items():
        a, b, c, res, sat = key
        rows += f'<tr data-gpu="{g["id"]}"><th scope="row">{name}</th><td>{types[a]} × {types[b]}</td><td>{types[c]} → {types[res]}</td><td class="mono">{", ".join(ss)}</td><td>{"Yes" if sat else "No"}</td><td>{badge(g["id"], a)}</td></tr>'
    count = len({(r["m"], r["n"], r["k"]) for r in g["khr"]})
    cards += f'<article class="gpu-card"><span class="eyebrow">{g["host"]}</span><h3>{name}</h3><p><b>{count}</b> fixed shapes · <b>{len(g["khr"])}</b> typed entries</p><small>{html.escape(g["driver"])} {html.escape(g["driver_info"])}<br>{("Vulkan " + g["api"]) if g["api"] else "from " + ("roofline campaign" if "campaign" in g.get("source", "") else "historical snapshot")}</small><br><span class="acc acc-{ACCEL[g["id"]]["fp16"][1]}">fp16: {html.escape(ACCEL[g["id"]]["fp16"][2])}</span> <span class="acc acc-{ACCEL[g["id"]]["int8"][1]}">int8: {html.escape(ACCEL[g["id"]]["int8"][2])}</span></article>'
sha = hashlib.sha256(src.read_bytes()).hexdigest()
template = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Matrix Geometry — Homelab WMMA Atlas</title>
<style>
:root{--paper:#fbfaf6;--ink:#192f35;--muted:#58666b;--green:#17685f;--line:#d6dcd6;--orange:#b95e30;--blue:#3b6591}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,-apple-system,sans-serif}main{max-width:1240px;margin:auto;padding:48px 48px 32px}h1,h2,h3,p{margin-top:0}h1{font-family:Georgia,serif;font-size:clamp(42px,6vw,78px);font-weight:400;line-height:1.06;letter-spacing:-2px;margin-bottom:24px}h2{font:400 34px/1.2 Georgia,serif;margin-bottom:16px}h3{font-size:17px;line-height:1.3}.eyebrow{font-size:11px;letter-spacing:1.7px;text-transform:uppercase;font-weight:700;color:var(--green)}.mast{display:flex;justify-content:space-between;border-bottom:2px solid var(--ink);padding-bottom:15px;margin-bottom:40px}.lead{max-width:810px;font-size:20px;color:var(--muted)}.tag{display:inline-block;border:1px solid var(--line);padding:3px 10px;font-size:12px;margin:0 5px 8px 0;border-radius:3px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin:32px 0 44px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:20px 0}.stat b{display:block;font:42px Georgia,serif}.stat span{font-size:13px;color:var(--muted)}section{padding:30px 0;border-top:1px solid var(--line)}.section-top{display:grid;grid-template-columns:60px 1fr}.section-no{font:italic 24px Georgia,serif;color:var(--green)}.caption{font-size:13px;color:var(--muted);margin:12px 0 24px}.figure{margin:24px 0}.figure svg{display:block;width:100%;height:auto}.callout{border-left:3px solid var(--green);padding:14px 20px;background:#edf1e9}.twocol{display:grid;grid-template-columns:1fr 1fr;gap:24px}.gpu-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:25px 0}.gpu-card{border:1px solid var(--line);padding:16px}.gpu-card .eyebrow{font-size:9px;letter-spacing:.6px}.gpu-card small{font-size:11px;color:var(--muted)}.gpu-card p{font-size:13px}.controls{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.controls label{font-size:12px;font-weight:600}select,button,input{font:inherit;padding:9px 12px;border:1px solid #adb9b5;border-radius:4px;background:var(--paper);color:var(--ink)}select{display:block;max-width:100%}button{cursor:pointer}button:hover{background:#edf1e9}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--orange);outline-offset:3px}.explorer{padding:24px;border:1px solid var(--line);background:#fffefa}.explorer svg{width:100%;height:auto}.metrics{display:flex;gap:30px;flex-wrap:wrap;font-size:13px}.metrics b{font-size:20px;display:block}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}th{text-align:left}td,th{padding:11px 13px;border-bottom:1px solid var(--line);vertical-align:top}thead{background:#e8eee8}tbody tr:nth-child(even){background:#f2f3ed}.mono{font-family:ui-monospace,monospace;font-size:12px}.legend{display:flex;gap:20px;font-size:13px}.dot{display:inline-block;width:11px;height:11px;margin-right:6px}.notes{font-size:13px;color:var(--muted)}a{color:var(--green)}footer{border-top:2px solid var(--ink);padding-top:20px;margin-top:24px}.sources{overflow-wrap:anywhere}details summary{cursor:pointer;font-weight:600}.print-button{font-size:12px}.interactive{display:none}.js .interactive{display:block}#empty{display:none}.flex-rule{font:25px/1.5 Georgia,serif;padding:20px;background:#edf1e9} @media(max-width:800px){main{padding:24px 18px}.stats{grid-template-columns:repeat(2,1fr)}.gpu-grid{grid-template-columns:repeat(2,1fr)}.twocol{grid-template-columns:1fr}.section-top{grid-template-columns:35px 1fr}.mast{gap:15px}.lead{font-size:17px}.explorer{padding:12px}h2{font-size:28px}}
@media print{@page{size:A4 landscape;margin:14mm}body{font-size:11px;print-color-adjust:exact;-webkit-print-color-adjust:exact}main{max-width:none;padding:0}h1{font-size:48px}h2{font-size:25px}.print-button,.controls,.interactive,details{display:none!important}.stats{margin:20px 0}.gpu-grid{grid-template-columns:repeat(5,1fr)}section{break-inside:auto}figure,.callout,.gpu-grid,thead,tr{break-inside:avoid}thead{display:table-header-group}.table-scroll{overflow:visible}table{font-size:10px}td,th{padding:6px 8px}tr[hidden]{display:table-row!important}.section-top{break-after:avoid}.caption{font-size:10px}a{color:inherit}}
.acc{display:inline-block;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:600;margin-top:4px}.acc-yes{background:#dcebe4;color:#125249}.acc-own{background:#e1e8f1;color:#2f5178}.acc-no{background:#f6e3d8;color:#8d3f19}.acc-unk{background:#ecebe6;color:#4d585c}td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
</style></head><body><main>
<header><div class="mast"><span class="eyebrow">Homelab / Compute Research</span><span class="eyebrow">Capability atlas · 28 September 2026</span><button class="print-button" onclick="window.print()">Print / Save PDF</button></div>
<span class="eyebrow">Vulkan cooperative matrices</span><h1>Small tiles.<br>Many ways to multiply.</h1><p class="lead">A visual atlas of WMMA-style matrix shapes across every GPU we tune for: NVIDIA, Intel and AMD desktop and edge GPUs, plus the Adreno, Xclipse and Mali phone GPUs. Read the geometry first, then the supported arithmetic.</p><span class="tag">Installed-driver query</span><span class="tag">Nine GPU models</span><span class="tag">No performance ranking</span>
<div class="stats"><div class="stat"><b>__NG__</b><span>GPU models with cooperative-matrix support</span></div><div class="stat"><b>6</b><span>vendors: NVIDIA, Intel, AMD, Qualcomm, Samsung, Arm</span></div><div class="stat"><b>__NS__</b><span>distinct fixed M×N×K shapes across the fleet</span></div><div class="stat"><b>2</b><span>queried GPUs expose flexible dimensions</span></div></div></header>
<section><div class="section-top"><span class="section-no">01</span><div><h2>What does a shape mean?</h2><p>M and N describe the output tile. K is the length of each dot product used to produce one output element.</p></div></div>
<div class="figure" id="static-diagram">__DIAGRAM__</div><p class="caption">Figure 1. A 16×8×32 tile multiplies a 16×32 matrix by a 32×8 matrix, then adds a 16×8 accumulator. Rectangles use one common scale; the faint grid marks blocks of 8 elements.</p>
<div class="legend"><span><i class="dot" style="background:#17685f"></i>A · M×K</span><span><i class="dot" style="background:#3b6591"></i>B · K×N</span><span><i class="dot" style="background:#b95e30"></i>C and D · M×N</span></div>
<div class="callout" style="margin-top:24px"><b>Geometry is not throughput.</b> A larger tile does more arithmetic per matrix operation, but shape alone does not reveal instruction count, occupancy, clock rate or measured speed. These are Vulkan API shapes, not a catalogue of native hardware instruction shapes.</div></section>
<section><div class="section-top"><span class="section-no">02</span><div><h2>The fixed-shape landscape</h2><p>Each filled cell means at least one supported arithmetic combination uses that geometry. All fixed entries here have subgroup scope.</p></div></div><figure class="figure">__CHART__<figcaption class="caption">Figure 2. Exact fixed shapes returned by VK_KHR_cooperative_matrix. A dash means that exact shape was absent from the fixed list; NVIDIA flexible dimensions can permit additional shapes. Precision restrictions are listed in Section 04.</figcaption></figure>
<div class="twocol"><p><b>Intel uses an 8×16 output tile.</b> FP16 and BF16 use K=16; integer inputs use K=32. B70 and B580 return the same six typed entries.</p><p><b>Radeon uses a 16×16 output tile.</b> The 780M and RX 7900 XTX both expose only 16×16×16, with multiple signedness, accumulator and saturation combinations. The Xclipse (M51) exposes the same single shape.</p></div>
<div class="twocol"><p><b>Adreno 840 always uses M = 64.</b> N can be 16, 32 or 64; FP16 uses K=16 with <b>FP16 accumulation only</b> (no FP16 → FP32), integer inputs use K=32 and FP32 uses K=8.</p><p><b>Mali-G1 has the smallest tiles.</b> 4×8×8 and 16×32×32 for FP16, 4×16×16 for INT8, plus FP32 4×4×4 and 16×16×16.</p></div>
<div class="gpu-grid">__CARDS__</div><p class="notes">The first five GPUs come from gpu-lab's installed-driver query of 26 September 2026. The RX 7900 XTX and Adreno 840 come from their agents' roofline campaigns of 27 September 2026; the Xclipse (M51) and Mali-G1 come from historical snapshots in <code>docs/COOPMAT-SHAPES.md</code> and still need a re-probe. The M51 is an internal device: its driver build is not published, and its subgroup size was not recorded. Two Arc Pro B70 cards and two Jetson Orin Nano devices are documented in the homelab; support on the second B70 and on <code>duck-stable</code> is inferred from matching hardware.</p>__ACCEL__</section>
<section class="interactive"><div class="section-top"><span class="section-no">03</span><div><h2>Explore one tile at a time</h2><p>Choose a queried GPU and an exact typed entry. The diagram keeps a common scale so longer K dimensions are immediately visible.</p></div></div><div class="explorer"><div class="controls"><label>GPU<select id="gpu"></select></label><label>Arithmetic and shape<select id="entry"></select></label></div><div id="diagram" aria-live="polite"></div><div id="metrics" class="metrics"></div></div></section>
<section><div class="section-top"><span class="section-no">04</span><div><h2>The complete fixed-shape catalogue</h2><p>Input types are listed separately for A and B. C is the accumulator; D is the result. Entries that differ in saturation remain separate.</p></div></div><div class="controls interactive"><label>Show GPU<select id="filter"><option value="all">All nine GPUs</option>__OPTIONS__</select></label></div><div class="table-scroll"><table id="fixed"><caption class="caption" style="text-align:left">Table 1. All __NE__ KHR typed entries, grouped only when their arithmetic and saturation match.</caption><thead><tr><th>GPU</th><th>A × B</th><th>C → D</th><th>M×N×K</th><th>Saturating</th><th>Hardware acceleration</th></tr></thead><tbody>__ROWS__</tbody></table></div><p class="notes">The 780M, RX 7900 XTX and Xclipse (M51) allow INT8/UINT8 input pairings; see each row for the accumulator types. The 780M allows every INT8/UINT8 input pairing, with either INT32 or UINT32 output. Only its INT32 variants additionally offer saturating accumulation. The RX 7900 XTX, Adreno 840 and Xclipse (M51) also report saturating variants, as listed. The legacy NVIDIA NV query adds no fixed shapes and omits BF16 and FP8 entries returned by KHR.</p></section>
<section><div class="section-top"><span class="section-no">05</span><div><h2>NVIDIA: a family of flexible tiles</h2><p>The queried RTX 4070 Ti SUPER and Orin Nano also expose flexible dimensions and workgroup scope through VK_NV_cooperative_matrix2.</p></div></div><div class="flex-rule">(M, N, K) = (a·g<sub>M</sub>, b·g<sub>N</sub>, c·g<sub>K</sub>)<br><small style="font:14px system-ui">a, b and c are independent positive integers; each resulting dimension must be ≤ 1024.</small></div>
<div class="table-scroll"><table><caption class="caption" style="text-align:left">Table 2. Flexible-dimension granularities, not an exhaustive fixed-shape list.</caption><thead><tr><th>Scope</th><th>Workgroup invocations</th><th>FP16 / BF16 granularity</th><th>INT8 / UINT8 / FP8 granularity</th></tr></thead><tbody><tr><td>Subgroup</td><td>Not specified</td><td>16×16×16</td><td>16×16×32</td></tr><tr><td>Workgroup</td><td>32 or 64</td><td>16×16×16</td><td>16×16×32</td></tr><tr><td>Workgroup</td><td>128</td><td>32×16×16</td><td>32×16×32</td></tr><tr><td>Workgroup</td><td>256</td><td>32×32×16</td><td>32×32×32</td></tr></tbody></table></div>
<p><b>Example:</b> subgroup FP16 supports a 32×64×16 API tile because all three dimensions are multiples of 16. A 24×64×16 tile fails the M granularity rule.</p><p class="notes">At every row: FP16 → FP16/FP32, BF16 → FP32, INT8 → INT32 and UINT8 → UINT32. FP8 E4M3/E5M2 → FP16/FP32 is RTX-only and uses the integer column's granularity. All flexible entries are non-saturating. Shader resource limits still apply; satisfying these dimension rules does not guarantee a particular shader will compile or execute. Intel advertises the NV2 extension but returns both flexible-dimension and workgroup-scope features as false.</p></section>
<section><div class="section-top"><span class="section-no">06</span><div><h2>Evidence, scope & reproducibility</h2></div></div><div class="twocol"><div><h3>What was measured</h3><p class="notes">A capability probe enumerated Vulkan physical devices, matched registered UUIDs, and queried KHR/NV matrix properties, NV flexible dimensions and feature flags. No matrix shaders were dispatched; these are driver-advertised capabilities, not execution validation or benchmark results.</p><h3>What “WMMA” means here</h3><p class="notes">WMMA is used as shorthand for Vulkan cooperative matrices. This report does not enumerate CUDA WMMA, AMD native WMMA or Intel DPAS instruction shapes. Features must be enabled by applications, and support may change with the installed driver.</p></div><div><h3>Devices outside this atlas</h3><p class="notes">The gpu-lab snapshot also queried the Ryzen 9600X iGPU, Galaxy S24+ Xclipse 940 and Pixel 7a Mali-G710 MP7: none exposed a cooperative-matrix extension. Other homelab GPUs were not queried in this snapshot; their omission does not establish a lack of hardware matrix support.</p><h3>Snapshot provenance</h3><p class="notes">gpu-lab query captured 26 September 2026, 09:57:42 −07:00; the four added GPUs were compiled 28 September 2026 from the sources above. Original UUIDs, feature flags and every returned property entry are embedded in this HTML. No network connection or external assets are required.</p></div></div>
<div class="sources notes"><p><b>Primary evidence:</b> gpu-lab/docs/data/cooperative-matrices-2026-09-26.json (five GPUs) and igpu-roofline/docs/reports/data/cooperative-matrices-extra-2026-09-28.json (RX 7900 XTX, Adreno 840, Xclipse M51, Mali-G1)<br><b>Interpretation:</b> gpu-lab/docs/cooperative-matrices.md<br><b>SHA-256:</b> <span class="mono">__HASH__</span> / <span class="mono">__XHASH__</span></p><button id="download">Download source snapshot</button><details style="margin-top:18px"><summary>Inspect the embedded query data</summary><pre id="raw" style="overflow:auto;max-height:380px;font-size:11px"></pre></details></div></section>
<footer class="notes">HOMELAB / MATRIX GEOMETRY · Snapshot 2026-09-26 · Report 2026-09-27<br>Five queried GPU models. Two additional physical units inferred. No throughput claims.</footer></main>
<script id="snapshot" type="application/json">__DATA__</script>
<script>
document.documentElement.classList.add('js');
const data=JSON.parse(document.getElementById('snapshot').textContent), ids=__IDS__, names=__NAMES__, types=__TYPES__;
const gs=ids.map(id=>data.gpus.find(g=>g.id===id));
const gpu=document.getElementById('gpu'),entry=document.getElementById('entry');
const shape=r=>`${r.m}×${r.n}×${r.k}`;
function diagram(m,n,k){const s=5,base=215;let x=35;const parts=[[m,k,'A','#17685f'],[k,n,'B','#3b6591'],[m,n,'C','#b95e30'],[m,n,'D','#b95e30']];let content='';parts.forEach(([h,w,label,color],i)=>{let y=base-h*s/2;content+=`<text x="${x+w*s/2}" y="65" text-anchor="middle" fill="${color}" font-size="22" font-weight="600">${label}</text><rect x="${x}" y="${y}" width="${w*s}" height="${h*s}" fill="${color}" fill-opacity=".14" stroke="${color}" stroke-width="2"/>`;for(let v=8;v<w;v+=8)content+=`<path d="M ${x+v*s} ${y} v ${h*s}" stroke="${color}" opacity=".3"/>`;for(let v=8;v<h;v+=8)content+=`<path d="M ${x} ${y+v*s} h ${w*s}" stroke="${color}" opacity=".3"/>`;content+=`<text x="${x+w*s/2}" y="${y+h*s+25}" text-anchor="middle" font-size="16" fill="#192f35">${h} × ${w}</text>`;x+=w*s+55;if(i<3)content+=`<text x="${x-28}" y="${base+8}" text-anchor="middle" font-size="25" fill="#192f35">${['×','+','='][i]}</text>`;});return `<svg viewBox="0 0 720 355" role="img" aria-label="${m} by ${k} matrix A times ${k} by ${n} matrix B plus ${m} by ${n} accumulator C equals result D">${content}</svg>`;}
function update(){let r=gs[gpu.selectedIndex].khr[entry.selectedIndex];document.getElementById('diagram').innerHTML=diagram(r.m,r.n,r.k);document.getElementById('metrics').innerHTML=`<span><b>${r.m*r.n}</b>output elements</span><span><b>${r.k}</b>products per output element</span><span><b>${(r.m*r.n*r.k).toLocaleString()}</b>scalar multiply-accumulates per tile</span><span><b>${r.saturating?'Yes':'No'}</b>saturating accumulation</span>`;}
function entries(){entry.replaceChildren(...gs[gpu.selectedIndex].khr.map(r=>new Option(`${types[r.a]} × ${types[r.b]} → ${types[r.c]} · ${shape(r)}${r.saturating?' · saturating':''}`)));update();}
gpu.replaceChildren(...names.map((n,i)=>new Option(n,ids[i])));gpu.addEventListener('change',entries);entry.addEventListener('change',update);entries();
document.getElementById('filter').addEventListener('change',e=>document.querySelectorAll('#fixed tbody tr').forEach(r=>r.hidden=e.target.value!=='all'&&r.dataset.gpu!==e.target.value));
document.getElementById('raw').textContent=JSON.stringify(data,null,2);
document.getElementById('download').addEventListener('click',()=>{const blob=new Blob([document.getElementById('snapshot').textContent],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='cooperative-matrices-2026-09-28-combined.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
</script></body></html>"""


# Static diagram stays readable without JavaScript and in print.
def diagram():
    out = '<svg viewBox="0 0 720 355" role="img" aria-label="16 by 32 matrix A times 32 by 8 matrix B plus 16 by 8 matrix C equals 16 by 8 result D">'
    x = 35
    for i, (h, w, label, col) in enumerate(
        [
            (16, 32, "A", "#17685f"),
            (32, 8, "B", "#3b6591"),
            (16, 8, "C", "#b95e30"),
            (16, 8, "D", "#b95e30"),
        ]
    ):
        y = 215 - h * 2.5
        out += f'<text x="{x + w * 2.5}" y="65" text-anchor="middle" fill="{col}" font-size="22">{label}</text><rect x="{x}" y="{y}" width="{w * 5}" height="{h * 5}" fill="{col}" fill-opacity=".14" stroke="{col}" stroke-width="2"/>'
        for v in range(8, w, 8):
            out += f'<path d="M{x + v * 5} {y}v{h * 5}" stroke="{col}" opacity=".3"/>'
        for v in range(8, h, 8):
            out += f'<path d="M{x} {y + v * 5}h{w * 5}" stroke="{col}" opacity=".3"/>'
        out += f'<text x="{x + w * 2.5}" y="{y + h * 5 + 25}" text-anchor="middle" font-size="16" fill="#192f35">{h} × {w}</text>'
        x += w * 5 + 55
        if i < 3:
            out += f'<text x="{x - 28}" y="223" text-anchor="middle" font-size="25" fill="#192f35">{["×", "+", "="][i]}</text>'
    return out + "</svg>"


for k, v in {
    "DIAGRAM": diagram(),
    "CHART": chart,
    "CARDS": cards,
    "ROWS": rows,
    "OPTIONS": "".join(f'<option value="{i}">{n}</option>' for i, n in zip(ids, names)),
    "HASH": sha,
    "XHASH": hashlib.sha256(extra_raw.encode()).hexdigest(),
    "IDS": json.dumps(ids),
    "NG": str(NG),
    "NS": str(len(shapes)),
    "NE": str(sum(len(g["khr"]) for g in gpus)),
    "DATA": raw.replace("</", "<\\/"),
    "NAMES": json.dumps(names),
    "TYPES": json.dumps(types),
}.items():
    template = template.replace("__" + k + "__", v)
print("entries", sum(len(g["khr"]) for g in gpus), "shapes", len(shapes))
template = template.replace("__ACCEL__", accel_table())
out = Path("docs/reports/wmma-shape-atlas.html")
out.write_text(template)
print(out, out.stat().st_size)

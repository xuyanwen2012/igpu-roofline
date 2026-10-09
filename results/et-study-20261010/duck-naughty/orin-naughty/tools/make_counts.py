#!/usr/bin/env python3
"""make_counts.py <results root>: part C. isa/counts.csv = static SPIR-V counts and driver pipeline statistics
(VK_KHR_pipeline_executable_properties; this driver returns statistics only, no internal representation) for the
dispatched kernels (isa/pipeline-stats-kernels/*.stats.txt, isa/kernel-coopmat-types.csv) and for the roofline
matrix shaders behind each roof used in efficiency.csv (pipeline-inspection/<variant>.json of the tool)."""
import csv, glob, json, pathlib, re, sys
R = pathlib.Path(sys.argv[1]); rows = []
static = {}
for r in csv.DictReader(open(R / "isa/kernel-coopmat-types.csv")):
    if r["kind"] == "counts":
        static[r["shader"]] = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", " ".join([r["c1"], r["c2"], r["c3"], r["c4"]]))}
reuse = json.load(open(R / "tools/kernel_reuse.json"))
KER = {"4w-": "sarc_linear_q4gsw_coopmat_orin_t256x128k16g42s32bt_texture3d_texture2d_half",
       "4w-f32": "sarc_dev_linear_q4gsw_coopmat_bx_t128x128k32g42s32f32c_texture3d_texture2d_half",
       "8da4w": "sarc_linear_dq8ca_coopmat_zpgtr_orin_bf_t128x128k64g24s32mk32ra_texture3d_texture2d_half",
       "sdpa-d64": "sarc_dev_orin_sdpa_fused3sb_d64_t32x32g11s32rko_buffer_buffer_half",
       "sdpa-d128": "sarc_dev_orin_sdpa_fused3sb_d128_t16x64g11s32rko_buffer_buffer_half"}
for f in sorted(glob.glob(str(R / "isa/pipeline-stats-kernels/*.stats.txt"))):
    tag = pathlib.Path(f).name.replace(".stats.txt", "")
    k = KER[max((p for p in KER if tag.startswith(p)), key=len)]
    txt = open(f).read()
    st = {m[0].strip(): int(m[1]) for m in re.findall(r"^\s+([A-Za-z ]+?)\s{2,}(\d+)", txt, re.M)}
    sg = re.search(r"subgroup (\d+)", txt)
    ru = reuse.get(k) or reuse.get(k.replace("_buffer_buffer_half", ""))
    args = next(l.split("args=")[1].strip() for l in open(R / "isa/pipeline-stats-kernels/status") if l.startswith(tag + " "))
    rows.append(["kernel", tag, k, args, sg.group(1) if sg else "", static[k]["MulAdd"], ru["muladd_per_chunk"], static[k]["CooperativeMatrixLoad"],
                 static[k]["CooperativeMatrixStore"], static[k]["ControlBarrier"], st.get("Register Count", ""), st.get("Binary Size", ""),
                 st.get("Stack Size", ""), st.get("Shared Memory Size", ""), st.get("Local Memory Size", ""),
                 "internal representations: none returned" if "representation" not in txt.lower() else "see stats file", f"isa/pipeline-stats-kernels/{tag}.stats.txt"])
used = set()
for r in csv.DictReader(open(R / "efficiency.csv")):
    used.update(re.findall(r"= (matrix_\w+?) \(", r["roof_source"]))
for v in sorted(used):
    d = json.load(open(R / f"pipeline-inspection/{v}.json"))
    rec = d["records"][0]; led = rec["config"]["spirv_ledger"]
    st = {}
    def walk(o):
        if isinstance(o, dict):
            if "name" in o and "value" in o: st[o["name"]] = o["value"]
            for x in o.values(): walk(x)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk({k: x for k, x in rec.items() if k != "config"})
    rows.append(["roofline shader", v, v, f"local size {rec['config'].get('wg', '')}", rec["config"].get("subgroup", ""), led.get("coopmat_muladd"), rec["config"]["chains"],
                 led.get("coopmat_load"), "", led.get("control_barrier", 0), st.get("Register Count", ""), st.get("Binary Size", ""), st.get("Stack Size", ""),
                 st.get("Shared Memory Size", ""), st.get("Local Memory Size", ""), "internal representations: " + str(sum(len(e.get("representations", [])) for e in rec.get("executables", []))),
                 f"pipeline-inspection/{v}.json"])
with open(R / "isa/counts.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow("kind,tag,shader,specialization,subgroup,static_muladd,muladd_per_loop_iteration_per_subgroup,static_coopmat_load,static_coopmat_store,static_control_barrier,register_count,binary_size,stack_size,shared_memory_size,local_memory_size_raw,isa,evidence".split(","))
    w.writerows(rows)
for r in rows: print(r[0][:6], r[1][:34], *r[4:15])

#!/usr/bin/env python3
"""build_efficiency.py <results root>: part B of et-study-20261010 (RTX 4070 Ti SUPER).

Writes efficiency.csv (the columns the task fixes) and efficiency-detail.json (every per-process value behind
each row) from files in the results root only:
  report/summary.json                roofs of part A (register, fed from shared memory, fed by reuse)
  confirm/*.json                     confirmation repeats of the reuse rows that have them
  microbench/linear-r*.json          test_llama_microbench --linear --regime=prefill, final build, 5 processes
  microbench/sdpa-r*.json            test_llama_microbench --sdpa, 5 processes
  isa/kernel-coopmat-types.txt       operand types of every OpCooperativeMatrixMulAddKHR (tools/spirv_mma.py)
  sources/s4-c1-trace-gemm.csv       the tuning campaign's in-model trace (cited, not re-run)
  sources/fused-roof-s4-c1.txt       the tuning campaign's in-model fused attention rates (cited)

Rate = 2*M*N*K / kernel_time for the linear kernels. Kernel time = median over the 5 processes of the
microbench's kernel_median_us (itself the median of 5 timed iterations after 3 warm-up iterations).
Fused attention: executed matrix work of QK^T and of attention x V over the tiles the kernel executes (a
workgroup owns TM rows and runs every TN-wide context block up to its last row) / op_mean_us of "total".
"""
import csv, glob, json, re, statistics, sys
from pathlib import Path

root = Path(sys.argv[1])
summary = json.loads((root / "report/summary.json").read_text())
roofs = summary["short_run"]
DEVICE = "NVIDIA GeForce RTX 4070 Ti SUPER"

# --- kernel facts: geometry from the shader source (isa/kernels/*.glsl), types from the SPIR-V -------------------
# reuse = matrix operations per loaded A/B tile byte, counted as the roofline tool counts ops_per_load_byte:
# one subgroup, one K step: (MMAs * 2*m*n*k) / ((A tiles + B tiles) * tile bytes).
KERNELS = {
    "sarc_linear_q4gsw_coopmat_t256x128k16g42s32ga_texture3d_texture2d_half": dict(
        family="fp16", mma=(16, 16, 16), a_tiles=8, b_tiles=2, mmas=16, tile_bytes=512,
        derive="WG 256x128, subgroup grid 4x2: a subgroup owns 128x32 = 8 A tiles x 2 B tiles; per K=16 step 16 MMAs, 10 tile loads of 512 B"),
    "sarc_linear_q4gsw_coopmat_t128x128k16g24s32ga_texture3d_texture2d_half": dict(
        family="fp16", mma=(16, 16, 16), a_tiles=2, b_tiles=4, mmas=8, tile_bytes=512,
        derive="WG 128x128, subgroup grid 2x4: a subgroup owns 32x64 = 2 A tiles x 4 B tiles; per K=16 step 8 MMAs, 6 tile loads of 512 B"),
    "sarc_linear_dq8ca_coopmat_zpgtr_t128x128k64g44s32mk32ra_texture3d_texture2d_half": dict(
        family="int8", mma=(16, 16, 32), a_tiles=2, b_tiles=2, mmas=4, tile_bytes=512,
        derive="WG 128x128, subgroup grid 4x4: a subgroup owns 32x32 = 2 A tiles x 2 B tiles; per K=32 step 4 MMAs, 4 tile loads of 512 B (two K steps per barrier)"),
}
SDPA = {  # head dim -> fused kernel, tile rows TM, context block TN; per context block of one workgroup
    64: dict(kernel="sarc_dev_4070ti_sdpa_fused3sb_d64_t32x32g11s32rko_buffer_buffer_half", tm=32, tn=32,
             mmas=32, loads=8 + 8 + 4,
             derive="per 32-column block of a 32-row workgroup: 16 MMAs QK^T + 16 MMAs attention x V; loads 8 K tiles + 8 V tiles from the packed buffers and 4 e tiles from shared memory (Q stays in registers)"),
    128: dict(kernel="sarc_dev_4070ti_sdpa_fused3sb_d128_t16x64g11s32rko_buffer_buffer_half", tm=16, tn=64,
              mmas=64, loads=32 + 32 + 4,
              derive="per 64-column block of a 16-row workgroup: 32 MMAs QK^T + 32 MMAs attention x V; loads 32 K tiles + 32 V tiles from the packed buffers and 4 e tiles from shared memory (Q stays in registers)"),
}
MODEL = {"llama-3.2-1b": "1b", "llama-3.2-3b": "3b", "llama-3.1-8b": "8b"}
TNAME = {"half": "fp16", "float": "fp32", "char": "int8", "int": "int32"}


def spirv_types(kernel):
    """(input type, accumulator type, muladd count) of the kernel's single OpCooperativeMatrixMulAddKHR signature."""
    text = (root / "isa/kernel-coopmat-types.txt").read_text()
    block = text.split("# " + kernel + "\n")[1].split("\n# ")[0]
    sig = re.findall(r"muladd,count=(\d+),result=\[(\w+) [^\]]*\],A=\[(\w+) [^\]]*\],B=\[(\w+) [^\]]*\],C=\[(\w+) [^\]]*\]", block)
    assert len(sig) == 1, (kernel, sig)
    n, res, a, b, c = sig[0]
    assert a == b and res == c
    return TNAME[a], TNAME[c], int(n)


def confirm_repeats(name):
    """Rates of the confirmation repeats of one roofline variant (empty when it was only measured in a sweep)."""
    out = []
    for f in sorted(glob.glob(str(root / f"confirm/{name}_*.json"))):
        if f.endswith((".config.json", ".telemetry.json")):
            continue
        r = json.loads(Path(f).read_text())
        if "accounting" not in r or "median_seconds" not in r:
            continue
        a = r["accounting"]
        out.append((a["float_ops"] + a["integer_ops"]) / r["median_seconds"] / 1e12)
    return out


def roof(key):
    v = roofs[key]
    return v["value"], bool(v.get("confirmed")), v["source"], v.get("repeats"), v.get("repeat_spread")


def reuse_row(dtype, kernel_reuse):
    rows = [x for x in summary["matrix_feed_by_reuse"] if x["dtype"] == dtype and x["level"] == "shared"]
    row = min(rows, key=lambda x: abs(x["ops_per_load_byte"] - kernel_reuse))
    name = re.sub(r"_[0-9a-f]{12}\.json$", "", row["source"].split("/")[1])
    reps = confirm_repeats(name)
    return row, name, reps


def roof_set(dtype, kernel_reuse):
    key = {"fp16": "matrix_fp16", "fp16_fp32": "matrix_fp16_fp32", "int8": "matrix_int8"}[dtype]
    reg, reg_ok, reg_src, _, _ = roof(key)
    fed, fed_ok, fed_src, _, _ = roof(key + "_feed_shared")
    row, name, reps = reuse_row(dtype, kernel_reuse)
    flags = []
    if not reg_ok:
        flags.append("register roof UNCONFIRMED")
    if not fed_ok:
        flags.append("fed-shared roof UNCONFIRMED")
    if row["source"].startswith("confirm/") and len(reps) >= 3:
        spread = (max(reps) - min(reps)) / statistics.median(reps)
        reuse_note = f"reuse row {name} ({row['ops_per_load_byte']:g} op/B): {len(reps)} confirmation repeats, spread {100 * spread:.2f} %"
        if spread > 0.05:
            flags.append("fed-reuse row repeat spread > 5 %")
    else:
        reuse_note = f"reuse row {name} ({row['ops_per_load_byte']:g} op/B)"
        flags.append("fed-reuse roof is a single sweep row, NOT CONFIRMED")
    src = f"report/summary.json short_run.{key} ({reg_src}); short_run.{key}_feed_shared ({fed_src}); matrix_feed_by_reuse {row['source']}"
    return reg, fed, row["rate"], src, reuse_note, flags, dict(register=reg_src, fed_shared=fed_src, fed_reuse=row["source"], fed_reuse_repeats=reps)


# --- in-model trace of the tuning campaign (gate s4-c1, candidate arm = the final configuration) -----------------
trace = {}
for r in csv.DictReader((root / "sources/s4-c1-trace-gemm.csv").open()):
    if r["build"] == "cand":
        trace.setdefault((r["model"], r["scheme"], int(r["N"]), int(r["K"])), []).append((float(r["ms"]), r["kernel"]))

# --- linear rows -------------------------------------------------------------------------------------------------
runs = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(root / "microbench/linear-r*.json")))]
assert len(runs) >= 5
cases = {}
for i, d in enumerate(runs):
    assert d["subgroup_size"] == 32 and d["warmup_runs"] == 3 and d["timed_runs"] == 5 and d["group_size"] == 128
    for c in d["cases"]:
        if c["suite"] == "linear" and c["regime"] == "prefill" and c["storage"] == "texture3d":
            cases.setdefault((c["model"], c["op"], c["scheme"]), []).append(c)
rows, detail = [], []
order = {"wq_wo": 0, "wk_wv": 1, "w1_w3": 2, "w2": 3}
for (model, op, scheme), cs in sorted(cases.items(), key=lambda kv: (MODEL[kv[0][0]], kv[0][2], order[kv[0][1]])):
    assert len(cs) == len(runs)
    kernels = {c["kernel"] for c in cs}
    assert len(kernels) == 1, kernels
    kernel = kernels.pop()
    M, N, K = cs[0]["M"], cs[0]["N"], cs[0]["K"]
    assert M == 2048
    k = KERNELS[kernel]
    in_t, acc_t, _ = spirv_types(kernel)
    m, n, kk = k["mma"]
    reuse = k["mmas"] * 2 * m * n * kk / ((k["a_tiles"] + k["b_tiles"]) * k["tile_bytes"])
    meds = [c["kernel_median_us"] for c in cs]
    us = statistics.median(meds)
    rate = 2 * M * N * K / (us * 1e-6) / 1e12
    reg, fed, fedr, src, reuse_note, flags, srcs = roof_set(k["family"], reuse)
    t = trace.get((MODEL[model], scheme, N, K), [])
    tk = {x[1] for x in t}
    assert tk == {kernel}, (model, op, scheme, tk, kernel)
    tms = statistics.median(x[0] for x in t)
    trate = 2 * M * N * K / (tms * 1e-3) / 1e12
    unit = "TFLOP/s" if scheme == "4w" else "TOP/s"
    acc_label = acc_t if scheme != "4w" else f"{acc_t} (one fp16 accumulator run per 128-K quantization group; group sums added in fp32 outside the MMA)"
    notes = [
        f"kernel reuse {reuse:.4g} op per loaded tile byte ({k['derive']})",
        reuse_note,
        f"in-model trace (tuning campaign gate s4-c1, candidate arm, same kernel): median {tms:.4f} ms over {len(t)} dispatches = {trate:.1f} {unit} = {100 * trate / reg:.1f} % of the register roof",
        f"microbench spread over 5 processes {100 * (max(meds) - min(meds)) / us:.2f} %",
        "dispatch field of the microbench: " + cs[0]["dispatch"],
    ] + flags
    rows.append([DEVICE, MODEL[model], "linear", op, M, N, K, scheme, kernel, in_t, acc_label, f"{m}x{n}x{kk}", 32,
                 f"{us / 1000:.4f}", f"{rate:.2f}", unit, f"{reg:.2f}", f"{fed:.2f}", f"{fedr:.2f}",
                 f"{100 * rate / reg:.1f}", f"{100 * rate / fed:.1f}", f"{100 * rate / fedr:.1f}", src,
                 "microbench/linear-r1..r5.json: median over 5 processes of kernel_median_us (each 3 warm-up + 5 timed iterations), storage texture3d",
                 "; ".join(notes)])
    detail.append(dict(model=MODEL[model], op="linear", shape=op, scheme=scheme, kernel=kernel, M=M, N=N, K=K,
                       kernel_median_us_per_process=meds, kernel_us=us, rate=rate, unit=unit, kernel_reuse=reuse,
                       roofs=dict(register=reg, fed_shared=fed, fed_reuse=fedr), roof_sources=srcs, flags=flags,
                       in_model=dict(median_ms=tms, dispatches=len(t), rate=trate)))

# --- fused attention rows ----------------------------------------------------------------------------------------
sruns = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(root / "microbench/sdpa-r*.json")))]
assert len(sruns) >= 5
inmodel = {}
for line in (root / "sources/fused-roof-s4-c1.txt").read_text().splitlines():
    p = line.split(",")
    if len(p) == 7 and p[0] in ("1b", "3b", "8b"):
        inmodel.setdefault(p[0], []).append((float(p[3]), float(p[5])))
for model in ("llama-3.2-1b", "llama-3.2-3b", "llama-3.1-8b"):
    cs = [c for d in sruns for c in d["cases"] if c["suite"] == "sdpa" and c["model"] == model
          and c["regime"] == "prefill" and c["op"] == "total" and c["variant"] == "coopmat"]
    assert len(cs) == len(sruns)
    S, d, heads = cs[0]["M"], cs[0]["K"], cs[0]["N"]
    k = SDPA[d]
    in_t, acc_t, nm = spirv_types(k["kernel"])
    assert nm == k["mmas"]
    # rows x context columns executed per head: workgroup i (1-based) owns rows up to i*TM and runs ceil(i*TM/TN) blocks
    cells = sum(k["tm"] * -(-(i * k["tm"]) // k["tn"]) * k["tn"] for i in range(1, S // k["tm"] + 1))
    work = heads * cells * 2 * d * 2  # QK^T and attention x V, 2*d flop per (row, column) each
    causal = heads * (S * (S + 1) // 2) * 2 * d * 2
    reuse = k["mmas"] * 2 * 16 * 16 * 16 / (k["loads"] * 512)
    means = [c["op_mean_us"] for c in cs]
    us = statistics.median(means)
    rate = work / (us * 1e-6) / 1e12
    reg, fed, fedr, src, reuse_note, flags, srcs = roof_set("fp16_fp32", reuse)
    im = inmodel[MODEL[model]]
    notes = [
        f"executed matrix work {work:.4g} flop per layer ({100 * causal / work:.1f} % of it at or below the causal diagonal)",
        "time is the whole attention of one layer in the microbench (op 'total', mean of 5 timed iterations): fused kernel plus its K/V copy pass, softmax included; no kernel-only time is reported",
        f"kernel name from the tuning campaign's in-model ETDump and source (sources/attention-kernel-evidence.txt): the microbench prints no kernel name for --sdpa",
        f"kernel reuse {reuse:.4g} flop per loaded tile byte ({k['derive']})",
        reuse_note,
        "operands K and V come from global buffers, not from shared memory: the shared-fed roofs are the nearest available, not a matched operand source",
        f"in-model (tuning campaign s4-c1, fused kernel alone, 4w / 8da4w cell): {im[0][0]:.1f} / {im[1][0]:.1f} us per layer = {im[0][1]:.1f} / {im[1][1]:.1f} TFLOP/s = {100 * im[0][1] / reg:.1f} / {100 * im[1][1] / reg:.1f} % of the register roof",
        f"microbench spread over 5 processes {100 * (max(means) - min(means)) / us:.2f} %",
    ] + flags
    rows.append([DEVICE, MODEL[model], "sdpa_fused", f"S{S}_d{d}_h{heads}", S, heads, d, "attention (both schemes)", k["kernel"], in_t, acc_t,
                 "16x16x16", 32, f"{us / 1000:.4f}", f"{rate:.2f}", "TFLOP/s", f"{reg:.2f}", f"{fed:.2f}", f"{fedr:.2f}",
                 f"{100 * rate / reg:.1f}", f"{100 * rate / fed:.1f}", f"{100 * rate / fedr:.1f}", src,
                 "microbench/sdpa-r1..r5.json: median over 5 processes of op_mean_us (op total, variant coopmat)",
                 "; ".join(notes)])
    detail.append(dict(model=MODEL[model], op="sdpa_fused", kernel=k["kernel"], S=S, head_dim=d, heads=heads,
                       op_mean_us_per_process=means, us=us, work_flop=work, rate=rate, kernel_reuse=reuse,
                       roofs=dict(register=reg, fed_shared=fed, fed_reuse=fedr), roof_sources=srcs, flags=flags,
                       in_model=[dict(us_per_layer=a, rate=b) for a, b in im]))

HEAD = "device,model,op,shape,M,N,K,scheme,kernel,in_type,acc_type,mma_shape,subgroup,kernel_ms,rate,unit,roof_register,roof_fed_shared,roof_fed_reuse,pct_register,pct_fed_shared,pct_fed_reuse,roof_source,rate_source,notes".split(",")
with (root / "efficiency.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(HEAD)
    w.writerows(rows)
(root / "efficiency-detail.json").write_text(json.dumps(detail, indent=1))
for r in rows:
    print(f"{r[1]:3s} {r[3]:14s} {r[7][:9]:9s} {r[8][12:52]:40s} {r[13]:>8s} ms {r[14]:>7s} {r[15]:8s} reg {r[19]:>5s} % fed {r[20]:>5s} % reuse {r[21]:>5s} %")

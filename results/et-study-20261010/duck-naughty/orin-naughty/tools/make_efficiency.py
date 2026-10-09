#!/usr/bin/env python3
"""make_efficiency.py <results root>: part B. Writes <root>/efficiency.csv from raw files only:

- kernel time: partB/linear-prefill/run*.json (`kernel_median_us` of test_llama_microbench, one fresh process per
  run, 3 warm-up + 5 timed dispatches each); the value is the median over the runs. Attention: op `total`, variant
  `coopmat` of partB/sdpa-prefill/run*.json (`op_mean_us`; the suite reports no per-kernel median).
- kernel name: the same JSON rows (must be identical in every run).
- operand / accumulator types and matrix shape: isa/kernel-coopmat-types.csv (spirv-dis of the build's SPIR-V).
- roofs: report/summary.json of the part A `fast` plan (`short_run`, confirmed flag, repeats, spread) and the
  fed-matrix rows at the kernel's reuse: reuse-confirm/*/report/summary.json (focused confirmation, same runner)
  or part A's `matrix_feed_by_reuse` rows. The reuse row is the quality-passing row of the kernel's feed level
  whose operations per loaded byte is nearest (absolute difference) to the kernel's (tools/kernel_reuse.json).
- in-model trace (cited, not re-run): partB/trace-s5-c1/{gemm,attention}.csv of the tuning campaign.

Rate = 2*M*N*K / kernel_time (attention: 2*S*S*head_dim*heads, the causal half of QK^T plus of attention x V, as
the tuning campaign counts it). No number is typed in by hand."""
import csv, glob, json, pathlib, statistics, sys

R = pathlib.Path(sys.argv[1])
DEVICE = "Jetson Orin Nano 8GB (nvgpu 595.78; 15 W mode as found, GPU 306-612 MHz)"
GLSLC = "build topic4: shaders compiled by the cross image's glslc, not the pinned one (accepted limitation)"
SHAPES = ["wq_wo", "wk_wv", "w1_w3", "w2"]
MODEL = {"llama-3.2-1b": "1B", "llama-3.2-3b": "3B", "llama-3.1-8b": "8B"}
TRACE_MODEL = {"1B": "1b", "3B": "3b", "8B": "8b"}
LAYERS = {"1B": 16, "3B": 28, "8B": 32}
ROOF = {("float16", "float16"): "fp16", ("float16", "float32"): "fp16_fp32", ("sint8", "sint32"): "int8"}


def sig(x, n=4):
    return f"{x:.{n}g}" if x < 10 ** n else f"{x:.0f}"


def rows_of(path):
    d = json.load(open(path))
    return next(v for v in d.values() if isinstance(v, list))


def kname(s):
    return s.split('"kernel_name": "')[1].split('"')[0] if "kernel_name" in s else s


# ---- kernel types from the SPIR-V analysis -------------------------------------------------------
types = {}
for r in csv.DictReader(open(R / "isa/kernel-coopmat-types.csv")):
    if r["kind"] != "muladd":
        continue
    a, b, c = (r[k].split(": ", 1)[1].split() for k in ("c2", "c3", "c4"))
    res = r["c1"].split(": ", 1)[1].split()
    am, ak = a[1].split("x")
    bk, bn = b[1].split("x")
    assert ak == bk and a[0] == b[0] and c[0] == res[0], r
    t = (a[0], c[0], f"{am}x{bn}x{ak}")
    assert types.setdefault(r["shader"], t) == t, ("mixed MulAdd signatures", r["shader"])

reuse = json.load(open(R / "tools/kernel_reuse.json"))

# ---- roofs ----------------------------------------------------------------------------------------
S = json.load(open(R / "report/summary.json"))


def roof(key, summary=S, where="report/summary.json"):
    v = summary["short_run"][key]
    ok = bool(v.get("confirmed")) and v.get("repeats", 0) >= 3 and v.get("repeat_spread", 1) <= 0.05
    flag = (f"confirmed, {v.get('repeats')} repeats, spread {v.get('repeat_spread', 0) * 100:.2f}%" if ok
            else f"FLAGGED not confirmed ({v.get('repeats')} quality repeats)")
    return v["value"], f"{where} short_run.{key} = {v['config']['name']} ({flag})", ok


def reuse_candidates(dtype, level):
    """(ops_per_byte, rate, description, confirmed) of every quality-passing row of this dtype and feed level."""
    out = []
    for sub in sorted(glob.glob(str(R / "reuse-confirm/*/report/summary.json"))):
        s = json.load(open(sub))
        rel = str(pathlib.Path(sub).relative_to(R))
        key = f"matrix_{dtype}_feed_{level}"
        if key not in s["short_run"]:
            continue
        v = s["short_run"][key]
        opb = next(x["ops_per_load_byte"] for x in s["matrix_feed_by_reuse"]
                   if (x["dtype"], x["level"], x["chains"]) == (dtype, level, v["config"]["chains"]))
        val, desc, ok = roof(key, s, rel)
        out.append((opb, val, desc + f" at {opb:g} ops/B", ok))
    for x in S["matrix_feed_by_reuse"]:
        if (x["dtype"], x["level"]) != (dtype, level) or x["gates"]:
            continue
        top = S["short_run"].get(f"matrix_{dtype}_feed_{level}")
        if top and top["config"]["chains"] == x["chains"]:
            val, desc, ok = roof(f"matrix_{dtype}_feed_{level}")
            out.append((x["ops_per_load_byte"], val, desc + f" at {x['ops_per_load_byte']:g} ops/B", ok))
        else:
            out.append((x["ops_per_load_byte"], x["rate"],
                        f"report/summary.json matrix_feed_by_reuse {dtype} {level} c{x['chains']} = {x['source']} "
                        f"(FLAGGED single quality-passing row, not a confirmed roof) at {x['ops_per_load_byte']:g} ops/B", False))
    return out


def reuse_roof(dtype, level, kernel_opb):
    c = reuse_candidates(dtype, level)
    best = min(c, key=lambda t: (abs(t[0] - kernel_opb), not t[3]))
    return best


# ---- in-model trace ---------------------------------------------------------------------------------
trace = {}
for r in csv.DictReader(open(R / "partB/trace-s5-c1/gemm.csv")):
    if r["build"] == "cand":
        trace.setdefault((r["model"], r["scheme"], int(r["N"]), int(r["K"])), []).append((float(r["ms"]), r["kernel"]))
att = {(r["model"], r["scheme"]): r for r in csv.DictReader(open(R / "partB/trace-s5-c1/attention.csv")) if r["build"] == "cand"}

# ---- linear rows ----------------------------------------------------------------------------------
runs = sorted(glob.glob(str(R / "partB/linear-prefill/run*.json")))
assert len(runs) >= 5, runs
cells = {}
for f in runs:
    for r in rows_of(f):
        if r["suite"] == "linear" and r["regime"] == "prefill" and r["storage"] == "texture3d":
            c = cells.setdefault((r["model"], r["scheme"], r["op"]), {"t": [], "k": set(), "mnk": (r["M"], r["N"], r["K"])})
            c["t"].append(r["kernel_median_us"])
            c["k"].add(kname(r["kernel"]))
out = []
for m in MODEL:
    for scheme in ("4w", "8da4w"):
        for op in SHAPES:
            c = cells[(m, scheme, op)]
            assert len(c["k"]) == 1 and len(c["t"]) == len(runs), c
            k = c["k"].pop()
            M, N, K = c["mnk"]
            ms = statistics.median(c["t"]) / 1e3
            rate = 2 * M * N * K / (ms * 1e-3) / 1e12
            a_t, c_t, shape = types[k]
            d = ROOF[(a_t, c_t)]
            unit = "TOP/s" if d == "int8" else "TFLOP/s"
            reg, reg_s, reg_ok = roof(f"matrix_{d}")
            fed, fed_s, fed_ok = roof(f"matrix_{d}_feed_shared")
            kr = reuse[k]["ops_per_load_byte"]
            ropb, rr, rr_s, rr_ok = reuse_roof(d, "shared", kr)
            tr = trace.get((TRACE_MODEL[MODEL[m]], scheme, N, K))
            tnote = "no in-model trace row"
            if tr:
                tms = statistics.median(x[0] for x in tr)
                tk = {x[1] for x in tr}
                tnote = (f"in-model trace (tuning campaign s5-c1 gemm.csv, final arm, {len(tr)} calls): median {sig(tms)} ms = "
                         f"{sig(2 * M * N * K / (tms * 1e-3) / 1e12)} {unit}, kernel {'same' if tk == {k} else 'DIFFERENT: ' + '+'.join(tk)}")
            spread = (max(c["t"]) - min(c["t"])) / statistics.median(c["t"]) * 100
            notes = (f"kernel reuse {kr:.4g} ops per loaded byte ({reuse[k]['derivation']}); reuse roof row at {ropb:g} ops/B"
                     + ("" if abs(ropb - kr) / kr < 0.6 else " (NEAREST PASSING ROW IS FAR: no quality-passing row nearer; context, not a matched ceiling)")
                     + f"; run-to-run spread {spread:.2f}%; {tnote}; {GLSLC}")
            out.append([DEVICE, MODEL[m], "linear", op, M, N, K, scheme, k, a_t, c_t, shape, 32, sig(ms), sig(rate), unit,
                        sig(reg), sig(fed), sig(rr), f"{rate / reg * 100:.1f}", f"{rate / fed * 100:.1f}", f"{rate / rr * 100:.1f}",
                        "register: " + reg_s + "; fed shared: " + fed_s + "; fed at reuse: " + rr_s,
                        f"partB/linear-prefill/run1..{len(runs)}.json kernel_median_us, median of {len(runs)} fresh processes "
                        "(each 3 warm-up + 5 timed), texture3d storage, --skip-correctness", notes])

# ---- attention rows -------------------------------------------------------------------------------
sruns = sorted(glob.glob(str(R / "partB/sdpa-prefill/run*.json")))
fused = open(R / "partB/sdpa-prefill/run1.log").read().split("orin fused attention: ")[1].split("\n")[0].split()
for m in MODEL:
    t, shp = [], None
    for f in sruns:
        for r in rows_of(f):
            if (r["suite"], r["model"], r["regime"], r["op"], r["variant"]) == ("sdpa", m, "prefill", "total", "coopmat"):
                t.append(r["op_mean_us"])
                shp = (r["M"], r["K"], r["N"])
    assert shp is not None and len(t) == len(sruns), m
    S_len, hd, heads = shp
    k = next(x for x in fused if f"_d{hd}_" in x)
    ms = statistics.median(t) / 1e3
    ops = 2 * S_len * S_len * hd * heads
    rate = ops / (ms * 1e-3) / 1e12
    a_t, c_t, shape = next(v for n, v in types.items() if n.startswith(k))  # SPIR-V file: <name>_buffer_buffer_half
    d = ROOF[(a_t, c_t)]
    reg, reg_s, _ = roof(f"matrix_{d}")
    fed, fed_s, _ = roof(f"matrix_{d}_feed_shared")
    kr = reuse[k]["ops_per_global_load_byte"]
    ropb, rr, rr_s, _ = reuse_roof(d, "cache", kr)
    a = att[(TRACE_MODEL[MODEL[m]], "4w")]
    tms = float(a["fused_ms"]) / LAYERS[MODEL[m]]
    notes = (f"S=2048 queries x 2048 keys, head_dim {hd}, {heads} heads; rate counts 2*S*S*head_dim*heads (causal half of QK^T and of attention x V); "
             f"kernel time is the suite's whole attention operator (op total, mean of 5 timed per process), kernel name from the run's '[sarc_dev] orin fused attention' line; "
             f"K and V tiles are loaded from the storage buffer and only the exp scores from shared memory, so the shared-fed roof is context and the reuse roof is the cache-fed row "
             f"nearest the kernel's {kr:g} ops per buffer-loaded byte ({reuse[k]['derivation']}); "
             f"in-model trace (tuning campaign s5-c1 attention.csv, 4w final arm): fused kernel {sig(tms)} ms per layer = {sig(ops / (tms * 1e-3) / 1e12)} TFLOP/s; "
             f"run-to-run spread {(max(t) - min(t)) / statistics.median(t) * 100:.2f}%; {GLSLC}")
    out.append([DEVICE, MODEL[m], "attention", "fused_sdpa", S_len, S_len, hd, "-", k, a_t, c_t, shape, 32, sig(ms), sig(rate), "TFLOP/s",
                sig(reg), sig(fed), sig(rr), f"{rate / reg * 100:.1f}", f"{rate / fed * 100:.1f}", f"{rate / rr * 100:.1f}",
                "register: " + reg_s + "; fed shared (context): " + fed_s + "; fed at reuse (cache-fed): " + rr_s,
                f"partB/sdpa-prefill/run1..{len(sruns)}.json op total / coopmat op_mean_us, median of {len(sruns)} fresh processes", notes])

hdr = ("device,model,op,shape,M,N,K,scheme,kernel,in_type,acc_type,mma_shape,subgroup,kernel_ms,rate,unit,roof_register,"
       "roof_fed_shared,roof_fed_reuse,pct_register,pct_fed_shared,pct_fed_reuse,roof_source,rate_source,notes").split(",")
with open(R / "efficiency.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(hdr)
    w.writerows(out)
for r in out:
    print(r[1], r[3], r[7], r[8].replace("sarc_", "")[:44], r[9], r[10], r[11], r[13], r[14], r[15], "|", r[16], r[17], r[18], "|", r[19], r[20], r[21])

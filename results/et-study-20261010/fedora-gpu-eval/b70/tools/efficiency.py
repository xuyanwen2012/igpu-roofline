#!/usr/bin/env python3
"""efficiency.py <results root>: write efficiency.csv (part B) from the raw files of the study.

Inputs, all under the results root:
  raw/linear-r{1,2,3}.json   test_llama_microbench.v1, --linear --regime=prefill --storage=texture3d, final build,
                             ET_VK_SARC_UNVERIFIED=1 ET_VK_SARC_DEV_PROFILE=b70-fused1 (3 warm-up + 5 timed runs per
                             case and process; kernel_median_us = median of the 5)
  raw/sdpa-r{1,2,3}.json     the same binary, --sdpa (the fused attention kernel; the tool reports the mean of the 5
                             timed runs of the whole attention call and no kernel name)
  report/summary.json        igpu-roofline fast plan of this study (part A)
  isa/spirv/types.csv        tools/spirv_types.py: component types read from each kernel's SPIR-V
  cited/s3-final-trace-gemm.csv, cited/s3-final-attention.csv   the tuning campaign's warm ETDump (cited, not re-run)

kernel_ms = median over the three processes of kernel_median_us. rate = 2*M*N*K / kernel_ms.
Reuse of a linear kernel (operations per byte it loads from shared memory per K step of one subgroup), from the
tile token t<TM>x<TN>k<TK>g<GX><GY>s16: a = (TM/GY)/8 A fragments (8 x Kmma) and b = (TN/GX)/16 B fragments
(Kmma x 16) are loaded for a*b multiply-adds, so ops/byte = a*b*2*8*16*Kmma / ((a*8*Kmma + b*Kmma*16) * elem).
The fed roof at the kernel's reuse is the matrix_feed_by_reuse row of the same component types and source whose
ops_per_load_byte is nearest; if the tool gated that row out, the field says "no matching roof".
"""
import csv, json, re, statistics, sys, pathlib

root = pathlib.Path(sys.argv[1])
S = json.load(open(root / "report/summary.json"))
types = {r["kernel"]: r for r in csv.DictReader(open(root / "isa/spirv/types.csv"))}
SR, REUSE = S["short_run"], S["matrix_feed_by_reuse"]
DT = {("fp16", "fp16"): "fp16", ("fp16", "fp32"): "fp16_fp32", ("int8", "int32"): "int8"}
ELEM = {"fp16": 2, "fp16_fp32": 2, "int8": 1}
GRID = [1, 2, 4, 8]
f3 = lambda x: "" if x is None else "%.4g" % x
pct = lambda a, b: "" if not b else "%.1f" % (100 * a / b)


def roof(key):
    r = SR[key]
    assert r.get("confirmed") is True, key          # every register / fed-shared roof used is a confirmed one
    return r["value"], "%s=%s (confirmed, %d repeats, spread %.1f%%)" % (key, r["config"]["name"], r["repeats"], 100 * r["repeat_spread"])


def reuse_row(dtype, level, opb):
    """nearest grid point of the tool, then the tool's row there (None if gated out)"""
    per_chain = 2 * 8 * 16 / ((8 + 16) * ELEM[dtype])          # ops per loaded byte of one chain, any Kmma
    c = min(GRID, key=lambda c: (abs(c * per_chain - opb), -c))  # a tie goes to the higher reuse
    rows = [r for r in REUSE if r["dtype"] == dtype and r["level"] == level and r["chains"] == c]
    return c, c * per_chain, (rows[0] if rows else None)


def flag(row, roofkey):
    conf = SR[roofkey]
    same = conf["config"].get("chains") == row["chains"] and conf.get("confirmed")
    return "confirmed roof" if same else "single run %s, NOT a confirmed roof" % row["source"]


def med3(vals):
    return statistics.median(vals), min(vals), max(vals)


runs = [json.load(open(root / ("raw/linear-r%d.json" % i))) for i in (1, 2, 3)]
trace = {}
for r in csv.DictReader(open(root / "cited/s3-final-trace-gemm.csv")):
    if r["build"] == "cand":
        trace.setdefault((r["model"], r["scheme"], int(r["N"]), int(r["K"])), []).append((float(r["ms"]), r["kernel"]))
SHORT = {"llama-3.2-1b": "1b", "llama-3.2-3b": "3b", "llama-3.1-8b": "8b"}
out = []
cases = [c for c in runs[0]["cases"] if c["suite"] == "linear" and c["regime"] == "prefill"]
for c in sorted(cases, key=lambda c: (c["scheme"], SHORT[c["model"]], c["N"] * 100000 + c["K"])):
    key = lambda x: (x["model"], x["scheme"], x["op"], x["storage"])
    same = [x for run in runs for x in run["cases"] if key(x) == key(c)]
    assert len(same) == 3 and len({x["kernel"] for x in same}) == 1 and all(x["M"] == 2048 for x in same)
    us, lo, hi = med3([x["kernel_median_us"] for x in same])
    M, N, K, kern = c["M"], c["N"], c["K"], c["kernel"]
    t = types[kern]
    dtype = DT[(t["in_type"], t["acc_type"])]
    kmma = int(t["mma_shape"].split("x")[2])
    tm, tn, tk, gx, gy, sg = map(int, re.search(r"_t(\d+)x(\d+)k(\d+)g(\d)(\d)s(\d+)", kern).groups())
    a, b = tm // gy // 8, tn // gx // 16
    opb = a * b * 2 * 8 * 16 * kmma / ((a * 8 * kmma + b * kmma * 16) * ELEM[dtype])
    rate = 2.0 * M * N * K / (us * 1e-6) / 1e12
    reg, s1 = roof("matrix_" + dtype)
    fed, s2 = roof("matrix_%s_feed_shared" % dtype)
    ch, gopb, row = reuse_row(dtype, "shared", opb)
    notes = ["kernel ops/loaded byte %.2f (a=%d A + b=%d B fragments per K step of %d, %d multiply-adds)" % (opb, a, b, kmma, a * b),
             "process medians %.1f-%.1f us (spread %.1f%%)" % (lo, hi, 100 * (hi - lo) / us),
             "roofs measured at subgroup size 32, kernel runs at 16"]
    if row:
        if dtype == "int8":
            notes.append("the reuse row is not a ceiling for this kernel: its shader issues 9 shared-memory load messages per multiply-add (B tile in 32-byte byte-granular messages), the kernel 4.6 (64-byte messages), see isa/counts.csv; a percentage above 100 is this mismatch, not a gain")
        fr, s3 = row["rate"], "matrix_feed_by_reuse %s shared chains=%d ops/byte=%.2f: %s" % (dtype, ch, gopb, flag(row, "matrix_%s_feed_shared" % dtype))
    else:
        fr, s3 = None, "matrix_feed_by_reuse %s shared chains=%d ops/byte=%.2f: no matching roof (the tool's row is gated out: short;fixed_cost)" % (dtype, ch, gopb)
        ctx = [r for r in REUSE if r["level"] == "shared" and r["chains"] == ch and r["dtype"] == "fp16_fp32"]
        ctx2 = [r for r in REUSE if r["level"] == "cache" and r["chains"] == ch and r["dtype"] == dtype]
        notes.append("context only, not matched: fp16->fp32 accumulator shared-fed chains=%d %.4g TFLOP/s (%.1f%% of it); same types cache-fed chains=%d %.4g TFLOP/s" % (ch, ctx[0]["rate"], 100 * rate / ctx[0]["rate"], ch, ctx2[0]["rate"]))
    tr = trace.get((SHORT[c["model"]], c["scheme"], N, K))
    if tr:
        ms = statistics.median(x[0] for x in tr)
        assert {x[1] for x in tr} == {kern}
        notes.append("in-model trace (cited, s3-final cand, %d dispatches): median %.4g ms = %.4g %s" % (len(tr), ms, 2.0 * M * N * K / (ms * 1e-3) / 1e12, "TFLOP/s" if c["scheme"] == "4w" else "TOP/s"))
    else:
        notes.append("no in-model trace row for this shape")
    out.append(["Arc Pro B70", c["model"], "linear", c["op"], M, N, K, c["scheme"], kern, t["in_type"], t["acc_type"], t["mma_shape"], sg,
                "%.4f" % (us / 1000), f3(rate), "TFLOP/s" if c["scheme"] == "4w" else "TOP/s", f3(reg), f3(fed), f3(fr) or "no matching roof",
                pct(rate, reg), pct(rate, fed), pct(rate, fr) if fr else "", "; ".join([s1, s2, s3]),
                "raw/linear-r{1,2,3}.json kernel_median_us (median of 5 timed runs), median of 3 processes; dispatch field '%s'" % c["dispatch"], "; ".join(notes)])

# Fused attention. Executed multiply-add work, from the kernel source (isa/glsl/): a workgroup owns 16 query rows of one
# head and walks the context in blocks of TN columns up to the causal limit: blocks(tile t) = min(S/TN, (16t+15)/TN + 1);
# per block QK^T and attn*V each do (16/8)*(TN/16)*(d/16) multiply-adds of 8x16x16.
FUSED = {64: ("sarc_dev_b580_sdpa_fused_d64_t16x64s16m8g4roj_buffer_buffer_half", 64, True),
         128: ("sarc_dev_b580_sdpa_fused_d128_t16x128s16m8g8oj_buffer_buffer_half", 128, False)}
sd = [json.load(open(root / ("raw/sdpa-r%d.json" % i))) for i in (1, 2, 3)]
att = {r["cell"] if "cell" in r else None: r for r in csv.DictReader(open(root / "cited/s3-final-attention.csv"))}
for c in [c for c in sd[0]["cases"] if c["regime"] == "prefill" and c["variant"] == "coopmat" and c["op"] == "total"]:
    same = [x for run in sd for x in run["cases"] if (x["model"], x["regime"], x["variant"], x["op"]) == (c["model"], "prefill", "coopmat", "total")]
    assert all(x["dispatch"] == "confirmed" for x in same)
    us, lo, hi = med3([x["op_mean_us"] for x in same])
    Sq, d, heads = c["M"], c["K"], c["N"]
    kern, tn, aq_reg = FUSED[d]
    t = types[kern]
    blocks = sum(min(Sq // tn, (16 * i + 15) // tn + 1) for i in range(Sq // 16))
    mma_block = 2 * (16 // 8) * (tn // 16) * (d // 16)
    ops = heads * blocks * mma_block * 2 * 8 * 16 * 16
    # bytes loaded per block: K and V^T tiles (512 B each) from the packed buffers, e tiles (256 B) from shared memory
    # once per subgroup that needs them, and Q fragments (256 B) from the buffer per product unless kept in registers
    kv = 2 * (tn // 16) * (d // 16) * 512
    e = (16 // 8) * (tn // 16) * (d // 16) * 256
    q = 0 if aq_reg else (16 // 8) * (tn // 16) * (d // 16) * 256
    opb = mma_block * 4096 / (kv + e + q)
    rate = ops / (us * 1e-6) / 1e12
    dense = 2 * 2.0 * heads * Sq * Sq * d / (us * 1e-6) / 1e12
    reg, s1 = roof("matrix_fp16_fp32")
    fed, s2 = roof("matrix_fp16_fp32_feed_shared")
    ch, gopb, row = reuse_row("fp16_fp32", "cache", opb)
    ctx = [r for r in REUSE if r["level"] == "shared" and r["chains"] == ch and r["dtype"] == "fp16_fp32"][0]
    notes = ["heads=%d kv_heads=%d; executed multiply-add work (causal blocks only): %d blocks x %d multiply-adds per head; dense 2*2*H*S*S*d would read %.4g TFLOP/s" % (heads, c["kv_heads"], blocks, mma_block, dense),
             "kernel ops/loaded byte %.2f (%d B from the packed K / V^T%s buffers, %d B of e from shared memory per block)" % (opb, kv + q, "" if aq_reg else " / Q", e),
             "operands come mostly from storage buffers, so the fed roof at the kernel's reuse is the cache-fed row; the shared-fed row at the same reuse is %.4g TFLOP/s (%.1f%%)" % (ctx["rate"], 100 * rate / ctx["rate"]),
             "process means %.1f-%.1f us (spread %.1f%%); the time is the whole attention call (K/V tile copy + fused kernel)" % (lo, hi, 100 * (hi - lo) / us),
             "kernel name from the profile table (b70-fused1) and the driver dump (workgroup of %d lanes), not printed by the tool" % (16 * (4 if d == 64 else 8)),
             "roofs measured at subgroup size 32, kernel runs at 16",
             "in-model trace (cited): cited/s3-final-attention.csv"]
    out.append(["Arc Pro B70", c["model"], "sdpa_fused", "qk_softmax_av", Sq, Sq, d, "fp16", kern, t["in_type"], t["acc_type"], t["mma_shape"], 16,
                "%.4f" % (us / 1000), f3(rate), "TFLOP/s", f3(reg), f3(fed), f3(row["rate"]), pct(rate, reg), pct(rate, fed), pct(rate, row["rate"]),
                "; ".join([s1, s2, "matrix_feed_by_reuse fp16_fp32 cache chains=%d ops/byte=%.2f: %s" % (ch, gopb, flag(row, "matrix_fp16_fp32_feed_cache"))]),
                "raw/sdpa-r{1,2,3}.json op_mean_us of op=total variant=coopmat (mean of 5 timed runs), median of 3 processes", "; ".join(notes)])

COLS = "device,model,op,shape,M,N,K,scheme,kernel,in_type,acc_type,mma_shape,subgroup,kernel_ms,rate,unit,roof_register,roof_fed_shared,roof_fed_reuse,pct_register,pct_fed_shared,pct_fed_reuse,roof_source,rate_source,notes".split(",")
with open(root / "efficiency.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(COLS); w.writerows(out)
for r in out:
    print("%-13s %-6s %-5s N=%-5s K=%-5s %-18s %8s ms %7s %-7s reg %5s%% fed %5s%% reuse %5s%% (%s)" % (r[1], r[3][:6], r[7], r[5], r[6], re.sub(r".*_(t\d+x\d+\w+?)_(tex|buf).*", r"\1", r[8])[-18:], r[13], r[14], r[15], r[19], r[20], r[21], r[18]))

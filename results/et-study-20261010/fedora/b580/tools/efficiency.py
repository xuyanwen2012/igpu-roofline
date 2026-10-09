#!/usr/bin/env python3
"""efficiency.py: writes efficiency.csv (part B) from the raw files of this results root. Run from the root.

kernel_ms   linear: median over the three processes microbench/<scheme>-r{1,2,3}.json of `kernel_median_us`
            (each itself the median of 5 timed iterations after 3 warm-up iterations) / 1000.
            attention: median over microbench/sdpa-r{1..5}.log of the mean_us of the line
            `RESULT,sdpa,<model>,,prefill,total,...,coopmat` (fused kernel plus its K/V copy pass) / 1000.
rate        linear: 2*M*N*K / kernel time, in 1e12 per second (TFLOP/s for 4w, TOP/s for 8da4w).
            attention: executed matrix operations / kernel time. The fused kernel skips the blocks that the
            causal mask removes for a whole row tile (num_blocks in the shader), so executed operations are
            heads * sum over row tiles of 2 * (2 * WG_TILE_M * WG_TILE_N * num_blocks * head_dim): QK^T and e*V.
roofs       report/summary.json (part A, all confirmed): register = short_run[matrix_<dtype>],
            fed shared = short_run[matrix_<dtype>_feed_shared] (its best configuration: CHAINS 8).
            fed at the kernel's reuse: the shared-fed row whose operations per loaded byte is nearest the
            kernel's, taken from the focused confirmation ../b580-reuse-<variant>/report/summary.json
            (same build, 3 confirmation repeats); empty when no quality-passing row of the matching
            accumulator type exists.
"""
import csv, glob, json, re, statistics as st
S = json.load(open("report/summary.json"))
KERNEL_DTYPE = {"4w": ("fp16", "fp16", "fp16", "8x16x16", "TFLOP/s"), "8da4w": ("int8", "int8", "int32", "8x16x32", "TOP/s")}
MODELS = {"llama-3.2-1b": "1b", "llama-3.2-3b": "3b", "llama-3.1-8b": "8b"}


def roof(key):
    r = S["short_run"][key]; assert r["confirmed"], key
    return r["value"]


def reuse_roof(variant, key):
    s = json.load(open(f"../b580-reuse-{variant}/report/summary.json"))
    r = s["short_run"].get(key)
    return (r["value"], r["repeat_spread"]) if r and r.get("confirmed") else None


# operations per loaded byte of the kernels (tile arithmetic of the dispatched variants, checked against the
# generated code in isa/counts.csv): per subgroup and K step
#  4w  t128x128k16g44s16m8: subgroup tile 32x32 -> 4 A fragments 8x16 fp16 (256 B) + 2 B fragments 16x16 fp16
#      (512 B) feed 8 multiply-adds of 2*8*16*16 = 4096 -> 32768 / 2048 B = 16.0
#  8da4w t128x128k64g84s16m8: subgroup tile 32x16 -> 4 A fragments 8x32 int8 (256 B) + 1 B fragment 32x16 int8
#      (512 B) feed 4 multiply-adds of 2*8*16*32 = 8192 -> 32768 / 1536 B = 21.33
KERNEL_OPB = {"4w": 32768 / 2048, "8da4w": 32768 / 1536}
trace = {}
for r in csv.DictReader(open("cited/s6-final-trace-gemm.csv")):
    if r["build"] == "cand":
        trace.setdefault((r["model"], r["scheme"], int(r["N"]), int(r["K"])), []).append(float(r["ms"]))
rows = []
for scheme, (dt, it, at, shape, unit) in KERNEL_DTYPE.items():
    runs = [json.load(open(f))["cases"] for f in sorted(glob.glob(f"microbench/{scheme}-r[0-9].json"))]
    assert len(runs) == 3
    reg, fed = roof(f"matrix_{dt}"), roof(f"matrix_{dt}_feed_shared")
    opb = KERNEL_OPB[scheme]
    by = sorted((r for r in S["matrix_feed_by_reuse"] if r["dtype"] == dt and r["level"] == "shared"), key=lambda r: abs(r["ops_per_load_byte"] - opb))
    for i, c in enumerate(runs[0]):
        same = [r[i] for r in runs]
        assert all((x["model"], x["op"], x["kernel"]) == (c["model"], c["op"], c["kernel"]) for x in same)
        med = [x["kernel_median_us"] for x in same]
        ms = st.median(med) / 1000
        rate = 2 * c["M"] * c["N"] * c["K"] / (ms * 1e-3) / 1e12
        t = trace[(MODELS[c["model"]], scheme, c["N"], c["K"])]
        tms = st.median(t); trate = 2 * c["M"] * c["N"] * c["K"] / (tms * 1e-3) / 1e12
        note = [f"3 process medians {min(med):.1f}-{max(med):.1f} us (spread {100 * (max(med) - min(med)) / st.median(med):.1f} %)",
                f"in-model trace (cited/s6-final-trace-gemm.csv, build cand, median of {len(t)} dispatches) {tms:.4f} ms = {trate:.2f} {unit} = {100 * trate / reg:.1f} % of register roof",
                f"kernel reuse {opb:.2f} ops per loaded byte", "roofs measured at subgroup 32 (SIMD32), kernel runs subgroup 16 (SIMD16)"]
        if scheme == "8da4w":
            v, sp = reuse_roof("matrix_int8_8x16x32_c2_lds", "matrix_int8_feed_shared")
            fr, pfr = f"{v:.3f}", f"{100 * rate / v:.1f}"
            note.append(f"reuse roof = int8 shared-fed CHAINS 2 (21.33 ops per loaded byte), confirmed in ../b580-reuse-matrix_int8_8x16x32_c2_lds (spread {100 * sp:.1f} %); part A sweep row {by[0]['rate']:.3f}; that roofline shader loads B by bytes (d8u32) while the kernel loads 32-bit words: access granularity differs")
            rs = "report/summary.json short_run matrix_int8, matrix_int8_feed_shared; ../b580-reuse-matrix_int8_8x16x32_c2_lds/report/summary.json"
        else:
            assert reuse_roof("matrix_fp16_8x16x16_c2_lds", "matrix_fp16_feed_shared") is None and reuse_roof("matrix_fp16_8x16x16_c4_lds", "matrix_fp16_feed_shared") is None
            c2, _ = reuse_roof("matrix_fp16_fp32_8x16x16_c2_lds", "matrix_fp16_fp32_feed_shared")
            c4 = next(r["rate"] for r in S["matrix_feed_by_reuse"] if (r["dtype"], r["level"], r["chains"]) == ("fp16_fp32", "shared", 4))
            fr, pfr = "", ""
            note.append(f"no matching roof at the kernel's reuse: the fp16->fp16 shared-fed rows at CHAINS 2 and 4 (10.67 and 21.33 ops per loaded byte, equally near 16.0) fail the tool's quality gates (short; fixed_cost) in part A and in the focused repeats; nearest as context only, other accumulator type: fp16->fp32 shared-fed CHAINS 2 {c2:.1f} and CHAINS 4 {c4:.1f} TFLOP/s (both confirmed) = {100 * rate / c2:.0f} % and {100 * rate / c4:.0f} %")
            rs = "report/summary.json short_run matrix_fp16, matrix_fp16_feed_shared"
        rows.append(["b580", c["model"], "linear", c["op"], c["M"], c["N"], c["K"], scheme, c["kernel"], it, at, shape, 16, f"{ms:.4f}", f"{rate:.2f}", unit,
                     f"{reg:.3f}", f"{fed:.3f}", fr, f"{100 * rate / reg:.1f}", f"{100 * rate / fed:.1f}", pfr, rs,
                     f"microbench/{scheme}-r1.json, -r2.json, -r3.json (kernel_median_us)", "; ".join(note)])
# attention: variants selected by the profile b580-fused1 (not printed by --sdpa; see STUDY.md, part B)
ATT = {"llama-3.2-1b": ("sarc_dev_b580_sdpa_fused_d64_t16x64s16m8g4roj_buffer_buffer_half", 16, 64), "llama-3.2-3b": ("sarc_dev_b580_sdpa_fused_d128_t16x128s16m8g8oj_buffer_buffer_half", 16, 128),
       "llama-3.1-8b": ("sarc_dev_b580_sdpa_fused_d128_t16x128s16m8g8oj_buffer_buffer_half", 16, 128)}
tot = {}
for f in sorted(glob.glob("microbench/sdpa-r[0-9].log")):
    for l in open(f):
        p = l.strip().split(",")
        if l.startswith("RESULT,sdpa") and p[4:6] == ["prefill", "total"] and p[-1] == "coopmat":
            tot.setdefault(p[2], []).append((float(p[8]), int(p[6]), int(p[7])))
att = {r["model"]: r for r in csv.DictReader(open("cited/s4-final-trace-attention.csv")) if r["arm"] == "cand" and r["scheme"] == "4w"}
reg = roof("matrix_fp16_fp32")
for model in ("llama-3.1-8b", "llama-3.2-3b", "llama-3.2-1b"):
    v = tot[model]; assert len(v) == 5
    kern, tm, tn = ATT[model]; d, heads, Sq = v[0][1], v[0][2], 2048
    ops = heads * sum(2 * 2 * tm * tn * min(Sq // tn, (s + tm - 1) // tn + 1) * d for s in range(0, Sq, tm))
    dense = heads * 2 * 2 * Sq * Sq * d
    ms = st.median(x[0] for x in v) / 1000; rate = ops / (ms * 1e-3) / 1e12
    a = att[MODELS[model]]; n = int(a["fused_n"]); tms = (float(a["fused_ms"]) + float(a["kv_copy_ms"])) / n; trate = ops / (tms * 1e-3) / 1e12
    note = [f"{heads} heads, head_dim {d}; rate counts the executed blocks of the causal walk ({ops / dense:.4f} of the dense 4*H*S*S*d; dense-equivalent {dense / (ms * 1e-3) / 1e12:.2f} TFLOP/s)",
            "kernel_ms = fused kernel + K/V copy pass + everything else in the op (microbench 'total', mean of the process, median of 5 processes "
            f"{min(x[0] for x in v):.1f}-{max(x[0] for x in v):.1f} us); kernel name from the profile definition and the campaign's logs, not printed by this run",
            f"in-model trace (cited/s4-final-trace-attention.csv, 4w cell, cand: (fused_ms + kv_copy_ms) / {n} layers) {tms:.4f} ms = {trate:.2f} TFLOP/s = {100 * trate / reg:.1f} % of register roof",
            "no matching fed roof: K and V tiles are loaded from storage buffers and e from shared memory, mixed sources and reuse; nearest as context: fp16->fp32 shared-fed "
            f"{roof('matrix_fp16_fp32_feed_shared'):.1f}, cache-fed {roof('matrix_fp16_fp32_feed_cache'):.1f} TFLOP/s (CHAINS 8)", "roof measured at subgroup 32 (SIMD32), kernel runs subgroup 16 (SIMD16)"]
    rows.append(["b580", model, "sdpa_fused", "attention", Sq, Sq, d, "fp16", kern, "fp16", "fp32", "8x16x16", 16, f"{ms:.4f}", f"{rate:.2f}", "TFLOP/s", f"{reg:.3f}", "", "",
                 f"{100 * rate / reg:.1f}", "", "", "report/summary.json short_run matrix_fp16_fp32", "microbench/sdpa-r1.log .. sdpa-r5.log (prefill,total,coopmat mean_us)", "; ".join(note)])
hdr = "device,model,op,shape,M,N,K,scheme,kernel,in_type,acc_type,mma_shape,subgroup,kernel_ms,rate,unit,roof_register,roof_fed_shared,roof_fed_reuse,pct_register,pct_fed_shared,pct_fed_reuse,roof_source,rate_source,notes".split(",")
csv.writer(open("efficiency.csv", "w", newline="")).writerows([hdr] + rows)
for r in rows: print(*r[1:4], r[7], r[8][-45:-24], r[13], r[14], r[16], r[17], r[18], r[19], r[20], r[21], sep="\t")

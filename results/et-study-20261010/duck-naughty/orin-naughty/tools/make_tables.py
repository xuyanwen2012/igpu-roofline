#!/usr/bin/env python3
"""make_tables.py <results root>: prints the markdown tables of STUDY.md from report/summary.json, efficiency.csv
and isa/counts.csv (no number in STUDY.md is typed from memory)."""
import csv, json, pathlib, statistics as st, sys
R = pathlib.Path(sys.argv[1]); S = json.load(open(R / "report/summary.json")); sr = S["short_run"]
print("### roofs")
print("| roof | confirmed median | repeat range | repeats | 120 s sustained (1 batch) | unit |\n|---|---:|---:|---:|---:|---|")
for k in ["matrix_fp16", "matrix_fp16_fp32", "matrix_int8", "matrix_fp16_feed_shared", "matrix_fp16_fp32_feed_shared", "matrix_int8_feed_shared",
          "matrix_fp16_feed_cache", "matrix_fp16_fp32_feed_cache", "matrix_int8_feed_cache", "alu_fp16", "alu_fp32", "dot_int8",
          "global_read", "global_write", "global_copy", "cache_read_effective", "shared_fp16_read", "shared_fp16_write"]:
    v = sr[k]; su = S["sustained"].get(k)
    flag = "" if v.get("confirmed") and v.get("repeats", 0) >= 3 else " **(not confirmed)**"
    print(f"| {k} ({v['config']['name']}) | {v['value']:.3f}{flag} | {v.get('repeat_min', 0):.3f} to {v.get('repeat_max', 0):.3f} | {v.get('repeats')} | {su['value']:.3f}" if su else
          f"| {k} ({v['config']['name']}) | {v['value']:.3f}{flag} | {v.get('repeat_min', 0):.3f} to {v.get('repeat_max', 0):.3f} | {v.get('repeats')} | -", f"| {v['unit']} |")
rows = list(csv.DictReader(open(R / "efficiency.csv")))
print("\n### efficiency")
print("| model | shape | scheme | kernel (short) | in -> acc | N x K | ms | rate | of register roof | of shared-fed roof | of fed roof at kernel reuse |\n|---|---|---|---|---|---|---:|---:|---:|---:|---:|")
short = lambda k: k.replace("sarc_linear_q4gsw_coopmat_", "").replace("sarc_dev_linear_q4gsw_coopmat_", "").replace("sarc_linear_dq8ca_coopmat_zpgtr_", "").replace("sarc_dev_orin_sdpa_", "").replace("_texture3d_texture2d_half", "")
ty = {"float16": "fp16", "float32": "fp32", "sint8": "int8", "sint32": "int32"}
for r in rows:
    print(f"| {r['model']} | {r['shape']} | {r['scheme']} | `{short(r['kernel'])}` | {ty[r['in_type']]} -> {ty[r['acc_type']]} | {r['N']} x {r['K']} | {r['kernel_ms']} | {r['rate']} {r['unit']} | {r['pct_register']} % | {r['pct_fed_shared']} % | {r['pct_fed_reuse']} % |")
print("\n### per scheme")
for sch in ("4w", "8da4w", "-"):
    x = [r for r in rows if r["scheme"] == sch]
    f = lambda c: [float(r[c]) for r in x]
    print(sch, "rate geomean %.3f min %.3f max %.3f" % (st.geometric_mean(f("rate")), min(f("rate")), max(f("rate"))),
          "| pct_register geomean %.1f range %.1f-%.1f" % (st.geometric_mean(f("pct_register")), min(f("pct_register")), max(f("pct_register"))),
          "| pct_fed_shared %.1f-%.1f | pct_fed_reuse %.1f-%.1f" % (min(f("pct_fed_shared")), max(f("pct_fed_shared")), min(f("pct_fed_reuse")), max(f("pct_fed_reuse"))))
for m in ("1B", "3B", "8B"):
    for sch in ("4w", "8da4w"):
        x = [r for r in rows if r["scheme"] == sch and r["model"] == m]
        ops = sum(2 * int(r["M"]) * int(r["N"]) * int(r["K"]) for r in x); t = sum(float(r["kernel_ms"]) for r in x)
        print(m, sch, "equal-call-weight rate %.3f" % (ops / t / 1e9), "pct of register roof %.1f" % (ops / t / 1e9 / float(x[0]["roof_register"]) * 100))
print("\n### chain (8da4w)")
x = [r for r in rows if r["scheme"] == "8da4w"]
reg, fed, reu = float(x[0]["roof_register"]), float(x[0]["roof_fed_shared"]), float(x[0]["roof_fed_reuse"]); k = st.geometric_mean(float(r["rate"]) for r in x)
for a, b, n in ((reg, fed, "register -> fed from shared (best reuse)"), (fed, reu, "fed (best) -> fed at the kernel's reuse"), (reu, k, "fed at reuse -> kernel (geomean of 12 shapes)")):
    print(f"| {n} | {a:.3f} | {b:.3f} | -{(1 - b / a) * 100:.1f} % |")
print("product check: kernel/register = %.4f ; (1-l1)(1-l2)(1-l3) = %.4f" % (k / reg, (fed / reg) * (reu / fed) * (k / reu)))
print("\n### counts")
for r in csv.DictReader(open(R / "isa/counts.csv")):
    print(f"| {r['kind']} | `{short(r['shader']).replace('_buffer_buffer_half', '')}` {r['tag'] if r['kind'] == 'kernel' else ''} | {r['static_muladd']} | {r['muladd_per_loop_iteration_per_subgroup']} | {r['static_coopmat_load']} | {r['register_count']} | {r['stack_size']} | {r['shared_memory_size']} | {r['binary_size']} |")

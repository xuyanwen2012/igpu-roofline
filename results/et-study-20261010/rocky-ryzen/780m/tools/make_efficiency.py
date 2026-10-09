#!/usr/bin/env python3
"""Build efficiency.csv (part B of et-study-20261010) from the raw files of one device.

Usage: make_efficiency.py <results root> [--device NAME]
Reads, all under the results root:
  <device dir>/report/summary.json, report/all-configurations.csv     igpu-roofline fast plan (part A)
  et/linear-r1..r5.json, et/sdpa-r1..r3.json                          test_llama_microbench of the final build
  isa/spirv-types.csv                                                 tools/spirv_coopmat.py over the kernels' SPIR-V
  et-trace/gemm.csv (optional)                                        the tuning campaign's in-model trace (cited copy)
Rate = 2*M*N*K / kernel_time, kernel_time = median over the repeats of the microbench's kernel_median_us
(each repeat: 3 warm-up + 5 timed runs). Roofs are the confirmed short-run medians of the report; the
by-reuse rows come from summary.json "matrix_feed_by_reuse" (nearest ops per loaded byte, absolute distance).
"""
import csv, glob, json, statistics, sys, pathlib

root = pathlib.Path(sys.argv[1])
DEVICE = 'Radeon 780M (RADV, Mesa 25.2.7)'
dev = [p for p in root.iterdir() if (p / 'report' / 'summary.json').exists()][0]
S = json.load(open(dev / 'report' / 'summary.json'))
allc = list(csv.DictReader(open(dev / 'report' / 'all-configurations.csv')))
spv = {}
for r in csv.DictReader(open(root / 'isa' / 'spirv-types.csv')):
    if r['record'] == 'OpCooperativeMatrixMulAddKHR':
        spv[r['file']] = r
MODEL = {'llama-3.2-1b': '1B', 'llama-3.2-3b': '3B', 'llama-3.1-8b': '8B'}
ROOF = {'4w': 'matrix_fp16_fp32', '8da4w': 'matrix_int8'}
UNIT = {'4w': 'TFLOP/s', '8da4w': 'TOP/s'}


def roof(key):
    r = S['short_run'][key]
    flag = '' if r.get('confirmed') else ' UNCONFIRMED'
    return r['value'], f"{key} {r['value']:.3f} ({r['repeats']} repeats, spread {100 * r['repeat_spread']:.2f} %{flag})"


def reuse_row(dtype, level, opb):
    rows = [r for r in S['matrix_feed_by_reuse'] if r['dtype'] == dtype and r['level'] == level]
    r = min(rows, key=lambda x: abs(x['ops_per_load_byte'] - opb))
    name = r['source'].split('/')[-1].rsplit('_', 1)[0]
    reps = [(float(c['float_ops']) + float(c['integer_ops'])) / float(c['median_seconds']) / 1e12 for c in allc
            if c['name'] == name and c['source'].startswith('confirm/') and c['accepted'] == 'True']
    # the same shader runs at other working sets too (cache- or DRAM-resident): keep only repeats of this configuration
    reps = [x for x in reps if abs(x / r['rate'] - 1) < 0.05]
    if len(reps) >= 3:
        status = f"{len(reps)} confirmation repeats, median {statistics.median(reps):.3f}, spread {100 * (max(reps) - min(reps)) / statistics.median(reps):.2f} %"
    else:
        status = 'FLAG: single validated sweep row, gates passed, NOT confirmed by repeats'
    return r['rate'], f"{name} (CHAINS {r['chains']}, {r['ops_per_load_byte']:.0f} ops/loaded byte, {r['rate']:.3f}; {status})"


def med(vals):
    return statistics.median(vals)


trace = {}
tp = root / 'et-trace' / 'gemm.csv'
if tp.exists():
    for r in csv.DictReader(open(tp)):
        if r['build'] == 'cand':
            trace.setdefault((r['model'].upper(), r['scheme'], int(r['M']), int(r['N']), int(r['K'])), []).append((float(r['ms']), r['kernel']))

runs = [json.load(open(f)) for f in sorted(glob.glob(str(root / 'et' / 'linear-r[1-9].json')))]
cases = {}
for d in runs:
    for c in d['cases']:
        if c['suite'] == 'linear' and c['storage'] == 'texture3d' and c['regime'] == 'prefill':
            cases.setdefault((c['model'], c['scheme'], c['op']), []).append(c)

out = []
order = {'1B': 0, '3B': 1, '8B': 2}
for (model, scheme, op), cs in sorted(cases.items(), key=lambda kv: (kv[0][1], order[MODEL[kv[0][0]]], ['wq_wo', 'wk_wv', 'w1_w3', 'w2'].index(kv[0][2]))):
    kernels = {c['kernel'] for c in cs}
    assert len(kernels) == 1, kernels
    kernel = kernels.pop()
    M, N, K = cs[0]['M'], cs[0]['N'], cs[0]['K']
    meds = [c['kernel_median_us'] / 1e3 for c in cs]
    ms = med(meds)
    rate = 2.0 * M * N * K / (ms * 1e-3) / 1e12
    t = spv[kernel]
    sig = t['detail']
    in_type = sig.split('A[')[1].split(' ')[0]
    acc_type = sig.split('-> ')[1].split(' ')[0]
    opb = float(t['ops_per_loaded_byte'])
    dtype = 'fp16_fp32' if scheme == '4w' else 'int8'
    assert (in_type, acc_type) == (('half', 'float') if scheme == '4w' else ('char', 'int')), sig
    rr, rr_s = roof(ROOF[scheme]); rs, rs_s = roof(ROOF[scheme] + '_feed_shared'); ru, ru_s = reuse_row(dtype, 'shared', opb)
    notes = [f"repeat medians ms {'/'.join(f'{x:.3f}' for x in meds)} (spread {100 * (max(meds) - min(meds)) / ms:.2f} %)",
             f"kernel ops per loaded operand byte {opb:.2f} (static SPIR-V: {t['count']} MulAdd, {t['loaded_operands']} distinct loaded 16x16 operand tiles = {t['loaded_bytes']} B, operands loaded from {t['A_source'].replace('load:', '')} memory)",
             'roofs measured at subgroup 64; the kernel runs at subgroup 32 (no roof at 32 in the tool)',
             f"dispatch status reported by the microbench: {cs[0]['dispatch']}"]
    if rate > ru:
        notes.append('kernel exceeds the by-reuse row: that row is not a ceiling for this kernel (see STUDY.md part D)')
    tr = trace.get((MODEL[model], scheme, M, N, K))
    if tr:
        tms = med([x[0] for x in tr]); tk = {x[1] for x in tr}
        notes.append(f"in-model trace (tuning campaign, s9-final-dev15, candidate arm, cited not re-run): median {tms:.4f} ms over {len(tr)} dispatches = {2.0 * M * N * K / (tms * 1e-3) / 1e12:.3f} {UNIT[scheme]}" + ('' if tk == {kernel} else f"; trace kernel differs: {'+'.join(sorted(tk))}"))
    else:
        notes.append('no in-model trace row for this shape')
    out.append([DEVICE, MODEL[model], 'linear', op, M, N, K, scheme, kernel, in_type, acc_type, '16x16x16', 32, f'{ms:.4f}', f'{rate:.4f}', UNIT[scheme],
                f'{rr:.3f}', f'{rs:.3f}', f'{ru:.3f}', f'{100 * rate / rr:.1f}', f'{100 * rate / rs:.1f}', f'{100 * rate / ru:.1f}',
                f"register: {rr_s}; fed shared: {rs_s}; fed at reuse: {ru_s}; report/summary.json of the fast plan of 2026-10-09",
                f"test_llama_microbench --linear --regime=prefill (final build head4, 780m-final), et/linear-r1..r{len(meds)}.json, median of {len(meds)} repeat medians (3 warm-up + 5 timed runs each)",
                '; '.join(notes)])

# fused attention kernel: operator time (copy pass + fused kernel), executed multiply-adds from the tile arithmetic
sd = [json.load(open(f)) for f in sorted(glob.glob(str(root / 'et' / 'sdpa-r[1-9].json')))]
FUSED = json.load(open(root / 'et' / 'fused-kernels.json')) if (root / 'et' / 'fused-kernels.json').exists() else {}
att = {}
for d in sd:
    for c in d['cases']:
        if c['suite'] == 'sdpa' and c['regime'] == 'prefill' and c['variant'] == 'coopmat' and c['op'] == 'total':
            att.setdefault(c['model'], []).append(c)
for model, cs in sorted(att.items(), key=lambda kv: order[MODEL[kv[0]]]):
    Sx, d_head, H = cs[0]['M'], cs[0]['K'], cs[0]['N']
    kernel = FUSED.get(str(d_head), '')
    t = spv[kernel]
    Rt, Ct = (32, 32) if d_head == 64 else (16, 64)      # row tile, context block: the t<R>x<C> of the kernel name
    assert f'_d{d_head}_t{Rt}x{Ct}' in kernel
    blocks = sum(-(-((i + 1) * Rt) // Ct) for i in range(Sx // Rt))          # causal: blocks up to the tile's last row
    mma = 2 * H * blocks * (Rt // 16) * (Ct // 16) * (d_head // 16)             # QK^T and e*V, 16x16x16 each
    assert int(t['count']) == 2 * (Rt // 16) * (Ct // 16) * (d_head // 16)
    meds = [c['op_mean_us'] / 1e3 for c in cs]
    ms = med(meds); rate = mma * 8192 / (ms * 1e-3) / 1e12
    opb = float(t['ops_per_loaded_byte'])
    rr, rr_s = roof('matrix_fp16_fp32'); rs, rs_s = roof('matrix_fp16_fp32_feed_shared'); ru, ru_s = reuse_row('fp16_fp32', 'cache', opb)
    notes = [f"repeat op means ms {'/'.join(f'{x:.3f}' for x in meds)} (spread {100 * (max(meds) - min(meds)) / ms:.2f} %)",
             'kernel_ms is the operator time of the fused node (copy pass + fused kernel; the microbench reports no separate kernel median), 40 warm-up + 10 timed runs',
             f"rate = executed multiply-adds x 8192 / time; {mma} multiply-adds = 2 (QK^T, e*V) x {H} heads x {blocks} causal (row tile {Rt}, context block {Ct}) blocks x {(Rt // 16) * (Ct // 16) * (d_head // 16)}; not 2*M*N*K",
             f"S={Sx} head_dim={d_head} heads={H} kv_heads={cs[0]['kv_heads']} (columns M,N,K hold S, heads, head_dim)",
             f"kernel ops per loaded operand byte {opb:.2f} (static SPIR-V: {t['count']} MulAdd, {t['loaded_operands']} loaded tiles = {t['loaded_bytes']} B; A from {t['A_source'].replace('load:', '')}, B from {t['B_source'].replace('load:', '')})",
             'K and V tiles are loaded from the storage buffer, not from shared memory: roof_fed_shared is context only (no matching roof); roof_fed_reuse is the cache-fed row',
             'roofs measured at subgroup 64; the kernel runs at subgroup 32']
    if rate > ru:
        notes.append('kernel exceeds the by-reuse row: that row is not a ceiling for this kernel')
    out.append([DEVICE, MODEL[model], 'sdpa_fused', 'attention', Sx, H, d_head, 'fp16', kernel, 'half', 'float', '16x16x16', 32, f'{ms:.4f}', f'{rate:.4f}', 'TFLOP/s',
                f'{rr:.3f}', f'{rs:.3f}', f'{ru:.3f}', f'{100 * rate / rr:.1f}', f'{100 * rate / rs:.1f}', f'{100 * rate / ru:.1f}',
                f"register: {rr_s}; fed shared (context): {rs_s}; fed from cache at reuse: {ru_s}; report/summary.json of the fast plan of 2026-10-09",
                f"test_llama_microbench --sdpa --regime=prefill, ET_VK_SDPA_PERF_RUNS=40,10 (final build head4, 780m-final), et/sdpa-r1..r{len(meds)}.json, median of {len(meds)} repeat op means",
                '; '.join(notes)])

cols = 'device,model,op,shape,M,N,K,scheme,kernel,in_type,acc_type,mma_shape,subgroup,kernel_ms,rate,unit,roof_register,roof_fed_shared,roof_fed_reuse,pct_register,pct_fed_shared,pct_fed_reuse,roof_source,rate_source,notes'.split(',')
with open(root / 'efficiency.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(cols); w.writerows(out)
print(f'{len(out)} rows written')

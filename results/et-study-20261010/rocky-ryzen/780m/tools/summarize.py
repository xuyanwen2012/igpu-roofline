#!/usr/bin/env python3
"""Aggregates behind STUDY.md, recomputed from efficiency.csv and et-trace/gemm.csv.
Usage: summarize.py <results root>   (prints text; redirect to summary-tables.txt)
1. Per model and scheme: rate weighted by time over the model's linear dispatches (dispatch counts per shape
   taken from the in-model trace), for the microbench kernel times and for the in-model trace times.
2. Range and geometric mean of the per-shape percentages.
3. 4w only: logical activation-fetch traffic of each shape, M*K*2 bytes read once per output-column tile,
   = M*K*2*(N/tile_N)/kernel_time, against the texture and DRAM read roofs of part A."""
import csv, json, math, pathlib, re, statistics, sys, collections
root = pathlib.Path(sys.argv[1])
rows = [r for r in csv.DictReader(open(root / 'efficiency.csv'))]
lin = [r for r in rows if r['op'] == 'linear']
dev = [p for p in root.iterdir() if (p / 'report' / 'summary.json').exists()][0]
S = json.load(open(dev / 'report' / 'summary.json'))['short_run']
cnt = collections.Counter(); tms = collections.defaultdict(list)
for r in csv.DictReader(open(root / 'et-trace' / 'gemm.csv')):
    if r['build'] == 'cand':
        k = (r['model'].upper(), r['scheme'], int(r['N']), int(r['K'])); cnt[k] += 1; tms[k].append(float(r['ms']))
print('1. time-weighted rate per model and scheme (weights: dispatches per prefill in the in-model trace)')
print('model scheme  microbench_rate pct_register  in_model_rate pct_register  (roof)')
for scheme in ('4w', '8da4w'):
    for model in ('1B', '3B', '8B'):
        ops = t_mb = t_tr = 0.0
        for r in lin:
            if r['model'] == model and r['scheme'] == scheme:
                k = (model, scheme, int(r['N']), int(r['K'])); n = cnt[k]
                ops += n * 2.0 * int(r['M']) * int(r['N']) * int(r['K'])
                t_mb += n * float(r['kernel_ms']) * 1e-3; t_tr += sum(tms[k]) * 1e-3
                roof = float(r['roof_register'])
        a, b = ops / t_mb / 1e12, ops / t_tr / 1e12
        print(f'{model:5s} {scheme:6s} {a:8.3f} {100 * a / roof:6.1f} %   {b:8.3f} {100 * b / roof:6.1f} %   ({roof})')
print('\n2. per-shape percentages: min, max, geometric mean')
for scheme in ('4w', '8da4w'):
    for col in ('pct_register', 'pct_fed_shared', 'pct_fed_reuse'):
        v = [float(r[col]) for r in lin if r['scheme'] == scheme]
        print(f'{scheme:6s} {col:15s} {min(v):6.1f} {max(v):6.1f} {math.exp(statistics.fmean(map(math.log, v))):6.1f}')
print('\n3. 4w: logical activation-fetch traffic (GB/s) = M*K*2*(N/tile_N)/kernel_time')
for k in ('texture_rgba16f_tex3d_cache', 'texture_rgba16f_tex3d_dram', 'global_read'):
    print(f'   roof {k}: {S[k]["value"]:.2f} GB/s (confirmed={S[k].get("confirmed")})')
print('model shape  tile     kernel_ms  rate   pct_reg  A_traffic_GBps  pct_of_tex3d_cache_roof')
for r in lin:
    if r['scheme'] != '4w':
        continue
    tm, tn = map(int, re.search(r'_t(\d+)x(\d+)k', r['kernel']).groups())
    M, N, K = int(r['M']), int(r['N']), int(r['K'])
    gb = M * K * 2.0 * (N / tn) / (float(r['kernel_ms']) * 1e-3) / 1e9
    print(f"{r['model']:5s} {r['shape']:6s} {tm}x{tn:<4d} {float(r['kernel_ms']):9.4f} {float(r['rate']):6.3f} {float(r['pct_register']):6.1f} {gb:10.1f} {100 * gb / S['texture_rgba16f_tex3d_cache']['value']:10.0f} %")

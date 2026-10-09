import json,glob,re,statistics,sys
for f in sorted(glob.glob('perf-*.json')):
    s,t=re.match(r'perf-(4w|8da4w)-(.*)\.json',f).groups(); d=json.load(open(f)); c=[x for x in d['cases'] if x['regime']=='prefill']
    corr=open(f'corr-{s}-{t}.log').read(); nfail=len(re.findall(r'FAILED for test',corr)); crash='Exception' in corr
    res={}
    for st in ('texture3d','buffer'):
        r=[2*x['M']*x['N']*x['K']/x['kernel_median_us']/1e6 for x in c if x['storage']==st and x.get('kernel_median_us') and t in x['kernel']]
        res[st]=round(statistics.mean(r),1) if len(r)==4 else f"n={len(r)}"
    print(f"{s:6} {t:20} tex={res['texture3d']!s:>6} buf={res['buffer']!s:>6}  corr_fail={nfail} crash={crash}")

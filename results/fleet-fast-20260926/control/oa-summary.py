"""oa-summary.py <rec>...: per-report Xe OA counters, keep reports with XVE_ACTIVE > 0.5 (kernel running), print medians."""
import re,statistics,subprocess,sys
for rec in sys.argv[1:]:
    out=subprocess.run(['xe-perf-reader','-r','-c','all',rec],capture_output=True,text=True).stdout
    reports=[];cur=None
    for l in out.splitlines():
        if re.match(r'\s*report\d+',l) or l.startswith('hw_id'):
            if cur: reports.append(cur)
            cur={}
        m=re.match(r'\s+([A-Za-z0-9_]+): ([-0-9.e+]+)',l)
        if m and cur is not None: cur[m.group(1)]=float(m.group(2))
    if cur: reports.append(cur)
    act=[r for r in reports if r.get('XVE_ACTIVE',0)>30]
    print(f'== {rec}: {len(reports)} reports, {len(act)} with XVE_ACTIVE>30%')
    if not act: continue
    keys=sorted({k for r in act for k in r})
    for k in keys:
        v=[r[k] for r in act if k in r]
        med=statistics.median(v)
        if med==0: continue
        print(f'  {k:45} {med:14.4g}')

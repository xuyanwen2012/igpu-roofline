"""Cross-device table of usable roofs (confirmed, spread <= 5 %) for fleet-fast-20260926."""
import json,pathlib,sys
base=pathlib.Path(__file__).resolve().parents[1]
DEV={'780m':'rocky-ryzen/780m','b70-0':'fedora-gpu-eval/b70-0','b580':'fedora/b580','s24':'fedora/R5CY21Y3VEV','pixel-7a':'fedora/3A021JEHN02756'}
KEYS=['alu_fp32','alu_fp16','dot_int8','matrix_fp16','matrix_fp16_fp32','matrix_int8','matrix_fp16_feed_shared','matrix_fp16_fp32_feed_shared','matrix_int8_feed_shared','global_read','global_write','global_copy','cache_read_effective','shared_fp16_read','shared_fp32_read','texture_rgba16f_tex2d_dram','texture_rgba16f_buffer_dram']
out={}
for dev,p in DEV.items():
 f=base/p/'report/summary.json'
 if not f.exists():continue
 s=json.loads(f.read_text());sr=s['short_run'];row={}
 for k in KEYS:
  r=sr.get(k)
  if not r:row[k]=None;continue
  ok=r.get('confirmed') and r.get('repeat_spread',1)<=0.05
  row[k]={'value':r['value'],'unit':r['unit'],'usable':bool(ok),'spread':r.get('repeat_spread'),'shape':(r.get('config') or {}).get('name')}
 sen=s['sentinel'];row['_sentinel']={'median':sen['median'],'degraded':sum(t['degraded'] for t in sen['timeline']),'n':len(sen['timeline'])}
 row['_sustained']={k:{'value':v['value'],'batches':v.get('batches'),'steady':v.get('all_steady')} for k,v in (s.get('sustained') or {}).items()} if isinstance(s.get('sustained'),dict) else s.get('sustained')
 row['_ridges']=s.get('ridges',{}).get('short_run',{})
 row['_device']=s['device'];row['_commit']=s.get('git_commit');row['_runner']=s.get('runner_sha256','')[:12];row['_stale']=s.get('stale_rows_excluded')
 row['_unconfirmed']=sorted(k for k,v in sr.items() if not v.get('confirmed'))
 out[dev]=row
(base/'overview.json').write_text(json.dumps(out,indent=1))
def cell(r):
 if not r:return '—'
 v=f"{r['value']:.3g}" if r['value']<100 else f"{r['value']:.0f}"
 return v if r['usable'] else f"({v})*"
print('| roof | unit | '+' | '.join(out)+' |');print('|---|---|'+'---:|'*len(out))
for k in KEYS:
 unit=next((out[d][k]['unit'] for d in out if out[d].get(k)),'')
 print(f'| {k} | {unit} | '+' | '.join(cell(out[d].get(k)) for d in out)+' |')
print('| sentinel median TFLOP/s (degraded/probes) | | '+' | '.join(f"{out[d]['_sentinel']['median']:.2f} ({out[d]['_sentinel']['degraded']}/{out[d]['_sentinel']['n']})" for d in out)+' |')
for d in out:print(d,out[d]['_device'],out[d]['_commit'],out[d]['_runner'],'stale',out[d]['_stale'],'unconfirmed:',out[d]['_unconfirmed'],'sustained:',out[d]['_sustained'])

"""Deploy source.tar.gz to each host, build the host runner there, start campaign.py detached."""
import pathlib,subprocess,concurrent.futures,json,shlex,sys
base=pathlib.Path(__file__).resolve().parents[1]
CAMPAIGN='fleet-fast-20260926'
# host -> list of controller invocations (device ids run sequentially within one invocation)
PLAN={'rocky-ryzen':[['780m']],'fedora-gpu-eval':[['b70-0']],'fedora':[['b580'],['s24'],['pixel-7a']]}
def ssh(h):return [] if h=='fedora' else ['ssh','-o','HostKeyAlias='+h,'-o','BatchMode=yes','-o','ConnectTimeout=8','doremy@'+h+'.tail031559.ts.net']
def run(h,cmd,**kw):return subprocess.run(ssh(h)+['bash','-c',shlex.quote(cmd)] if ssh(h) else ['bash','-c',cmd],**kw)
def one(h):
 dest='/home/doremy/'+('igpu-roofline/fleet/'+CAMPAIGN if h=='rocky-ryzen' else '.cache/igpu-roofline/'+CAMPAIGN)
 results='/home/doremy/igpu-roofline/campaigns/780m/2026-09-26-fast-et-study' if h=='rocky-ryzen' else dest+'/results'
 with (base/'source.tar.gz').open('rb') as f:
  p=run(h,'set -e; test ! -e '+dest+'; mkdir -p '+dest+'; tar xz -C '+dest,stdin=f,capture_output=True,timeout=120)
 if p.returncode:raise RuntimeError(h+': '+p.stderr.decode())
 build=f'''set -eu
cd {dest}
mkdir -p build/host {results}
/usr/bin/c++ -O2 -std=c++17 -I third_party/nlohmann_json/include -I deps/include runner/src/roofline.cpp -l:libvulkan.so.1 -o build/host/roofline
cp build/host/roofline build/host/roofline_sustained
/usr/bin/c++ -O2 -std=c++17 -I third_party/nlohmann_json/include -I deps/include runner/src/inspect.cpp -l:libvulkan.so.1 -o build/host/inspect
sha256sum build/host/roofline build/host/inspect build/android/roofline build/shader-manifest.json > {results}/build-hashes.txt
'''
 p=run(h,build,capture_output=True,text=True,timeout=600)
 if p.returncode:raise RuntimeError(h+' build: '+p.stderr)
 infos=[]
 for ids in PLAN[h]:
  tag='-'.join(ids)
  cmd=f'cd {dest}; nohup setsid python3 -u campaign.py {results} {h} {" ".join(ids)} > {dest}/controller-{tag}.log 2>&1 < /dev/null & echo $!'
  p=run(h,cmd,text=True,capture_output=True,timeout=20,check=True)
  infos.append({'host':h,'devices':ids,'source':dest,'results':results,'pid':p.stdout.strip(),'log':f'{dest}/controller-{tag}.log'})
 (base/'control'/(h+'-launch.json')).write_text(json.dumps(infos,indent=2))
 if h=='rocky-ryzen':
  text='\n- 2026-09-26: `780m/2026-09-26-fast-et-study` — fleet fast campaign (igpu-roofline c898a5a, runner built on host), automatic clocks, roofs for ExecuTorch 4w/8da4w tuning; in progress.\n'
  run(h,'cat >> /home/doremy/igpu-roofline/campaigns/README.md',input=text,text=True,check=True,timeout=20)
 return infos
hosts=sys.argv[1:] or list(PLAN)
with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as ex:
 for r in ex.map(one,hosts):print(json.dumps(r),flush=True)

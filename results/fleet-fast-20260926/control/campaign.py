"""fleet-fast-20260926 coordinator: fast plan, automatic clocks (no pinning), gpu-lab lock held.

Derived from fleet-quick-20260925/control/campaign.py without the clock pinning: CLAUDE.md
("root access does not authorize pinning") and gpu-lab ("never change clocks"). Clocks are
observed every 10 s instead, from the same read-only telemetry the Session records.
"""
import contextlib,fcntl,json,os,pathlib,signal,subprocess,sys,time,traceback,threading
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from igpu_roofline import paths
from igpu_roofline.device import LocalDevice,AdbDevice,utc_now
from igpu_roofline.session import Session
from igpu_roofline.stages import run_plan
PLAN='fast'

def command(args,check=True,timeout=30):
 p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
 if check and p.returncode:raise RuntimeError(str(args)+': '+p.stderr+p.stdout)
 return p.stdout.strip()
def interrupted(signum,frame):raise KeyboardInterrupt()
signal.signal(signal.SIGTERM,interrupted)

@contextlib.contextmanager
def lab_lock(g):
 """Hold gpu-lab's own device lock for the whole run so gpu-lab jobs back off."""
 if 'adb_serial' in g:
  adb=['adb','-s',g['adb_serial']];dest='/data/local/tmp/gpu-lab/fleet-lock-holder'
  command(adb+['shell','mkdir','-p','/data/local/tmp/gpu-lab'])
  command(adb+['push',str(ROOT/'build/android/hold-lock'),dest]);command(adb+['shell','chmod','755',dest])
  p=subprocess.Popen(adb+['shell',dest,'/data/local/tmp/gpu-lab/lock-'+g['uuid']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  if p.stdout.readline().strip()!='LOCKED':raise RuntimeError('gpu-lab device lock unavailable')
  try:yield
  finally:
   p.stdin.close()
   try:p.wait(timeout=10)
   except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
 else:
  p=pathlib.Path.home()/'.cache/gpu-lab'/('lock-'+g['uuid']);p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);f.seek(0);f.truncate();f.write(str(os.getpid())+'\n');f.flush();yield

def busy(g):
 if 'adb_serial' in g:
  cmd=['adb','-s',g['adb_serial'],'shell','/data/local/tmp/gpu-lab/gpu-harness-* --lock-dir /data/local/tmp/gpu-lab --list']
 else:
  harnesses=sorted((pathlib.Path.home()/'.cache/gpu-lab').glob('gpu-harness-*'),key=lambda p:p.stat().st_mtime)
  if not harnesses:raise RuntimeError('No gpu-lab harness for preflight')
  cmd=[str(harnesses[-1]),'--lock-dir',str(pathlib.Path.home()/'.cache/gpu-lab'),'--list']
 text=command(cmd);data=json.loads(next(x for x in text.splitlines() if x.startswith('{')))
 dev=next(x for x in data['devices'] if x['uuid']==g['uuid'])
 if dev.get('locked_by_pid'):raise RuntimeError('busy: gpu-lab lock held')
 if (dev.get('busy_pct') or 0)>=g.get('busy_threshold',10):raise RuntimeError('busy: '+str(dev.get('busy_pct')))
 return dev

def snapshot(device):
 return {'gpu_freq':device.gpu_freq(),'gpu_temp_c':device.gpu_temp_c()}

def main():
 config=json.loads((ROOT/'campaign-config.json').read_text());outroot=pathlib.Path(sys.argv[1]);outroot.mkdir(parents=True,exist_ok=True)
 only=set(sys.argv[3:])
 devices=[g for g in config['devices'] if g['host']==sys.argv[2] and (not only or g['id'] in only)]
 for g in devices:
  started=time.monotonic();meta={'schema_version':1,'campaign':config['campaign'],'source_commit':config['source_commit'],'plan':PLAN,'clock_mode':os.environ.get('FLEET_CLOCK_MODE','automatic (not pinned)'),'registry_device':g,'started_utc':utc_now(),'status':'starting'}
  result=outroot/(g.get('adb_serial') or g['id']);result.mkdir(exist_ok=True)
  s=None
  try:
   meta['preflight']=busy(g)
   with lab_lock(g):
    paths.use_target('android' if 'adb_serial' in g else 'host')
    os.environ['IGPU_ROOFLINE_UUID']=g['uuid'].replace('-','')
    os.environ['IGPU_ROOFLINE_STAGE']=str(ROOT/'stage')
    device=AdbDevice(g['adb_serial']) if 'adb_serial' in g else LocalDevice(g['id'])
    s=Session(device,outroot,plan=PLAN)
    stop=threading.Event();thread=None
    try:
     meta['status']='running';(result/'fleet-metadata.json').write_text(json.dumps(meta,indent=2))
     def monitor():
      with (result/'clock-observations.jsonl').open('a') as f:
       while not stop.is_set():
        try:record={'utc':utc_now(),**snapshot(device)}
        except Exception as e:record={'utc':utc_now(),'error':str(e)}
        f.write(json.dumps(record)+'\n');f.flush();stop.wait(10)
     thread=threading.Thread(target=monitor,daemon=True);thread.start()
     print('START',g['id'],PLAN,flush=True);run_plan(s,PLAN);meta['status']='finished'
    finally:
     stop.set()
     if thread:thread.join(timeout=35)
     s.close();s=None
  except BaseException as e:
   meta['status']='failed';meta['error']=str(e);meta['traceback']=traceback.format_exc();traceback.print_exc()
   if isinstance(e,KeyboardInterrupt):meta['status']='interrupted'
  finally:
   if s:s.close()
   meta['ended_utc']=utc_now();meta['elapsed_seconds']=time.monotonic()-started
   (result/'fleet-metadata.json').write_text(json.dumps(meta,indent=2));print('END',g['id'],meta['status'],meta.get('error',''),flush=True)
  if meta['status']=='interrupted':break
 (outroot/('controller-finished-'+sys.argv[2]+'.json')).write_text(json.dumps({'utc':utc_now()}))
if __name__=='__main__':main()

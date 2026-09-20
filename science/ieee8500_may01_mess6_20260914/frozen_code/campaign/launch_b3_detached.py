"""Create the supervisor outside all inherited Windows job objects."""
import os,sys,subprocess,json
from pathlib import Path
H=Path(__file__).absolute().parent
D=H/'codex_independent_handoff_20260913'
if __name__=='__main__':
 D.mkdir(exist_ok=False)
 with (D/'supervisor.log').open('xb') as out,(D/'supervisor.stderr.log').open('xb') as err:
  p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(H/'b3_detached_supervisor.py')],cwd=H,stdin=subprocess.DEVNULL,stdout=out,stderr=err,close_fds=True,creationflags=0x01000000|0x08000000)
 (D/'LAUNCH.json').write_text(json.dumps(dict(pid=p.pid,launcher_pid=os.getpid(),flags=p.creationflags if hasattr(p,'creationflags') else 0x09000000),indent=2),encoding='utf-8')
 print('DETACHED_SUPERVISOR_PID',p.pid,flush=True)

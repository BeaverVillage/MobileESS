"""The six-part B2 natural-completion gate; no writer touches B2 state."""
from contextlib import contextmanager,ExitStack
from pathlib import Path
import os,psutil
from . import config as c
from .io import read,optional,record,verify,atomic,now
from .contracts import b2_terminal

def alive(who):
 try:return psutil.Process(who['pid']).is_running() and abs(psutil.Process(who['pid']).create_time()-who['process_created'])<.001
 except (psutil.Error,KeyError,TypeError):return False

def b2_state():
 registry=optional(Path('D:/MobileESS_V44/runtime/ACTIVE_EQUIPMENT_LEDGER.json'))
 state=registry.get('B2_state') or {}
 pointer=Path(state.get('state_path',c.B2_HOME/'STATE.json'))
 allowed=pointer==c.B2_HOME/'STATE.json' or pointer.resolve().is_relative_to((c.B2_ROOT/'CONTROLLERS').resolve())
 if not allowed:raise PermissionError('UNKNOWN_B2_CONTROLLER_STATE')
 return read(pointer),pointer

def inspect_b2():
 state,pointer=b2_state();live=[];inflight=[];evidence=[]
 lease=state.get('lease') or {}
 if alive(lease):live.append(lease)
 for job in state.get('jobs',[]):
  root=Path(job['case_root']) if job.get('case_root') else None
  if root:
   for name in ('START.json','ACTUAL_START.json'):
    who=optional(root/name)
    if alive(who):live.append(who)
   if job.get('result'):
    verify([job['result']]);evidence.append(job['result'])
   # A stale failed attempt cannot hide an in-flight call beneath a prior root.
   for ledger in root.parent.glob('attempt*/**/*LEDGER.json'):
    value=optional(ledger)
    if value.get('inflight') is not None:inflight.append(str(ledger))
    if value.get('calls') or 'measured_Native_Runtime' in value:evidence.append(record(ledger))
   for checkpoint in root.rglob('*STAGE_CHECKPOINT.json'):evidence.append(record(checkpoint))
 for process in psutil.process_iter(['pid','cmdline','create_time']):
  try:
   args=process.info['cmdline'] or []
   if process.pid==os.getpid():continue
   if any(x in args for x in ('--case','--worker')) and any(str(c.B2_HOME).casefold() in str(x).casefold() or str(c.B2_ROOT).casefold() in str(x).casefold() for x in args):
    live.append(dict(pid=process.pid,process_created=process.info['create_time']))
  except (psutil.Error,TypeError):pass
 return dict(ready=b2_terminal(state,live,inflight),phase=state.get('phase'),live=live,inflight=inflight,
  state=record(pointer) if state else None,evidence=list({r['path']:r for r in evidence}.values()),UTC=now())

@contextmanager
def try_os_locks(paths):
 """Nonblocking probes; never waits with a subset of the shared locks held."""
 handles=[]
 try:
  for path in paths:
   p=Path(path)
   if not p.exists():raise PermissionError('B2_LOCK_PATH_MISSING:'+str(p))
   f=p.open('r+b');handles.append(f)
   if os.name=='nt':
    import msvcrt
    f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
   else:
    import fcntl
    fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  yield
 finally:
  for f in reversed(handles):f.close()

def ready_receipt():
 gate=inspect_b2()
 if not gate['ready']:return gate
 try:
  with try_os_locks(c.LOCKS):
   # Repeat under all six OS lock handles. Actual dispatch reacquires them.
   gate=inspect_b2()
   if not gate['ready']:return gate
   verify(gate['evidence'])
   atomic(c.OPS/'B2_RELEASE_PRESERVATION.json',dict(gate,OS_locks_verified_released=True,original_files_untouched=True))
 except (OSError,PermissionError) as error:gate.update(ready=False,lock_error=repr(error))
 return gate

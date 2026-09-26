"""Native Windows breakaway supervisor; independent of the launching app job."""
import ctypes, os, time, traceback
from pathlib import Path
import b3_resume_supervisor as campaign
H=campaign.H
D=H/'codex_independent_handoff_20260913'
def in_job():
 k=ctypes.WinDLL('kernel32',use_last_error=True)
 k.GetCurrentProcess.restype=ctypes.c_void_p
 k.IsProcessInJob.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
 flag=ctypes.c_int()
 if not k.IsProcessInJob(k.GetCurrentProcess(),None,ctypes.byref(flag)):raise ctypes.WinError(ctypes.get_last_error())
 return bool(flag.value)
def main():
 assert not in_job(),'BREAKAWAY_DID_NOT_ESCAPE_JOB'
 campaign.save(str(D.relative_to(H)/'DETACHED_READY.json'),dict(pid=os.getpid(),unix=time.time(),in_windows_job=False,status='WAITING_FOR_PRESERVED_HANDOFF'))
 while not(D/'GO.json').exists():time.sleep(.5)
 gate=campaign.read(D/'GO.json');assert gate['status']=='PRESERVED_AND_STOPPED'
 assert campaign.sha(D/'PRESERVATION_SHA.json')==gate['preservation_sha256']
 for r in campaign.read(D/'PRESERVATION_SHA.json')['files']:
  assert campaign.sha(r['path'])==r['sha256'],r['path']
 assert not(H/'SEARCH_CLOCK.json').exists(),'A1_CLOCK_MUST_NOT_BE_RESTARTED'
 b2=campaign.read(campaign.F/'B2_ACTUAL_COMPLETE.json');assert b2['status']=='PASS'
 assert campaign.sha(b2['result']['path'])==b2['result']['sha256']
 campaign.save('B3_DETACHED_STARTED.json',dict(pid=os.getpid(),unix=time.time(),in_windows_job=False,launch='Windows WMI process service; hidden window; independent parent',handoff_gate=gate,sequence=['M1_CACHE_RESUME','A1_CONTINUOUS_14400S','MF','ACTUAL_SHELL_QSAFE']))
 if not(H/'B3_M1/COMPLETE.json').exists():campaign.run('mess_worker.py','B3_M1','--resume')
 assert campaign.read(H/'B3_M1/COMPLETE.json')['status']=='PASS'
 campaign.run('a1_supervisor.py')
 campaign.run('mf_worker.py')
 campaign.run('b3_actual_shell.py')
 campaign.run('finalize_campaign_shell.py')
 campaign.save('SUPERVISOR_STATUS.json',dict(status='COMPLETE',updated_unix=time.time(),pid=os.getpid(),codex_independent=True))
if __name__=='__main__':
 import sys
 out=open(D/'wmi_supervisor.log','a',encoding='utf-8',buffering=1)
 err=open(D/'wmi_supervisor.stderr.log','a',encoding='utf-8',buffering=1)
 sys.stdout=out;sys.stderr=err
 try:main()
 except BaseException as e:
  target='B3_CONTINUATION_FAILURE.json' if (D/'GO.json').exists() else str(D.relative_to(H)/'DETACHED_LAUNCH_FAILURE.json')
  campaign.save(target,dict(error=repr(e),traceback=traceback.format_exc()))
  if (D/'GO.json').exists():campaign.save('SUPERVISOR_STATUS.json',dict(status='FAILED',error=repr(e),updated_unix=time.time(),pid=os.getpid()))
  raise

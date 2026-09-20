"""Resume a preserved M1 checkpoint after a machine restart, outside Codex."""
import os,sys,time,traceback
from pathlib import Path
import b3_resume_supervisor as c
from b3_detached_supervisor import in_job
H=c.H
R=Path(sys.argv[1]).absolute()
assert R.is_relative_to(H) and R.name.startswith('reboot_recovery_')
def save(name,value):c.save(str((R/name).relative_to(H)),value)
def main():
 assert not in_job(),'NOT_CODEX_INDEPENDENT'
 assert not(R/'STARTED.json').exists(),'DUPLICATE_RESTART'
 assert not(H/'SEARCH_CLOCK.json').exists(),'A1_CONTINUOUS_CLOCK_REQUIRES_SEPARATE_RECOVERY'
 assert c.read(H/'B3_M1/STARTED.json')['fleet']==6
 for r in c.read(R/'PRESERVATION_SHA.json')['files']:
  assert c.sha(r['path'])==c.sha(r['preserved_copy'])==r['sha256'],r['path']
 for manifest in ['INHERITED_SOURCE_FREEZE.json','B3_CONTINUATION_SOURCE_SHA.json']:
  for r in c.read(H/manifest)['files']:assert c.sha(r['path'])==r['sha256'],r['path']
 b2=c.read(c.F/'B2_ACTUAL_COMPLETE.json');assert b2['status']=='PASS'
 assert c.sha(b2['result']['path'])==b2['result']['sha256']
 save('STARTED.json',dict(pid=os.getpid(),unix=time.time(),in_windows_job=False,resume='Original M1 --resume with preserved stage/candidate cache',A1_started=False,A1_continuous_seconds=14400,source_sha256=c.sha(Path(__file__))))
 if not(H/'B3_M1/COMPLETE.json').exists():c.run('mess_worker.py','B3_M1','--resume')
 assert c.read(H/'B3_M1/COMPLETE.json')['status']=='PASS'
 c.run('a1_supervisor.py')
 c.run('mf_worker.py')
 c.run('b3_actual_shell.py')
 c.run('finalize_campaign_shell.py')
 c.save('SUPERVISOR_STATUS.json',dict(status='COMPLETE',updated_unix=time.time(),pid=os.getpid(),codex_independent=True))
 save('COMPLETE.json',dict(status='PASS',unix=time.time()))
if __name__=='__main__':
 sys.stdout=open(R/'supervisor.log','a',encoding='utf-8',buffering=1)
 sys.stderr=open(R/'supervisor.stderr.log','a',encoding='utf-8',buffering=1)
 try:main()
 except BaseException as e:
  failure=dict(error=repr(e),traceback=traceback.format_exc())
  save('FAILURE.json',failure);c.save('B3_CONTINUATION_FAILURE.json',failure)
  c.save('SUPERVISOR_STATUS.json',dict(status='FAILED',updated_unix=time.time(),pid=os.getpid(),error=repr(e)))
  raise

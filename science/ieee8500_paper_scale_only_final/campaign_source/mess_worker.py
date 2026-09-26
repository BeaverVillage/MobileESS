from bootstrap import *
from types import SimpleNamespace
import traceback
def main():
 started_wall=time.perf_counter()
 policy=sys.argv[1];assert policy in ('B2','B3_M1')
 resume='--resume' in sys.argv[2:]
 resume_active='--resume-active' in sys.argv[2:]
 resume_paper='--resume-paper-repair' in sys.argv[2:]
 assert sum((resume,resume_active,resume_paper))<=1
 if resume_paper:
  assert policy=='B2' and (H/policy/'STARTED.json').exists() and not(H/policy/'COMPLETE.json').exists()
  repair=read(H/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json')
  assert repair['status']=='PASS' and repair['same_fresh_paper_run_only']
  assert sha(H/'mess_runtime.py')==repair['current_runtime_sha256']
  save(H/policy/('RESUMED_PAPER_REPAIR_'+str(time.time_ns())+'.json'),dict(
      pid=os.getpid(),unix=time.time(),checkpoint_reuse=True,authority=record(H/'PAPER_PARENT_GUARD_REPAIR_AUTHORITY.json')))
 elif resume_active:
  assert policy=='B2'
  assert (H/policy/'STARTED.json').exists() and not(H/policy/'COMPLETE.json').exists()
  benchmark=read(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK.json')
  assert benchmark['status']=='BENCHMARK_COMPLETE' and benchmark['full_separation_closed']
  assert read(H/'CAMPAIGN_STATUS.json')['full_B2_restart_permitted']
  assert (H/'diagnostic_attempts/B2_FULL_MIP_STALL_20260920/SNAPSHOT.json').exists()
  save(H/policy/('RESUMED_ACTIVE_'+str(time.time_ns())+'.json'),dict(
      pid=os.getpid(),unix=time.time(),fleet=6,checkpoint_reuse=True,
      sparse_violated_row_benchmark=record(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK.json'),
      prior_dense_attempt_preserved=True))
 elif resume:
  assert (H/policy/'STARTED.json').exists() and not(H/policy/'COMPLETE.json').exists()
  assert read(H/'recovery_stall/NUMERICAL_REPAIR_PROOF.json')['status']=='PASS'
  save(H/policy/('RESUMED_'+str(time.time_ns())+'.json'),dict(pid=os.getpid(),unix=time.time(),fleet=6,checkpoint_reuse=True))
 else:
  if (H/policy/'STARTED.json').exists():
   failure=read(H/(policy+'_FAILURE.json'))
   assert 'NUMERICAL_REPAIR_PROOF.json' in failure['traceback']
   assert not(H/policy/'beam').exists() and not(H/policy/'FINAL_AUTHORITY.json').exists()
   save(H/policy/'STARTED_RETRY_02.json',dict(pid=os.getpid(),unix=time.time(),fleet=6,
       prior_preparation_failure=record(H/(policy+'_FAILURE.json'))))
  else:save(H/policy/'STARTED.json',dict(pid=os.getpid(),unix=time.time(),fleet=6))
 protect()
 import mess_runtime
 if resume:
  from numerical_repair import install
  install()
 path=H/'MAY01_B0_AIDC_POWER.npz' if policy=='B2' else H/'B1_REUSE/POWER.npz'
 with np.load(path) as z:pcc=z['pcc'].copy()
 state(status='RUNNING',stage=policy+':PREPARATION',search_started=False)
 selected=H/policy/'ORIGINAL_SELECTED_BEFORE_EXACT.json'
 primary=H/policy/'final_exact/AC_VALIDATION.json'
 if not selected.exists():
  try:trajectory,result=mess_runtime.search(SimpleNamespace(day='2025-05-01'),pcc,policy)
  except AssertionError:
   if not(selected.exists() and primary.exists() and read(primary)['status']=='FAIL'):raise
 if not(H/policy/'FINAL_AUTHORITY.json').exists():
  from dayahead.v40h.beam_driver import _restore_slots
  from dayahead.v33m.mess_trajectory import MessTrajectory
  from physical_closure import close
  result=read(selected);trajectory=MessTrajectory(tuple(_restore_slots(result['trajectory_slots'])))
  assert len(result['selected_state']['completed_vehicles'])==6
  ac=read(primary)
  if ac['status']=='FAIL':
   jobs=read(H/'REFERENCE_JOBS.json' if policy=='B2' else H/'B1_REUSE/JOBS.json')
   trajectory,ac,p1=close(policy,pcc,trajectory,jobs,record(primary))
  else:p1=result['planning']['rho']
  save(H/policy/'FINAL_AUTHORITY.json',dict(status='PASS',P1=p1,primary_planning_P1=result['planning']['rho'],AC=ac['metrics'],trajectory_slots=[r.to_dict() for r in trajectory.slots],original_selected=record(selected),primary_exact=record(primary),post_selection_physical_closure=read(primary)['status']=='FAIL',original_K_sequence=[200,400,800,'FULL'],original_beams=[2,4],worker_count=1))
 else:
  from dayahead.v40h.beam_driver import _restore_slots
  from dayahead.v33m.mess_trajectory import MessTrajectory
  trajectory=MessTrajectory(tuple(_restore_slots(read(H/policy/'FINAL_AUTHORITY.json')['trajectory_slots'])))
 assert {r.mess_id for r in trajectory.slots}==set(fleet_binding.IDS) and len(trajectory.slots)==576
 if policy=='B2':
  clean=exact(pcc,trajectory.slots,H/'B2/independent_clean_exact');assert clean['status']=='PASS'
  fresh=exact(pcc,trajectory.slots,H/'B2/Fresh');assert fresh['status']=='PASS'
 save(H/policy/'COMPLETE.json',dict(status='PASS',unix=time.time(),result=record(H/policy/'FINAL_AUTHORITY.json'),
      wall_seconds=time.perf_counter()-started_wall,Fresh=record(H/policy/'Fresh/AC_VALIDATION.json') if policy=='B2' else None))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/(sys.argv[1]+'_FAILURE.json'),dict(error=repr(e),traceback=traceback.format_exc()));raise

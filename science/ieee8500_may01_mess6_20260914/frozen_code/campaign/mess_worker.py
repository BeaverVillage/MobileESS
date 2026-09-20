from bootstrap import *
from types import SimpleNamespace
import traceback
def main():
 policy=sys.argv[1];assert policy in ('B2','B3_M1')
 resume='--resume' in sys.argv[2:]
 if resume:
  assert (H/policy/'STARTED.json').exists() and not(H/policy/'COMPLETE.json').exists()
  assert read(H/'recovery_stall/NUMERICAL_REPAIR_PROOF.json')['status']=='PASS'
  save(H/policy/('RESUMED_'+str(time.time_ns())+'.json'),dict(pid=os.getpid(),unix=time.time(),fleet=6,checkpoint_reuse=True))
 else:
  assert not(H/policy/'STARTED.json').exists()
  save(H/policy/'STARTED.json',dict(pid=os.getpid(),unix=time.time(),fleet=6))
 protect()
 import mess_runtime
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
 save(H/policy/'COMPLETE.json',dict(status='PASS',unix=time.time(),result=record(H/policy/'FINAL_AUTHORITY.json')))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/(sys.argv[1]+'_FAILURE.json'),dict(error=repr(e),traceback=traceback.format_exc()));raise

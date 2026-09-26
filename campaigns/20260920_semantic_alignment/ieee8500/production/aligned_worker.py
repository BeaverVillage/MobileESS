from bootstrap import *
import traceback
from pathlib import Path

def mess(role):
 from aligned_mess import bounded_run,load_worker_context,observe_candidate
 from dayahead.v40g_segments.canonical import import_frozen,planning_power
 from dayahead.v40h.recourse import validate_physics
 from dayahead.v33m.mess_trajectory import MessTrajectory
 from dayahead.v40h.beam_driver import _restore_slots
 start=time.time();ctx=load_worker_context('2025-05-01')
 jobs=import_frozen(ctx.reference if role=='B2' else read(P/'B1_REUSE/JOBS.json'))
 pcc=planning_power(import_frozen(jobs),ctx)['pcc'];out=P/role;out.mkdir(exist_ok=True)
 from aligned_mess import install_grid
 install_grid()
 trajectory,result=bounded_run(ctx,jobs,out,'B2' if role=='B2' else 'B3')
 physics=validate_physics(trajectory);assert physics['status']=='PASS'
 observation=observe_candidate(ctx,jobs,trajectory,out/'accepted_final','M1_FINAL')
 m1=dict(status='PLANNING_PASS',P1=result['planning']['rho_max'],jobs=jobs,trajectory_slots=[r.to_dict() for r in trajectory.slots],physics=physics,observation=observation,wall_seconds=time.time()-start,physical_closure_before_A2=False)
 save(out/'M1_AUTHORITY.json',m1);save(out/'FINAL_AUTHORITY.json',m1)
 if role=='B2':
  ac=exact(pcc,trajectory.slots,out/'primary_exact')
  if ac['status']!='PASS':
   from physical_closure import close
   trajectory,ac,p1=close('B2',pcc,trajectory,jobs,record(out/'primary_exact/AC_VALIDATION.json'))
   observation=observe_candidate(ctx,jobs,trajectory,out/'after_final_closure','FINAL_PHYSICAL_CLOSURE')
   save(out/'CLOSED_AUTHORITY.json',dict(status='PASS',P1=p1,trajectory_slots=[r.to_dict() for r in trajectory.slots],AC=ac,observation=observation))
  assert ac['status']=='PASS'
  fresh=exact(pcc,trajectory.slots,out/'Fresh');assert fresh['status']=='PASS'
  save(out/'FINAL_AUTHORITY.json',dict(status='PASS',P1=observation['approximate_rho'],jobs=jobs,trajectory_slots=[r.to_dict() for r in trajectory.slots],physics=validate_physics(trajectory),observation=observation,AC=fresh['metrics'],wall_seconds=time.time()-start))
 save(out/'COMPLETE.json',dict(status='PASS',stage='M1_PLANNING' if role!='B2' else 'B2_PLANNING_FRESH',wall_seconds=time.time()-start))

def mf():
 from aligned_mess import load_worker_context,recourse
 from dayahead.v40h.beam_driver import _restore_slots
 from dayahead.v33m.mess_trajectory import MessTrajectory
 from dayahead.v40g_segments.canonical import planning_power,import_frozen
 ctx=load_worker_context('2025-05-01');jobs=import_frozen(read(P/'B3_A1/FINAL_JOBS.json'));pcc=planning_power(jobs,ctx)['pcc']
 m1=MessTrajectory(tuple(_restore_slots(read(P/'B3_M1/FINAL_AUTHORITY.json')['trajectory_slots'])))
 out=P/'B3_MF';out.mkdir(exist_ok=True)
 selected,result,proof=recourse(ctx,jobs,pcc,m1,out)
 ac=exact(pcc,selected.slots,P/'B3/primary_exact')
 if ac['status']!='PASS':
  from physical_closure import close
  selected,ac,p1=close('B3',pcc,selected,jobs,record(P/'B3/primary_exact/AC_VALIDATION.json'))
  from aligned_mess import observe_candidate
  proof=observe_candidate(ctx,jobs,selected,P/'B3/after_final_closure','FINAL_PHYSICAL_CLOSURE')
 assert ac['status']=='PASS'
 fresh=exact(pcc,selected.slots,P/'B3/Fresh');assert fresh['status']=='PASS'
 save(P/'B3/FINAL_AUTHORITY.json',dict(status='PASS',jobs=jobs,P1=proof['approximate_rho'],trajectory_slots=[r.to_dict() for r in selected.slots],AC=fresh['metrics'],comparison=proof,M2=result))
 save(out/'COMPLETE.json',dict(status='PASS'))

def reuse_b0():
 from aligned_dependency_audit import verify as verify_b0
 verify_b0()
 with np.load(P/'MAY01_B0_AIDC_POWER.npz') as z:pcc=z['pcc']
 ac=exact(pcc,(),P/'B0_ALIGNED_REPLAY')
 expected=(.8996518400994494,.9535531871678895,1.0403443712992246)
 actual=tuple(ac['metrics'][k] for k in ('max_phase_line_loading_pu','Vmin_pu','Vmax_pu'))
 assert np.max(np.abs(np.array(actual)-expected))<1e-9
 save(P/'B0_REUSE_VERIFIED.json',dict(status='PASS',metrics=ac['metrics'],same_96_slot_coefficients=True,electrical_code_unchanged=True))

if __name__=='__main__':
 protect()
 try:
  role=sys.argv[1];began=time.time();state(status='RUNNING',stage=role,error=None)
  if role=='B0_VERIFY':reuse_b0()
  elif role in ('B2','B3_M1'):mess(role)
  elif role=='B3_MF':mf()
  else:
   from production_worker import aidc
   aidc(role)
  save(P/(role+'_RUNTIME.json'),dict(wall_seconds=time.time()-began,worker_pid=os.getpid(),threads=4))
  state(status='STAGE_COMPLETE',stage=role,error=None)
 except BaseException as exc:
  save(P/'failures'/f'{sys.argv[1]}_{time.time_ns()}.json',dict(error=repr(exc),traceback=traceback.format_exc()))
  save(P/(sys.argv[1]+'_ALIGNED_FAILURE.json'),dict(error=repr(exc),traceback=traceback.format_exc()))
  state(status='STOP' if (P/'SEMANTIC_ALIGNMENT_STOP.json').exists() else 'FAILED',stage=sys.argv[1],error=repr(exc))
  raise

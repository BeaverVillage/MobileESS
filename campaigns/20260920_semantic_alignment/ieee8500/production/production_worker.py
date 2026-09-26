"""One fresh policy worker; original full-day search and fixed infrastructure."""
from bootstrap import *
import traceback,shutil
def aidc(role):
 from evidence_path_binding import install as install_evidence_paths
 install_evidence_paths()
 from dayahead.v41r1.migration_factor import verify_gate
 verify_gate()
 print('ORIGINAL_EQUIVALENCE_GATE_PASS',flush=True)
 clock_binding()
 import aidc_runtime,grid8500
 from dayahead.v40a.grid import controls_from_trajectory
 from dayahead.v40g_segments.canonical import planning_power,import_frozen
 from dayahead.v40h.beam_driver import _restore_slots
 ctx=new_context();fixed=()
 if role=='B3_A1':
  reuse=read(H/'FINAL_B1_REUSE.json');jobs=read(reuse['jobs']['path']);power=planning_power(import_frozen(jobs),ctx)
  fixed=tuple(_restore_slots(read(H/'B3_M1/FINAL_AUTHORITY.json')['trajectory_slots']))
  ctx.v41_fixed_mess=fixed;ctx.v41_a1_seed_jobs=jobs;ctx.v41_a1_seed_pcc=power['pcc'];ctx.ieee8500_final_B1_seed=reuse['seed_bundle']
 else:
  jobs=ctx.reference;power=ctx.power
  with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z:assert np.max(abs(power['pcc']-z['pcc']))<1e-9
 seed=exact(power['pcc'],fixed,H/role/'seed_exact');assert role!='B1' or seed['status']=='PASS'
 state(status='RUNNING',stage=role+':FULL_ELECTRICAL_ROWS',search_started=False)
 prep=H/(role+'_electrical_rows');resume=H/(role+'_PREPARATION_RESUME.json')
 if prep.exists() and resume.exists():
  manifest=read(resume);assert manifest['status']=='PASS' and manifest['full_96_slot_current_run_only']
  for ref in manifest['files']:assert sha(ref['path'])==ref['sha256'] and Path(ref['path']).stat().st_size==ref['bytes'],ref['path']
  assert role=='B1' and not fixed and np.array_equal(power['pcc'],np.load(H/'MAY01_B0_AIDC_POWER.npz')['pcc'])
  with np.load(prep/'PCC_IMPLIED_BOUNDS.npz') as z:
   assert np.array_equal(z['lower'],np.array([[min(ctx.tables[s][t]) for s in ctx.capacity.aidc_ids] for t in range(96)]))
   assert np.array_equal(z['upper'],np.array([[max(ctx.tables[s][t]) for s in ctx.capacity.aidc_ids] for t in range(96)]))
  save(H/role/'PREPARATION_RESUME_VERIFIED.json',dict(status='PASS',manifest=record(resume),same_full_day_inputs=True,prior_search_seconds=0))
  print('FULL_DAY_ELECTRICAL_PREPARATION_REUSE_VERIFIED',flush=True)
 else:grid8500.prepare(ctx,prep,controls_from_trajectory(ctx.coefficients,power['pcc'],fixed))
 original=aidc_runtime.ProductionLex;engines=[]
 class Capture(original):
  def __init__(self,*a,**k):super().__init__(*a,**k);engines.append(self);assert self.model.Params.Threads==4
 aidc_runtime.ProductionLex=Capture
 result=aidc_runtime.run(ctx,role);engine=engines[-1]
 power=planning_power(import_frozen(result['jobs']),ctx);assert np.max(abs(power['pcc']-result['PCC']))<1e-9
 out=H/role;save(out/'FINAL_JOBS.json',result['jobs']);np.savez_compressed(out/'FINAL_POWER.npz',**power)
 np.savez_compressed(out/'FINAL_ASSIGNMENT.npz',values=engine.values);np.savez_compressed(out/'FINAL_VARIABLE_NAMES.npz',names=np.asarray(engine.names))
 fresh=exact(power['pcc'],fixed,out/'Fresh');assert role!='B1' or fresh['status']=='PASS'
 chosen=dict(status='INDEPENDENTLY_VALIDATED',jobs=record(out/'FINAL_JOBS.json'),power=record(out/'FINAL_POWER.npz'),power_is_physical=False,checkpoint=record(out/'FINAL_ASSIGNMENT.npz'),P1=result['grid']['rho_max'])
 if role=='B1':
  dest=H/'B1_REUSE';dest.mkdir(exist_ok=True)
  for src,n in [(out/'FINAL_JOBS.json','JOBS.json'),(out/'FINAL_POWER.npz','POWER.npz'),(out/'FINAL_ASSIGNMENT.npz','assignment.npz'),(out/'FINAL_VARIABLE_NAMES.npz','variable_names.npz')]:shutil.copyfile(src,dest/n)
  save(H/'FINAL_B1_REUSE.json',dict(status='PASS',source='This full production run only',jobs=record(dest/'JOBS.json'),power=record(dest/'POWER.npz'),seed_bundle=dict(status='FINAL_B1_INDEPENDENTLY_VALIDATED',candidate_stream_sha256=EXPECTED,binding_gate_sha256=sha(H/'IEEE8500_V41R4_AIDC_BINDING_PASS.json'),assignment=record(dest/'assignment.npz'),variable_names=record(dest/'variable_names.npz'))))
 else:save(H/'FOUR_HOUR_A1_INCUMBENT.json',chosen)
 save(out/'COMPLETE.json',dict(status='PASS',Actual=False,Fresh=record(out/'Fresh/AC_VALIDATION.json')))
def mess(policy):
 from types import SimpleNamespace
 import mess_runtime
 from dayahead.v40h.beam_driver import _restore_slots
 from dayahead.v33m.mess_trajectory import MessTrajectory
 from physical_closure import close
 path=H/('MAY01_B0_AIDC_POWER.npz' if policy=='B2' else 'B1_REUSE/POWER.npz')
 with np.load(path) as z:pcc=z['pcc'].copy()
 selected=H/policy/'ORIGINAL_SELECTED_BEFORE_EXACT.json';primary=H/policy/'final_exact/AC_VALIDATION.json'
 try:trajectory,result=mess_runtime.search(SimpleNamespace(day='2025-05-01'),pcc,policy)
 except AssertionError:
  if not(selected.exists() and primary.exists() and read(primary)['status']=='FAIL'):raise
  result=read(selected);trajectory=MessTrajectory(tuple(_restore_slots(result['trajectory_slots'])))
 ac=read(primary);p1=result['planning']['rho']
 if ac['status']=='FAIL':
  jobs=read(H/('REFERENCE_JOBS.json' if policy=='B2' else 'B1_REUSE/JOBS.json'))
  trajectory,ac,p1=close(policy,pcc,trajectory,jobs,record(primary))
 from dayahead.v40h.recourse import validate_physics
 physics=validate_physics(trajectory);assert physics['status']=='PASS'
 fresh=exact(pcc,trajectory.slots,H/policy/'Fresh');assert fresh['status']=='PASS'
 save(H/policy/'FINAL_AUTHORITY.json',dict(status='PASS',P1=p1,AC=ac['metrics'],trajectory_slots=[r.to_dict() for r in trajectory.slots],original_K_sequence=[200,400,800,'FULL'],original_beams=[2,4],worker_count=1,threads=4,physics=physics))
 save(H/policy/'COMPLETE.json',dict(status='PASS',Actual=False))
def main():
 protect()
 assert str(H).isascii(),'LAUNCH_WITH_EXISTING_ASCII_RUN_ALIAS'
 import gurobipy as gp
 gp.setParam('Threads',4)
 role=sys.argv[1];assert role in ('B1','B2','B3_M1','B3_A1','B3_MF');began=time.perf_counter()
 state(status='RUNNING',stage=role+':START',workers=1,threads=4)
 if role in ('B1','B3_A1'):aidc(role)
 elif role in ('B2','B3_M1'):mess(role)
 else:
  import mf_worker
  mf_worker.main()
 save(H/(role+'_RUNTIME.json'),dict(wall_seconds=time.perf_counter()-began,worker_pid=os.getpid(),threads=4,workers=1))
if __name__=='__main__':
 try:main()
 except BaseException as e:save(H/(sys.argv[1]+'_FAILURE.json'),dict(error=repr(e),traceback=traceback.format_exc()));raise

"""Exactly one fixed-order full-scale pair; no pricing or warm basis."""
from .common import *
from .persistent import FullScalePersistentRMP,sparse_identity
from .resources import Monitor,resource_failures
from v42_degen.identity import inputs
from v42_dw_root.partition import axes
from v42_dw_resume.audit import Master,prototypes,corrected_rows,pure_binary_equalities
import numpy as np,multiprocessing as mp

def build(B,e,owner,rows,native):
 start=time.perf_counter();m=Master(B,e,owner,rows,native)
 for directory,h in old_columns():
  unit=UNITS.index(h['MESS'])
  with np.load(directory/h['file']) as z:
   new='x' in z;x=z['x'] if new else z['local_values'];a=z['a'] if new else z['master_coefficients'];c=float(z['c'] if new else z['objective'])
  m.add(unit,x,a,c,h['SHA256'])
 assert len(m.lambdas)==1244
 return m,time.perf_counter()-start

def run():
 verify_freeze();assert read(OUT/'PRECG_REGRESSION.json')['PASS']
 with (OUT/'PERSISTENT_CANARY_STARTED.json').open('x') as f:json.dump(dict(preopt_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),prereg_SHA=sha(OUT/'DW_ACCELERATED_CG_PREREGISTRATION.json')),f)
 event=mp.get_context('spawn').Event();monitor=Monitor([],event)
 from .integration import Integration
 from types import SimpleNamespace
 probe=SimpleNamespace(monitor=monitor,pids=[])
 try:
  Integration.resource_gate(probe,'PERSISTENT_RMP_CANARY')
  A,d,B,e,*_=inputs();owner,rows=axes()
  with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
  blocks=prototypes(B,e,owner,rows,native);mask=pure_binary_equalities(A,d)
  retained,initialization=build(B,e,owner,rows,native);adapter=FullScalePersistentRMP(retained)
  results=[];points=[];intervals=[]
  for kind in ['cold_fresh','persistent']:
   Integration.resource_gate(probe,'PERSISTENT_RMP_CANARY');begin=time.perf_counter()
   if kind=='cold_fresh':master,buildwall=build(B,e,owner,rows,native)
   else:master=retained;buildwall=adapter.append(())
   model=master.model
   params=dict(Threads=1,Method=2,Crossover=1,LPWarmStart=0,PreDual=0,BarConvTol=1e-11,Seed=20260929,FeasibilityTol=EPS,IntFeasTol=EPS,OptimalityTol=EPS,TimeLimit=60)
   for k,v in params.items():model.setParam(k,v)
   identity=sparse_identity(model);model.Params.LogFile=(OUT.relative_to(ROOT)/('logs/CANARY_'+kind+'.log')).as_posix();monitor.phase='CANARY_'+kind
   model.reset(1 if kind=='cold_fresh' else 0);start=time.perf_counter();model.optimize(lambda m,w:m.terminate() if event.is_set() else None);end=time.perf_counter();intervals.append([start,end]);terminalwall=end-begin
   row=dict(kind=kind,status=model.Status,identity=identity,build_or_update_wall=buildwall,optimize_wall=end-start,total_paired_wall=terminalwall,settings=params,warm_basis_selected=False,solution_state_reset=True,reset_argument=1 if kind=='cold_fresh' else 0)
   if model.Status==2:
    x=np.array(model.getAttr('X'));pi=np.array(model.getAttr('Pi'));rc=np.array(model.getAttr('RC'));full=np.zeros(B.shape[1]);full[master.columns]=model.getAttr('X',master.z)
    for v,c in zip(master.lambdas,master.column_data):full[blocks[c['unit']].columns]+=v.X*c['x']
    post=corrected_rows(A,d,full,False,mask);raw=master.raw_audit();assert post['PASS'] and raw['PASS']
    file='CANARY_'+kind+'.npz';np.savez_compressed(OUT/file,x=x,pi=pi,rc=rc,original_point=full)
    row.update(objective=model.ObjVal,full_original_postsolve=post,master_audit=raw,point_file=file,point_SHA=sha(OUT/file),DualVio=model.DualVio,postsolve_wall=time.perf_counter()-end)
    points.append((x,pi))
   row['total_paired_wall']=time.perf_counter()-begin;results.append(row);print('FULLSCALE_CANARY',kind,row['status'],row.get('objective'),terminalwall,flush=True)
   if kind=='cold_fresh':master.model.dispose()
  mathematical=len(points)==2 and results[0]['identity']==results[1]['identity'];objdiff=abs(results[0]['objective']-results[1]['objective']) if len(points)==2 else None
  dualdiff=float(np.max(abs(points[0][1]-points[1][1]),initial=0)) if len(points)==2 else None;primaldiff=float(np.max(abs(points[0][0]-points[1][0]),initial=0)) if len(points)==2 else None
  reduction=1-results[1]['total_paired_wall']/results[0]['total_paired_wall'];correct=mathematical and objdiff<=EPS and dualdiff<=EPS and all(r['DualVio']<=EPS and r['full_original_postsolve']['PASS'] for r in results)
  selected=bool(correct and reduction>=.15 and not monitor.failed)
  reason='ALL_IDENTITY_NUMERICAL_AND_15_PERCENT_GATES_PASS' if selected else 'MATHEMATICAL_OR_POSTSOLVE_GATE_FAILED' if not correct else 'PAIRED_TOTAL_WALL_REDUCTION_BELOW_15_PERCENT' if reduction<.15 else 'RESOURCE_GATE_FAILED'
  write('DW_PERSISTENT_RMP_FULLSCALE_CANARY.json',dict(PASS=bool(correct),tested=True,pair_count=1,retained_columns=1244,persistent_initialization_wall=initialization,results=results,objective_difference=objdiff,dual_max_difference=dualdiff,primal_max_difference=primaldiff,paired_total_wall_reduction=reduction,initialization_excluded_from_steady_append_pair_but_reported=True,no_warm_basis=True,optimize_union=union_seconds(intervals),native_budget=122,resource=monitor.summary(monitor.rows)))
  assert union_seconds(intervals)<=122
  write('DW_PERSISTENT_RMP_SELECTION.json',dict(tested=True,selected=selected,reason=reason,minimum_wall_reduction=.15,observed_reduction=reduction,correctness_PASS=bool(correct),retest_allowed=False,warm_basis_selected=False))
  write('DW_RUNTIME_FEATURE_SELECTION.json',dict(early_stop_enabled=True,parallel_validation_enabled=True,incremental_audit_enabled=True,persistent_tested=True,persistent_selected=selected,persistent_reason=reason,activation_order=['EARLY_STOP','PARALLEL_VALIDATION','INCREMENTAL_AUDIT'],regression_SHA=sha(OUT/'PRECG_REGRESSION.json'),warm_basis_selected=False,frozen_before_CG=True))
  retained.model.dispose()
 finally:monitor.close()
if __name__=='__main__':run()

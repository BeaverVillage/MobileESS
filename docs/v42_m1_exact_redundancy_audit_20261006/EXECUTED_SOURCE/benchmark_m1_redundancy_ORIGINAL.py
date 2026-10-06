"""One preregistered sequential original/reduced monolithic comparison."""
import time,threading,math,json,traceback,subprocess,gc,re,os
from datetime import datetime,timezone
import numpy as np
import gurobipy as gp
import psutil
from v42_degen.identity import inputs,signature
from v42_degen.common import POLICY
from v42_one_tree_bc.audit import Validator
from v42_rowgen.native import transport_audit
from v42_m1_accel_vnext.native_state import inspect_live
from v42_dw_continuation.resources import WindowsCounters
from v42_redundancy.common import *
from v42_redundancy.model import build

NATIVE_SECONDS=270
ARM_WALL_SECONDS=300
def read(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def finite(x):return float(x) if math.isfinite(x) and abs(x)<1e90 else None
def safe_bound(v):
 v=finite(v);return None if v is None else float(np.nextafter(v-1e-8,-np.inf))
def gap(ub,lb):return max(0.,ub-lb)/max(abs(ub),1e-10)
def parameters(m):
 result={}
 for name in dir(m.Params):
  if name.startswith('_'):continue
  try:
   info=m.getParamInfo(name)
   if info is not None:result[name]=info[2]
  except (gp.GurobiError,AttributeError):pass
 assert all(k in result for k in ['Threads','Seed','MIPGap','Method','Presolve','Cuts','Heuristics','MIPFocus','FeasibilityTol','OptimalityTol','IntFeasTol'])
 return result

class Resource:
 def __init__(self):self.rows=[];self.phase='common';self.origin=time.perf_counter();self.stop=threading.Event()
 def sample(self):
  p=psutil.Process();m=p.memory_info();v=psutil.virtual_memory()
  return dict(UTC=datetime.now(timezone.utc).isoformat(),wall=time.perf_counter()-self.origin,arm=self.phase,RSS=m.rss,process_commit=getattr(m,'pagefile',None),free_RAM=v.available,**self.windows.sample())
 def worker(self):
  self.windows=WindowsCounters()
  try:
   while not self.stop.is_set():self.rows.append(self.sample());self.stop.wait(.5)
   self.rows.append(self.sample())
  finally:self.windows.close()
 def start(self):self.thread=threading.Thread(target=self.worker,daemon=True);self.thread.start()
 def close(self):self.stop.set();self.thread.join(timeout=3);table('M1_REDUNDANCY_RESOURCE_LEDGER.csv',self.rows,list(self.rows[0]))

def resource_gate(label):
 rows,blocked=inspect_live();write('M1_RESOURCE_GATE_'+label+'.json',dict(PASS=not blocked,processes=rows,blocked=blocked,result_dependent_fleet_outputs_read=False,source_read_scope='Only AST call-site witness for live native solve detection.'))
 if blocked:raise RuntimeError('BENCHMARK_DEFERRED_RESOURCE_CONFLICT')

def arm(label,B,e,keep,validator,seed,initial_lb,memory):
 begin=time.perf_counter();memory.phase=label;deadline=begin+ARM_WALL_SECONDS
 resource_gate(label+'_BEFORE_BUILD');t=time.perf_counter();m=build(B,e,keep);buildwall=time.perf_counter()-t
 settings=dict(POLICY,TimeLimit=NATIVE_SECONDS,PreCrush=1,LazyConstraints=0)
 for k,v in settings.items():m.setParam(k,v)
 m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.LogFile=str(OUT/('M1_REDUNDANCY_'+label+'.log'))
 transport=transport_audit(m,B,e,keep)
 assert np.array_equal(np.asarray(m.getAttr('VarName')),e['names']) and np.array_equal(np.asarray(m.getAttr('ConstrName')),e['row_names'][keep])
 params=parameters(m);variables=m.getVars();m.setAttr('Start',variables,seed.tolist())
 ub=float(e['objective']@seed+float(e['constant']));lb=initial_lb;best=seed.copy();first_native=None;first_valid=None;candidate_records=[];progress=[];errors=[];messages=[];last=-1.
 def callback(model,where):
  nonlocal ub,lb,best,first_native,first_valid,last
  try:
   elapsed=time.perf_counter()-begin
   if where==gp.GRB.Callback.MESSAGE:messages.append(model.cbGet(gp.GRB.Callback.MSG_STRING));return
   if where==gp.GRB.Callback.MIPSOL:
    if first_native is None:first_native=elapsed
    x=np.asarray(model.cbGetSolution(variables));r=validator(x);when=time.perf_counter()-begin
    candidate_records.append(dict(native_time=elapsed,audit_completed_time=when,raw_objective=float(model.cbGet(gp.GRB.Callback.MIPSOL_OBJ)),PASS=r['PASS'],independent_objective=r['objective'],audit=r))
    if r['PASS']:
     if first_valid is None:first_valid=when
     if r['objective']<ub:ub=r['objective'];best=x.copy()
   if where==gp.GRB.Callback.MIP and elapsed-last>=1.:
    raw=finite(model.cbGet(gp.GRB.Callback.MIP_OBJBND));b=safe_bound(raw) if raw is not None else None
    if b is not None:
     if b>ub+1e-8:raise RuntimeError('NATIVE_BOUND_EXCEEDS_VALID_UB')
     lb=max(lb,b)
    progress.append(dict(arm=label,arm_wall=elapsed,raw_native_BestBd=raw,valid_LB=lb,valid_UB=ub,gap=gap(ub,lb),nodes=float(model.cbGet(gp.GRB.Callback.MIP_NODCNT))))
    last=elapsed
   if time.perf_counter()>=deadline-5:model.terminate()
  except BaseException:errors.append(traceback.format_exc());model.terminate()
 resource_gate(label+'_BEFORE_OPTIMIZE')
 timer=threading.Timer(max(.001,deadline-time.perf_counter()-5),m.terminate);timer.daemon=True;timer.start()
 print('ARM_START',label,'rows',m.NumConstrs,'nnz',m.NumNZs,'native_limit',NATIVE_SECONDS,flush=True)
 native_begin=time.perf_counter()
 try:
  m.optimize(callback)
  optimize_wall=time.perf_counter()-native_begin
  rawbd=finite(m.ObjBound);b=safe_bound(m.ObjBound)
  if b is not None:
   if b>ub+1e-8:errors.append('FINAL_BOUND_EXCEEDS_VALID_UB')
   else:lb=max(lb,b)
  terminal=None
  if m.SolCount:
   point=np.asarray(m.getAttr('X'));terminal=validator(point);np.savez_compressed(OUT/('M1_REDUNDANCY_'+label+'_RAW_POINT.npz'),point=point)
   if terminal['PASS'] and terminal['objective']<ub:ub=terminal['objective'];best=point.copy()
  final=validator(best);assert final['PASS'];np.savez_compressed(OUT/('M1_REDUNDANCY_'+label+'_VALID_POINT.npz'),point=best)
  log=''.join(messages);root=re.search(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',log);presolved=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
  sampled=[r for r in memory.rows if r['arm']==label];wall=time.perf_counter()-begin
  if wall>ARM_WALL_SECONDS+.5:errors.append('ARM_WALL_CAP_EXCEEDED')
  if m.Status not in [2,9,11]:errors.append('UNEXPECTED_NATIVE_STATUS:'+str(m.Status))
  result=dict(arm=label,executed=True,optimize_calls=1,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),settings=settings,all_native_parameters=params,build_wall=buildwall,rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,continuous=int(np.sum(e['types']=='C')),nnz=m.NumNZs,transport=transport,
   presolved=dict(rows=int(presolved[1]),columns=int(presolved[2]),nnz=int(presolved[3])) if presolved else None,
   root_completed=bool(root),root_time=float(root[3]) if root else None,root_objective_rounded=float(root[1]) if root else None,root_iterations=int(root[2]) if root else None,
   raw_native_BestBd=rawbd,valid_global_LB=lb,valid_UB=ub,valid_global_gap=gap(ub,lb),initial_valid_UB=float(e['objective']@seed+float(e['constant'])),initial_valid_LB=initial_lb,first_native_incumbent=first_native,first_independently_valid_incumbent=first_valid,initial_independently_valid_start_time=0.,node_count=m.NodeCount,LP_iterations=m.IterCount,barrier_iterations=m.BarIterCount,Gurobi_Work=m.Work,native_runtime=m.Runtime,optimize_wall=optimize_wall,total_arm_wall=wall,
   peak_RSS=max((r['RSS'] for r in sampled),default=None),peak_process_commit=max((r['process_commit'] for r in sampled),default=None),minimum_free_RAM=min((r['free_RAM'] for r in sampled),default=None),peak_system_commit_percent=max((r['commit_percent'] for r in sampled if r['commit_percent'] is not None),default=None),native_status=m.Status,native_SolCount=m.SolCount,raw_native_UB=finite(m.ObjVal) if m.SolCount else None,valid_final_full_original_audit=final,terminal_native_point_audit=terminal,candidates=candidate_records,progress=progress,errors=errors,PASS=not errors,benchmark_native_cap=NATIVE_SECONDS,benchmark_arm_wall_cap=ARM_WALL_SECONDS,native_bound_safety='Raw BestBd is verbatim; valid native contribution subtracts inherited 1e-8 and rounds downward before combining same inherited full-domain LB.',sampled_memory_peaks_not_exact=True)
  write('M1_REDUNDANCY_'+('BASELINE' if label=='ORIGINAL' else 'REDUCED')+'_RESULT.json',result)
  print('ARM_END',label,'root',bool(root),'LB',lb,'UB',ub,'gap',gap(ub,lb),'work',m.Work,'runtime',m.Runtime,'errors',errors,flush=True)
  return result
 finally:timer.cancel();m.dispose();gc.collect()

def run():
 resource_gate('PREFLIGHT');assert read('M1_FINAL_REDUCTION_CENSUS.json')['materiality_gate']
 for n in ['M1_INDEPENDENT_CERTIFICATE_REPLAY.json','M1_REDUNDANCY_FIXTURE_RESULTS.json','M1_REDUNDANCY_ADVERSARIAL_RESULTS.json']:assert read(n)['PASS']
 assert not subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip(),'FREEZE_TRACKED_SOURCE_BEFORE_BENCHMARK'
 with (OUT/'M1_BENCHMARK_ONCE.json').open('x',encoding='utf-8') as f:json.dump(dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),maximum_comparisons=1,native_seconds=NATIVE_SECONDS,arm_wall_seconds=ARM_WALL_SECONDS,pid=os.getpid()),f)
 A,d,B,e,identity,_=inputs();validator=Validator(A,d)
 seedpath=ROOT/'docs/v42_m1_exact_grid_rowgen_20261006/A_BASELINE_FINAL_VALID_POINT.npz'
 with np.load(seedpath) as z:seed=z['point'].copy()
 seedcheck=validator(seed);assert seedcheck['PASS']
 parent=ROOT/'docs/v42_m1_one_tree_bc_20261006/M1_ONE_TREE_BC_INPUT_FREEZE.json';lb=json.loads(parent.read_text())['inherited_full_domain_LB']
 with np.load(OUT/'M1_REDUCTION_AXES.npz') as z:keep=z['keep']
 write('M1_BENCHMARK_EXECUTION_FREEZE.json',dict(base=BASE,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),source_files={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [ROOT/'benchmark_m1_redundancy.py',ROOT/'v42_redundancy/model.py',ROOT/'v42_one_tree_bc/audit.py']},scientific_identity=identity,scientific_signature=signature(B,e),start_file=str(seedpath.relative_to(ROOT)),start_SHA=sha(seedpath),start_full_original_validation=seedcheck,initial_LB=lb,LB_provenance_file=str(parent.relative_to(ROOT)),LB_provenance_SHA=sha(parent),POLICY=dict(POLICY,TimeLimit=NATIVE_SECONDS,PreCrush=1,LazyConstraints=0),sequential=True,no_row_generation_or_separation_callbacks=True,callback_scope='Read-only bounds/incumbent audits and bounded wall termination only. No constraint additions/cuts/lazy rows/pricing.'))
 memory=Resource();memory.start();begin=time.perf_counter()
 try:
  original=arm('ORIGINAL',B,e,np.arange(B.shape[0]),validator,seed,lb,memory)
  assert original['PASS'],'BASELINE_EXECUTION_FAILED'
  reduced=arm('REDUCED',B,e,keep,validator,seed,lb,memory)
 finally:memory.close()
 # Only LogFile differs between native parameter payloads; all scientific,
 # numerical and optimization settings including TimeLimit are identical.
 pa={k:v for k,v in original['all_native_parameters'].items() if k!='LogFile'};pb={k:v for k,v in reduced['all_native_parameters'].items() if k!='LogFile'};assert pa==pb
 root_gate=bool(original['root_completed'] and reduced['root_completed'] and original['root_time'] and reduced['root_time']<=.85*original['root_time'])
 # Work at an unfinished root is not matched solved work, so cannot justify
 # selection merely from its numerical decrease.
 bound_gate=bool(reduced['valid_global_LB']>original['valid_global_LB']+.001 and reduced['valid_global_gap']<original['valid_global_gap']-.001 and reduced['native_runtime']<=original['native_runtime']+2)
 transition=bool(not original['root_completed'] and reduced['root_completed'] and reduced['node_count']>1)
 selected=bool(original['PASS'] and reduced['PASS'] and (root_gate or bound_gate or transition))
 final='EXACT_REDUNDANCY_REDUCTION_SELECTED' if selected else 'EXACT_REDUNDANCY_PROVEN_BUT_NO_SPEEDUP'
 write('M1_REDUNDANCY_COMPARISON.json',dict(PASS=original['PASS'] and reduced['PASS'],final_state=final,EXACT_REDUNDANCY_REDUCTION_SELECTED=selected,identical_all_solver_parameters_except_LogFile=True,compared_parameter_count=len(pa),sequential=True,concurrent_heavy_solves=False,arms=['ORIGINAL','REDUCED'],root_time_gate=root_gate,valid_LB_gap_gate=bound_gate,beyond_root_transition_gate=transition,memory_only_selection=False,unmatched_unfinished_root_Work_used_for_selection=False,original_root_completed=original['root_completed'],reduced_root_completed=reduced['root_completed'],original_root_time=original['root_time'],reduced_root_time=reduced['root_time'],original_UB=original['valid_UB'],reduced_UB=reduced['valid_UB'],original_LB=original['valid_global_LB'],reduced_LB=reduced['valid_global_LB'],original_gap=original['valid_global_gap'],reduced_gap=reduced['valid_global_gap'],original_peak_RSS=original['peak_RSS'],reduced_peak_RSS=reduced['peak_RSS'],original_Work=original['Gurobi_Work'],reduced_Work=reduced['Gurobi_Work'],original_native_runtime=original['native_runtime'],reduced_native_runtime=reduced['native_runtime'],combined_arm_wall=time.perf_counter()-begin,optional_second_benchmark=False,production=False,STOP=True))
 print('BENCHMARK_COMPLETE',final,'selected',selected,flush=True)
if __name__=='__main__':
 try:run()
 except BaseException:write('M1_BENCHMARK_EXECUTION_ERROR.json',dict(traceback=traceback.format_exc()));raise

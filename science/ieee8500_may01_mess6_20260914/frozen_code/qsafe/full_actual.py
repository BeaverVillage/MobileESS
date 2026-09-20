"""Restart B2 Actual from frozen inputs using the same validated shell core."""
from runtime import *
import shutil,traceback
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
sys.path.insert(0,str(H/'shared'))
from qsafe_shell import correct_slot
def worker_init():
 global DATA
 DATA=data()
def worker_replay(task):
 slot,index,q,prefix,hashes,taps=task;check_stop()
 e=Electrical(H/f'B2/parallel_trials/slot_{slot:02}/{index:06}',DATA)
 try:
  for s in range(slot+1):
   r=e.apply(s,q if s==slot else prefix[s])
   if s<slot:assert hashlib.sha256(r['v'].tobytes()).hexdigest()==hashes[s] and r['taps']==taps[s],('ACCEPTED_PREFIX_DRIFT',slot,index,s)
  return r
 finally:e.close()
class Batch:
 def __init__(self,t,prefix,accepted):
  self.t=t;self.prefix=np.asarray(prefix).copy();self.hashes=[hashlib.sha256(r['v'].tobytes()).hexdigest() for r in accepted];self.taps=[r['taps'] for r in accepted];self.count=0;self.trials=[]
 def many(self,qs):
  tasks=[(self.t,self.count+i,q,self.prefix,self.hashes,self.taps) for i,q in enumerate(qs)]
  values=list(POOL.map(worker_replay,tasks));self.count+=len(tasks)
  for task,r in zip(tasks,values):self.trials.append(dict(index=task[1],Q=task[2],feasible=feasible(r),Vmin=float(r['v'].min()),Vmax=float(r['v'].max()),line=float(r['line'].max()),transformer_current=float(r['tx'].max()),transformer_kVA=float(r['kva'].max()),start_taps=self.taps[-1] if self.taps else None,final_taps=r['taps'],final_caps=r['caps']))
  save(H/f'B2/SHELL_TRIALS/slot_{self.t:02}.json',dict(full_chronological=True,trials=self.trials,AC_solves=self.count*(self.t+1)))
  return values
def bound(evaluate,q0,lo,hi,q_da=None,**kw):
 return correct_slot(evaluate,q0,lo,hi,q_da=q_da,rules=RULES,feasible=feasible,constraints=constraints,progress=lambda v:state(status='RUNNING',stage='B2_ACTUAL_SHELL_QSAFE',**v),**kw)
def main():
 global POOL
 assert read(H/'SLOT_RESULT.json')['status']=='IEEE8500_QSAFE_V2_SEARCH_PASS'
 assert not(H/'B2').exists(),'NEW_NAMESPACE_ALREADY_STARTED'
 folder=H/'B2';folder.mkdir()
 names=['ACTUAL_INPUTS.npz','ACTUAL_MESS_AUDIT.json','ACTUAL_MESS_TIMESERIES.parquet','ACTUAL_AIDC_POWER.npz','FROZEN_MESS_COMMANDS.json','ACTUAL_EXECUTION_FEASIBILITY.json','ACTUAL_EXECUTION_DELAY_KPIS.json','ACTUAL_EXECUTION_RATE.json','POWER_AUDIT.json','INPUT_READY.json']
 for name in names:shutil.copyfile(BASE/'actual_B2/B2'/name,folder/name)
 save(H/'ACTUAL_RULE_FREEZE.json',dict(version='QSAFE_V2_LEGACY_EXACT_DEVIATION_SHELL_V1',date='2025-05-01',policy='B2',scope='Frozen input reuse; only QSAFE search changes',files=[rec(BASE/'B2/FINAL_AUTHORITY.json'),rec(H/'shared/qsafe_shell.py'),rec(Path(__file__))]+[rec(folder/name) for name in names],target_slot_validation=rec(H/'SLOT_RESULT.json'),checkpoint_evaluator_prohibited=True,B3_promotion_requires_B2_full_PASS=True))
 import actual_binding
 ns=dict(correct_slot=bound,q_bounds=q_bounds,feasible=feasible,independent_audit=actual_binding.independent_audit)
 text=source.read_text(encoding='utf-8');node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='run_policy')
 run_source=ast.get_source_segment(text,node).replace('2025-05-21','2025-05-01').replace("W/'IEEE8500_numerical_preflight_20260911/AXES.json'","BASE/'AXES.json'").replace("H/'RULE_FREEZE.json'","H/'ACTUAL_RULE_FREEZE.json'")
 old="qt,r,event=ns['correct_slot'](evaluate,q[t],lo,hi,q_da=data['Q_DA'][t]);q[t]=qt;accepted.append(r);event.update"
 new="batch=Batch(t,q[:t],accepted)\n   qt,r,event=ns['correct_slot'](evaluate,q[t],lo,hi,q_da=data['Q_DA'][t],evaluate_many=batch.many)\n   engine_count+=batch.count;solve_count+=batch.count*(t+1)\n   trials.extend(dict(slot=t,prefix_max_slot=t,parallel=True,**item) for item in batch.trials)\n   q[t]=qt;accepted.append(r);event.update"
 assert run_source.count(old)==1;run_source=run_source.replace(old,new)
 scope=dict(globals());exec(compile(run_source,str(source)+'::shell_only','exec'),scope)
 with ProcessPoolExecutor(max_workers=4,mp_context=get_context('spawn'),initializer=worker_init) as POOL:
  scope['run_policy']('B2',ns,AUTH)
 complete=read(folder/'COMPLETE.json')
 for r in read(H/'ACTUAL_RULE_FREEZE.json')['files']:assert sha(r['path'])==r['sha256'],r['path']
 save(H/'B2_ACTUAL_COMPLETE.json',dict(status='PASS' if complete['AC_feasible'] else 'FAIL',result=rec(folder/'COMPLETE.json'),B3_promoted=False))
 state(status='PASS' if complete['AC_feasible'] else 'FAIL',stage='B2_ACTUAL_COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as error:save(H/'ACTUAL_FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc()));state(status='FAILED',stage='B2_ACTUAL_FAILURE');raise

"""Original B3 Actual with the validated shared QSAFE shell search and full replay."""
import sys, os, time, uuid, ast, hashlib, traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
BASE=Path(__file__).absolute().parent
F=BASE.parent/'IEEE8500_QSAFE_V2_LEGACY_SHELL_20260913'
sys.argv=[str(BASE/'actual_worker.py'),'B3']
import actual_worker as w
sys.path.insert(0,str(F/'shared'))
from qsafe_shell import correct_slot
CORE=F/'shared/qsafe_shell.py'
assert w.sha(CORE)=='04448962bf46b33a15c6350aecd7ac3bd6efe763d1e910e924c5f682a0f39865'
RULES=w.read(w.METHOD/'METHOD_FREEZE.json')['search']
ORIGINAL_KERNEL=w.kernel
def save(p,value):
 p=Path(p);assert p.absolute().is_relative_to(w.H)
 if p==w.H/'RULE_FREEZE.json':
  value=dict(value,QSAFE='Validated common deviation-shell search; legacy full chronological exact replay; no cap; separate existing local refinement',parallel_contexts=4)
  value['source_files']=list(value['source_files'])+[w.rec(Path(__file__)),w.rec(CORE)]
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
 tmp.write_text(w.json.dumps(w.clean(value),indent=2),encoding='utf-8')
 for attempt in range(101):
  try:os.replace(tmp,p);return
  except PermissionError:
   if attempt==100:raise
   time.sleep(.05)
w.save=save
def worker_init():
 global DATA
 with w.np.load(w.H/'B3/ACTUAL_INPUTS.npz') as z:DATA={k:z[k].copy() for k in z.files}
def worker_replay(task):
 slot,index,q,prefix,hashes,taps=task
 e=w.Electrical(w.H/f'B3/parallel_trials/slot_{slot:02}/{index:06}',DATA)
 try:
  for s in range(slot+1):
   r=e.apply(s,q if s==slot else prefix[s])
   if s<slot:assert hashlib.sha256(r['v'].tobytes()).hexdigest()==hashes[s] and r['taps']==taps[s],('ACCEPTED_PREFIX_DRIFT',slot,index,s)
  return r
 finally:e.close()
class Batch:
 def __init__(self,t,prefix,accepted):
  self.t=t;self.prefix=w.np.asarray(prefix).copy();self.hashes=[hashlib.sha256(r['v'].tobytes()).hexdigest() for r in accepted];self.taps=[r['taps'] for r in accepted];self.count=0;self.trials=[]
 def many(self,qs):
  tasks=[(self.t,self.count+i,q,self.prefix,self.hashes,self.taps) for i,q in enumerate(qs)]
  values=list(POOL.map(worker_replay,tasks));self.count+=len(tasks)
  for task,r in zip(tasks,values):self.trials.append(dict(index=task[1],Q=task[2],feasible=NS['feasible'](r),Vmin=float(r['v'].min()),Vmax=float(r['v'].max()),line=float(r['line'].max()),transformer_current=float(r['tx'].max()),transformer_kVA=float(r['kva'].max()),start_taps=self.taps[-1] if self.taps else None,final_taps=r['taps'],final_caps=r['caps']))
  save(w.H/f'B3/SHELL_TRIALS/slot_{self.t:02}.json',dict(full_chronological=True,trials=self.trials,AC_solves=self.count*(self.t+1)))
  return values
def bound(evaluate,q0,lo,hi,q_da=None,**kw):
 return correct_slot(evaluate,q0,lo,hi,q_da=q_da,rules=RULES,feasible=NS['feasible'],constraints=NS['constraints'],progress=lambda v:w.state(status='RUNNING',stage='B3_ACTUAL_SHELL_QSAFE',**v),**kw)
def kernel():
 global NS
 NS=ORIGINAL_KERNEL();NS['correct_slot']=bound
 return NS
w.kernel=kernel
source=w.source.read_text(encoding='utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='run_policy')
run_source=ast.get_source_segment(source,node).replace('2025-05-21','2025-05-01').replace("W/'IEEE8500_numerical_preflight_20260911/AXES.json'","BASE/'AXES.json'")
old="qt,r,event=ns['correct_slot'](evaluate,q[t],lo,hi,q_da=data['Q_DA'][t]);q[t]=qt;accepted.append(r);event.update"
new="batch=Batch(t,q[:t],accepted)\n   qt,r,event=ns['correct_slot'](evaluate,q[t],lo,hi,q_da=data['Q_DA'][t],evaluate_many=batch.many)\n   engine_count+=batch.count;solve_count+=batch.count*(t+1)\n   trials.extend(dict(slot=t,prefix_max_slot=t,parallel=True,**item) for item in batch.trials)\n   q[t]=qt;accepted.append(r);event.update"
assert run_source.count(old)==1
w.Batch=Batch
exec(compile(run_source.replace(old,new),str(w.source)+'::B3_shell_only','exec'),w.__dict__)
def main():
 global POOL
 with ProcessPoolExecutor(max_workers=4,mp_context=get_context('spawn'),initializer=worker_init) as POOL:w.main()
 result=w.read(w.H/'B3/COMPLETE.json')
 assert result['AC_feasible'] and result['independent_replay_PASS'] and result['ROBUST_Q_ONLY_UNRESOLVED_slots']==0
if __name__=='__main__':
 try:main()
 except BaseException as e:
  save(w.H/'FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise

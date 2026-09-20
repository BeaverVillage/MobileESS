"""Actual legacy-runner binding and four-resource contract; production calls=0."""
import ast,json,hashlib,types,sys
from pathlib import Path
import numpy as np
from activate import activate
from qsafe_shell import coarse_shells
H=Path(__file__).absolute().parent
LEGACY=H.parent/'v41r4_actual_snapshot/robust_v2'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
source=LEGACY/'frozen_code/qsafe.py'
before=sha(source)
text=source.read_text(encoding='utf-8');tree=ast.parse(text)
legacy=types.ModuleType('ieee123_qsafe_preflight')
legacy.__dict__.update(np=np,HARD_TOLERANCE=1e-9)
for node in tree.body:
 if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in ('q_bounds','constraints','feasible','PrefixEngine','run_qsafe'):
  code=ast.get_source_segment(text,node)
  if node.name=='run_qsafe':
   code=code.replace('def run_qsafe(context,voltage,trajectory,connected,authority,folder):','def run_qsafe(context,voltage,trajectory,connected,authority,folder,q_da=None):')
   code=code.replace('initialq=trajectory.mess_q_kvar.copy();fixedp=trajectory.mess_p_kw.copy();fixedaidc=trajectory.pcc_p_kw.copy()','initialq=trajectory.mess_q_kvar.copy();fixedp=trajectory.mess_p_kw.copy();fixedaidc=trajectory.pcc_p_kw.copy();reference=initialq.copy() if q_da is None else np.asarray(q_da).copy()')
   code=code.replace('correct_slot(lambda q:e.evaluate(t,q),initialq[t],lo,hi)','correct_slot(lambda q:e.evaluate(t,q),initialq[t],lo,hi,q_da=reference[t])')
   code=code.replace('Q_ONLY_INFEASIBLE','ROBUST_Q_ONLY_UNRESOLVED')
  exec(compile(code,str(source),'exec'),legacy.__dict__)
method=read(LEGACY/'METHOD_FREEZE.json');legacy.RULES=method['search']
runner=legacy.run_qsafe;engine=legacy.PrefixEngine;bounds=legacy.q_bounds
worker=types.SimpleNamespace(run_qsafe=runner)
report=activate(legacy,worker)
assert worker.run_qsafe.__code__ is runner.__code__
assert worker.run_qsafe.__globals__['PrefixEngine'] is engine and legacy.q_bounds is bounds
a=types.SimpleNamespace(pcs_kva=400,pcs_polygon_faces=16,active_power_limit_kw=300)
p=np.zeros(4);connected=np.ones(4,dtype=bool);lo,hi=legacy.q_bounds(p,connected,a)
count=sum(len(qs) for _,qs in coarse_shells(lo,hi,np.zeros(4),legacy.RULES['coarse_grid']['unit_coordinates']))
assert count==625
q0=np.zeros(4)
def evaluate(q):return dict(v=np.array([1.]),ipu=np.array([.5]),kva=np.array([.5]),taps=[0],converged=True)
q,r,event=legacy.correct_slot(evaluate,q0,lo,hi,q_da=q0)
assert len(q)==4 and event['status']=='UNCHANGED'
shared=H.parents[3]/'independent_screening/IEEE8500_QSAFE_V2_LEGACY_SHELL_20260913/shared/qsafe_shell.py'
assert sha(H/'qsafe_shell.py')==sha(shared) and sha(source)==before
report.update(status='IEEE123_QSAFE_V2_SHELL_BINDING_PREFLIGHT_PASS',fleet=4,coarse_domain=625,shared_core_sha256=sha(shared),source= str(source),source_sha256=before,legacy_full_prefix_engine_unchanged=True,legacy_runner_bytecode_unchanged=True,actual_physical_engine_executions=0,production_execution_started=False,activation='activate.activate(robust_search_module, frozen_worker_module)',new_mapping_full_campaign_readiness='Existing electrical/input release gate still required before production')
(H/'PREFLIGHT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))

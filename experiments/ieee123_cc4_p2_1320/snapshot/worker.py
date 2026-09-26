from pathlib import Path
import os,sys,json,time,traceback,types,hashlib,inspect,textwrap,shutil
ROOT=Path(__file__).parent
DAY=sys.argv[1];PHASE=sys.argv[2]
CASE=ROOT/'days'/DAY
CASE.mkdir(parents=True,exist_ok=True)
os.environ['ABLATION_CASE_ROOT']=str(CASE)
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['GIT_OPTIONAL_LOCKS']='0'
os.environ['OMP_NUM_THREADS']=os.environ['MKL_NUM_THREADS']=os.environ['OPENBLAS_NUM_THREADS']='4'
import runtime_environment as env
env.WRITE_ROOTS=tuple(env.norm(p) for p in (CASE,CASE.resolve(),Path('D:/c5')))
# Path.resolve routing must retain the case suffix rather than map to namespace root.
env.ROOT=CASE
# Authority files and source loader are read-only shared; all writes are date-owned.
original_seed=env.seed_aliases
def aliases():
 env.ROOT=ROOT
 try:original_seed()
 finally:env.ROOT=CASE
env.seed_aliases=aliases
original_find=env.SourceFinder.find_spec
def find(self,*a,**kw):
 env.ROOT=ROOT
 try:return original_find(self,*a,**kw)
 finally:env.ROOT=CASE
env.SourceFinder.find_spec=find
env.install('ACTUAL' if PHASE=='ACTUAL' else 'DA')
# Numeric recovery contract is immutable and verified independently.
import authority_recovery as recovery
recovery.OUT=ROOT/'authority_recovery'
old_envroot=env.ROOT;env.ROOT=ROOT
try:recovery.install_validator()
finally:env.ROOT=old_envroot
from native_runtime_paths import install
install(CASE/'native'/PHASE)
OLD=env.ORIGINAL/'frozen_artifacts/v41r4_may/loop_wall_v4'
RUN=CASE/'runs';OUT=RUN/'audit'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')
def copy(a,b):
 b=Path(b);b.parent.mkdir(parents=True,exist_ok=True)
 if not env.exists(b):b.write_bytes(Path(a).read_bytes())
def adapt(fn,pairs,extra=None):
 s=textwrap.dedent(inspect.getsource(fn))
 for a,b in pairs:assert s.count(a)==1,(fn.__name__,a);s=s.replace(a,b)
 ns=dict(fn.__globals__,**(extra or {}));exec(compile(s,__file__+'::'+fn.__name__,'exec'),ns);return ns[fn.__name__]
def setup(policy):
 for p in (OLD/'audit').glob('MAY_CAMPAIGN_RELEASE*.json'):copy(p,OUT/p.name)
 for name in ['INPUT_PREPARATION.json','V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json','V41R3_TIMESHIFTING_PRESERVATION_AUDIT.json','V41R3_B0_ACCEPTANCE.json','B0_DAYAHEAD_SUMMARY.json']:
  copy(OLD/'audit'/DAY/name,OUT/DAY/name)
 copy(env.ORIGINAL/'frozen_artifacts/v41r4_may/audit'/DAY/'domain/DAILY_DOMAIN_AUTHORITY.json',OUT/DAY/'domain/DAILY_DOMAIN_AUTHORITY.json')
 producer=read(OLD/DAY/policy/'dayahead/DAYAHEAD_RECEIPT.json')
 if any(r['relative_path']=='mission_loop_large_block.py' for r in producer['science']['files']):
  from mission_loop_large_block import install as block;block()
 import v41r4_loop_runtime as runtime
 from dayahead.v41r1 import bounded_mess
 original_mess_run=bounded_mess.run
 runtime.MAY_RUN=RUN;runtime.MAY_OUT=OUT
 execution=runtime.configure(DAY,policy)
 from round2_empty_table import install as empty_table;empty_table()
 from round2_compound_readback import install as compound_readback;compound_readback()
 # Include the ablation implementation as a separately verified source binding.
 base_science=execution.science
 patch_manifest=read(ROOT/'PATCH_MANIFEST.json')
 def science():return dict(base_science(),CC4_ablation_manifest={'path':str(ROOT/'PATCH_MANIFEST.json'),'sha256':recovery.sha(ROOT/'PATCH_MANIFEST.json')},CC4_optimization_enabled=False)
 execution.science=science;execution.dayahead.__globals__['science']=science
 from dayahead.v40h.identity import verify_manifest
 original_verify=runtime.VERIFY
 def verify(day,method):
  assert day==DAY
  folder=(OLD if method=='B0' else RUN)/day/method/'dayahead'
  r=read(folder/'DAYAHEAD_RECEIPT.json');verify_manifest(r['science'])
  if method!='B0':assert r['science']['CC4_ablation_manifest']['sha256']==recovery.sha(ROOT/'PATCH_MANIFEST.json')
  fn=types.FunctionType(original_verify.__code__,dict(original_verify.__globals__,RUNS=OLD if method=='B0' else RUN,science=lambda:r['science']))
  return fn(day,method)
 execution.verify_dayahead=verify;execution.dayahead.__globals__['verify_dayahead']=verify
 from dayahead.v41r1 import bounded_mess
 bounded_mess.run=adapt(original_mess_run,[("Path('D:/MobileESS_FO_M1')","Path('D:/c5')"),("[sys.executable,'-u','-m','dayahead.v41r1.bounded_mess',str(request)]","[sys.executable,'-B','-u',str(ROOT_ADAPTER/'worker.py'),DAY,'M1_WORKER',str(request)]"),("cwd=ROOT,stdin=","cwd=CASE,stdin=")],dict(CASE=CASE,ROOT_ADAPTER=ROOT,DAY=DAY))
 # The model must contain no CC4 variables/constraints at solver entry.
 import gurobipy as gp
 original_opt=gp.Model.optimize
 def optimize(model,*a,**kw):
  model.update()
  bad=[v.VarName for v in model.getVars() if v.VarName.startswith('V41_H4_shortfall')]
  bad += [c.ConstrName for c in model.getConstrs() if c.ConstrName.startswith(('V41_H4_reserve','V41_MEAN_H4_SHORTFALL_LOCK'))]
  assert not bad,('CC4_INTERFACE_STILL_ACTIVE',bad)
  assert model.Params.Threads==4 or model.Params.Threads==1,('UNEXPECTED_THREADS',model.Params.Threads)
  return original_opt(model,*a,**kw)
 gp.Model.optimize=optimize
 return runtime,execution
def main():
 started=time.time();status=CASE/'status'/f'{PHASE}.json'
 save(status,dict(status='RUNNING',phase=PHASE,started_at=started,pid=os.getpid()))
 try:
  if PHASE in ('A1','B3','M1_WORKER'):
   runtime,ex=setup('B1' if PHASE=='A1' else 'B3')
   if PHASE=='M1_WORKER':
    from dayahead.v41r1.bounded_mess import worker;worker(sys.argv[3]);return
   from dayahead.v41.temporal_restore import activate
   if PHASE=='A1':runtime.prepare_ranking(DAY)
   try:
    with activate():ex.dayahead(DAY,'B1' if PHASE=='A1' else 'B3')
   except ValueError as err:
    if PHASE!='B3' or str(err)!='DAYAHEAD_FRESH_PHYSICAL_VIOLATION':raise
    save(CASE/'ORIGINAL_CLOSURE_REQUIRED.json',dict(reason=str(err),raw_result_preserved=True))
   from dayahead.v41r3 import candidates
   if candidates._store is not None and not candidates._store.complete:candidates._store.finish()
   if PHASE=='B3':
    da=RUN/DAY/'B3/dayahead'
    save(CASE/'closure'/DAY/'ACCEPTANCE.json',dict(status='PASS' if not read(da/'FRESH_RESULT.json')['summary']['physical_violation'] else 'NEEDS_ORIGINAL_CLOSURE',final_dayahead=str(da)))
  elif PHASE=='ACTUAL':
   from actual_adapter import main as actual;actual(DAY,CASE,RUN)
  elif PHASE=='CLOSURE':
   from closure_adapter import close;close(DAY,CASE,RUN)
  elif PHASE=='REPORT':
   from report import day_report;day_report(DAY,CASE)
  elif PHASE=='IMPORT_CHECK':
   runtime,ex=setup('B1')
   from dayahead.v41r1 import early_stop
   assert early_stop.GUARDS==(900.,0.,180.,120.,120.)
   from dayahead.v40g import optimizer
   assert 'reserve_mean, reserve_xi = None, []' in inspect.getsource(optimizer.solve)
   save(CASE/'IMPORT_CHECK.json',dict(status='PASS',solver_calls=0,threads=4,stage_weights=early_stop.GUARDS,source=optimizer.__file__))
  else:raise ValueError(PHASE)
  save(status,dict(status='COMPLETE',phase=PHASE,started_at=started,wall_seconds=time.time()-started,pid=os.getpid()))
 except BaseException as e:
  save(status,dict(status='FAILED',phase=PHASE,error=repr(e),traceback=traceback.format_exc(),wall_seconds=time.time()-started,pid=os.getpid()));raise
 finally:env.save_audit(CASE/'io'/f'{PHASE}.json')
if __name__=='__main__':main()

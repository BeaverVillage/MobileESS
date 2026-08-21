from __future__ import annotations
import importlib.util,inspect,json,os,sys,threading,time
from pathlib import Path
from typing import Any,Mapping
from r26.dispatch import DispatchResult,OpenDssResult,audit_model_structure
from r26.production_adapter import ProductionModelBundle,SourceLockManifest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/"runtime"))
import MobileESS_A_STEP2_3_LOCAL_RUNNER_20260815_R2 as base

_CONTEXT={}
class _Stop(BaseException):pass

def _resume_env(issue,state_path,state_hash,hint):
 return {
  "MOBILEESS_RESUME_ISSUE":str(issue),"MOBILEESS_R25Q_RESUME_STATE_PATH":str(state_path),
  "MOBILEESS_RESUME_STATE_SHA256":str(state_hash),"MOBILEESS_R25Q_RESUME_HINT_DIR":str(hint),
  "MOBILEESS_R25Q_RESUME_MOVE_PLAN_NAME":"NONE.csv","MOBILEESS_R25Q_RESUME_MESS_PLAN_NAME":"NONE.csv",
  "MOBILEESS_R25V_RESUME_JOB_PLAN_NAME":"NONE.csv","MOBILEESS_R25V_RESUME_GUIDANCE_PATH":str(hint/"NONE.json")}

class ReusableScienceBridge:
 """Real pre-opt model capture. Frozen science bytes are imported unchanged."""
 def __init__(self,config,output,plans=None):
  self.config=config;self.output=Path(output)
  self.repo=base.locate_repo(config.get("repo"))
  self.source_lock=SourceLockManifest.from_file(HERE/"authority/R26_STAGE2_SOURCE_LOCK.json")
  self.source_lock.verify(self.repo)
 def build_conditioned_model(self,*,frame,pre_state,route_plan,route_steps,work_assignments,binding,output):
  issue=int(frame.issue);out=Path(output);out.mkdir(parents=True,exist_ok=True)
  state_path=out/"BRIDGE_PRE_STATE.json"
  raw=pre_state if isinstance(pre_state,dict) else pre_state.to_jsonable()
  # state-store objects may wrap the exact BUILD7C envelope.
  if "state" not in raw and hasattr(pre_state,"payload"):raw=pre_state.payload
  state_path.write_text(json.dumps(raw,indent=2,sort_keys=True)+"\n")
  hint=out/"empty_hints";hint.mkdir(exist_ok=True)
  base.set_science_environment();env=_resume_env(issue,state_path,frame.pre_state_hash,hint);os.environ.update(env)
  sm=base.load_science(self.repo);os.environ.update(env)
  ready=threading.Event();release=threading.Event();ctx={"sm":sm}
  def hook(**kwargs):
   fr=inspect.currentframe().f_back;loc=fr.f_locals;ctx["loc"]=loc;ctx["model"]=kwargs["m"];ready.set()
   if not release.wait(120):raise RuntimeError("science bridge optimize barrier timeout")
   return None
  sm.certified_path_decomposition_solve=hook
  def run():
   try:sm.rolling54_main(out/"science_capture",Path.home()/"mobile_ess_work")
   except _Stop:pass
   except BaseException as e:ctx["error"]=e
  # Stop before any physical POST. Generic controller owns Fresh/commit.
  original_jw=sm.jw
  def jw(p,v):
   pp=Path(p)
   if pp.name=="BUILD7C_POSTCOMMIT_STATE.json":raise _Stop()
   return original_jw(p,v)
  sm.jw=jw
  th=threading.Thread(target=run,name=f"science_bridge_{issue}",daemon=True);ctx["thread"]=th;ctx["release"]=release;th.start()
  if not ready.wait(120):raise RuntimeError("science bridge did not reach pre-opt barrier")
  if "error" in ctx:raise ctx["error"]
  _CONTEXT[issue]=ctx
  return ProductionModelBundle(model=ctx["model"],plan_checksum=route_plan.checksum,pre_state_hash=frame.pre_state_hash,
    source_lock_authority_id=self.source_lock.authority_id,future_actual_used=False,
    metadata={"real_science_bridge":True,"thread_barrier":True,"scientific_source_modified":False})
 def slow_variable_inventory(self,model):
  for ctx in _CONTEXT.values():
   if ctx.get("model") is model:
    out={}
    for name,fam in (("x","WORK_START"),("defer","WORK_DEFER"),("stay","MOBILITY_STAY"),("mv","MOBILITY_MOVE"),("node_occ","MOBILITY_OCCUPANCY")):
     for v in ctx["loc"].get(name,{}).values():out[str(v.VarName)]=fam
    return out
  raise RuntimeError("model context not found")
 def classify_remaining_integer(self,name):
  return "FAST_DISPATCH_MODE" if str(name).startswith("mode_") else "OTHER_EXPLICITLY_REVIEWED_FAST_INTEGER"
 def extract_result(self,*,model,frame,pre_state,structure,bundle,output):
  ctx=_CONTEXT[int(frame.issue)];ctx["release"].set()
  # Frozen science post-solve extraction is allowed to continue until the POST barrier.
  # h0 start list is available directly from solved x variables.
  loc=ctx["loc"];started=sorted({str(k[0]) for k,v in loc.get("x",{}).items() if int(k[3])==int(frame.issue) and float(v.X)>0.5})
  feasible=int(model.SolCount)>0
  return DispatchResult(feasible=feasible,status="OPTIMAL" if int(model.Status)==2 else f"GUROBI_{int(model.Status)}",
   objective=float(model.ObjVal) if feasible else None,runtime_seconds=float(model.Runtime),next_state={"science_thread_issue":int(frame.issue)},
   h0_solution={"started_job_uids":started,"real_gurobi_executed":True},structure=structure,
   numerical_gates_passed=bool(feasible and float(getattr(model,"ConstrVio",0.0))<=1e-6))

class ReusableFreshOpenDssVerifier:
 """Couples to the frozen science thread so Fresh Exact OpenDSS runs exactly once."""
 def __init__(self,config,output,plans=None):self.output=Path(output)
 def verify_fresh(self,*,frame,pre_state,dispatch):
  issue=int(frame.issue);ctx=_CONTEXT.get(issue)
  if not ctx:raise RuntimeError("science context missing for Fresh verifier")
  # The bridge thread is released after optimize and runs frozen build/exact path.
  # Wait for exact-grid artifact, but do not authorize a controller commit unless it passes.
  root=Path(ctx["loc"]["out"])
  p=root/f"exact_grid/FRESH_EXACT_OPENDSS_24SERVICE_ISSUE_{issue}.json"
  deadline=time.monotonic()+180
  while time.monotonic()<deadline:
   if p.is_file():
    m=json.loads(p.read_text());passed=bool(m.get("converged") and m.get("hard_constraint_pass"))
    return OpenDssResult(passed=passed,status="PASS_FRESH_EXACT_OPENDSS" if passed else "FAIL_FRESH_EXACT_OPENDSS",
      metrics={**m,"real_opendss_executed":True})
   if "error" in ctx:raise ctx["error"]
   time.sleep(.05)
  raise RuntimeError("Fresh Exact OpenDSS artifact timeout")

class ContinuationStateStore:
 """Fail-closed persisted actual-state store. Offline FIX4 PRE114 fallback is impossible."""
 def __init__(self,config,output,plans=None):
  self.root=Path(output)/"portable_state_store";self.root.mkdir(parents=True,exist_ok=True)
 def restore_pre(self,frame):
  p=self.root/"CURRENT_STATE.json"
  if not p.is_file():raise RuntimeError("no persisted actual PRE; offline PRE114 fallback forbidden")
  x=json.loads(p.read_text())
  if str(x.get("sha256"))!=str(frame.pre_state_hash):raise RuntimeError("persisted PRE hash mismatch")
  return x
 def commit_post(self,*,frame,pre_state,dispatch,opendss):
  issue=int(frame.issue);ctx=_CONTEXT.get(issue)
  if not ctx:raise RuntimeError("science context missing at commit")
  # Frozen science thread is already proceeding. Wait for its exact POST artifact.
  root=Path(ctx["loc"]["out"]);p=root/"BUILD7C_POSTCOMMIT_STATE.json";deadline=time.monotonic()+180
  while time.monotonic()<deadline:
   if p.is_file():
    x=json.loads(p.read_text());tmp=self.root/"CURRENT_STATE.json.tmp";tmp.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n");tmp.replace(self.root/"CURRENT_STATE.json")
    return str(x["sha256"])
   if "error" in ctx:raise ctx["error"]
   time.sleep(.05)
  raise RuntimeError("physical POST artifact timeout")

class ContinuationInputProvider:
 def __init__(self,config,output,plans=None):self.config=config
 def snapshot(self,issue):
  from r26.controller import CausalFrame
  # Generic production use requires caller to populate state hash through runtime config.
  state_path=Path(self.config["portable_runtime"]["current_state_path"])
  x=json.loads(state_path.read_text())
  return CausalFrame(issue=int(issue),cutoff_timestamp_utc=str(self.config["portable_runtime"]["cutoff_timestamp_utc"]),
   pre_state_hash=str(x["sha256"]),planner_target_issue=int(issue),planner_target_state_hash=str(x["sha256"]),
   hard_flags={},soft_metrics={},affected_mess_ids=(),affected_job_ids=(),
   payload={"future_actual_used":False,"actual_through_issue":int(issue)})

def create_science_bridge(config,output,plans=None):return ReusableScienceBridge(config,output,plans)
def create_fresh_opendss_verifier(config,output,plans=None):return ReusableFreshOpenDssVerifier(config,output,plans)
def create_continuation_state_store(config,output,plans=None):return ContinuationStateStore(config,output,plans)
def create_continuation_input_provider(config,output,plans=None):return ContinuationInputProvider(config,output,plans)
def create_validation_planner(config,output,plans=None):
 def planner(req):raise RuntimeError("generic fixed-plan validation planner received replan request; use authoritative B9 executor for event/full-replan continuation")
 return planner

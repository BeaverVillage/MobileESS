from __future__ import annotations
import hashlib,json,math
from pathlib import Path
from typing import Any,Mapping

FAMILIES={"x":"WORK_START","defer":"WORK_DEFER","stay":"MOBILITY_STAY","mv":"MOBILITY_MOVE","node_occ":"MOBILITY_OCCUPANCY"}

def canonical_sha(obj):
 return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def capture_semantic_plan(loc:Mapping[str,Any],issue:int,pre_hash:str,model:Any)->dict[str,Any]:
 def selected(name):
  return [list(k) if isinstance(k,tuple) else str(k) for k,v in loc.get(name,{}).items() if float(v.X)>0.5]
 slow={
  "issue":int(issue),"source_pre_state_sha256":str(pre_hash),
  "selected_x":selected("x"),"selected_defer":selected("defer"),
  "selected_stay":selected("stay"),"selected_mv":selected("mv"),
  "selected_occ":selected("node_occ"),
 }
 return {"schema_version":"a.b9.semantic_slow_plan.v1",**slow,"plan_checksum":canonical_sha(slow),
         "planner_objective":float(model.ObjVal),"future_actual_used":False}

def _norm_key(name,k):
 if name=="x":return (str(k[0]),str(k[1]),str(k[2]),int(k[3]))
 if name in ("stay","node_occ"):return (str(k[0]),int(k[1]),str(k[2]))
 if name=="mv":return (str(k[0]),int(k[1]),int(k[2]))
 return str(k)

def binding_from_semantic(loc:Mapping[str,Any],plan:Mapping[str,Any],source_lock_authority_id:str)->tuple[dict[str,Any],dict[str,float]]:
 selected={
  "x":{_norm_key("x",k) for k in plan["selected_x"]},
  "defer":{str(k) for k in plan["selected_defer"]},
  "stay":{_norm_key("stay",k) for k in plan["selected_stay"]},
  "mv":{_norm_key("mv",k) for k in plan["selected_mv"]},
  "node_occ":{_norm_key("node_occ",k) for k in plan["selected_occ"]},
 }
 # Every selected key must exist in the current causal model.
 for name in ("x","stay","mv","node_occ"):
  missing=sorted(selected[name]-set(loc.get(name,{})))
  if missing:raise RuntimeError(f"plan invalid: selected {name} keys absent {missing[:20]}")
 # New queued Job decisions not represented by the active plan invalidate it.
 plan_jobs={k[0] for k in selected["x"]}|selected["defer"]
 model_jobs={str(k[0]) for k in loc.get("x",{})}|{str(k) for k in loc.get("defer",{})}
 unplanned=sorted(model_jobs-plan_jobs)
 if unplanned:raise RuntimeError(f"plan invalid: new/unplanned job decisions {unplanned[:30]}")
 assignments={};families={}
 for name in ("x","defer","stay","mv","node_occ"):
  for k,var in loc.get(name,{}).items():
   nk=_norm_key(name,k)
   value=1.0 if nk in selected[name] else 0.0
   assignments[str(var.VarName)]=value;families[str(var.VarName)]=FAMILIES[name]
 expected=sorted(assignments)
 binding={
  "schema_version":"r26.plan_binding.v1",
  "plan_checksum":str(plan["plan_checksum"]),
  "source_state_hash":str(plan["source_pre_state_sha256"]),
  "valid_from_issue":int(plan["issue"]),
  "source_lock_authority_id":str(source_lock_authority_id),
  "named_assignments":{k:assignments[k] for k in expected},
  "assignment_families":{k:families[k] for k in expected},
  "expected_slow_variable_names":expected,
  "future_actual_used":False,
  "metadata":{"generator":"a_b9_plan_binding.binding_from_semantic","complete_model_inventory":True},
 }
 return binding,assignments

def write_binding(directory:Path,binding:Mapping[str,Any])->Path:
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 path=directory/f"{binding['plan_checksum']}.json"
 tmp=path.with_suffix(".json.tmp")
 tmp.write_text(json.dumps(binding,indent=2,sort_keys=True,allow_nan=False)+"\n")
 tmp.replace(path)
 alias=directory/f"issue_{int(binding['valid_from_issue']):06d}.json"
 alias.write_text(path.read_text())
 return path

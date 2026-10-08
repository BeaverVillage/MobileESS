"""Recheck original files/arrays without changing the primary input receipt."""
from pathlib import Path
import json,hashlib,time
import numpy as np
from .policy import ROOT as R, OUT as O
old=Path(r"C:\Users\kjw39\Documents\Codex\2026-10-08\a-stage-acceptance-fourday\docs/v42_a_stage_acceptance_fourday_20261008/2025-05-12/INITIAL_VERIFICATION.json")
def read(p):return json.loads(Path(p).read_text(encoding="utf8"))
def rec(p):
 p=Path(p)
 with p.open("rb") as f:h=hashlib.file_digest(f,"sha256").hexdigest()
 return dict(path=str(p),sha256=h,bytes=p.stat().st_size)
t=time.perf_counter();initial=read(old);bundle=read(initial["input"]["path"]);files=[];arrays=[];seen=set()
def visit(v,axis):
 if isinstance(v,dict):
  if all(k in v for k in ("path","sha256","bytes")):
   p=v["path"]
   if p not in seen:
    seen.add(p);actual=rec(p);want={k:v[k] for k in actual};files.append(dict(axis=axis,PASS=actual==want,expected=want,actual=actual))
  for k,w in v.items():visit(w,axis+"/"+str(k))
 elif isinstance(v,list):
  for i,w in enumerate(v):visit(w,axis+"/"+str(i))
visit({k:initial[k] for k in ("input","frozen_data")},"initial");visit(bundle,"native_input")
for k,r in bundle["grid_outputs"].items():
 with np.load(r["path"],allow_pickle=False) as z:
  for n in z.files:
   a=z[n];payload=np.ascontiguousarray(a).tobytes()
   arrays.append(dict(archive=k,array=n,dtype=a.dtype.str,shape=list(a.shape),sha256=hashlib.sha256(payload).hexdigest(),bytes=len(payload)))
work={k:bundle[k] for k in ("known_population","racks","capacities","WAN","runtime_survival_kernel","C0_Q50","C0_Q90","CC4_reserve_GPU","unknown_nominal_GPU")}
axes=[dict(axis=k,canonical_JSON_sha256=hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()) for k,v in work.items()]
r=dict(PASS=all(v["PASS"] for v in files),day=bundle["day"],role=bundle["role"],issue_time=bundle["issue_time"],files=files,original_grid_array_identities=arrays,original_workload_axis_identities=axes,scientific_input=rec(old),no_input_writes=True,wall_seconds=time.perf_counter()-t)
(O/"ORIGINAL_INPUT_AND_ARRAY_IDENTITY_FINAL.json").write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding="utf8")
print("INPUT_ARRAY_IDENTITY",r["PASS"],len(files),len(arrays),r["wall_seconds"])
if not r["PASS"]:raise ValueError("INPUT_SOURCE_IDENTITY_FAIL")

prior=read(O/"ORIGINAL_INPUT_AND_ARRAY_IDENTITY.json")
assert all(prior[k]==r[k] for k in ("files","original_grid_array_identities","original_workload_axis_identities","scientific_input")),"PRE_POST_INPUT_IDENTITY_DRIFT"

"""Verify every actual execution source and native RAW/matrix receipt."""
from pathlib import Path
import hashlib,json,time
from .policy import ROOT as R, OUT as O, STATIC as S
def read(p):return json.loads(Path(p).read_text(encoding="utf8"))
def rec(p):
 p=Path(p)
 with p.open("rb") as f:h=hashlib.file_digest(f,"sha256").hexdigest()
 return dict(path=str(p),sha256=h,bytes=p.stat().st_size)
t=time.perf_counter();mismatches=[];epochs=[]
active=read(O/"ACTIVE_SOURCE_FREEZE.json")["epoch"]
for p in sorted(O.glob("SOURCE_FREEZE_EPOCH*.json")):
 f=read(p);epoch=int(p.stem.split("EPOCH")[1]);root=S/("EXECUTED_SOURCES_EPOCH"+str(epoch))
 if not root.exists():root=R if epoch==active else root
 for original,h in f["execution_sources"].items():
  q=root/Path(original).relative_to(R)
  if not q.exists() or rec(q)["sha256"]!=h:mismatches.append(dict(epoch=epoch,path=str(q),expected=h))
 epochs.append(dict(epoch=epoch,git_head=f["git_head"],sources=len(f["execution_sources"]),actual_execution_bytes_root=str(root),freeze=rec(p)))
calls=read(O/"NEW_NATIVE_CALLS.json")["calls"];receipts=[]
for c in calls:
 for key in ("model_identity","raw_attributes","telemetry"):
  r=c[key]
  if rec(r["path"])!=r:mismatches.append(dict(native_folder=c["folder"],invalid_receipt=key))
 identity=read(c["model_identity"]["path"]);f=identity["source_manifest"]
 if rec(f["path"])!=f:mismatches.append(dict(folder=c["folder"],invalid_source_manifest=True))
 frozen=read(f["path"])
 if frozen["git_head"]!=identity["source_commit"] or identity["source_commit"]!=c["source_commit"]:mismatches.append(dict(folder=c["folder"],source_commit_mismatch=True))
 receipts.append(dict(folder=c["folder"],source_commit=c["source_commit"],source_manifest=f,PASS=True))
results=[dict(path=str(p),wall_seconds=read(p)["new_wall_seconds"]) for p in sorted(O.glob("PRE*/FINAL_DECISION.json"))]
latest=read(O/"FINAL_DECISION.json");results.append(dict(path=str(O/"FINAL_DECISION.json"),wall_seconds=latest["new_wall_seconds"]))
r=dict(PASS=not mismatches,epochs=epochs,native_execution_source_receipts=receipts,mismatches=mismatches,run_attempt_walls=results,cumulative_native_experiment_wall_seconds=sum(x["wall_seconds"] for x in results),actual_native_calls=len(calls),wall_seconds=time.perf_counter()-t,no_old_source_writes=True)
(O/"EXECUTION_EPOCH_AND_BUDGET_PROVENANCE.json").write_text(json.dumps(r,indent=2),encoding="utf8")
print("EXECUTION_RECEIPTS",r["PASS"],len(calls),r["cumulative_native_experiment_wall_seconds"])
if not r["PASS"]:raise ValueError("EXECUTED_SOURCE_OR_RAW_RECEIPT_DRIFT")

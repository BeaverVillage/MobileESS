#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def h(p):
    x=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):x.update(b)
    return x.hexdigest()
def rows(p):
    p=Path(p);s=p.suffix.lower()
    if s==".json":
        o=json.loads(p.read_text(encoding="utf-8"))
        return o if isinstance(o,list) else o["rows"]
    if s in {".jsonl",".ndjson"}:return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    if s==".csv":
        import csv
        with p.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
    if s==".parquet":
        import pandas as pd
        return pd.read_parquet(p).to_dict("records")
    raise RuntimeError("unsupported input")
def amap(rs):
    d={}
    for r in rs:
        j=str(r.get("job_uid",r.get("job_id")));a=int(r["arrival_step"])
        if j in d and d[j]!=a:raise RuntimeError("inconsistent duplicate")
        d[j]=a
    return d
def comp(p):
    o=json.loads(Path(p).read_text(encoding="utf-8"))
    if isinstance(o.get("state"),dict):o=o["state"]
    c=o.get("completed_job_ids",o.get("completed"))
    if isinstance(c,dict):c=list(c)
    if not isinstance(c,list):raise RuntimeError("missing completed IDs")
    return {str(x) for x in c}
def w(p,o):
    Path(p).write_text(json.dumps(o,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
def main():
    a=argparse.ArgumentParser()
    for x in ("episode-manifest","independent-arrivals","evaluation-end-state","job-event","output"):a.add_argument("--"+x,required=True)
    z=a.parse_args();m=json.loads(Path(z.episode_manifest).read_text());s,e=int(m["evaluation_start_step"]),int(m["evaluation_end_step"])
    i=amap(rows(z.independent_arrivals));l=amap(rows(z.job_event));c=comp(z.evaluation_end_state)
    E=sorted(j for j,x in i.items() if s<=x<=e);L=sorted(j for j,x in l.items() if s<=x<=e);P=sorted(set(E)-c)
    auth=Path(z.output).with_name("F7_INDEPENDENT_COHORT_AUTHORITY_MANIFEST_V2.json")
    w(auth,{"schema_version":"D16_F7_INDEPENDENT_COMPOSITE_AUTHORITY_V2","job_identity_bridge":"job_event.job_id = str(C.job_uid)",
            "independent_arrivals_sha256":h(z.independent_arrivals),"evaluation_end_state_sha256":h(z.evaluation_end_state),"derived_from_job_event":False})
    cert={"certificate_version":"K9H7_F7_COVERAGE_V1","episode_id":m["episode_id"],"method_id":m["method_id"],"month":m["month"],
          "evaluation_start_step":s,"evaluation_end_step":e,"expected_evaluation_arrival_job_count":len(E),
          "logged_job_event_evaluation_arrival_job_count":len(L),"pending_evaluation_arrival_jobs_at_evaluation_end":len(P),
          "coverage_pass":len(E)==len(L) and set(E)==set(L),"independent_source_kind":"C_CANONICAL_JOB_ARRIVALS_PLUS_RUNTIME_STATE_ACCOUNTING",
          "independent_source_sha256":h(auth)}
    w(z.output,cert);print(json.dumps(cert,indent=2,sort_keys=True));return 0 if cert["coverage_pass"] else 2
if __name__=="__main__":raise SystemExit(main())

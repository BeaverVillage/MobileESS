"""Stable representative assignment within verified scientific symmetry classes."""
from dataclasses import asdict
from v42_job_capability import Option,validate

def option(row):
    d=dict(row);d['segments']=tuple(tuple(x) for x in d['segments']);d['wan']=tuple(tuple(x) for x in d['wan']);return Option(**d)

def assign(selected,data):
    bundle,jobs,bounds,r,raw,graphs,old,prep=data;out=dict(selected)
    for us in prep['classes'].values():
        paths=sorted(option(selected[u]) for u in us)
        for u,path in zip(sorted(us),paths):
            validate(jobs[u],path,bounds[u],r);out[u]=asdict(path)
    return {u:out[u] for u in sorted(out)}

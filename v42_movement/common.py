import os
from pathlib import Path
ENV = dict.fromkeys(('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'),'1')
os.environ.update(ENV)
from v42_strengthening.common import sha,read,SOURCE,SCIENCE,REF,BASE_LB,UB_REF
from v42_disjunctive.common import material
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_movement_grid_epigraph_strengthening'
LOCAL=ROOT.parent/'MOVEMENT_GRID_LOCAL'
BASE='4ea94878a40327a11e57c7a9b69030da9e158993'
def write(name,value):
    import json
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def table(name,rows,fields=None):
    import csv
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)
def once(label):
    LOCAL.mkdir(parents=True,exist_ok=True)
    with (LOCAL/(label+'_STARTED.json')).open('x',encoding='utf8') as f:f.write('{"retries_allowed":0}\n')
def gate(label):
    from v42_single_thread.resources import snapshot
    r=snapshot();r.update(label=label,environment={k:os.environ.get(k) for k in ENV})
    r['PASS']=all(os.environ.get(k)=='1' for k in ENV) and not any(not p['self'] for p in r['heavy_processes'])
    write('RESOURCE_GATE_'+label+'.json',r)
    if not r['PASS']:raise RuntimeError('SINGLE_HEAVY_WORKER_REQUIRED')
    return r
def census(d,x,label):
    import v42_strengthening.analysis as a
    a.write=write;a.table=table
    sites,initial,arcs,*_=a.graph_inputs()
    return a.census(d,x,sites,initial,arcs,label)[0]

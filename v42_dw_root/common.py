import os
from pathlib import Path
ENV=dict.fromkeys(('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'),'1')
os.environ.update(ENV)
from v42_strengthening.common import sha,read,SOURCE,SCIENCE,REF,BASE_LB
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_exact_dw_cg_root_pilot'
LOCAL=ROOT.parent/'DW_ROOT_LOCAL'
BASE='c8e518f97cbe1748f3e8773128ff8152bd394ee8'
U_REF=.6694159238756876
UNITS=('MESS01','MESS02','MESS03','MESS04')
def write(name,value):
    import json
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def table(name,rows,fields):
    import csv
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
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
def finite(value):
    import math
    return float(value) if math.isfinite(value) and abs(value)<1e90 else None
def material(lb,certified):
    delta=None if lb is None else lb-BASE_LB;closure=None if delta is None else delta/(U_REF-BASE_LB)
    return dict(status='INCONCLUSIVE' if not certified else 'PASS' if lb>=BASE_LB-1e-8 and (delta>=.005 or closure>=.05) else 'FAIL',
                delta_LB=delta,relative_gap_closure=closure,baseline_gap=(U_REF-BASE_LB)/U_REF,
                new_gap=None if lb is None else (U_REF-lb)/U_REF,U_ref=U_REF,diagnostic_only=True)

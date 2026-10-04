from v42_dw_bound.common import ROOT,ENV,BASE,OLD,RESUME,OUT as PREVIOUS,EPS,POST,UNITS,BASE_LB,T_MATERIAL,sha,read,pool
from pathlib import Path
import os,json,csv,hashlib,time,subprocess
os.environ.update(ENV)
OUT=ROOT/'docs/v42_m1_dw_discovery_certification_policy'
DISCOVERY_RC=-1e-7
BUDGET=900.
STOP=OUT/'STOP_REQUEST.json'
def write(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');q.replace(p)
def table(name,rows):
    p=OUT/name
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['round']);w.writeheader();w.writerows(rows)
def ledger(name,directory=OUT):
    with (directory/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def old_columns():
    return pool()+[(PREVIOUS,dict(h,file=h['file'],format='policy_optimal')) for h in ledger('DW_NEW_COLUMN_LEDGER.csv',PREVIOUS)]
def union_seconds(intervals):
    spans=sorted((float(a),float(b)) for a,b in intervals)
    assert all(b>=a for a,b in spans)
    total=0.;end=None
    for a,b in spans:
        total+=b-max(a,end if end is not None else a) if end is None or b>end else 0.
        end=b if end is None else max(end,b)
    return total
def candidate_class(status,valid,rc):
    if valid and rc is not None and rc<=DISCOVERY_RC:return 'VALID_NEGATIVE_DISCOVERY_COLUMN'
    return 'NO_VALID_NEGATIVE_DISCOVERY_COLUMN'
def resource_threshold(total):return max(8*1024**3,.15*total)
def verify_freeze():
    f=read(OUT/'EXECUTION_FREEZE.json')
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['sources'])
    assert sha(OUT/'DW_DISCOVERY_CERT_PREREGISTRATION.json')==f['preregistration_SHA']
    assert not subprocess.check_output(['git','status','--porcelain','--','v42_dw_policy'],cwd=ROOT,text=True)
    return subprocess.check_output(['git','log','-1','--format=%H','--','v42_dw_policy/run.py'],cwd=ROOT,text=True).strip()
def preserve_old():
    f=read(OUT/'OLD_POLICY_BYTE_FREEZE.json')
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['files'])
    return len(f['files'])

from v42_dw_root.common import ENV,ROOT,LOCAL,SOURCE,SCIENCE,REF,BASE_LB,U_REF,UNITS,sha,read,finite
import os,json,csv,subprocess,time,hashlib
from pathlib import Path
os.environ.update(ENV)
BASE='851956172cf9b5cde5ebcfb2f3145b90de024987'
OLD=ROOT/'docs/v42_m1_exact_dw_cg_root_pilot'
RESUME=ROOT/'docs/v42_m1_exact_dw_cg_root_resume'
OUT=ROOT/'docs/v42_m1_dw_certified_dual_bound'
T_MATERIAL=BASE_LB+.005
EPS=1e-8
POST=1e-6
def write(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');tmp.replace(p)
def table(name,rows,fields=None):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields or list(rows[0]) if rows else fields or ['iteration']);writer.writeheader();writer.writerows(rows)
def ledger(name,directory):
    with (directory/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def pool():
    return [(OLD,h) for h in ledger('DW_COLUMN_HASH_LEDGER.csv',OLD) if h['added']=='True']+[(RESUME,h) for h in ledger('DW_RESUME_COLUMN_HASH_LEDGER.csv',RESUME) if h['added']=='True']
def gate(label):
    from v42_single_thread.resources import snapshot
    r=snapshot();r.update(label=label,environment={k:os.environ.get(k) for k in ENV})
    r['PASS']=all(os.environ.get(k)=='1' for k in ENV) and not any(not p['self'] for p in r['heavy_processes'])
    write('RESOURCE_GATE_'+label+'.json',r);assert r['PASS'],'ONE_WORKER_REQUIRED';return r
def preserved():
    records=read(OUT/'BASE_BYTE_FREEZE.json')['files'];bad=[r['path'] for r in records if sha(ROOT/r['path'])!=r['sha256']]
    assert not bad,bad;return len(records)
def verify_freeze():
    f=read(OUT/'EXECUTION_FREEZE.json')
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in f['sources'])
    assert sha(OUT/'DW_DUAL_BOUND_PREREGISTRATION.json')==f['preregistration_SHA']
    assert subprocess.check_output(['git','status','--porcelain','--','v42_dw_bound'],cwd=ROOT,text=True)==''
    return subprocess.check_output(['git','log','-1','--format=%H','--','v42_dw_bound/run.py'],cwd=ROOT,text=True).strip()

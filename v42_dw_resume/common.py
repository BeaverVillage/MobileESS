from v42_dw_root.common import ENV,ROOT,LOCAL,SOURCE,SCIENCE,REF,BASE,BASE_LB,U_REF,UNITS,sha,read,finite,material
import os,json,csv,subprocess
os.environ.update(ENV)
ORIGINAL=ROOT/'docs/v42_m1_exact_dw_cg_root_pilot'
OUT=ROOT/'docs/v42_m1_exact_dw_cg_root_resume'
POST_TOL=1e-6
STRICT_TOL=1e-8
ORIGINAL_HEAD='5ca8e7765f44ef9ee5d2e6c2270ab0d8ca272a90'
def write(name,value):
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    temporary=p.with_suffix(p.suffix+'.tmp');temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');temporary.replace(p)
def table(name,rows,fields):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def ledger(name,directory=ORIGINAL):
    with (directory/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def gate(label):
    from v42_single_thread.resources import snapshot
    r=snapshot();r.update(label=label,environment={k:os.environ.get(k) for k in ENV})
    r['PASS']=all(os.environ.get(k)=='1' for k in ENV) and not any(not p['self'] for p in r['heavy_processes'])
    write('RESOURCE_GATE_'+label+'.json',r)
    assert r['PASS'],'ONE_SCIENTIFIC_WORKER_REQUIRED';return r
def preserved():
    records=read(OUT/'ORIGINAL_HISTORY_BYTE_FREEZE.json')['files']
    drift=[r['path'] for r in records if sha(ROOT/r['path'])!=r['sha256']]
    assert not drift,drift;return len(records)
def source_freeze():
    return [dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted((ROOT/'v42_dw_resume').glob('*.py'))]
def verify_execution_freeze():
    frozen=read(OUT/'RESUME_EXECUTION_SOURCE_FREEZE.json')
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in frozen['sources'])
    commit=subprocess.check_output(['git','log','-1','--format=%H','--','v42_dw_resume/run.py'],cwd=ROOT,text=True).strip()
    assert commit and subprocess.check_output(['git','status','--porcelain','--','v42_dw_resume'],cwd=ROOT,text=True)==''
    assert subprocess.check_output(['git','status','--porcelain','--',str((OUT/'NUMERICAL_GATE_CORRECTION_ADDENDUM.json').relative_to(ROOT))],cwd=ROOT,text=True)==''
    return commit

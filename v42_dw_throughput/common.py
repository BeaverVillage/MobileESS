from v42_dw_policy.common import ROOT,ENV,BASE,OLD,RESUME,PREVIOUS,EPS,POST,UNITS,BASE_LB,T_MATERIAL,sha,read,pool,union_seconds,candidate_class
from pathlib import Path
import os,json,csv,hashlib,time,subprocess
os.environ.update(ENV)
BASE_HEAD='cae31ce64c83d1e94c158a46e2739fd2ff7e7da3'
POLICY=ROOT/'docs/v42_m1_dw_discovery_certification_policy'
OUT=ROOT/'docs/v42_m1_dw_throughput_optimization'
DISCOVERY_RC=-1e-7
BUDGET=900.
STOP=OUT/'STOP_REQUEST.json'
MAX_COLUMNS=4
def write(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');q.replace(p)
def table(name,rows):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['round']);w.writeheader();w.writerows(rows)
def ledger(name,directory=OUT):
    with (directory/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def old_columns():
    accepted=read(POLICY/'DW_POLICY_CHECKPOINT_LATEST.json')['pool']
    for h in accepted:
        p=ROOT/h['file'];yield p.parent,dict(MESS=h['MESS'],file=p.name,SHA256=h['column_SHA'],format='accepted',file_SHA=h['file_SHA'])
def resource_threshold(total=None):return 1024**3
def verify_freeze():
    f=read(OUT/'EXECUTION_FREEZE.json')
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['sources'])
    assert all(sha(OUT/p)==s for p,s in f['preregistrations'].items())
    assert not subprocess.check_output(['git','status','--porcelain','--','v42_dw_throughput'],cwd=ROOT,text=True)
    return subprocess.check_output(['git','log','-1','--format=%H','--','v42_dw_throughput/run.py'],cwd=ROOT,text=True).strip()
def preserve_old():
    f=read(OUT/'PR141_BYTE_FREEZE.json');assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['files']);return len(f['files'])
def severe_paging(rows):
    if len(rows)<11:return False
    window=rows[-11:];duration=window[-1]['perf']-window[0]['perf']
    rates=[r['hard_page_input_pages_per_sec'] for r in window[1:]]
    growth=window[-1]['pagefile_used']-window[0]['pagefile_used']
    return duration>=9.5 and all(r is not None and r>=1000 for r in rates) and growth>=256*1024**2
def resource_failures(row,history):
    errors=[]
    if row['available_RAM']<1024**3:errors.append('AVAILABLE_RAM_BELOW_1_GIB')
    if row['commit_percent'] is not None and row['commit_percent']>=95:errors.append('SYSTEM_COMMIT_AT_LEAST_95_PERCENT')
    if severe_paging(history):errors.append('SUSTAINED_PAGEFILE_GROWTH_AND_SEVERE_HARD_PAGING')
    return errors
def overlap_seconds(intervals,minimum):
    events=sorted([(a,1) for a,b in intervals]+[(b,-1) for a,b in intervals]);active=0;last=None;total=0.
    for t,n in events:
        if last is not None and active>=minimum:total+=t-last
        active+=n;last=t
    return total
def next_smoothing_weight(current,d_norm):
    if d_norm>.50:return max(.10,.5*current)
    if d_norm>.10:return current
    return min(.80,1.25*current)

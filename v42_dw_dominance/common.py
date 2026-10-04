"""Fixed PR142 authority; all previous packages and evidence are read-only."""
from v42_dw_throughput.common import *
from v42_dw_root.common import SOURCE,REF,SCIENCE
BASE_HEAD='29a115748e7c1f3a983019fe005e91710defa0d2'
PR142=ROOT/'docs/v42_m1_dw_throughput_optimization'
OUT=ROOT/'docs/v42_m1_dw_dominance_threshold_bound'
STOP=OUT/'STOP_REQUEST.json'

def write(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');q.replace(p)

def table(name,rows):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['round']);w.writeheader();w.writerows(rows)

def ledger(name,directory=None):
    with ((directory or OUT)/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))

def old_columns():
    for h in read(PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json')['pool']:
        p=ROOT/h['file'];yield p.parent,dict(MESS=h['MESS'],file=p.name,SHA256=h['column_SHA'],file_SHA=h['file_SHA'])

def preserve_old():
    f=read(OUT/'PR142_BYTE_FREEZE.json');assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['files']);return len(f['files'])

def verify_freeze():
    f=read(OUT/'EXECUTION_FREEZE.json')
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['sources'])
    assert all(sha(OUT/p)==s for p,s in f['preregistrations'].items())
    assert not subprocess.check_output(['git','status','--porcelain','--','v42_dw_dominance'],cwd=ROOT,text=True)
    assert read(OUT/'DW_DOMINANCE_BASE_AUDIT.json')['PASS']
    assert read(OUT/'DW_BOUND_AGGREGATION_PROOF.json')['PASS']
    return subprocess.check_output(['git','log','-1','--format=%H','--','v42_dw_dominance/prepare.py'],cwd=ROOT,text=True).strip()

def decision(lower,upper):
    if lower is not None and lower>=T_MATERIAL:return 'PROVEN_MATERIAL'
    if upper is not None and upper<=T_MATERIAL:return 'PROVEN_NONMATERIAL'
    return 'INCONCLUSIVE'

def early_trigger(accepted,uppers):
    if len(accepted)>=2 and not any(accepted[-2:]):return 'TWO_ZERO_ACCEPTED'
    if len(uppers)>=4 and uppers[-4]-uppers[-1]<.001:return 'THREE_ROUND_IMPROVEMENT_BELOW_0_001'
    if uppers and uppers[-1]-T_MATERIAL<=.002:return 'UPPER_WITHIN_0_002'
    return None

def classify(room,negative,deficit,sufficient=True):
    if not sufficient:return 'INCONCLUSIVE'
    weak=room>=max(.001,deficit)
    true=negative>=.001
    return 'MIXED' if weak and true else 'PRICING_BOUND_WEAKNESS_SUPPORTED' if weak else 'TRUE_NEGATIVE_RC_DOMINANT' if true and room<=max(1e-6,.05*negative) else 'INCONCLUSIVE'

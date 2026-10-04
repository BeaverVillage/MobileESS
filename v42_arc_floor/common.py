"""PR143 authority and separate LP/CG budgets; legacy scalar is diagnostic."""
from v42_dw_throughput.common import *
from v42_dw_root.common import SOURCE,SCIENCE
from v42_dw_dominance.common import OUT as DOMINANCE
BASE_HEAD='ce5d30fb9bcb91ab8395d1313e868d24f5fde517'
PR142=ROOT/'docs/v42_m1_dw_throughput_optimization'
OUT=ROOT/'docs/v42_m1_certified_arc_lp_floor_and_threshold_cg'
STOP=OUT/'STOP_REQUEST.json'
ARC_BUDGET=600.

def write(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp')
    q.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8');q.replace(p)

def table(name,rows):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['round']);w.writeheader();w.writerows(rows)

def ledger(name,directory=None):
    with ((directory or OUT)/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))

def old_columns():
    for h in read(DOMINANCE/'DW_CHECKPOINT_LATEST.json')['pool']:
        p=ROOT/h['file'];yield p.parent,dict(MESS=h['MESS'],file=p.name,SHA256=h['column_SHA'],file_SHA=h['file_SHA'])

def preserve_old():
    f=read(OUT/'PR143_BYTE_FREEZE.json');assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['files']);return len(f['files'])

def verify_freeze():
    f=read(OUT/'EXECUTION_FREEZE.json')
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in f['sources'])
    assert all(sha(OUT/p)==s for p,s in f['preregistrations'].items())
    assert all(sha(OUT/p)==s for p,s in f['arrays'].items())
    assert not subprocess.check_output(['git','status','--porcelain','--','v42_arc_floor','tests/v42_arc_floor'],cwd=ROOT,text=True)
    assert read(OUT/'ARC_LP_BASE_IDENTITY.json')['PASS']
    return subprocess.check_output(['git','log','-1','--format=%H','--','v42_arc_floor/arc.py'],cwd=ROOT,text=True).strip()

def thresholds(native,lower):
    from fractions import Fraction as F
    from v42_disjunctive.certificate import down,up
    a=F(float(native))+F(1,200);b=F(float(lower))+F(1,200)
    return dict(T_cert=float(a),T_from_lower=float(b),material_comparator=up(max(a,b)),nonmaterial_comparator=down(min(a,b)),reference='Terminal OPTIMAL native arc objective; certified support threshold recorded separately',increment_exact='1/200',outward_decision_rounding=True)

def decision(lower,upper,authority):
    if lower is not None and lower>=authority['material_comparator']:return 'PROVEN_MATERIAL'
    if upper is not None and upper<=authority['nonmaterial_comparator']:return 'PROVEN_NONMATERIAL'
    return 'INCONCLUSIVE'

def early_trigger(accepted,uppers,threshold):
    if len(accepted)>=2 and not any(accepted[-2:]):return 'TWO_ZERO_ACCEPTED'
    if len(uppers)>=4 and uppers[-4]-uppers[-1]<.001:return 'THREE_ROUND_IMPROVEMENT_BELOW_0_001'
    if uppers and uppers[-1]-threshold<=.002:return 'UPPER_WITHIN_0_002'
    return None

from v42_dw_continuation.common import *
from v42_m_stage.common import ROOT,OUT,SCI,PR152,PR154,read,write,table,sha

BUDGET=1800.
START_COLUMNS=1604
BASE_HEAD=PR152
STOP=OUT/'STOP_REQUEST.json'

def old_columns():
    for h in read(SCI/'DW_CHECKPOINT_LATEST.json')['pool']:
        p=ROOT/h['file']
        yield p.parent,dict(MESS=h['MESS'],file=p.name,SHA256=h['column_SHA'],file_SHA=h['file_SHA'])

def preserve_old():
    f=read(OUT/'PR152_BYTE_FREEZE.json')
    assert all(sha(ROOT/p)==h for p,h in f['files'].items())
    return len(f['files'])

def verify_freeze():
    f=read(OUT/'ROOT_EXECUTION_FREEZE.json')
    assert all(sha(ROOT/p)==h for p,h in f['sources'].items())
    assert all(sha(OUT/p)==h for p,h in f['authorities'].items())
    assert read(OUT/'HYBRID_PRICING_SELECTION.json')['PRICING_BACKEND']=='ORIGINAL_GUROBI_EXACT'
    preserve_old()
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()

def early_trigger(accepted,uppers,threshold):
    if len(accepted)>=2 and not any(accepted[-2:]):return 'TWO_ZERO_ACCEPTED'
    if accepted and len(accepted)%8==0:return 'EIGHT_DISCOVERY_ROUNDS'
    return None

"""Frozen PR147 authority; one new1800s run, official threshold policy."""
from v42_arc_floor.common import *
from .base import OUT,SCI,BASE as BASE_HEAD,write
BUDGET=1800.
STOP=OUT/'STOP_REQUEST.json'
def old_columns():
 for h in read(SCI/'DW_CHECKPOINT_LATEST.json')['pool']:
  p=ROOT/h['file'];yield p.parent,dict(MESS=h['MESS'],file=p.name,SHA256=h['column_SHA'],file_SHA=h['file_SHA'])
def preserve_old():
 f=read(OUT/'PR147_BYTE_FREEZE.json');assert all(sha(ROOT/r['path'])==r['sha256'] for r in f['files']);return len(f['files'])
def verify_freeze():
 f=read(OUT/'EXECUTION_FREEZE.json');assert all(sha(ROOT/r['path'])==r['sha256'] for r in f['sources']);assert all(sha(OUT/p)==s for p,s in f['authorities'].items());preserve_old()
 assert not subprocess.check_output(['git','status','--porcelain','--','v42_dw_accelerated','tests/v42_dw_accelerated','v42_dw_runtime','tests/v42_dw_runtime'],cwd=ROOT,text=True)
 return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def table(name,rows):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',encoding='utf8',newline='') as f:
  keys=list(dict.fromkeys(k for r in rows for k in r)) or ['round'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def decision(lower,upper,authority):
 if lower>=authority['T_cert']:return 'PROVEN_MATERIAL'
 if upper<=authority['T_cert']:return 'PROVEN_NONMATERIAL'
 return 'INCONCLUSIVE'
def early_trigger(accepted,uppers,threshold):
 if len(accepted)>=2 and not any(accepted[-2:]):return 'TWO_ZERO_ACCEPTED'
 if len(uppers)>=4 and uppers[-4]-uppers[-1]<.0005:return 'THREE_ROUND_IMPROVEMENT_BELOW_0_0005'
 if uppers and uppers[-1]-threshold<=.0015:return 'UPPER_WITHIN_0_0015'
 return None

def ledger(name,directory=None):
 with ((directory or OUT)/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))

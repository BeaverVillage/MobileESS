"""PR149 frozen science, a distinct single1800s continuation grant."""
from v42_arc_floor.common import *
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_m1_dw_root_continuation_v2'
SCI=ROOT/'docs/v42_m1_dw_accelerated_root_integration'
ARC=ROOT/'docs/v42_m1_certified_arc_lp_floor_and_threshold_cg'
BASE_HEAD='867b86d2c503dfb991f08f27c3240c69aeba5153'
SCIENTIFIC_HEAD='31858f4e35b44caadeee2a72ef2ae2d35b74899b'
BUDGET=1800.;START_COLUMNS=1433
STOP=OUT/'STOP_REQUEST.json'
def write(n,d):
 p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n');q.replace(p)
def old_columns():
 for h in read(SCI/'DW_CHECKPOINT_LATEST.json')['pool']:
  p=ROOT/h['file'];yield p.parent,dict(MESS=h['MESS'],file=p.name,SHA256=h['column_SHA'],file_SHA=h['file_SHA'])
def preserve_old():
 f=read(OUT/'PR149_BYTE_FREEZE.json');assert all(sha(ROOT/r['path'])==r['sha256'] for r in f['files']);return len(f['files'])
def verify_freeze():
 f=read(OUT/'EXECUTION_FREEZE.json');assert all(sha(ROOT/r['path'])==r['sha256'] for r in f['sources']);assert all(sha(OUT/p)==s for p,s in f['authorities'].items());preserve_old()
 assert not subprocess.check_output(['git','status','--porcelain','--','v42_dw_continuation','tests/v42_dw_continuation'],cwd=ROOT,text=True)
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
 if len(uppers)>=6 and uppers[-6]-uppers[-1]<.00025:return 'FIVE_ROUND_IMPROVEMENT_BELOW_0_00025'
 if uppers and uppers[-1]-threshold<=.001:return 'UPPER_WITHIN_0_001'
 return None
def ledger(name,directory=None):
 with ((directory or OUT)/name).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))

import os,sys,json,hashlib,ast,time,math,itertools
from pathlib import Path
H=Path(__file__).absolute().parent
W=H.parent.parent
BASE=H.parent/'IEEE8500_MAY01_MESS6_B2B3_20260913'
ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
METHOD=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2'
sys.dont_write_bytecode=True
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
sys.path.insert(0,str(BASE))
import fleet_binding
fleet_binding.install();sys.path.insert(0,str(BASE))
from headroom_authority import install_power_binding
install_power_binding()
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import qmc
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def clean(x):
 if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
 if isinstance(x,np.generic):return clean(x.item())
 if isinstance(x,Path):return str(x)
 if isinstance(x,float) and not math.isfinite(x):return None
 return x
def save(p,v):
 p=Path(p);assert p.absolute().is_relative_to(H)
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
 tmp.write_text(json.dumps(clean(v),indent=2),encoding='utf-8');os.replace(tmp,p)
def rec(p):return dict(path=str(p),sha256=sha(p))
def state(**kw):save(H/'STATUS.json',dict(unix=time.time(),pid=os.getpid(),**kw))
def bind(path,names,ns):
 tree=ast.parse(Path(path).read_text(encoding='utf-8'))
 for node in tree.body:
  if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names:exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
source=W/'IEEE8500_actual_20260912_r3/actual8500.py'
bind(source,['Electrical','summary','outputs','continuous'],globals())
RULES=read(METHOD/'METHOD_FREEZE.json')['search']
HARD_TOLERANCE=1e-9
bind(METHOD/'frozen_code/qsafe.py',['q_bounds','constraints','feasible'],globals())
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
AUTH=MessElectricalAuthority.from_repository()
def data():
 with np.load(BASE/'actual_B2/B2/ACTUAL_INPUTS.npz') as z:return {k:z[k].copy() for k in z.files}
def check_stop():
 if (H/'STOP_REQUESTED').exists():raise InterruptedError('COOPERATIVE_STOP_AT_CANDIDATE_BOUNDARY')

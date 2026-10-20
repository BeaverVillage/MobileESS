from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
from v44_recovery_r019.a2_checkpoint import load
p=load('D:/MobileESS_V44/development/r018_verified_s14_state.pkl.gz')
print(type(p),list(p) if isinstance(p,dict) else len(p),flush=True)
if isinstance(p,dict):
 for k,v in p.items():print(k,type(v),list(v)[:8] if isinstance(v,dict) else '',flush=True)

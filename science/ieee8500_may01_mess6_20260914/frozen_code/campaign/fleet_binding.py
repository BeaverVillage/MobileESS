"""Process-local SHA-checked imports. Frozen repository remains read-only."""
import sys,json,hashlib,importlib.abc,importlib.util
from pathlib import Path
H=Path(__file__).absolute().parent
ROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
AUTH=json.loads((H/'FLEET_AUTHORITY.json').read_text(encoding='utf-8'))
IDS=tuple(AUTH['fleet_ids']);INITIAL=AUTH['initial_locations']
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
class FleetFinder(importlib.abc.MetaPathFinder):
 def __init__(self):self.rows={r['module']:r for r in json.loads((H/'CODE_DIFF.json').read_text(encoding='utf-8'))}
 def find_spec(self,fullname,path=None,target=None):
  if fullname in self.rows:
   r=self.rows[fullname]
   assert sha(r['source'])==r['source_sha256'] and sha(r['override'])==r['override_sha256']
   return importlib.util.spec_from_file_location(fullname,r['override'])
def install():
 sys.dont_write_bytecode=True
 if not any(isinstance(f,FleetFinder) for f in sys.meta_path):
  finder=FleetFinder();assert not(set(finder.rows)&set(sys.modules)),'INSTALL_FLEET_BINDING_BEFORE_IMPORTS'
  sys.meta_path.insert(0,finder)
 sys.path.insert(0,str(ROOT))
def require_production_authorization():
 raise RuntimeError('STOP_GATE: six-MESS preflight only; B2/B3 production requires next user instruction')

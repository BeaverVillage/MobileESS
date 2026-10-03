"""Block legacy M1 matrix/certificate authorities in the scientific lane."""
import importlib.abc,sys
from contextlib import contextmanager

BLOCKED=('v42_forensic','v42_threshold','v42_certificate','v42_monolithic',
         'v42_exact_start','v42_root_diagnostics','v42_benders','v42_benders_v2',
         'v42_benders_fullscale','v42_root_path_fix_v1')

def blocked(name):return any(name==p or name.startswith(p+'.') for p in BLOCKED)

class SelectedOnly(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if blocked(fullname):raise ImportError('SUPERSEDED_SCIENTIFIC_AUTHORITY_BLOCKED:'+fullname)
        return None

@contextmanager
def selected_imports():
    present=[name for name in sys.modules if blocked(name)]
    if present:raise ImportError('SUPERSEDED_AUTHORITY_ALREADY_IMPORTED:'+','.join(present))
    finder=SelectedOnly();sys.meta_path.insert(0,finder)
    try:yield
    finally:sys.meta_path.remove(finder)

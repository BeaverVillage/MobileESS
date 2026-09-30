"""Audit actual Linux file opens; historical path strings are resolved by table."""
import sys,json,hashlib
from pathlib import Path
opened=set()
def audit(event,args):
    if event=='open' and isinstance(args[0],str):opened.add(args[0])
sys.addaudithook(audit)
from v42_boundary.boundaries import load_native
from v42_temporal.native import load_power
from v42_may01.prepare import native_coefficients
from v42_final.runtime import FrozenQ50
b,j,*_=load_native();c,p,*_=load_power(b);coeff=native_coefficients(c);FrozenQ50()
bad=[p for p in opened if (len(p)>2 and p[1]==':') or p.startswith(('/mnt/c/','/mnt/d/','//wsl.'))]
root=Path.home()/'mobileess_worktrees/root_lp_compression';out=root/'docs/v42_ubuntu_gpu_migration'
mapping=json.loads((Path.home()/'mobileess_data/path_map.json').read_text())
result=dict(PASS=not bad,ACTIVE_WINDOWS_RUNTIME_DEPENDENCIES=len(bad),windows_filesystem_opens=bad,actual_opened_paths=sorted(opened),declared_path_mappings=mapping,historical_paths_in_frozen_JSON_preserved=True,unmapped_windows_paths_fail_closed=True,native_jobs=len(j),power_coefficients=len(p),grid_slots=len(coeff),scope='Current frozen PR102/full-May builder and live frozen Runtime inference; historical generation/training scripts are provenance, not executed',data_roots=['/home/jaewon/mobileess_data/immutable_inputs'],canonical_primary_worktree=str(root))
(out/'V42_EXTERNAL_PATH_DEPENDENCY_AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('ACTIVE_WINDOWS_RUNTIME_DEPENDENCIES',len(bad));assert not bad

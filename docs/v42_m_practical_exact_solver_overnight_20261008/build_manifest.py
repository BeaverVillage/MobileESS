"""Bind quiescent final raw artifacts; no solver and no self-reference."""
from practical_support import *
from owned_solver_guard_v4 import owned_controller_alive

def run():
    assert owned_controller_alive() is None,'CLOSE_OWNED_SOLVERS_BEFORE_FINAL_MANIFEST'
    assert read(OUT/'PACKAGE_AUDIT.json')['PASS'] and read(OUT/'FINAL_TEST_RUNS.json')['PASS']
    assert (OUT/'FINAL_REVIEW_KO.md').is_file() and (OUT/'OWNED_RESOURCE_MONITOR_RESULT.json').is_file()
    path=OUT/'SHA256_MANIFEST.json';files={}
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or p==path or '__pycache__' in p.parts or p.suffix=='.pyc':continue
        files[p.relative_to(ROOT).as_posix()]=dict(SHA256=sha(p),bytes=p.stat().st_size)
    science={p.relative_to(ROOT).as_posix():sha(p) for p in [hc.PARENT/'C3A_A.npz',hc.PARENT/'C3A_DATA.npz',hc.PARENT/'C3A_VALID_START.npz',OLD/'bb_controller.py',OLD/'objective_identity.py',Path(hc.exact_bound_module.__file__)]}
    atomic(path,dict(UTC=stamp(),schema_version=1,scope='Raw final package bytes; excludes this manifest itself and Python bytecode caches',optimize_calls=0,files=files,file_count=len(files),total_bytes=sum(r['bytes'] for r in files.values()),read_only_scientific_sources=science,self_reference_excluded=True))
    for name,r in files.items():assert sha(ROOT/name)==r['SHA256']
    print(json.dumps(dict(PASS=True,files=len(files),bytes=sum(r['bytes'] for r in files.values()),optimize_calls=0)))
if __name__=='__main__':run()

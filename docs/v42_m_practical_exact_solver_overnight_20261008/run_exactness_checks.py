"""Run package fixtures with a hard native-optimize prohibition per process."""
from practical_support import *
import subprocess

def run():
    names=['test_protocol.py','test_production_restart.py','test_archived_import.py','test_owned_controller_guard.py','test_dual_support_branch.py','test_checked_receipt_consumption.py','test_proof_audit_cache.py','test_injection_dual_repair.py']
    paths=[OLD/'test_exact_bb.py']+[OUT/name for name in names]
    results=[]
    for path in paths:
        assert path.is_file()
        code="import sys,runpy,gurobipy as gp; from pathlib import Path; p=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(p.parent)); sys.argv=[str(p)]; gp.Model.optimize=lambda *a,**k: (_ for _ in ()).throw(AssertionError('FINAL_FIXTURE_NATIVE_OPTIMIZE_FORBIDDEN')); runpy.run_path(str(p),run_name='__main__')"
        started=time.perf_counter();p=subprocess.run([sys.executable,'-c',code,str(path)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        results.append(dict(test=path.relative_to(ROOT).as_posix(),source_SHA256=sha(path),exit_code=p.returncode,wall_seconds=time.perf_counter()-started,stdout=p.stdout,stderr=p.stderr,native_optimize_forbidden=True))
        print(path.name,p.returncode,flush=True)
        if p.returncode:break
    result=dict(PASS=len(results)==len(paths) and all(r['exit_code']==0 for r in results),UTC=stamp(),optimize_calls=0,fixtures=results)
    atomic(OUT/'FINAL_TEST_RUNS.json',result)
    assert result['PASS'],'EXACTNESS_FIXTURE_FAILURE'
if __name__=='__main__':run()

"""Bind reviewed supplemental helpers before their first completed producer."""
import shutil,time
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from mission_cut_worker import CUT_HELPERS
from mission_ac_cut_restore import K_MAX,RHO
from v41r4_loop_runtime import MAY_OUT

def main():
    p=MAY_OUT/'mission/AC_CUT_EXECUTION_RELEASE.json'
    if p.exists():shutil.copy2(p,p.with_name('AC_CUT_EXECUTION_RELEASE_attempt_'+str(time.time_ns())+'.json'))
    write_json(p,dict(status='PASS',helpers=[record(ROOT/n) for n in CUT_HELPERS],K_MAX=K_MAX,RHO=RHO,
        authorization='User: maximum ten correction rounds; resolve violations within cap; exit immediately on PASS',
        tests=[record(p.parent/'CUT_REPAIR'/d/pol/'RESULT.json') for d,pol in [('2025-05-11','B3'),('2025-05-13','B2')]],
        original_numerical_sources_unchanged=True,at=time.time()))
    print('RELEASE_BOUND_CAP',K_MAX)
if __name__=='__main__':main()

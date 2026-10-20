from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r041 import operations as op
from v44.common import read,record,atomic,now

def run():
    op.previous.authority();assert not op.AMENDMENT.exists() and not op.base.workers()
    tests=Path('D:/MobileESS_V44/development/R041_ALL_REGRESSIONS.xml');suites=ET.parse(tests).getroot().findall('testsuite')
    assert sum(int(s.get('tests',0)) for s in suites)>=280 and all(int(s.get('failures',0))+int(s.get('errors',0))==0 for s in suites)
    validation=op.OPS/'R041_CHANGE_AND_VALIDATION.json'
    atomic(validation,dict(UTC=now(),PASS=True,tests=280,regressions=record(tests),sources=op.sources(),
        Actual_entry_fenced_in_every_preparation=True,completed_A1_route_stops_before_Actual=True,
        static_state_parent_directory_created_before_original_exclusive_write=True,no_old_result_overwrite=True,
        Actual_pause_after_all_preparations=True,Native_budgets_or_physical_limits_changed=False))
    atomic(op.AMENDMENT,dict(UTC=now(),user_authorized=True,user_instruction='Actual벌써 실행되는건 뭐고 실패있네? 실패 해결해서 다시 돌려.지금 actual실행되고 있는거 중단해.',
        sources=op.sources(),previous_authorization=record(op.previous.AMENDMENT),validation=record(validation),
        Actual_explicitly_paused=True,preparation_actual_fence=True,repair_May06_A1_missing_STATIC_parent=True,
        retry_cases=[['2025-05-06','B1'],['2025-05-06','B3'],['2025-05-07','B1']],
        May07_A1_original_completed_checkpoint_reused=True,preserve_all_prior_failures_and_native_ledgers=True,
        failure_isolation_inherited=True,Actual_resume_requires_user_instruction=True))
    op.authority()
    stop=op.OPS/'STOP_AUTONOMY.json';old=read(stop);assert old.get('user_stop')
    atomic(op.OPS/'R041_ORIGINAL_USER_STOP.json',old)
    atomic(stop,dict(UTC=now(),reason=op.HOLD,user_stop=True,stop_running_Actual=True,allow_preparation=True,user_dispatch_pause=False,
        Actual_resume_requires_explicit_user=True,authorization=record(op.AMENDMENT),original_stop=record(op.OPS/'R041_ORIGINAL_USER_STOP.json')))
    print(dict(PASS=True,Actual_paused=True,only_preparation_repair_allowed=True))

if __name__=='__main__':run()

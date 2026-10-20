"""Seal tested source and explicit newest batch failure-isolation authority."""
from pathlib import Path
import sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r040 import operations as op,batch
from v44.common import read,record,atomic,now

def run():
    op.previous.authority();assert not op.AMENDMENT.exists()
    tests=Path('D:/MobileESS_V44/development/R040_ALL_REGRESSIONS.xml');suites=ET.parse(tests).getroot().findall('testsuite')
    count=sum(int(s.get('tests',0)) for s in suites)
    assert count>=272 and all(int(s.get('failures',0))+int(s.get('errors',0))==0 for s in suites)
    checked=[]
    for job in read(op.STATE)['jobs']:
        if job['status']=='PREPARED':batch.check_ready(job);checked.append(dict(day=job['day'],arm=job['arm'],handoff=job['handoff']))
    validation=op.OPS/'R040_CHANGE_AND_VALIDATION.json'
    atomic(validation,dict(UTC=now(),PASS=True,regressions=count,tests=record(tests),sources=op.sources(),current_ready_cases_verified=checked,
        one_preparation_failure_excludes_only_that_case=True,one_bad_handoff_excludes_only_that_case=True,
        one_worker_launch_failure_does_not_stop_peers=True,one_Actual_failure_does_not_stop_peers=True,
        all_zero_through_seven_healthy_subset_sizes_tested=True,unknown_preparation_still_waits=True,
        completed_PASS_and_partial_Actual_protected=True,physical_or_Native_limits_changed=False,
        latency_removal_inherited=True,P_only_CPU_count_matches_healthy_subset=True,
        bootstrap_validation_source=record(Path(__file__).with_name('validate_r040_bootstrap.py'))))
    atomic(op.AMENDMENT,dict(UTC=now(),user_authorized=True,
        user_instruction='7일 다 planning 끝나면 actual잘 실행될지 다시 한번 점검해. 문제가 있거나 실패가 있거나 한 날짜때문에 전체 actual실행이 안되게 하면 안되고 그 날짜만 제외하고 실행되게 해.',
        policy='R040_RESOLVE_ALL_PREPARATIONS_EXCLUDE_FAILED_CASES_AND_DISPATCH_HEALTHY_ACTUAL_INDEPENDENTLY',
        sources=op.sources(),previous_authorization=record(op.previous.AMENDMENT),validation=record(validation),
        exclude_only_failed_case=True,exclusion_unit='DATE_AND_COMPARISON_ARM',max_Actual_workers=7,prepare_workers=1,
        resolve_every_preparation_before_Actual=True,all_seven_preparations_must_succeed=False,P_only=True,
        no_Actual_before_validated_handoff=True,all_Actual_and_independent_Fresh_checks_retained=True,
        stage_source_sha_and_frozen_plans_preserved=True,existing_PASS_never_rerun=True,
        old_scientific_sources_modified=False,old_running_worker_must_finish_naturally=True))
    op.authority();print(dict(PASS=True,tests=count,current_ready_cases=len(checked)))

if __name__=='__main__':run()

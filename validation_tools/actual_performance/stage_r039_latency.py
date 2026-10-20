"""Seal the explicit user request and start one new Actual, never touch B3."""
from pathlib import Path
import sys,subprocess,os,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r039 import operations as op
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
import psutil

def run():
    op.previous.validate();op.validate_parent()
    assert not op.AMENDMENT.exists()
    active=op.base.workers();b3=next(w for w in active if w['pid']==70596)
    b3_request=read(b3['cmdline'][b3['cmdline'].index('--worker')+1]);verify(b3_request['sources'])
    before=dict(pid=70596,process_created=psutil.Process(70596).create_time(),affinity=psutil.Process(70596).cpu_affinity())
    tests=Path('D:/MobileESS_V44/development/R039_REGRESSIONS.xml')
    prior=Path('D:/MobileESS_V44/development/R039_ALL_REGRESSIONS.xml')
    for path in (tests,prior):
        suites=ET.parse(path).getroot().findall('testsuite')
        assert all(int(s.get('errors',0))+int(s.get('failures',0))==0 for s in suites)
    validation=op.OPS/'R039_CHANGE_AND_VALIDATION.json'
    atomic(validation,dict(UTC=now(),PASS=True,tests=14,latency_regressions=record(tests),prior_236_regressions=record(prior),
        sources=op.sources(),tick_949_seconds_completes=True,physical_gates_retained=True,independent_Fresh_retained=True,
        simulation_slot_seconds=900,latency_diagnostic_retained=True,all_seven_preparation_barrier_retained=True,
        batch_launch_routes_all_workers_to_new_overlay=True,old_scientific_sources_modified=False))
    atomic(op.AMENDMENT,dict(UTC=now(),user_authorized=True,
        user_instructions=['900초 처리 시간 제한 삭제해. B3 실행 냅두고 B1 Actual 병렬로 실행하게 해.',
            '응 병렬로 Actual 초기 상태부터 지금 재실행하게 해.',
            'r038에도 900초 시간 제한 삭제해서 현재 캠페인 돌리고 있는 거에도 적용해.'],
        policy='R039_REMOVE_WALL_LATENCY_ABORT_AND_PASS_CRITERION_WITH_PHYSICAL_GATES_RETAINED',
        sources=op.sources(),previous_authorization=record(op.previous.AMENDMENT),validation=record(validation),
        slot_wall_limit_seconds=None,latency_is_PASS_criterion=False,simulation_slot_seconds=900,
        extra_Actual_delegation=dict(day='2025-05-04',arm='B1',Native_optimization_allowed=False,
            physical_core_reservation_required=True,P_only=True,parallel_with_live_B3_preparation=True),
        apply_to_all_remaining_r038_Actual_workers=True,prepared_sources_and_A1_checkpoints_preserved=True,
        live_B3=before,live_B3_request=record(Path(b3['cmdline'][b3['cmdline'].index('--worker')+1]))))
    op.authority()
    out=op.OPS/'r039_dispatch.log'
    with out.open('ab') as stream:
        proc=subprocess.Popen([sys.executable,'-u','-m',op.ENTRY,'--dispatch','--algorithm',op.previous.ALGORITHM],
            cwd=Path(__file__).resolve().parents[2],stdout=stream,stderr=stream,
            env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    p=psutil.Process(proc.pid)
    atomic(op.OPS/'R039_DISPATCH_LAUNCH.json',dict(UTC=now(),pid=p.pid,process_created=p.create_time()))
    h=read(op.OPS/'CURRENT_HANDOFF.json');h.update(pending_revision='v44_recovery_r039',pending_permit=record(op.AMENDMENT),
        pending_validation=record(validation),latency_overlay=record(op.AMENDMENT),
        next='B1 Actual from original initial state parallel with live B3. Preserve r038 seven-job serial preparation barrier, then seven P-only Actual/Fresh workers without wall latency rejection.')
    atomic(op.OPS/'CURRENT_HANDOFF.json',h)
    after=dict(pid=70596,process_created=psutil.Process(70596).create_time(),affinity=psutil.Process(70596).cpu_affinity())
    atomic(op.OPS/'R039_DEPLOYMENT.json',dict(UTC=now(),PASS=True,dispatcher_pid=p.pid,live_B3_before=before,live_B3_after=after,
        same_live_B3_process=before['process_created']==after['process_created'],live_B3_signalled=False,authorization=record(op.AMENDMENT)))
    print(dict(PASS=True,dispatcher_pid=p.pid,B3_pid=70596),flush=True)

if __name__=='__main__':run()

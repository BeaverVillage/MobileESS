"""Apply the user's explicit campaign resume after verified storage cleanup."""
from pathlib import Path
import json,shutil,sqlite3,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import psutil
import v44_recovery_r029
from v44_recovery_r037 import operations as op
from v44.common import read,record,verify,atomic,now
from v44.locks import alive,process_identity

INSTRUCTION='작업 끝났으면 5월3일 B1부터 캠페인 시작해. 최신버전이 r37인가? 최신버전 시작해.'

def run():
    import v44_audit_archive as archive
    from v44.config import B2_ORDER,MAIN_ORDER
    from v44_recovery_r029 import failure_continue
    archive.guard();op.validate()
    archive_result=op.OPS/'LEGACY_RAW_ARCHIVE_RESULT.json'
    result=read(archive_result)
    assert result['PASS'] and not result['errors']
    plan=read(archive.PLAN);expected=2*len(plan['eligible_candidates'])
    assert result['catalog_archived_files']==expected
    with sqlite3.connect(archive.CATALOG) as db:
        assert db.execute("SELECT COUNT(*) FROM archived WHERE state!='ARCHIVED'").fetchone()[0]==0
    verify(read(op.OPS/'LEGACY_RAW_ARCHIVE_PRE_DELETE_PROOF.json')['metadata'])
    proofs=[op.OPS/name for name in ('R035_EXISTING_RAW_CLEANUP.json',
        'LEGACY_RAW_ARCHIVE_PROTECTED_VERIFICATION.json','LEGACY_RAW_ARCHIVE_EXPORT_VERIFICATION.json')]
    assert all(read(p)['PASS'] for p in proofs)
    with op.install():
        state=op.base.states(op.CAMPAIGN);blocked=failure_continue.deferred_dates(op.OPS)
        eligible=[k for k in (*B2_ORDER,*MAIN_ORDER) if state.get(k)=='READY' and k not in blocked]
        assert eligible[0]==('2025-05-03','B1')
        assert not any(state.get(k)=='READY' and op.latest(op.CAMPAIGN,*k) is not None
            and read(op.latest(op.CAMPAIGN,*k)/'RESULT.json').get('error')=="RuntimeError('V43_ACTUAL_USER_40_MINUTE_WALL_LIMIT_REACHED')"
            for k in MAIN_ORDER)
    out=op.OPS/'USER_RESUME_R037_AFTER_STORAGE_20261018';out.mkdir(exist_ok=False)
    for name in ('CURRENT_HANDOFF.json','STOP_AUTONOMY.json'):
        shutil.copy2(op.OPS/name,out/name)
    ps=out/'register.ps1'
    ps.write_text("""$ErrorActionPreference='Stop'
$taskName='MobileESS_V44_Campaign004_Recovery_R032'
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'REPLACE_OUT/ScheduledTask.before.xml' -Encoding Unicode
$actions=@(
  (New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 D:/v44_r022_rowgen_20261017/validation_tools/actual_performance/launch_r036_storage.py' -WorkingDirectory 'D:/v44_r022_rowgen_20261017'),
  (New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 -u -m v44_recovery_r037.operations --watchdog --algorithm v44_recovery_r029.operations' -WorkingDirectory 'D:/v44_r022_rowgen_20261017')
)
Set-ScheduledTask -TaskName $taskName -Action $actions | Out-Null
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'REPLACE_OUT/ScheduledTask.after.xml' -Encoding Unicode
""".replace('REPLACE_OUT',out.as_posix()),encoding='utf-8-sig')
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ps)],check=True,capture_output=True)
    atomic(op.OPS/'USER_STORAGE_REVIEW_RELEASE.json',dict(UTC=now(),user_authorized=True,
        action='RESUME_CAMPAIGN_AFTER_STORAGE_REVIEW',user_instruction=INSTRUCTION,
        revision=op.ENTRY,start_day='2025-05-03',start_arm='B1',archive_result=record(archive_result),
        verification=[record(p) for p in proofs],authorization=record(op.AMENDMENT),launcher=record(__file__)))
    stop=op.OPS/'STOP_AUTONOMY.json'
    assert read(stop)['reason']=='USER_WAIT_AFTER_MAY02_B3_STORAGE_REVIEW'
    stop.rename(out/'RELEASED_STOP_AUTONOMY.json')
    op.require_user_resume()
    old=read(op.OPS/'USER_STORAGE_REVIEW_HEARTBEAT.json')
    deadline=time.monotonic()+25
    while alive(old) and time.monotonic()<deadline:time.sleep(1)
    assert not alive(old),'CLEANUP_ONLY_HELPER_DID_NOT_EXIT'
    handoff=read(op.OPS/'CURRENT_HANDOFF.json')
    handoff.update(UTC=now(),pending_revision='v44_recovery_r037',pending_permit=record(op.AMENDMENT),
        pending_validation=record(op.OPS/'R037_CHANGE_AND_VALIDATION.json'),pending_handover_pid=psutil.Process().pid,
        user_dispatch_pause=False,dispatch_hold_reason=None,latest_user_instruction=INSTRUCTION,
        next='Start May03 B1 with r037; retain all completed cases and shared lossless audit storage.')
    atomic(op.OPS/'CURRENT_HANDOFF.json',handoff)
    atomic(op.OPS/'R037_HANDOVER_HEARTBEAT.json',dict(UTC=now(),**process_identity(),phase='USER_AUTHORIZED_POST_CLEANUP_RESUME'))
    maintenance=op.previous.storage_maintenance.start(op.previous)
    log=out/'supervisor.log'
    with log.open('ab') as stream:
        process=subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),'-X','utf8','-u','-m',op.ENTRY,
            '--watchdog','--algorithm',op.ALGORITHM],cwd=Path(__file__).resolve().parents[2],
            stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError('R037_SUPERVISOR_EXITED:'+log.read_text(errors='replace')[-3000:])
        current=read(op.OPS/'CURRENT_HANDOFF.json');workers=op.base.workers()
        if current['active_revision']=='v44_recovery_r037' and workers:break
        time.sleep(1)
    else:raise RuntimeError('R037_FIRST_WORKER_NOT_OBSERVED')
    request=op.OPS/'requests/2025-05-03_B1_attempt003.json'
    case=read(request);assert (case['day'],case['arm'])==('2025-05-03','B1')
    op.authorize(case);verify(case['sources'])
    assert any(op.ENTRY in w['cmdline'] and str(request) in w['cmdline'] for w in workers)
    current=read(op.OPS/'CURRENT_HANDOFF.json')
    current.update(UTC=now(),entry=f'python -m {op.ENTRY} --watchdog --algorithm {op.ALGORITHM}',
        user_dispatch_pause=False,dispatch_hold_reason=None,pending_handover_mode=None,
        latest_user_instruction=INSTRUCTION,user_resume=record(op.OPS/'USER_STORAGE_REVIEW_RELEASE.json'),
        legacy_storage_cleanup=record(archive_result))
    atomic(op.OPS/'CURRENT_HANDOFF.json',current)
    value=dict(UTC=now(),PASS=True,revision=op.ENTRY,supervisor_pid=process.pid,
        first_case=case['case_root'],request=record(request),workers=workers,
        maintenance=maintenance,storage_cleanup=record(archive_result),
        source_pins_verified=len(case['sources']),free_GiB=shutil.disk_usage('D:/').free/2**30)
    atomic(out/'RESULT.json',value);print(json.dumps(value,ensure_ascii=False),flush=True)

if __name__=='__main__':run()

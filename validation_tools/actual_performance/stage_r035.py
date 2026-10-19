"""Seal the reduction and replace only the pending natural-boundary helper."""
from pathlib import Path
import json,sys,subprocess,time,shutil
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r035 import operations as op
from v44.common import read,record,verify,atomic,now

def run():
    out=Path('D:/MobileESS_V44/development/R035_DEPLOYMENT_20261018')
    out.mkdir(exist_ok=False)
    OPS=op.OPS
    proofs=[Path('D:/MobileESS_V44/development')/name for name in (
        'R035_RECORD_QUEUE_PROBES_20261018/RESULT.json',
        'R035_STORAGE_PROBES_20261018c/RESULT.json',
        'DISK_PHYSICAL_AUDIT_20261018.json')]
    assert all(read(p)['PASS'] for p in proofs[:2])
    import xml.etree.ElementTree as ET
    tests=Path('D:/MobileESS_V44/development/R035_REGRESSIONS_20261018.xml')
    suites=ET.parse(tests).getroot().findall('testsuite')
    assert sum(int(s.attrib.get('tests',0)) for s in suites)==171
    assert all(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0))==0 for s in suites)
    handoff=read(OPS/'CURRENT_HANDOFF.json')
    assert handoff['active_revision']=='v44_recovery_r032'
    assert handoff['pending_revision']=='v44_recovery_r034'
    oldhold=read(OPS/'STOP_AUTONOMY.json')
    assert oldhold['reason']==op.previous.HOLD_REASON and not oldhold.get('user_stop')
    hb=read(OPS/'R034_HANDOVER_HEARTBEAT.json')
    hp=psutil.Process(hb['pid'])
    assert abs(hp.create_time()-hb['process_created'])<.001
    assert 'v44_recovery_r034.operations' in hp.cmdline() and '--handover' in hp.cmdline()
    worker=psutil.Process(56372)
    assert abs(worker.create_time()-1792293590.9875228)<.001
    identity=dict(pid=worker.pid,created=worker.create_time(),affinity=worker.cpu_affinity(),priority=int(worker.nice()))
    request=read(OPS/'requests/2025-05-02_B3_attempt015.json')
    pins=request['sources'];verify(pins)
    for name in ('CURRENT_HANDOFF.json','STOP_AUTONOMY.json'):
        shutil.copy2(OPS/name,out/(name+'.before'))
    monitors=[]
    for stem in ('collect_watchdog','audit_active_revision'):
        source=OPS/(stem+'_r034.py');target=OPS/(stem+'_r035.py')
        assert not target.exists()
        text=source.read_text(encoding='utf-8').replace("'v44_recovery_r033','v44_recovery_r034'", "'v44_recovery_r033','v44_recovery_r034','v44_recovery_r035'")
        if stem=='audit_active_revision':
            insert="if revision=='v44_recovery_r035':\n    value.update(active_exact_storage_authorization=record(module.AMENDMENT),active_exact_storage_source_sha=digest(module.sources()),native_checkpoint_fast_path=False,physical_checks_removed=0)\n"
            text=text.replace('if pending:\n    handover=',insert+'if pending:\n    handover=')
        target.write_text(text,encoding='utf-8');monitors.append(record(target))
    validation=OPS/'R035_CHANGE_AND_VALIDATION.json'
    atomic(validation,dict(UTC=now(),PASS=True,tests=171,regressions=record(tests),
        evidence=[record(p) for p in proofs],sources=op.sources(),
        removed=['Repeated immutable control JSON conversion in slot/event rows','Immediate unchanged native queue rereads without callbacks','Writing byte-identical complete raw audit records again'],
        retained=['Full first and final live controls and ratings','Every chronological native TIME solve and queue',
            'Current candidate checks','Independent Fresh measurements','Source hash guards','Exact duplicate full-key comparison'],
        existing_cleanup_boundary=str(op.CLEANUP_CASE),cleanup_only_after_case_and_coordinator_exit=True,
        duplicate_plan=record('D:/MobileESS_V44/development/EXACT_AUDIT_DUPLICATE_PLAN_20261018.json'),
        whole_Actual_speedup_measured=False,physical_checks_removed=0,native_checkpoint_fast_path=False))
    atomic(op.AMENDMENT,dict(UTC=now(),policy=op.POLICY,user_authorized=True,
        user_instruction='캠페인에서 저장하는 것도 효율화가 필요할 것 같아. 수정해.',
        cleanup_instruction='실행에 지장 없게 이미 저장된 것들 중 중복되는 것 삭제하는 건 5월 2일 B3 끝나면 실시해.',
        cleanup_after_case_root=str(op.CLEANUP_CASE),cleanup_condition='NO_LIVE_WORKERS_OR_COORDINATOR_AND_TERMINAL_MAY02_B3_RESULT',
        sources=op.sources(),previous_authorization=record(op.previous.AMENDMENT),validation=record(validation),
        monitoring_sources=monitors,native_checkpoint_fast_path=False,physical_checks_removed=0,
        deployment='AFTER_RUNNING_CASE_EXITS_NATURALLY_NO_WORKER_RESTART'))
    op.validate()
    # Validate inherited decorator receipts without creating a worker or case.
    with op.install():
        case=op.base.decorate(dict(request),read(op.PERMIT))
        op.authorize(case);verify(case['sources'])
    # Do not change sealed monitoring files or any live scientific source.
    for stem in ('collect_watchdog','audit_active_revision'):
        target=OPS/(stem+'_r032.py')
        assert str(target).lower() not in {r['path'].lower() for r in pins}
        shutil.copy2(target,out/(target.name+'.before'))
        prefix=("# Route the authorized lightweight revision to its compatible inspector.\n"
            "import json as _r035_json,runpy as _r035_runpy\nfrom pathlib import Path as _r035_Path\n"
            "_r035_ops=_r035_Path(__file__).parent\n"
            "_r035_handoff=_r035_json.loads((_r035_ops/'CURRENT_HANDOFF.json').read_text(encoding='utf-8-sig'))\n"
            "if 'v44_recovery_r035' in (_r035_handoff.get('active_revision'),_r035_handoff.get('pending_revision')):\n"
            f"    _r035_runpy.run_path(str(_r035_ops/'{stem}_r035.py'),run_name='__main__')\n"
            "    raise SystemExit(0)\n")
        target.write_text(prefix+target.read_text(encoding='utf-8'),encoding='utf-8')
    verify(pins)
    hp.terminate();hp.wait(timeout=15)  # This is ONLY the idle handover helper.
    atomic(OPS/'STOP_AUTONOMY.json',dict(oldhold,UTC=now(),reason=op.HOLD_REASON,
        authorization=record(op.AMENDMENT),scope='BLOCK_NEXT_DISPATCH_ONLY_FOR_REQUESTED_POST_B3_CLEANUP_AND_EXACT_STORAGE'))
    handoff.update(UTC=now(),pending_revision='v44_recovery_r035',pending_permit=record(op.AMENDMENT),
        pending_validation=record(validation),collector=str(OPS/'collect_watchdog_r035.py'),
        active_source_auditor=str(OPS/'audit_active_revision_r035.py'),
        latest_user_instruction=read(op.AMENDMENT)['user_instruction'],
        next='Finish May02 B3 unchanged; then deduplicate exact existing raw copies preserving paths, and start next worker with efficient exact raw storage and record/queue reductions.')
    atomic(OPS/'CURRENT_HANDOFF.json',handoff)
    ps=out/'register.ps1'
    ps.write_text('''$ErrorActionPreference='Stop'
$taskName='MobileESS_V44_Campaign004_Recovery_R032'
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'D:/MobileESS_V44/development/R035_DEPLOYMENT_20261018/ScheduledTask.before.xml' -Encoding Unicode
$action=New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 -u -m v44_recovery_r035.operations --handover --algorithm v44_recovery_r029.operations' -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Set-ScheduledTask -TaskName $taskName -Action $action | Out-Null
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'D:/MobileESS_V44/development/R035_DEPLOYMENT_20261018/ScheduledTask.after.xml' -Encoding Unicode
''',encoding='utf-8-sig')
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ps)],check=True,capture_output=True)
    process=subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),'-X','utf8','-u','-m',op.ENTRY,
        '--handover','--algorithm',op.ALGORITHM],cwd=Path(__file__).resolve().parents[2])
    for _ in range(30):
        path=OPS/'R035_HANDOVER_HEARTBEAT.json'
        if path.exists() and read(path).get('pid')==process.pid:break
        if process.poll() is not None:raise RuntimeError('R035_HELPER_EXITED')
        time.sleep(.5)
    else:raise RuntimeError('NO_R035_HEARTBEAT')
    handoff=read(OPS/'CURRENT_HANDOFF.json');handoff['pending_handover_pid']=process.pid
    atomic(OPS/'CURRENT_HANDOFF.json',handoff)
    verify(pins)
    assert worker.is_running() and abs(worker.create_time()-identity['created'])<.001
    assert worker.cpu_affinity()==identity['affinity'] and int(worker.nice())==identity['priority']
    result=dict(UTC=now(),PASS=True,state='PENDING_NATURAL_CASE_BOUNDARY',handover_pid=process.pid,
        worker_untouched=identity,authorization=record(op.AMENDMENT),validation=record(validation),
        old_source_seals_verified=len(pins),physical_checks_removed=0,native_checkpoint_fast_path=False,
        tests=171,whole_Actual_speedup_measured=False)
    atomic(out/'RESULT.json',result);print(json.dumps(result))

if __name__=='__main__':run()

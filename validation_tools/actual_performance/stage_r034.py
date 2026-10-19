"""Seal the reduction and replace only the pending natural-boundary helper."""
from pathlib import Path
import json,sys,subprocess,time,shutil
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r034 import operations as op
from v44.common import read,record,verify,atomic,now

def run():
    out=Path('D:/MobileESS_V44/development/R034_DEPLOYMENT_20261018')
    out.mkdir(exist_ok=False)
    OPS=op.OPS
    proofs=[Path('D:/MobileESS_V44/development')/name for name in (
        'R034_BANK_GATE_BENCHMARK_20261018_1435/RESULT.json',
        'R034_CONTROL_KEY_BENCHMARK_20261018.json',
        'R034_COMPLETE_PROBES_20261018b/RESULT.json')]
    assert all(read(p)['PASS'] for p in proofs)
    import xml.etree.ElementTree as ET
    tests=Path('D:/MobileESS_V44/development/R034_REGRESSIONS_20261018.xml')
    suites=ET.parse(tests).getroot().findall('testsuite')
    assert sum(int(s.attrib.get('tests',0)) for s in suites)==149
    assert all(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0))==0 for s in suites)
    handoff=read(OPS/'CURRENT_HANDOFF.json')
    assert handoff['active_revision']=='v44_recovery_r032'
    assert handoff['pending_revision']=='v44_recovery_r033'
    oldhold=read(OPS/'STOP_AUTONOMY.json')
    assert oldhold['reason']==op.previous.HOLD_REASON and not oldhold.get('user_stop')
    hb=read(OPS/'R033_HANDOVER_HEARTBEAT.json')
    hp=psutil.Process(hb['pid'])
    assert abs(hp.create_time()-hb['process_created'])<.001
    assert 'v44_recovery_r033.operations' in hp.cmdline() and '--handover' in hp.cmdline()
    worker=psutil.Process(56372)
    assert abs(worker.create_time()-1792293590.9875228)<.001
    identity=dict(pid=worker.pid,created=worker.create_time(),affinity=worker.cpu_affinity(),priority=int(worker.nice()))
    request=read(OPS/'requests/2025-05-02_B3_attempt015.json')
    pins=request['sources'];verify(pins)
    for name in ('CURRENT_HANDOFF.json','STOP_AUTONOMY.json'):
        shutil.copy2(OPS/name,out/(name+'.before'))
    monitors=[]
    for stem in ('collect_watchdog','audit_active_revision'):
        source=OPS/(stem+'_r033.py');target=OPS/(stem+'_r034.py')
        assert not target.exists()
        text=source.read_text(encoding='utf-8').replace("'v44_recovery_r032','v44_recovery_r033'", "'v44_recovery_r032','v44_recovery_r033','v44_recovery_r034'")
        if stem=='audit_active_revision':
            insert="if revision=='v44_recovery_r034':\n    value.update(active_lightweight_authorization=record(module.AMENDMENT),active_lightweight_source_sha=digest(module.sources()),native_checkpoint_fast_path=False,physical_checks_removed=0)\n"
            text=text.replace('if pending:\n    handover=',insert+'if pending:\n    handover=')
        target.write_text(text,encoding='utf-8');monitors.append(record(target))
    validation=OPS/'R034_CHANGE_AND_VALIDATION.json'
    atomic(validation,dict(UTC=now(),PASS=True,tests=149,regressions=record(tests),
        evidence=[record(p) for p in proofs],sources=op.sources(),
        removed=['Impossible pre-measurement cache keys','Repeated tap/capacitor/counter reads for first historical key'],
        retained=['Full first and final live controls and ratings','Every chronological native TIME solve and queue',
            'Current candidate checks','Independent Fresh measurements','Source hash guards','Exact duplicate full-key comparison'],
        rejected_projection='9.3% fewer static property reads but only 0.8% faster component; not installed',
        whole_Actual_speedup_measured=False,physical_checks_removed=0,native_checkpoint_fast_path=False))
    atomic(op.AMENDMENT,dict(UTC=now(),policy=op.POLICY,user_authorized=True,
        user_instruction='검사가 너무 많은지, 불필요한 검사가 있는지 점검해. 경량화할 필요가 있을 것 같아.',
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
            "import json as _r034_json,runpy as _r034_runpy\nfrom pathlib import Path as _r034_Path\n"
            "_r034_ops=_r034_Path(__file__).parent\n"
            "_r034_handoff=_r034_json.loads((_r034_ops/'CURRENT_HANDOFF.json').read_text(encoding='utf-8-sig'))\n"
            "if 'v44_recovery_r034' in (_r034_handoff.get('active_revision'),_r034_handoff.get('pending_revision')):\n"
            f"    _r034_runpy.run_path(str(_r034_ops/'{stem}_r034.py'),run_name='__main__')\n"
            "    raise SystemExit(0)\n")
        target.write_text(prefix+target.read_text(encoding='utf-8'),encoding='utf-8')
    verify(pins)
    hp.terminate();hp.wait(timeout=15)  # This is ONLY the idle handover helper.
    atomic(OPS/'STOP_AUTONOMY.json',dict(oldhold,UTC=now(),reason=op.HOLD_REASON,
        authorization=record(op.AMENDMENT),scope='BLOCK_NEXT_DISPATCH_ONLY_FOR_SAFE_LIGHTWEIGHT_HANDOVER'))
    handoff.update(UTC=now(),pending_revision='v44_recovery_r034',pending_permit=record(op.AMENDMENT),
        pending_validation=record(validation),collector=str(OPS/'collect_watchdog_r034.py'),
        active_source_auditor=str(OPS/'audit_active_revision_r034.py'),
        latest_user_instruction=read(op.AMENDMENT)['user_instruction'],
        next='Finish current case unchanged; next worker inherits r033 encoding plus exact cache-key read reductions.')
    atomic(OPS/'CURRENT_HANDOFF.json',handoff)
    ps=out/'register.ps1'
    ps.write_text('''$ErrorActionPreference='Stop'
$taskName='MobileESS_V44_Campaign004_Recovery_R032'
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'D:/MobileESS_V44/development/R034_DEPLOYMENT_20261018/ScheduledTask.before.xml' -Encoding Unicode
$action=New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 -u -m v44_recovery_r034.operations --handover --algorithm v44_recovery_r029.operations' -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Set-ScheduledTask -TaskName $taskName -Action $action | Out-Null
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'D:/MobileESS_V44/development/R034_DEPLOYMENT_20261018/ScheduledTask.after.xml' -Encoding Unicode
''',encoding='utf-8-sig')
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ps)],check=True,capture_output=True)
    process=subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),'-X','utf8','-u','-m',op.ENTRY,
        '--handover','--algorithm',op.ALGORITHM],cwd=Path(__file__).resolve().parents[2])
    for _ in range(30):
        path=OPS/'R034_HANDOVER_HEARTBEAT.json'
        if path.exists() and read(path).get('pid')==process.pid:break
        if process.poll() is not None:raise RuntimeError('R034_HELPER_EXITED')
        time.sleep(.5)
    else:raise RuntimeError('NO_R034_HEARTBEAT')
    handoff=read(OPS/'CURRENT_HANDOFF.json');handoff['pending_handover_pid']=process.pid
    atomic(OPS/'CURRENT_HANDOFF.json',handoff)
    verify(pins)
    assert worker.is_running() and abs(worker.create_time()-identity['created'])<.001
    assert worker.cpu_affinity()==identity['affinity'] and int(worker.nice())==identity['priority']
    result=dict(UTC=now(),PASS=True,state='PENDING_NATURAL_CASE_BOUNDARY',handover_pid=process.pid,
        worker_untouched=identity,authorization=record(op.AMENDMENT),validation=record(validation),
        old_source_seals_verified=len(pins),physical_checks_removed=0,native_checkpoint_fast_path=False,
        tests=149,whole_Actual_speedup_measured=False)
    atomic(out/'RESULT.json',result);print(json.dumps(result))

if __name__=='__main__':run()

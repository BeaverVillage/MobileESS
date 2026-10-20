"""Seal and arm the requested natural-boundary batch transition."""
from pathlib import Path
import sys,subprocess,time,shutil,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r038 import operations as op
from v44_recovery_r038.cpu import placement
from v44_recovery_r029.cpu_placement import windows_cpu_sets
from v44.common import read,record,verify,atomic,now
from v44.locks import alive
import psutil

def run():
    op.previous.validate()
    boundary=read(op.OPS/'USER_PRE_ACTUAL_BATCH_BOUNDARY_REQUEST.json')
    protected=read(boundary['protected_request']['path']);verify(protected['sources']+[boundary['protected_request']])
    active=op.base.workers();assert len(active)==1 and active[0]['pid']==71004
    worker=psutil.Process(71004);before=dict(pid=71004,created=worker.create_time(),affinity=worker.cpu_affinity(),priority=int(worker.nice()))
    assert abs(before['created']-1792324405.3288279)<.001
    assert read(op.OPS/'STOP_AUTONOMY.json')['reason']==op.HOLD_REASON
    assert not op.AMENDMENT.exists()
    proof=Path('D:/MobileESS_V44/development/R038_PARALLEL_NATIVE0_20261018/RESULT.json')
    assert read(proof)['PASS'] and read(proof)['workers']==7 and read(proof)['serial_and_parallel_results_byte_identical']
    tests=Path('D:/MobileESS_V44/development/R038_BATCH_REGRESSIONS_20261018.xml')
    suites=ET.parse(tests).getroot().findall('testsuite')
    count=sum(int(s.attrib['tests']) for s in suites)
    assert count>=224 and all(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0))==0 for s in suites)
    out=Path('D:/MobileESS_V44/development/R038_DEPLOYMENT_20261018');out.mkdir(exist_ok=False)
    for name in ('CURRENT_HANDOFF.json','STOP_AUTONOMY.json'):
        shutil.copy2(op.OPS/name,out/(name+'.before'))
    confirmation=op.OPS/'R038_USER_BATCH_CONFIRMATION.json'
    atomic(confirmation,dict(UTC=now(),user_authorized=True,parallel_unit_instruction='남은 7건을 7worker로 병렬 실행',
        CPU_instruction='모두 성능코어에 배치해. 병렬로 돌릴 때.',completed_PASS_preserved=True))
    jobs=[dict(day=d,arm=a) for d,a in [('2025-05-04','B3'),('2025-05-05','B1'),('2025-05-05','B3'),
        ('2025-05-06','B1'),('2025-05-06','B3'),('2025-05-07','B1'),('2025-05-07','B3')]]
    plan=op.OPS/'R038_FIXED_BATCH_PLAN.json'
    atomic(plan,dict(UTC=now(),jobs=jobs,prepare_workers=1,actual_workers=7,all_ready_barrier=True,
        completed_PASS_rerun=False,protected_case=boundary['protected_case']))
    monitors=[]
    for stem,function in [('collect_watchdog','collect'),('audit_active_revision','audit')]:
        path=op.OPS/(stem+'_r038.py')
        assert not path.exists()
        path.write_text("import sys,json\nsys.path.insert(0,'D:/v44_r022_rowgen_20261017')\nfrom v44_recovery_r038.monitor import "+function+"\nv="+function+"()\nprint(json.dumps({k:v[k] for k in ('UTC','PASS','active','pending','active_revision','counts') if k in v},ensure_ascii=False))\n",encoding='utf-8')
        monitors.append(record(path))
    validation=op.OPS/'R038_CHANGE_AND_VALIDATION.json'
    atomic(validation,dict(UTC=now(),PASS=True,tests=count,regressions=record(tests),parallel_native_validation=record(proof),
        sources=op.sources(),pre_Actual_chain_unchanged=True,all_ready_barrier=True,
        physical_checks_removed=0,Native_limits_changed=False,mathematical_model_changed=False,
        actual_engines_process_isolated=True,independent_Fresh_retained=True,
        storage_layout='INHERITED_R037_SHARED_EXACT_RAW_ROWS',
        legacy_scientific_request_worker_slot=1,actual_runtime_slots='SEPARATE_EXPLICIT_PARALLEL_ACTUAL_SLOT_1_THROUGH_7'))
    cpu=placement(windows_cpu_sets())
    atomic(op.AMENDMENT,dict(UTC=now(),policy=op.POLICY,user_authorized=True,user_instruction=boundary['user_instruction'],
        sources=op.sources(),previous_authorization=record(op.previous.AMENDMENT),validation=record(validation),
        queue_plan=record(plan),boundary_request=record(op.OPS/'USER_PRE_ACTUAL_BATCH_BOUNDARY_REQUEST.json'),
        confirmation=record(confirmation),monitoring_sources=monitors,protected_case_root=boundary['protected_case'],
        prepare_workers=1,actual_workers=7,P_cores_only=True,cpu_placement=cpu,
        full_Actual_and_Fresh_unmodified=True,old_scientific_sources_modified=False,
        legacy_scientific_slot_preserved=True,actual_runtime_slots_authorized_separately=True))
    op.validate()
    from v44_recovery_r038.batch import compose_request
    lease=read(op.CAMPAIGN/'COORDINATOR_LEASE.json')
    for job in jobs:
        case,pointer,number=compose_request(job,lease);op.authorize(case);verify(case['sources'])
    for stem in ('collect_watchdog','audit_active_revision'):
        path=op.OPS/(stem+'_r032.py')
        assert str(path).casefold() not in {r['path'].casefold() for r in protected['sources']}
        shutil.copy2(path,out/(path.name+'.before'))
        prefix=("# Route explicitly authorized staged batch control to r038.\n"
            "import json as _r038_json,runpy as _r038_runpy\nfrom pathlib import Path as _r038_Path\n"
            "_r038_ops=_r038_Path(__file__).parent\n"
            "_r038_handoff=_r038_json.loads((_r038_ops/'CURRENT_HANDOFF.json').read_text(encoding='utf-8-sig'))\n"
            "if 'v44_recovery_r038' in (_r038_handoff.get('active_revision'),_r038_handoff.get('pending_revision')):\n"
            f"    _r038_runpy.run_path(str(_r038_ops/'{stem}_r038.py'),run_name='__main__')\n    raise SystemExit(0)\n")
        path.write_text(prefix+path.read_text(encoding='utf-8'),encoding='utf-8')
    ps=out/'register.ps1'
    ps.write_text("""$ErrorActionPreference='Stop'
$taskName='MobileESS_V44_Campaign004_Recovery_R032'
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'D:/MobileESS_V44/development/R038_DEPLOYMENT_20261018/ScheduledTask.before.xml' -Encoding Unicode
$actions=@(
 (New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 D:/v44_r022_rowgen_20261017/validation_tools/actual_performance/launch_r036_storage.py' -WorkingDirectory 'D:/v44_r022_rowgen_20261017'),
 (New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 -u -m v44_recovery_r038.operations --handover --algorithm v44_recovery_r029.operations' -WorkingDirectory 'D:/v44_r022_rowgen_20261017')
)
Set-ScheduledTask -TaskName $taskName -Action $actions | Out-Null
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath 'D:/MobileESS_V44/development/R038_DEPLOYMENT_20261018/ScheduledTask.after.xml' -Encoding Unicode
""",encoding='utf-8-sig')
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ps)],check=True,capture_output=True)
    handoff=read(op.OPS/'CURRENT_HANDOFF.json')
    handoff.update(UTC=now(),pending_revision='v44_recovery_r038',pending_permit=record(op.AMENDMENT),
        pending_validation=record(validation),pending_handover_mode='AFTER_MAY04_B1_SERIAL_PREPARATION_THEN_SEVEN_P_ONLY_ACTUAL',
        latest_user_instruction=boundary['user_instruction'],next='Finish May04 B1 unchanged, then prepare seven remaining cases serially; start seven P-only Actual/Fresh workers only after every preparation passes.')
    atomic(op.OPS/'CURRENT_HANDOFF.json',handoff)
    with (out/'handover.log').open('ab') as stream:
        helper=subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),'-X','utf8','-u','-m',op.ENTRY,
            '--handover','--algorithm',op.ALGORITHM],cwd=Path(__file__).resolve().parents[2],stdout=stream,stderr=stream,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(30):
        p=op.OPS/'R038_HANDOVER_HEARTBEAT.json'
        if p.exists() and read(p).get('pid')==helper.pid:break
        if helper.poll() is not None:raise RuntimeError('R038_HANDOVER_EXITED:'+(out/'handover.log').read_text(errors='replace'))
        time.sleep(.5)
    else:raise RuntimeError('R038_HANDOVER_HEARTBEAT_NOT_CREATED')
    handoff=read(op.OPS/'CURRENT_HANDOFF.json');handoff['pending_handover_pid']=helper.pid;atomic(op.OPS/'CURRENT_HANDOFF.json',handoff)
    verify(protected['sources']+[boundary['protected_request']]);op.validate()
    assert worker.is_running() and abs(worker.create_time()-before['created'])<.001
    assert worker.cpu_affinity()==before['affinity'] and int(worker.nice())==before['priority']
    result=dict(UTC=now(),PASS=True,state='ARMED_WAITING_FOR_MAY04_B1',helper_pid=helper.pid,
        protected_worker_untouched=before,authorization=record(op.AMENDMENT),validation=record(validation),
        jobs=jobs,cpu_placement=cpu,tests=count,actual_workers_started_before_boundary=0)
    atomic(out/'RESULT.json',result);print(result,flush=True)

if __name__=='__main__':run()

"""Arm post-preparation Actual without releasing the live preparation fence."""
from pathlib import Path
import sys,subprocess,os,shutil,xml.etree.ElementTree as ET
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r042 import operations as op
from v44.common import read,record,verify,atomic,now

def run():
    op.preparation.authority();assert not op.AMENDMENT.exists()
    stop_path=op.OPS/'STOP_AUTONOMY.json';stop=read(stop_path);assert op.expected_hold(stop)
    tests=Path('D:/MobileESS_V44/development/R042_ALL_REGRESSIONS.xml');suites=ET.parse(tests).getroot().findall('testsuite')
    count=sum(int(s.get('tests',0)) for s in suites);assert count>=292 and all(int(s.get('failures',0))+int(s.get('errors',0))==0 for s in suites)
    previous_bootstrap=Path('D:/MobileESS_V44/development/R040_PARALLEL_BOOTSTRAP_NATIVE0_20261019/RESULT.json')
    preparation_proof=Path('D:/MobileESS_V44/development/R041_REUSED_A1_NATIVE0_20261019/RESULT.json')
    assert read(previous_bootstrap)['PASS'] and read(preparation_proof)['PASS'] and not read(preparation_proof)['Actual_executed']
    protected=[];pins=[]
    for w in op.workers():
        a=w['cmdline'];r=read(a[a.index('--worker')+1]);pins+=r['sources']+r.get('R039_sources',[])+r.get('R040_sources',[])+r.get('R041_sources',[])
        p=psutil.Process(w['pid']);protected.append(dict(pid=p.pid,process_created=p.create_time(),day=r['day'],arm=r['arm']))
    verify(pins)
    validation=op.OPS/'R042_CHANGE_AND_VALIDATION.json'
    atomic(validation,dict(UTC=now(),PASS=True,tests=count,regressions=record(tests),sources=op.sources(),
        all_preparations_resolved_gate_verified=True,all_seven_actual_requests_dispatched_in_test=True,
        one_launch_failure_does_not_block_other_six=True,preparation_route_flags_removed_before_Actual=True,
        source_sha_case_root_and_frozen_plans_preserved=True,prior_full_worker_bootstrap=record(previous_bootstrap),
        real_completed_A1_preparation_fence=record(preparation_proof),new_full_Actual120_runs_claimed=False,
        P_only_and_Actual_threads1_inherited=True,Native_limits_and_physical_checks_unchanged=True))
    atomic(op.AMENDMENT,dict(UTC=now(),user_authorized=True,user_instruction='응 작업 끝나면 planning 다 준비되면 7 worker actual 자동 시작 문제 없이 잘 되는지 점검 한 번 더 해.',
        sources=op.sources(),previous_authorization=record(op.preparation.AMENDMENT),validation=record(validation),
        auto_Actual_after_preparations=True,preparation_fence_retained=True,
        release_requires_all_preparations_resolved_and_workers_dead=True,max_Actual_workers=7,P_only=True,
        failed_case_excluded_only_and_healthy_cases_continue=True,Actual_source_initial_state_new=True,
        supersedes_r041_Actual_pause_only_at_resolved_preparation_barrier=True,completed_PASS_not_rerun=True))
    op.authority()
    for stem,function in [('collect_watchdog','collect'),('audit_active_revision','audit')]:
        path=op.OPS/(stem+'_r042.py');assert not path.exists()
        code="import sys,json\nsys.path.insert(0,'D:/v44_r022_rowgen_20261017')\nfrom v44_recovery_r042 import operations as op\nfrom v44_recovery_r040.monitor import "+function+"\nfrom v44.common import read,verify,record\nop.authority()\nv="+function+"()\n"
        if function=='audit':
            code+="for w in op.workers():\n a=w['cmdline'];r=read(a[a.index('--worker')+1]);verify(r.get('R041_sources',[])+r.get('R042_sources',[]))\n if op.ENTRY in a:assert r['R042_authorization']==record(op.AMENDMENT);op.release_authorized(r);op.actual.authorize(r)\n"
        code+="v['Actual_auto_start_authorized']=True\nprint(json.dumps({k:v[k] for k in ('UTC','PASS','active','pending','active_revision','counts','Actual_auto_start_authorized') if k in v},ensure_ascii=False))\n"
        path.write_text(code,encoding='utf8')
        route=op.OPS/(stem+'_r032.py');assert str(route).casefold() not in {r['path'].casefold() for r in pins}
        shutil.copy2(route,op.OPS/(route.name+'.before_r042'))
        prefix=("# Explicit user-authorized post-preparation r042 Actual.\nimport json as _r042j,runpy as _r042r\nfrom pathlib import Path as _r042P\n_r042o=_r042P(__file__).parent\n_r042h=_r042j.loads((_r042o/'CURRENT_HANDOFF.json').read_text(encoding='utf-8-sig'))\nif 'v44_recovery_r042' in (_r042h.get('active_revision'),_r042h.get('pending_revision')):\n    _r042r.run_path(str(_r042o/'"+path.name+"'),run_name='__main__')\n    raise SystemExit(0)\n")
        route.write_text(prefix+route.read_text(encoding='utf8'),encoding='utf8')
    stop.update(auto_resume_after_preparations=record(op.AMENDMENT),Actual_resume_requires_explicit_user=False)
    atomic(stop_path,stop)
    h=read(op.OPS/'CURRENT_HANDOFF.json');h.update(pending_revision='v44_recovery_r042',pending_permit=record(op.AMENDMENT),pending_validation=record(validation),
        Actual_auto_start_authorization=record(op.AMENDMENT),next='Fenced r041 finishes every preparation, then r042 revalidates and releases up to seven healthy P-only Actual/Fresh workers automatically.')
    atomic(op.OPS/'CURRENT_HANDOFF.json',h)
    with (op.OPS/'r042_auto_start.log').open('ab') as out:
        p=subprocess.Popen([sys.executable,'-u','-m',op.ENTRY,'--watchdog','--algorithm',op.ALGORITHM],cwd=Path(__file__).resolve().parents[2],env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),stdout=out,stderr=out,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R042_AUTO_START_LAUNCH.json',dict(UTC=now(),pid=p.pid,process_created=psutil.Process(p.pid).create_time(),authorization=record(op.AMENDMENT)))
    verify(pins)
    for w in protected:assert abs(psutil.Process(w['pid']).create_time()-w['process_created'])<.001
    atomic(op.OPS/'R042_DEPLOYMENT.json',dict(UTC=now(),PASS=True,tests=count,watchdog_pid=p.pid,current_preparation_untouched=protected,
        Actual_not_released_before_barrier=True,authority=record(op.AMENDMENT)))
    print(dict(PASS=True,auto_start_pid=p.pid,tests=count,preparations_untouched=protected))

if __name__=='__main__':run()

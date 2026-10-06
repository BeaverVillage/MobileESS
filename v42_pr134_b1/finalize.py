"""Publish honest terminal evidence; never extend budgets or alter scientific code."""
import shutil,msvcrt
from .common import *
from .coordinator import counts,export

def publish(root,freeze,cp):
    lock=(root/'PUBLICATION.lock').open('a+b');lock.seek(0)
    if not lock.read(1):lock.write(b'0');lock.flush()
    lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:lock.close();return
    try:return _publish(root,freeze,cp)
    finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()

def _publish(root,freeze,cp):
    totals=counts(cp)
    if totals['pending']:return
    verify_freeze(freeze);export(root,freeze,cp);OUT.mkdir(parents=True,exist_ok=True)
    passed=[];violations=dict(voltage=0,line_current=0,transformer_current=0,transformer_kVA=0);native=[]
    for day,r in cp['dates'].items():
        if r['status']=='PASS':
            entry=cp['stages'][day+'/VALIDATION'];receipt=read(entry['receipt'])
            if not valid_receipt(receipt,identity(freeze,day,'VALIDATION'),root):raise ValueError('FINAL_COMPLETE_DATE_IDENTITY_FAILED')
            passed.append(day);s=receipt['physical']['summary']
            for k,field in [('voltage','voltage_violation_count'),('line_current','line_current_violation_count'),('transformer_current','transformer_current_violation_count'),('transformer_kVA','transformer_kva_violation_count')]:violations[k]+=s[field]
        for stage in STAGES:
            entry=cp['stages'].get(day+'/'+stage,{})
            if stage=='A1' and entry.get('request'):
                p=Path(read(entry['request'])['output'])/'A1_SOLVE_RESULT.json'
                if p.exists():native.append(dict(day=day,source_Git_SHA=freeze['Git_SHA'],source_scientific_SHA=freeze['scientific_SHA'],receipt=record(p),runtime=read(p)['total_runtime']))
    failure_classes={s:sum(r['status']==s for r in cp['dates'].values()) for s in sorted({r['status'] for r in cp['dates'].values()})}
    infra=any(r['status'] in ('IMPLEMENTATION_FAILURE','OS_RESOURCE_FAILURE') for r in cp['dates'].values())
    state='MAY_B1_CAMPAIGN_COMPLETE' if len(passed)==31 else 'MAY_B1_CAMPAIGN_INCOMPLETE_INFRASTRUCTURE_FAILURE' if infra else 'MAY_B1_CAMPAIGN_COMPLETE_WITH_RECORDED_FAILURES'
    result=dict(state=state,run_id=freeze['run_id'],all_31_attempted=True,PASS_dates=passed,counts=totals,failure_classes=failure_classes,
        proven_infeasible_dates=[],unresolved_dates=[d for d,r in cp['dates'].items() if r['status']!='PASS'],repair_queue_completed=totals['FAIL']==0 and totals['TIMEOUT']==0,
        native_runtime_provenance=native,physical_violations_on_PASS=violations,Actual_reoptimization=0,PQ_repair=0,memory_guard_enabled=False,
        artificial_slowdown=False,scientific_parameter_sweep=False,detached_ownership_evidence=record(root/'INDEPENDENT_LAUNCH_VERIFICATION.json') if (root/'INDEPENDENT_LAUNCH_VERIFICATION.json').exists() else None,
        app_close_experiment_performed=False,source_commit=freeze['Git_SHA'])
    atomic(root/'FINAL_CAMPAIGN_RESULT.json',result)
    atomic(root/'FINAL_VALIDATION_SUMMARY.json',dict(PASS_dates=len(passed),violations=violations,Actual_reoptimization=0,PQ_repair=0,unresolved_results_fabricated=False))
    atomic(root/'VERIFICATION.json',dict(all_31_attempted=True,all_31_scientific_PASS=len(passed)==31,repair_queue_resolved=result['repair_queue_completed'],state=state))
    # Fixed approved namespaces only. Large immutable raw payloads stay in the
    # durable run folder and are referenced by SHA, not rewritten or clipped.
    for name in ['MAY_B1_PROGRESS.csv','MAY_B1_FINAL_DATE_STATUS.csv','MAY_B1_REPAIR_QUEUE.csv','MAY_B1_ERROR_REPAIR_LEDGER.csv',
                 'MAY_B1_RESOURCE_LEDGER.csv','FINAL_VALIDATION_SUMMARY.json','FINAL_CAMPAIGN_RESULT.json','VERIFICATION.json','MAY_B1_HOURLY_STATUS.json','MAY_B1_HOURLY_STATUS.md']:
        if (root/name).exists():shutil.copyfile(root/name,OUT/name)
    atomic(OUT/'MAY_B1_RESOURCE_LEDGER_INDEX.json',record(root/'MAY_B1_RESOURCE_LEDGER.csv'))
    (OUT/'FINAL_REVIEW_KO.md').write_text(f'''# PR134 supercompact May B1 최종 상태

{state}. 모든 31 날짜를 시도했다. PASS {totals['PASS']}, TIMEOUT {totals['TIMEOUT']}, 실패/미해결 {totals['FAIL']}.
true infeasibility는 단일 native status에서 주장하지 않는다. 실패와 원본 budget을 보존하며 Actual 재최적화·P/Q repair·메모리 guard·감속·parameter sweep은 모두 0/false이다.

source {freeze['Git_SHA']}. 원본 출처별 Runtime은 FINAL_CAMPAIGN_RESULT.json에 있다. detached service 소유 계통을 기록했으며 앱 종료 실험을 수행했다고 주장하지 않는다.
''',encoding='utf8')
    atomic(OUT/'SHA256_MANIFEST.json',dict(files=[record(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256_MANIFEST.json']))
    if not (root/'FINAL_PUBLICATION.json').exists():
        # User explicitly requested final evidence commit/publication. No code
        # generation or unattended agent is invoked by this OS worker.
        try:
            subprocess.run(['git','add','--',str(OUT.relative_to(ROOT))],cwd=ROOT,check=True,capture_output=True)
            staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).splitlines()
            if any(not p.startswith(str(OUT.relative_to(ROOT)).replace('\\','/')+'/') for p in staged):raise ValueError('UNRELATED_STAGED_FILES_PREVENT_FINAL_PUBLICATION')
            if staged:subprocess.run(['git','commit','-m','Record 31-date PR134 supercompact May B1 campaign evidence'],cwd=ROOT,check=True,capture_output=True)
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            subprocess.run(['git','push','origin',freeze['branch']],cwd=ROOT,check=True,capture_output=True)
            atomic(root/'FINAL_PUBLICATION.json',dict(PASS=True,commit=commit,UTC=now()))
            subprocess.run(['schtasks.exe','/Change','/TN',freeze['watchdog_task'],'/DISABLE'],check=True,capture_output=True)
        except Exception as error:atomic(root/'FINAL_PUBLICATION_ERROR.json',dict(PASS=False,error=str(error),UTC=now()))

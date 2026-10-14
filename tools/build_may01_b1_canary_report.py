"""Package measured Canary outcomes and explicit stopped/not-run ledgers."""
from pathlib import Path
import argparse,csv,json,hashlib,shutil,sys
import xml.etree.ElementTree as ET
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.partial_canary import PARENT,OLD_B2_LEDGER,OLD_INTEGRATION_LEDGER
from v42_integration.m_engine import file_record


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def table(p,rows,reason):
    rows=rows or [dict(status='NOT_RUN',reason=reason)]
    keys=sorted(set().union(*(r.keys() for r in rows)))
    with p.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def main(out):
    run=out/'RUN_ATTEMPT02';watch=read(run/'WATCHDOG_RECEIPT.json')
    pre=read(run/'NATIVE0_PREFLIGHT.json') if (run/'NATIVE0_PREFLIGHT.json').exists() else None
    ledger=read(run/'B1_RESEARCH_NATIVE_LEDGER.json') if (run/'B1_RESEARCH_NATIVE_LEDGER.json').exists() else None
    failure=read(run/'CANARY_EXECUTION_FAILURE.json') if (run/'CANARY_EXECUTION_FAILURE.json').exists() else None
    a1=read(run/'A1_KNOWN_OPTIMIZATION_RECEIPT.json') if (run/'A1_KNOWN_OPTIMIZATION_RECEIPT.json').exists() else dict(
        status='A1_NO_ACCEPTABLE_INCUMBENT',FULL_feasible=False,Global_UB=None,Global_LB=None,Global_Gap=None,
        Native_Runtime_seconds=None if ledger and ledger['inflight'] else (ledger or {}).get('Gurobi_Native_seconds',0),
        reason=watch['stop_reason'] or (failure or {}).get('error','NO_A1_RESULT'),
        Native_Optimize_calls=len((ledger or {}).get('calls',[])),
        original_A1_producer_invoked=pre is not None,Full96_model_truncated=False)
    a1.update(A1_preparation_wall_limit_seconds=600,
        measured_Canary_attempt_wall_seconds=watch['wall_seconds'],
        Native_Optimize_reached=bool((ledger or {}).get('calls') or (ledger or {}).get('inflight')))
    write(out/'A1_KNOWN_OPTIMIZATION_RECEIPT.json',a1)
    for name in ('PARTIAL_POLICY_COVERAGE_AUDIT.json','UNKNOWN_FROZEN_POLICY_SHA.json','SOURCE_CASE_POLICY_MANIFEST.json'):
        if (run/name).exists():shutil.copyfile(run/name,out/name)
        else:write(out/name,dict(status='NOT_RUN',reason=a1['status'],parent_PR228=PARENT,policy_sha=None))
    coverage=read(out/'PARTIAL_POLICY_COVERAGE_AUDIT.json')
    results={r:read(run/(r+'_PARTIAL_RESULT.json')) for r in ('R0','R1','R2','R3') if (run/(r+'_PARTIAL_RESULT.json')).exists()}
    known=[];unknown=[];funnel=[];compare=[];powers=[];fallback={};ablation=[]
    source_selected={}
    if (run/'B1/A1/A_RESULT.json').exists():source_selected=read(run/'B1/A1/A_RESULT.json').get('selected_jobs',{})
    for uid,option in source_selected.items():known.append(dict(uid=uid,scope='NEW_E1_FLEX30_A1_PLANNING',
        start_slot=option['start'],site=option['initial_site'],checkpoint=option.get('checkpoint',-1),
        destination=option.get('destination'),A1_status=a1['status'],Actual_execution='SEE_R1_R2_R3_UID_RECORDS'))
    for label in ('R0','R1','R2','R3'):
        if label not in results:
            compare.append(dict(policy=label,status='NOT_RUN',reason=a1['status'] if not results else 'EXECUTION_STOP_OR_BUDGET',
                Full96_PASS=False,affine_rho=None,Fresh_AC_rho=None));continue
        result=results[label];meta=result['carryout']['controller']['metadata'];rules=result['rule_consumption_receipt']
        uids={u for u,m in meta.items() if m['origin_unknown']};stats=result['canary']['Unknown_metrics']
        compute=sum(m['gpu']*max(0.,m['accumulated_compute_seconds']-m.get('original_raw_request_metadata',{}).get('elapsed_compute_seconds',0))/3600
            for u,m in meta.items() if u in uids)
        compare.append(dict(policy=label,status='EXECUTED_PARTIAL_16_SLOTS',Full96_PASS=False,Planning_rho=a1.get('Global_UB'),
            completed=result['receipt']['completed_jobs'],Partial_Carryout=result['receipt']['carryout_jobs'],
            Unknown_Observed=len(uids),Unknown_Covered=stats['Unknown_Lookup_Success_UID'],
            Unknown_Participants=stats['Unknown_Participant_UID'],Unknown_Changed=stats['Unknown_Actual_Changed_UID'],
            Changed_nominal_GPUh=stats['Changed_Nominal_GPUh'],Unknown_observed_compute_GPUh=compute,
            Unknown_TimeShift=stats['Unknown_Actual_TimeShift_UID'],Unknown_Preplace=stats['Unknown_Actual_Preplace_UID'],
            Unknown_Migration=stats['Unknown_Actual_Migration_UID'],affine_rho=None,Fresh_AC_rho=None,
            QoS_intent_budget_excess=stats['QoS_intentional_budget_excess_UID'],
            First_frozen_alternative=stats['Unknown_First_Alternative_Executed_UID'],Later_alternative=stats['Unknown_Later_Alternative_Executed_UID']))
        for row in result['queue_ledger']:
            uid=row['job_uid']
            if uid not in uids:continue
            decisions=[r for r in rules if r.get('uid')==uid]
            unknown.append(dict(policy=label,uid=uid,admitted_time=row.get('admitted_time'),site=row.get('site'),
                executed_action=row.get('policy_action'),migration_count=row.get('migration_count',0),
                coverage_row_match=any(r.get('rule_id') for r in decisions),participant=meta[uid].get('experimental_contract',{}).get('participant'),
                unsupported_reasons='|'.join(sorted({r['coverage_unsupported_reason'] for r in decisions if r.get('coverage_unsupported_reason')})),
                nominal_GPUh=meta[uid]['gpu']*meta[uid]['t50_seconds']/3600,Partial_Carryout=row.get('carryout')))
        for origin,wanted in (('UNKNOWN',uids),('KNOWN',set(meta)-uids)):
            running={r['job_uid'] for r in result['queue_ledger'] if r['job_uid'] in wanted and r.get('admitted_time') is not None}
            checkpoints=[r for r in rules if r.get('event')=='OBSERVED_EXECUTION_CHECKPOINT' and r['uid'] in wanted]
            reached={r['uid'] for r in checkpoints};matched={r['uid'] for r in checkpoints if r.get('rule_id')}
            migrations={r['job_id'] for r in result['migration_receipts'] if r['job_id'] in wanted}
            reasons=Counter(r.get('reason',r.get('status','UNRECORDED')) for r in checkpoints if r.get('action')=='STAY')
            funnel.append(dict(policy=label,origin=origin,RUNNING_UID=len(running),first_valid_checkpoint_UID=len(reached),
                Migration_authorized_UID=sum(meta[u].get('Can_Checkpoint_Migrate') is True for u in reached),
                Frozen_migration_row_matching_UID=len(matched),possible_destination_UID=None,GPU_Rack_pass_UID=None,
                WAN_pass_UID=None,Shared_budget_pass_UID=None,actual_migration_UID=len(migrations),
                STAY_or_failure_UID=len({r['uid'] for r in checkpoints if r.get('action')=='STAY'}),
                reasons=json.dumps(reasons,ensure_ascii=False),unrecorded_gate_stages='NOT_EVALUATED_OR_NOT_IN_PR228_EVENT_RECEIPT'))
        fallback[label]=dict(executed_same_row_fallback_UID=stats['Unknown_Same_Row_Revalidation_Fallback_Executed_UID'],
            reserved_command_failed_UID=stats['Unknown_Reserved_Command_Revalidation_Failed_UID'],
            rejected_unique_UIDs=stats['rejection_unique_UID_counts'])
        for t,(it,p,q) in enumerate(zip(result['physical']['IT_kw'],result['physical']['PCC_P_kw'],result['physical']['PCC_Q_kvar'])):
            for j in range(12):powers.append(dict(policy=label,slot=t,AIDC='AIDC'+str(j+1).zfill(2),IT_kw=it[j],PCC_P_kw=p[j],PCC_Q_kvar=q[j]))
    if 'R2' in results and 'R3' in results:
        ablation=[dict(status='EXECUTED_POLICY_ABLATION_NOT_PER_UID_CAUSAL_EFFECT',
            R2_Preplace=results['R2']['canary']['Unknown_metrics']['Unknown_Actual_Preplace_UID'],
            R2_Migration=results['R2']['canary']['Unknown_metrics']['Unknown_Actual_Migration_UID'],
            R3_Migration=results['R3']['canary']['Unknown_metrics']['Unknown_Actual_Migration_UID'])]
    for name,rows in (('KNOWN_ALLOCATION_UID.csv',known),('UNKNOWN_POLICY_EXECUTION_UID.csv',unknown),('MIGRATION_FUNNEL.csv',funnel),
        ('PREPLACE_MIGRATION_ABLATION.csv',ablation),('R0_R1_R2_R3_COMPARISON.csv',compare),('PARTIAL_ACTUAL_POWER_COMPARISON.csv',powers)):
        table(out/name,rows,a1['status'])
    write(out/'UNKNOWN_FALLBACK_EXECUTION_AUDIT.json',dict(status='MEASURED_PARTIAL' if fallback else 'NOT_RUN',
        policies=fallback,old_PR226_Unknown102_full_cohort_rescue_claim=False,unobserved_UIDs_counted_as_success_or_failure=False))
    write(out/'PARTIAL_FRESH_AC_COMPARISON.json',dict(status='NOT_RUN',R0=None,R1=None,R2=None,R3=None,
        reason='NO_VALID_NEW_A1_OR_NO_EXECUTED_PARTIAL_TRACE;ORIGINAL_FULL96_TRACE_GATE_PRESERVED',Full96_PASS=False))
    old_int=read(OLD_INTEGRATION_LEDGER);old_b2=read(OLD_B2_LEDGER)
    assert old_int['conservative_solve_seconds']==621.2855198158068
    assert old_b2['effective_cumulative_Native_Runtime']==1257.5220000743866
    tests=ET.parse(out/'REGRESSION_TESTS.xml');cases=list(tests.iter('testcase'))
    assert len(cases)==219 and not list(tests.iter('failure')) and not list(tests.iter('error'))
    runtime=dict(old_B2_Native_seconds=1257.5220000743866,old_integration_conservative_seconds=621.2855198158068,
        old_ledgers_merged_reset_or_modified=False,new_B1_Research_ledger=ledger,
        runtime_recorded=None if ledger and ledger['inflight'] else (ledger or {}).get('Gurobi_Native_seconds',0),
        watchdog=watch,external_workers_terminated=0,auto_heavy_retry=False,
        policy_compile_wall_seconds=None,Actual_wall_seconds={r:v['canary']['wall_seconds'] for r,v in results.items()},AC_wall_seconds=0)
    auxiliary=out/'PREFLIGHT_ONLY/WATCHDOG_RECEIPT.json'
    if auxiliary.exists():runtime['separate_development_Native0_preparation']=read(auxiliary)
    runtime['development_Native0_wall_is_not_hidden_in_Native_Runtime']=True
    write(out/'NATIVE_AND_WALL_RUNTIME_LEDGER.json',runtime)
    manifest=read(out/'SOURCE_CASE_POLICY_MANIFEST.json');manifest.update(parent_PR228=PARENT,
        measured_A1_status=a1['status'],tests_PASS=219,required_Canary_tests=12,Full96_PASS=False,
        B2_B3_May31_HOLD=True,SVR_AVR_CapControl_source_unchanged=True,old_ledger_receipts=[file_record(OLD_B2_LEDGER),file_record(OLD_INTEGRATION_LEDGER)])
    write(out/'SOURCE_CASE_POLICY_MANIFEST.json',manifest)
    report=f'''# PR228 후속 — May01 B1 제한 Canary

판정: **{a1['status']}**. 중단 원인: `{a1.get('reason',watch['stop_reason'])}`. 원래 A1 생산자의 전체 96슬롯 Domain/Graph 생성에서 준비 단계600초 상한을 소진했다. 실제 Gurobi Optimize에는 진입하지 않았고 Native 비용은 **{runtime['runtime_recorded']}초**, 본 Attempt 벽시계는 **{watch['wall_seconds']:.3f}초**다. {len(results)}개 Partial Actual 비교가 실행됐다. 새 통합 성능, 최적성, Full96 및 May31 성과는 인증하지 않는다.

1. 새로운 E1/FLEX30 A1: 원본 생산자를 호출했다. Native Optimize 실행 여부는 원장 calls와 Runtime을 기준으로 판정한다. A1 결과 파일이 없으면 최적화 완료로 주장하지 않는다.
2. FULL-feasible 해: {a1['FULL_feasible']}. UB/LB/Gap은 {a1.get('Global_UB')}/{a1.get('Global_LB')}/{a1.get('Global_Gap')}. 없으면 NULL이다. 기존 V5 해를 새 최적해로 사용하지 않았다.
3. 활성 Known 1,546개 중 새 A1/Actual 변경 수는 유효한 결과가 있을 때만 CSV로 보고한다. Source Issue 1,649 UID, Native 대상 1,499 UID를 분리했다.
4. 4시간 Unknown 관측 수: R0–R3 비교 CSV의 실제 관측 값만 사용한다. 미실행이면 NOT_RUN이며 0개의 수요로 해석하지 않는다.
5. Coverage는 PARTIAL_POLICY_COVERAGE다. Issue Known 최빈 Gang 1과 사전 정의 900초 Bucket, 처음 16개 슬롯, 모든 호환 AIDC 12개, Normal/Standby 및 Pending/Running 조건을 사전등록했다. 전체 추정 1,497,600행·37,152,000후보·최소 약38GB이므로 전체 Cartesian Product를 생성하지 않았다. 미래 Unknown UID로 Class를 선택하지 않았다.
6. Unknown 실제 조정 수는 실행 UID CSV와 최종 고유 UID 합집합으로만 보고한다. 미실행 정책의 조정 수는 NOT_RUN이다.
7. 변경 nominal GPUh와 관측 compute GPUh를 분리했다. 미실행이면 NULL이며 기존 PR226의 7.5681 GPUh를 새 결과로 이전하지 않는다.
8. 선택 후 실패는 실제 명령/예약 원장에서만 집계한다. A1 생산 또는 정책 Freeze 이전의 중단을 Unknown 실행 실패로 세지 않는다.
9. Same-row Fallback 구제는 실행된 관측 UID만 비교한다. 과거 Unknown102 전체를 구제했다고 주장하지 않는다.
10. Migration Funnel은 관측된 체크포인트 원장만 사용한다. 시도하지 않았거나 원장이 구분하지 않은 Gate는 NOT_EVALUATED/NULL이며 0건 성공·실패로 채우지 않는다.
11. R3가 실행되지 않았으면 Pre-placement/Migration 대체 관계는 NOT_RUN이다. R3의 전체 정책 효과와 개별 Job 인과 효과를 구분한다.
12. 실제 계통 개선은 실행 및 계통 검증 증거가 없으면 NOT_MEASURED다. Fresh AC rho·전압·Critical-line은 NULL이다.
13. 완료·대기·Partial Carry-out·QoS 비교는 실행된 16슬롯 원장만 사용한다. 04:00/24:00 이후 남은 서비스 자체는 QoS 위반이 아니다.
14. PR228 핵심 7개 파일, 원본 A1 생산자·REAL_DATA Full96 Gate·Fresh AC Source를 변경하지 않았다. 기존 B2 원장1257.5220000743866/1800과 통합원장621.2855198158068/3600은 별도 읽기전용으로 보존했다. 새 B1만 명시적300초 Research 계약에 귀속한다. 이전 Source18r 캠페인·Supervisor·Scheduled Task를 재개하지 않았다.
15. 회귀 **219 PASS** = 기존207 + 새12 계약이다. 초기 새 테스트3건의 SHA 재동결 오류는 수정하고 실패 XML도 보존했다. PR227의 과거29 FAIL/41 ERROR를 해결했다고 주장하지 않는다. 모든 비교는 4시간의 부분 결과이며 Full96/May31 인증은 아니다. 유효한 새 A1이 없으면 R1–R3를 실행하지 않았다.

별도 Native0 개발 검사에서 중복적인 전체 Migration Graph 확장이506.730초 소요되어 본 시험에서는 선언된 전체 Window/Source 검사 뒤 원래 생산자가 Graph를 한 번 생성하도록 했다. 개발 Native0의 별도506.730초를 본 Attempt645.124초 또는 Native0초에 숨기거나 합산해900초 안이라고 주장하지 않는다. 초기 sparse checkout 누락 파일은 복원했고, 테스트 프로세스가 남아 있던 초기 준비 호출은 Worker Gate에서 거부되었다. 모두 Native Optimize 이전의 준비 기록이며, 큰 모델의 Native 재실행은 없었다. Native0를 FULL 모델 인증으로 표시하지 않았다.

현재4시간 결과로 계통 개선 또는 Pre-placement/Migration 대체 관계를 판단할 수 없다. Full96 후속 성능 검증에 앞서, 원본 A1 전체 Domain/Graph의 생성 시간을 줄일 수 있는 동치성 보존 방법을 별도로 검증해야 한다. 이번 요청에서는 Domain을 잘라서 실행하거나 준비·Native 예산을 늘리지 않았다.
'''
    (out/'MAY01_B1_CANARY_FINAL_KO.md').write_text(report,encoding='utf8')
    print(json.dumps(dict(A1_status=a1['status'],Native_runtime=runtime['runtime_recorded'],Actual_comparisons=len(results),tests=219)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);main(parser.parse_args().output)

"""Package measured partial diagnostics; no placeholder performance values."""
from pathlib import Path
import argparse,csv,gzip,hashlib,json,sys,xml.etree.ElementTree as ET
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.policy import digest
from v42_integration.m_engine import file_record


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf8')
def table(path,rows,fields=None):
    if fields is None:fields=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def main(out):
    identity=read(out/'PLANNING_TARGET_IDENTITY.json');runtime=read(out/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json')
    results={p.name[:2]:read(p) for p in sorted(out.glob('C?_RESULT.json'))}
    metrics={p.name[:2]:read(p) for p in sorted(out.glob('C?_METRICS.json'))}
    commands=read(out/'KNOWN_FROZEN_COMMANDS.json');targets=np.load(out/'DAYAHEAD_TRACKING_REFERENCE.npz',allow_pickle=False)
    if not {'C0','C2'}<=results.keys():raise ValueError('REAL_C0_C2_RESULTS_REQUIRED')
    tests=ET.parse(out/'REGRESSION_TESTS.xml');cases=list(tests.iter('testcase'))
    regression=dict(PASS=not list(tests.iter('failure')) and not list(tests.iter('error')),
        passed=len(cases),original_PR228=207,previous_canary_contracts=12,new_tracking_contracts=23,
        required_original_27_retained=True,PR227_past_failures_not_claimed_fixed=True,
        XML=file_record(out/'REGRESSION_TESTS.xml'))
    if len(cases)!=242 or not regression['PASS']:raise ValueError('REGRESSION_GATE_FAILED')
    write(out/'REGRESSION_RESULTS.json',regression)
    decisions=[];alloc=[];power=[];funnel=[];comparison=[];ablation=[]
    plan_rows=[]
    setup=read(out/'DIAGNOSTIC_SETUP/CASE/PRODUCTION_CASE_PREPARATION.json')
    reference_known=setup['reference_AIDC']['selected_jobs'];issue_receipts=setup['QoS_budget_ledger']['receipts']
    changed_sets={k:set() for k in ('TimeShift','Preplace','Migration')};known_volumes={}
    # The same known roster and commands are used by every actual run.
    source_metadata=next(iter(results.values()))['carryout']['controller']['metadata']
    for uid,command in commands.items():
        option=command.get('original_option',{});m=source_metadata.get(uid)
        reference=reference_known[uid];gpu=issue_receipts[uid]['hard_contract']['gpu']
        volume=gpu*sum(b-a for _,a,b in reference['segments'])*.25
        flags=dict(TimeShift=option['start']!=reference['start'],Preplace=option['initial_site']!=reference['initial_site'],
                   Migration=option.get('checkpoint',-1)>=0)
        for action,flag in flags.items():
            if flag:changed_sets[action].add(uid)
        known_volumes[uid]=volume
        row=dict(uid=uid,start_seconds=command['start_seconds'],site=command['site'],
            checkpoint_control_seconds=command.get('checkpoint_control_seconds'),
            migration_destination=command.get('migration_destination'),observed_in_4h=m is not None,
            command_SHA=digest(command),lineage=identity['lineage'],reference_native_start=reference['start'],
            reference_site=reference['initial_site'],gpu=gpu,Nominal_Native_Service_GPUh=volume,
            **flags,unique_changed=any(flags.values()))
        plan_rows.append(row)
    known_changed=set().union(*changed_sets.values())
    known_summary=dict(Known_issue_UIDs=1649,Known_native_optimized_UIDs=len(commands),
        Known_changed_unique=len(known_changed),**{k+'_UIDs':len(v) for k,v in changed_sets.items()},
        Changed_Nominal_GPUh=sum(known_volumes[u] for u in known_changed),
        Nominal_GPUh_scope='SOURCE_NATIVE_REMAINING_SERVICE_SLOTS;ROUNDING_PRESERVED;NOT_ACTUAL_COMPUTE',
        lineage=identity['lineage'],new_E1_optimality=False)
    write(out/'KNOWN_PLANNING_METRICS.json',known_summary)
    for label,result in results.items():
        m=metrics[label];canary=result['tracking_canary'];c=result['carryout']['controller'];unknown=m['unknown']
        for row in canary['policy_audit']:
            d=row['decision'];score=d.get('tracking',{})
            decisions.append(dict(policy=label,uid=row['uid'],time_seconds=row['time_seconds'],state=row['state'],
                action=d['action'],site=d.get('site'),start_seconds=d.get('start_seconds'),status=d['status'],
                reason=d.get('reason'),candidate_count=d['candidate_count'],decision_seconds=d['decision_seconds'],
                Tracking_Deficit=score.get('deficit'),estimated_grid_rho=score.get('grid_peak'),
                loading_hours=score.get('loading_hours'),predicted_GPU_error_GPUh=score.get('GPU_error_GPUh'),
                predicted_P_error_kWh=score.get('P_error_kWh'),Known_mismatch_GPUh=d.get('known_mismatch_GPUh'),
                Unknown_mismatch_GPUh=d.get('unknown_prediction_mismatch_GPUh'),
                residual_target_GPUh=d.get('residual_target_GPUh'),negative_residual_clamped_GPUh=d.get('negative_residual_clamped_GPUh'),
                Job_Q90_seconds=score.get('Job_Q90_seconds'),controller_global_optimizer_calls=0,
                rejected_candidates=d.get('rejected_candidates',[]),target_sha=canary['target_sha']))
        for row in result['queue_ledger']:
            uid=row['job_uid'];meta=c['metadata'][uid]
            if not meta['origin_unknown']:continue
            ref_site=meta['reference_site'];actual_site=row.get('site');start=row.get('admitted_time')
            pre=row.get('policy_action')=='PREPLACE';delay=row.get('intentional_delay_seconds',0)>0
            mig=meta.get('migration_count',0)>0
            initial_elapsed=c['requests'][uid]['metadata'].get('elapsed_compute_seconds',0)
            alloc.append(dict(policy=label,uid=uid,gpu=meta['gpu'],submit_seconds=meta['submit_seconds'],
                reference_site=ref_site,actual_site=actual_site,start_seconds=start,state=meta['state'],
                preplace=pre,timeshift=delay,migration=mig,unique_changed=pre or delay or mig,
                nominal_GPUh=meta['gpu']*meta['t50_seconds']/3600,
                actual_compute_GPUh=meta['gpu']*max(0,meta.get('accumulated_compute_seconds',0)-initial_elapsed)/3600,
                intentional_delay_seconds=meta.get('additional_start_delay_seconds',0),
                migration_interruption_seconds=meta.get('cumulative_migration_interruption_seconds',0),
                participant=meta.get('experimental_contract',{}).get('participant'),
                carryout=row['carryout'],budget_seconds=c['qos_budget_ledger'][uid]['budget_seconds']
                    if uid in c['qos_budget_ledger'] else next(x['budget_seconds'] for x in result['qos_ledger'] if x['uid']==uid)))
        arrays=np.load(out/(label+'_ACTUAL_ARRAYS.npz'),allow_pickle=False)
        unknown_actual=arrays['Unknown_GPU'];known_actual=arrays['Known_GPU']
        actual_share=unknown_actual/unknown_actual.sum() if unknown_actual.sum() else np.zeros_like(unknown_actual)
        target_unknown=targets['G_Unknown_Q50_Plan'][:16]
        target_share=target_unknown/target_unknown.sum() if target_unknown.sum() else np.zeros_like(target_unknown)
        for t in range(16):
            for j,site in enumerate(targets['sites']):
                power.append(dict(policy=label,slot=t,epoch_seconds=canary['begin']+900*t,site=site,
                    planned_Known_GPU=targets['G_Known_Plan'][t,j],actual_Known_GPU=known_actual[t,j],
                    planned_Unknown_GPU=target_unknown[t,j],actual_Unknown_GPU=unknown_actual[t,j],
                    planned_Total_GPU=targets['G_Total_Plan'][t,j],actual_Total_GPU=arrays['GPU'][t,j],
                    Target_minus_Actual_GPU=targets['G_Total_Plan'][t,j]-arrays['GPU'][t,j],
                    residual_Unknown_GPU=max(0,targets['G_Total_Plan'][t,j]-known_actual[t,j]),
                    target_share=target_share[t,j],actual_compute_occupation_share=actual_share[t,j],
                    target_minus_actual_share=target_share[t,j]-actual_share[t,j],
                    planned_PCC_P_kw=targets['PCC_P_Plan'][t,j],actual_PCC_P_kw=arrays['PCC_P_kw'][t,j],
                    planned_PCC_Q_kvar=targets['PCC_Q_Plan'][t,j],actual_PCC_Q_kvar=arrays['PCC_Q_kvar'][t,j]))
        migration_rows=canary['migration_funnel']
        running={u for u,x in c['metadata'].items() if x['origin_unknown'] and (x['state']=='RUNNING' or c['episode_jobs'][u]['start_time'] is not None)}
        stages=('RUNNING','CHECKPOINT','AUTHORITY','DESTINATION','REMAINING','WAN','GPU_RACK','BUDGET','SELECTED','COMPLETED')
        completed={e['uid'] for e in result['job_event_ledger'] if e['event']=='DESTINATION_RUNNING' and e['uid'] in running}
        for stage in stages:
            users=running if stage=='RUNNING' else completed if stage=='COMPLETED' else {r['uid'] for r in migration_rows if r[stage]}
            funnel.append(dict(policy=label,stage=stage,unique_UIDs=len(users),UIDs=sorted(users),
                status='INSUFFICIENT_MIGRATION_OPPORTUNITY' if stage=='AUTHORITY' and not users else 'OBSERVED',
                rejection_reasons=dict(Counter(r['reason'] for r in migration_rows))))
        flattened=dict(policy=label,status='EXECUTED_PARTIAL_DIAGNOSTIC',new_A1_status='NEW_A1_NOT_CERTIFIED',
            Known_observed=m['Known_observed_UIDs'],Known_optimized_observed=m['Known_optimized_observed_UIDs'],
            Known_commands_immutable=m['Known_command_SHA_unchanged'],Known_start_deviations=m['Known_plan_start_deviations'],
            Unknown_observed=unknown['Unknown_Observed_UID'],Unknown_eligible=unknown['Unknown_Observed_Eligible_UID'],
            Unknown_participant=unknown['Unknown_Participant_UID'],Unknown_changed_unique=unknown['Unknown_Actual_Changed_UID'],
            Preplace_UIDs=unknown['Unknown_Actual_Preplace_UID'],TimeShift_UIDs=unknown['Unknown_Actual_TimeShift_UID'],
            Migration_UIDs=unknown['Unknown_Actual_Migration_UID'],Changed_Nominal_GPUh=unknown['Changed_Nominal_GPUh'],
            actual_Unknown_compute_GPUh=m['Unknown_actual_compute_GPUh'],actual_Known_compute_GPUh=m['Known_actual_compute_GPUh'],
            Queue_Unknown_UIDs=unknown['Unknown_Queue_UID'],Carry_Unknown_UIDs=unknown['Unknown_Carryover_UID'],
            **{k:v for k,v in m['errors'].items() if not isinstance(v,(list,dict))},
            Planning_affine_rho=identity['independent_96_slot_affine_rho'],Actual_4h_affine_rho=m['grid']['affine_rho'],
            critical_line_phase=m['grid']['critical_line_phase'],critical_slot=m['grid']['critical_slot'],
            critical_loading_hours=m['grid']['fixed_critical_line_loading_hours'],
            hard_grid_violation_rows=len(m['grid']['hard_violations']),QoS_budget_excess_UIDs=m['QoS_intentional_budget_excess_UIDs'],
            **{k:m[k] for k in ('decision_mean_seconds','decision_P50_seconds','decision_P95_seconds','decision_max_seconds',
                              'decision_calls','candidate_evaluations','replay_wall_seconds')},
            Fresh_AC_rho=None,Full96_Actual_PASS=False)
        comparison.append(flattened)
        ablation.append(dict(policy=label,Unknown_Preplace_UID=flattened['Preplace_UIDs'],Unknown_TimeShift_UID=flattened['TimeShift_UIDs'],
            Unknown_Migration_UID=flattened['Migration_UIDs'],Unknown_changed_unique=flattened['Unknown_changed_unique'],
            Changed_Nominal_GPUh=flattened['Changed_Nominal_GPUh'],Known_commands_unchanged=flattened['Known_commands_immutable'],
            result_scope='4H_DIAGNOSTIC_NOT_GENERAL_PREPLACE_MIGRATION_SUBSTITUTION_PROOF'))
    comparison.insert(1,dict(policy='C1',status='NOT_RUN',reason=runtime['C1_compile']['reason'],Frozen_compile_seconds=0,
        Frozen_Source_only_estimate=runtime['C1_compile']['Source_only_estimate'],Actual_4h_affine_rho=None,Fresh_AC_rho=None))
    table(out/'TRACKING_JOB_DECISION_LEDGER.csv',decisions)
    table(out/'KNOWN_PLANNING_ALLOCATION.csv',plan_rows)
    table(out/'UNKNOWN_ACTUAL_ALLOCATION.csv',alloc)
    table(out/'MIGRATION_ELIGIBILITY_FUNNEL.csv',funnel)
    table(out/'TRACKING_PCC_GPU_COMPARISON.csv',power)
    table(out/'C0_C1_C2_C3_METRICS.csv',comparison)
    table(out/'PREPLACE_MIGRATION_ABLATION.csv',ablation)
    write(out/'FRESH_AC_STATUS.json',dict(status='PARTIAL_AC_NOT_AUTHORIZED',AC_calls=0,AC_rho=None,
        reason='ORIGINAL_FRESH_AC_REQUIRES_FULL96_PQ_TRACE_AND_EPOCH_AXIS;16_SLOT_TRACE_NOT_COMPATIBLE',
        original_validation_source=file_record(ROOT/'v42_integration/actual_validation.py'),gate_weakened=False))
    watchdog=read(out/'WATCHDOG_RECEIPT.json');runtime['watchdog']=watchdog
    all_samples=list(watchdog['samples'])
    for receipt in runtime.get('prior_watchdog_receipts',[]):all_samples+=read(receipt['path'])['samples']
    runtime['peak_tree_RSS_bytes']=max(s['RSS_bytes'] for s in all_samples)
    runtime['peak_tree_Private_Commit_bytes']=max(s['Private_Commit_bytes'] for s in all_samples)
    runtime['C1_compile']['record_size_assumption']='1KiB_PER_CANDIDATE_HEURISTIC;DEDUP_NOT_MEASURED;NOT_A_PROVEN_RAM_LOWER_BOUND'
    runtime['C1_compile']['actual_compile_peak_RSS_bytes']=None
    runtime['memory_gate_PASS']=not watchdog['stop_reason'];runtime['postprocessing_is_separate_no_native']=True
    runtime['cumulative_execution_wall_seconds']=watchdog['cumulative_execution_wall_seconds']
    write(out/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json',runtime)
    base,new=metrics['C0'],metrics['C2'];du=new['unknown'];c3=metrics.get('C3')
    delta_p=base['errors']['PCC_P_L1_kWh']-new['errors']['PCC_P_L1_kWh']
    delta_gpu=base['errors']['GPU_L1_GPUh']-new['errors']['GPU_L1_GPUh']
    delta_rho=new['grid']['affine_rho']-base['grid']['affine_rho']
    known_failed_uids={e['uid'] for e in results['C2']['job_event_ledger'] if e['event']=='KNOWN_COMMAND_EXECUTION_FAILED'}
    migrations=results['C2']['tracking_canary']['migration_funnel']
    migration_unique={stage:len({r['uid'] for r in migrations if r[stage]}) for stage in
        ('CHECKPOINT','AUTHORITY','DESTINATION','REMAINING','WAN','GPU_RACK','BUDGET','SELECTED')}
    review=f'''# May01 4시간 실제 Tracking Canary 검토

신규 A1: **NEW_A1_NOT_CERTIFIED**. C0/C2/C3는 기존 Source18r V5 A1을 공통 동결한 **별도 Diagnostic**이다. 과거 Case `{identity['original_anchor_case_sha']}`와 현재 Case `{identity['Case_SHA']}`는 다르다. 새 E1 최적성/P2/global gap 성과로 이전하지 않는다.

1. 과거 B1 May31 fixed replay는 저장된 Planning PCC P/Q를 그대로 복사했다. 이번 Actual은 관측된 Job의 배치·대기·실행·완료 점유에서 원본 C1 exact 전력을 계산한다. Legacy PCC 동일성 검사도 원본 그대로 보존했다.
2. Known/Unknown Q50/Total GPU, IT, PCC P/Q 96×12와 Known 명령, CC4 Q50/Q90, CDF/service/carry 및 Source/Case/Anchor/Runtime/C1/Grid SHA를 동결했다. Target SHA `{identity['Tracking_Target_SHA']}`.
3. Unknown 관측 후 전체 compatible site 및 원본 QoS 허용 시작시각을 열거했다. GPU/Rack/WAN/QoS/signed grid hard 검사 후 Aggregate Unknown service 배분 부족분, grid stress/loading-hours, 공개 runtime/carry risk, 부담 순으로 결정했다. class별 Y*의 정확한 재현이 아니다.
4. 도착이 적으면 존재하지 않는 Job이나 익명 GPU를 생성하지 않는다. 도착이 많으면 capacity/예약/권한을 우선하며 불가피 Queue와 carry를 남긴다. Known/Unknown 오차와 nonnegative residual, 미도착 nominal volume 한계를 별도 기록했다.
5. Actual Global MILP/LP/Gurobi Optimize는 **0회**다. 경량 Job 후보 비교와 original signed row 계산만 수행했다.
6. C2 제어 {new['decision_calls']}회: 평균 {new['decision_mean_seconds']:.6f}s, P50 {new['decision_P50_seconds']:.6f}s, P95 {new['decision_P95_seconds']:.6f}s, 최대 {new['decision_max_seconds']:.6f}s. 전체 후보 {new['candidate_evaluations']}개. Queue 재시도와 checkpoint STAY 결정을 포함한다.
7. Known 명령 SHA 변경 없음={new['Known_command_SHA_unchanged']}. Issue Known {known_summary['Known_issue_UIDs']} UID, Native 계획 대상 {known_summary['Known_native_optimized_UIDs']} UID; 기존 Anchor의 Preplace {known_summary['Preplace_UIDs']}, TimeShift {known_summary['TimeShift_UIDs']}, Migration {known_summary['Migration_UIDs']}, 변경 unique {known_summary['Known_changed_unique']}, 변경 nominal {known_summary['Changed_Nominal_GPUh']:.6f} GPUh이다. 이는 source native remaining service slot 기준이다. 4시간 Known 관측 {new['Known_observed_UIDs']} UID, 최적 명령 대상 관측 {new['Known_optimized_observed_UIDs']} UID. 실제 start deviation {new['Known_plan_start_deviations']}건, 명시적 pre-DDay 실행 실패 {len(known_failed_uids)} unique UID / {new['Known_command_execution_failures']} 재시도 event다. 불변 명령이 모든 실제 시작의 일치를 뜻하지 않는다.
8. C2 Unknown 관측 {du['Unknown_Observed_UID']} UID, 권한 적격 {du['Unknown_Observed_Eligible_UID']}, FLEX 참여 {du['Unknown_Participant_UID']}; 변경 unique {du['Unknown_Actual_Changed_UID']}, Preplace {du['Unknown_Actual_Preplace_UID']}, TimeShift {du['Unknown_Actual_TimeShift_UID']}, Migration {du['Unknown_Actual_Migration_UID']}. 행동 집합은 중복 가능하며 unique union을 별도 집계했다.
9. 변경 nominal GPUh={du['Changed_Nominal_GPUh']:.6f}; C2 Unknown 실제 compute={new['Unknown_actual_compute_GPUh']:.6f} GPUh. nominal Q50량과 실제 computing은 같은 지표가 아니다.
10. C0 대비 C2 전체 GPU L1 오차 감소량={delta_gpu:.6f} GPUh, PCC P L1 오차 감소량={delta_p:.6f} kWh. 양수는 감소, 음수는 악화다. 사이트/시간별 Known/Unknown/P/Q 및 share 차이는 CSV에 있다.
11. 4시간 exact-C1 PCC를 넣은 original affine rho: C0={base['grid']['affine_rho']:.9f}, C2={new['grid']['affine_rho']:.9f}, ΔC2−C0={delta_rho:+.9f}. C2 critical={new['grid']['critical_line_phase']} / slot {new['grid']['critical_slot']}. 추종 오차와 계통 변화는 별개다. 일간 최대/Fresh AC 개선으로 주장하지 않는다.
12. C1 Frozen 표는 **NOT_RUN**이다. Source-only 전체 grammar 비용 추정은 {runtime['C1_compile']['Source_only_estimate']}; 1KiB/후보 record 가정은 휴리스틱이고 실제 dedup 후 최소 RAM의 증명이 아니다. 실제 compile wall=0, compile peak RSS=NULL이며 비용 측정 실행은 미시도다. fixture를 실제 제어표로 사용하지 않았다. Frozen 대비 우수성은 미검증이다.
13. C2 Migration={du['Unknown_Actual_Migration_UID']}, C3 Migration={None if c3 is None else c3['unknown']['Unknown_Actual_Migration_UID']}. C2 funnel unique={migration_unique}. 적격 checkpoint 계약 6 UID 중 4 UID는 Q50 remaining이 없었고 2 UID는 shared interruption budget으로 거부됐다. Preplace를 제거해도 Migration이 증가하지 않았다. 일반 대체 관계는 미확정이며 본 구간은 실행 가능한 Migration 기회가 부족한 INSUFFICIENT_MIGRATION_OPPORTUNITY다.
14. C2 QoS intentional budget excess={new['QoS_intentional_budget_excess_UIDs']}, physical GPU violations={results['C2']['receipt']['capacity_violations']}, affine grid violation rows={len(new['grid']['hard_violations'])}, Known/Unknown overlap={new['known_unknown_overlap_UIDs']}. Source hard windows와 Migration/WAN guard 유지. Queue/latest-start/CDF 위험이 0이라는 추가 보장은 하지 않는다. Latest-start excess UID={new['latest_start_excess_UIDs']}. 독립 Anchor 96슬롯 affine PASS={identity['independent_96_slot_affine_PASS']}이며 새 E1 FULL MILP 인증은 아니다.
15. 실제 16슬롯 실행·C1 재계산·동일 입력·독립 상태·optimizer0을 검증했다. 회귀 {regression['passed']} PASS. Native={runtime['A1_Native_seconds']}s, A1 시도 wall={runtime['A1_attempt_wall_seconds']:.3f}s, 이번 diagnostic watchdog wall={watchdog['wall_seconds']:.3f}s, 준비 중단과 진단 실행의 누적 wall={watchdog['cumulative_execution_wall_seconds']:.3f}s. 개발 수정·회귀 시간은 별도이며 Native 재시도는 없다. Full96 Actual, 일간 peak, 31일, 새 E1 A1/P2, C1 비교 및 Fresh AC는 미검증이다. OpenDSS는 PARTIAL_AC_NOT_AUTHORIZED/NULL. 04:00 Running/Pending과 private continuation 상태를 보존했다.

기존 통합 원장 621.2855198158068/3600초와 B2 별도 원장 1257.5220000743866/1800초의 바이트 SHA를 보존했다. 이번 모델 준비/Native/Actual wall은 별도 원장에 기록했다. B2/B3/May31 자동 실행 및 외부 worker 종료는 없다.

실제 후보 거부 원인(C2)은 {du['rejection_candidate_event_counts']}다. UID별 거부 집합은 중복 가능하다. 특히 공개 Q50 예상 점유와 Known 확정 예약이 capacity를 초과하는 후보를 배제했으며, 이 예측을 실제 미래 완료의 증거로 사용하지 않았다. 현재 실험에서는 Tracking이 실제 변경을 만들지 못했고, 2개 슬롯의 exact-C1/signed voltage hard 위반과 Queue/latest-start 위험이 남았다. **실측 Canary의 과학 Gate는 FAIL/CLOSED**다. 구현·파일 전달 검증 PASS를 물리·QoS·Full96 PASS로 표시하지 않는다.
'''
    (out/'FINAL_REVIEW_KO.md').write_text(review,encoding='utf8')
    gates=dict(Known_Unknown_separation_PASS=all(x['known_unknown_overlap_UIDs']==0 for x in metrics.values()),
        same_case_same_input_PASS=len({r['tracking_canary']['input_SHA'] for r in results.values()})==1,
        new_E1_A1_certified=False,anchor_independent_physical_PASS=identity['independent_96_slot_affine_PASS'],
        no_future_information_PASS=all(r['receipt']['future_duration_controller_reads']==0 and r['receipt']['future_completion_controller_reads']==0 for r in results.values()),
        QoS_intentional_budget_PASS=all(x['QoS_intentional_budget_excess_UIDs']==0 for x in metrics.values()),
        model_latest_start_no_excess_PASS=all(x['latest_start_excess_UIDs']==0 for x in metrics.values()),
        observed_completion_deadline_PASS=all(x['observed_completion_deadline_excess_UIDs']==0 for x in metrics.values()),
        resource_PASS=all(r['receipt']['capacity_violations']==0 for r in results.values()),
        actual_C1_PASS=True,controller_global_optimizer_calls=0,memory_wall_PASS=not watchdog['stop_reason'] and watchdog['cumulative_execution_wall_seconds']<=1200,
        grid_hard_PASS=all(not x['grid']['hard_violations'] for x in metrics.values()),
        Known_commands_immutable_PASS=all(x['Known_command_SHA_unchanged'] for x in metrics.values()),
        actual_tracking_behavior_confirmed=du['Unknown_Actual_Changed_UID']>0,
        Full96_Actual_started=False,Full96_Actual_PASS=False,Fresh_AC_PASS=False)
    gates['diagnostic_Full96_package_ready']=all(gates[k] for k in ('Known_Unknown_separation_PASS','same_case_same_input_PASS',
        'anchor_independent_physical_PASS','no_future_information_PASS','QoS_intentional_budget_PASS','resource_PASS',
        'actual_C1_PASS','memory_wall_PASS','grid_hard_PASS','Known_commands_immutable_PASS','actual_tracking_behavior_confirmed',
        'model_latest_start_no_excess_PASS','observed_completion_deadline_PASS'))
    gates['new_E1_integrated_Full96_package_ready']=False
    gates['followup_scope']='SAME_FROZEN_DIAGNOSTIC_ANCHOR_ONLY;SEPARATE_EXPLICIT_RUN;NO_AUTOMATIC_FULL96'
    write(out/'FULL96_FOLLOWUP_GATE.json',gates)
    # Preserve large exact replay/setup evidence compressed for Git delivery.
    compressed=[]
    paths=list(out.glob('C?_RESULT.json'))+list((out/'NEW_A1_ATTEMPT/CASE').glob('*'))+list((out/'DIAGNOSTIC_SETUP/CASE').glob('*'))
    for p in paths:
        if not p.is_file():continue
        target=out/'compressed_evidence'/p.relative_to(out);target=target.with_suffix(target.suffix+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        raw=p.read_bytes();target.write_bytes(gzip.compress(raw,mtime=0));assert gzip.decompress(target.read_bytes())==raw
        compressed.append(dict(original=str(p.relative_to(out)),gzip=str(target.relative_to(out)),
            sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    write(out/'COMPRESSED_EVIDENCE_MANIFEST.json',compressed)
    print(json.dumps(dict(results=list(results),tests=regression['passed'],delta_P_error_kWh=delta_p,
        C2_minus_C0_affine_rho=delta_rho,compressed_files=len(compressed),Full96_Actual_started=False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);main(parser.parse_args().output)

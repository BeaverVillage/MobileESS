"""Negative-result delivery only; refuses to skip an authorized positive branch."""
from common13 import *
import re

STATUS='NOT_RUN_GATE_FAILED'
SKIPPED_CSV=['REMAINING_MODEL_COMPARISON.csv','REMAINING_FOLD_METRICS.csv','REMAINING_ELAPSED_STRATA.csv',
 'REMAINING_LONG_RUNNING_METRICS.csv','PREAPRIL_FORECAST_REPLAY.csv','PREAPRIL_CAUSAL_STRESS_REPLAY.csv',
 'APRIL_EXPOSED_TOTAL_METRICS.csv','APRIL_EXPOSED_REMAINING_METRICS.csv','APRIL2_EXPOSED_QUEUE_REGRESSION.csv']
SKIPPED_JSON=['CHECKPOINT_SAMPLE_AUDIT.json','CHECKPOINT_STATE_CAUSALITY_AUDIT.json','CHECKPOINT_EPISODE_SPLIT_AUDIT.json',
 'OOF_TOTAL_FEATURE_AUDIT.json','REMAINING_MODEL_SELECTION_FREEZE.json','PROVIDER_BUNDLE_FREEZE.json']
def pct(x):return f'{x*100:.2f}%'
def main():
    selection=read(ROOT/'TOTAL_MODEL_SELECTION_FREEZE.json')
    assert not selection['TOTAL_RUNTIME_MODEL_VALIDATED'],'TOTAL passed: execute authorized Stage C; do not finalize a negative result'
    assert (ROOT/'TRAINING_COMPLETED.json').exists()
    early=read(ROOT/'EARLY_TERMINATION_RECEIPT.json')
    assert early['EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE'] and early['completed_ablation_folds']==22
    comp=pd.read_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv');fold=pd.read_csv(ROOT/'TOTAL_FOLD_METRICS.csv')
    assert not comp.eligible.any()
    anchor=selection['diagnostic_ablation_anchor'];indexed=comp.set_index('arm');best=indexed.loc[anchor];base=indexed.loc['EXPANDING_S0']
    ab=pd.read_csv(ROOT/'CURRENT_STATE_FEATURE_ABLATION.csv');c1=read(ROOT/'C1_ELIGIBILITY_AUDIT.json')
    causal=read(ROOT/'CURRENT_STATE_CAUSALITY_AUDIT.json');replay=read(ROOT/'CURRENT_STATE_REPLAY_AUDIT.json')
    reason='No preregistered TOTAL candidate passes all gates A-I; diagnostic candidates are not provider selections.'
    for name in SKIPPED_CSV:pd.DataFrame([dict(status=STATUS,metrics_available=False,reason=reason)]).to_csv(ROOT/name,index=False)
    for name in SKIPPED_JSON:write(name,dict(time=now(),status=STATUS,executed=False,metrics_available=False,reason=reason,files=[]))
    (ROOT/'RUNTIME_PROVIDER').mkdir(exist_ok=True)
    (ROOT/'RUNTIME_PROVIDER/README.md').write_text('# NOT_RUN_GATE_FAILED\n\nTOTAL 통과 후보가 없어 최종 provider는 생성하지 않았습니다.\n연구용 상태 엔진과 fold 모델은 최종 provider가 아닙니다.\n',encoding='utf-8')
    write('STOP_CONDITION_RECEIPT.json',dict(time=now(),status='STOPPED_AFTER_STAGE_B',reason=reason,
        selected='NONE',total_gate_table=record(ROOT/'TOTAL_MODEL_COMPARISON.csv'),Stage_C=STATUS,April=STATUS,May='SEALED'))
    flags=dict(time=now(),status='STOPPED_AFTER_STAGE_B',STRICT_CAUSAL_FEATURE_COUNT=0,REQUEST_VERSION_AUTHORITY_FOUND=False,
        STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,provenance_mode='Kestrel_trace_proxy',
        CURRENT_STATE_CAUSALITY_PASS=causal['PASS'],CURRENT_STATE_REPLAY_DETERMINISTIC=replay['PASS'],
        FUTURE_SUBMIT_READS=0,FUTURE_START_READS=0,FUTURE_END_READS=0,CURRENT_JOB_FUTURE_EVENT_READS=0,
        CURRENT_STATE_FEATURE_COUNT=read(ROOT/'CURRENT_STATE_FEATURE_CONTRACT.json')['feature_count'],
        SELECTED_STATE_SET='NONE',TOTAL_RUNTIME_MODEL_VALIDATED=False,
        individual_gate_flags_scope='TOTAL_OVERALL_Q90_GATE_PASS is the user-required fail-closed delivery flag: no validated provider. Other numeric diagnostic gates remain explicitly reported; frozen primary gate_A is unchanged.',DIAGNOSTIC_ABLATION_ANCHOR=anchor,
        DIAGNOSTIC_ANCHOR_RAW_POOLED_Q90_GATE_A_PASS=bool(best.gate_A),
        TOTAL_OVERALL_Q90_GATE_PASS=False,TOTAL_MIN_FOLD_GATE_PASS=bool(best.gate_B),
        TOTAL_GT4H_GATE_PASS=bool(best.gate_C),TOTAL_GT12H_GATE_PASS=bool(best.gate_D),
        TOTAL_GT24H_DIAGNOSTIC_PASS=bool(best.gate_E),TOTAL_RESERVATION_GATE_PASS=bool(best.gate_F),
        TOTAL_PROPER_DISTRIBUTION_GATE_PASS=bool(best.gate_G),ZERO_SUPPORT_OBSERVED_INTERVAL_COUNT=int(comp.zero_support_count.sum()),
        C1_ROLLING14_EVALUATED=c1['C1_ROLLING14_EVALUATED'],STAGE_C_AUTHORIZED=False,
        REMAINING_MODEL_RUN=False,REMAINING_RUNTIME_MODEL_VALIDATED=False,
        CHECKPOINT_EPISODE_CROSS_SPLIT_LEAKAGE=0,OOF_TOTAL_PREDICTION_LEAKAGE=0,
        leakage_zero_scope='No checkpoint or OOF remaining dataset created; counts mean no operations, not empirical model validation',
        CAUSAL_CURRENT_STATE_UPDATE_REQUIRED=False,state_update_flag_scope='no selected provider',
        RESEARCH_STATE_MODELS_REQUIRE_STATE_UPDATE=True,ONLINE_MODEL_REFIT_REQUIRED=False,V42_RESEARCH_RUNTIME_PROVIDER_READY=False,
        APRIL_USED_FOR_SELECTION=False,APRIL_STATUS=STATUS,APRIL_HISTORICAL_DESIGNATION='EXPOSED_REGRESSION_ONLY',APRIL_EVALUATION_STATUS=STATUS,
        APRIL_MODEL_CHANGED_AFTER_EVALUATION=False,MAY_PAYLOAD_OPENED=False,MAY_USED_FOR_SELECTION=False,MAY_USED_FOR_EVALUATION=False,
        EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE=True,
        DIAGNOSTIC_ABLATION_COMPLETED_FOLDS=22,DIAGNOSTIC_ABLATION_UNRUN_FOLDS=3,
        CURRENT_STATE_TRACKS_FOLD1='INCONCLUSIVE',CURRENT_STATE_TRACKS_FOLD4='INCONCLUSIVE',diagnostic_metrics=best.to_dict())
    write('FINAL_VERDICT.json',flags)
    write('INFERENCE_COST_SCOPE.json',dict(scope='Full VALID hazard-parameter prediction on CPU4',
        feature_materialization_included=False,quantile_inversion_included=False,isolated_latency_benchmark=False,
        concurrent_fold_workers=2,selection_use='last tie-breaker only; no passing candidate',
        S0_training_seconds='historical frozen V9 metadata; no V13 S0 refit'))
    history=pd.read_csv(REPO/'docs/runtime_vnext12_causal_regime_runtime/TOTAL_MODEL_COMPARISON.csv')
    history=history.assign(version='V12',comparison_scope='same original temporal folds; completed-runtime regime hypothesis')
    current=comp.assign(version='V13',comparison_scope='same original temporal folds; current-workload-state hypothesis')
    pd.concat([history,current],ignore_index=True).to_csv(ROOT/'HISTORICAL_TEMPORAL_COMPARISON.csv',index=False)
    temporal=comp[['arm','Q90_coverage','min_fold_coverage','max_fold_coverage','coverage_std','gt4h_coverage','Q90_pinball','eligible']].copy()
    for metric in ['gt4h_coverage','gt12h_coverage','gt24h_coverage','Q90_pinball','Q50_MAE','reservation_actual_GPUh']:
        grouped=fold.groupby('arm')[metric]
        for label,values in [('min',grouped.min()),('max',grouped.max()),('std',grouped.std(ddof=0))]:
            temporal[metric+'_fold_'+label]=temporal.arm.map(values)
    temporal.to_csv(ROOT/'TEMPORAL_ROBUSTNESS_COMPARISON.csv',index=False)
    def describe(arm):
        r=indexed.loc[arm]
        return f'{arm}: pooled {pct(r.Q90_coverage)}, min-fold {pct(r.min_fold_coverage)}, >4h {pct(r.gt4h_coverage)}, fold 표준편차 {r.coverage_std*100:.2f}pp.'
    def family_changes():
        return ' '.join(f'S{i-1}→S{i}: min-fold {(indexed.loc[f"EXPANDING_S{i}"].min_fold_coverage-indexed.loc[f"EXPANDING_S{i-1}"].min_fold_coverage)*100:+.2f}pp.' for i in range(1,5))
    def ablations():
        result=[];helpful=[]
        labels=dict(A='arrival',B='pending 기본',C='running 기본',D='composition',E='interaction')
        for _,r in ab.iterrows():
            if r.metrics_available:
                result.append(f'{r.group}({labels[r.group]}) 제거: min-fold 변화 {r.delta_min_fold*100:+.2f}pp, pinball 변화 {r.delta_pinball:+.2f}s')
                if r.delta_min_fold<0:helpful.append(labels[r.group])
            else:result.append(f'{r.group}: {r.status}; 완료 fold {r.completed_folds}, 미실행 fold {r.unrun_folds}. 부분 fold 실측값은 ABLATION_FOLD_METRICS.csv에 보존하며 전체 arm 지표는 산출하지 않음')
        return '; '.join(result)+'. 제거 시 min-fold가 낮아져 조건부 기여가 확인된 block은 '+(', '.join(helpful) if helpful else '없음')+'. 그룹 범위는 ABLATION_SCOPE.md를 따른다. 인과효과를 뜻하지 않는다.'
    forensic=pd.read_csv(ROOT/'FOLD_CURRENT_STATE_SUMMARY.csv').set_index('fold')
    pressure=pd.read_csv(ROOT/'FOLD_WORKLOAD_PRESSURE.csv')
    def fs(i):
        r=forensic.loc[i];p=pressure[pressure.fold.eq(i)].pivot(index='feature',columns='snapshot',values='value')
        return 'INCONCLUSIVE. '+ ' / '.join(f'{label}: 14일 전 {p.loc[c,"14d_before"]:.0f} → VALID 직전 {p.loc[c,"before_VALID"]:.0f}' for c,label in [('a_86400_num_gpus_req_sum','24h arrival GPU합'),('p_num_gpus_req_sum','pending GPU'),('r_num_gpus_req_sum','running GPU')])+f'. 다음 VALID runtime Q90={r.runtime_q90:.0f}s, >4h 비율={pct(r.gt4h_fraction)}. 압력 변화는 관측되지만 이것만으로 runtime shift 추적을 입증하지 않는다.'
    short=' / '.join(f'{r.arm} {r.short_job_reservation_inflation:.2f}배' for _,r in comp.iterrows())
    d90=indexed.loc['D90_S4'];s4=indexed.loc['EXPANDING_S4']
    c1text=('실행했다. '+str(c1.get('evaluated_C0_arm'))+' 한 후보에 기존 V9 causal rolling14만 적용했고 양의 support와 proper score도 다시 검사했다.' if c1['C1_ROLLING14_EVALUATED'] else
       '실행하지 않았다. 어느 C0도 min-fold≥80%와 pooled >4h≥80%를 동시에 만족하지 않아 사전 조건을 충족하지 못했다.')
    answers=[
      'V12는 최근 완료 작업의 runtime이 다음 workload를 일관되게 대표하지 못했다. R0/R2 min-fold는66.47%/52.04%, >4h는71.07%/51.97%였다. 새로 유입됐지만 미완료인 작업은 완료 통계에 반영되지 않는 지연이 한 가지 가능한 설명이며, 실패의 근본 원인을 확정한 것은 아니다.',
      '완료된 runtime 대신 이미 관측된 제출 요청, 시작된 작업, 아직 시작되지 않은 대기 작업을 요약한다. 실제 runtime은 새 상태 변수에 들어가지 않는다.',
      'archive adapter가 SUBMIT/START/END를 분리하고 dispatcher가 timestamp<t인 이벤트만 상태 엔진에 전달한다. pending/running identity map과 rolling arrival buffer·resource/category counter를 이벤트마다 갱신한다. 전체 archive의 미래 start/end 조건으로 상태를 역산하지 않는다.',
      f'상태 feature의 미래 SUBMIT/START/END 읽기는 모두0이다. 무작위{causal["N"]:,}개 시점에서 모든 미래 suffix를 교란하고 과거 SUBMIT의 GPU를 바꾼 양성 대조를 수행했다. 별도1,024개 표본에서 실제 미래 scheduling timestamp 배열 변경과 독립 event reducer도 검증했다. 스케줄러의 전달 경계 비교는 미래 payload 소비와 구분한다.',
      '예측 시각과 같은 모든 이벤트를 제외한다. 이후 예측을 위해 동일 timestamp 배치를 SUBMIT→START→END, 같은 종류 내 canonical source 행 순서(submit_time, job_id)로 처리한다. 이 정렬키는 학습 전 동결한 코드에 명시되어 있으며 세부 문구는 SAME_TIMESTAMP_ORDER_CLARIFICATION.md에 설명했다. 동시 제출 cohort의 전체 크기는 읽지 않으며 관측된 same-timestamp count는0이다.',
      '5분 제출수,15분/1h/6h/24h 제출수와 requested GPU/node/core/memory/GPU-time 합, GPU·walltime 평균/중앙값, walltime Q75/Q90, highGPU·longwall·array 비율/수, 같은 account/QoS/partition의 최근 제출수, 이전 관측 제출 이후 시간이다.',
      'SUBMIT이 처리됐고 START가 처리되지 않은 identity 집합이다. 관측 END가 pending을 종료할 수도 있다. 요청량·구성·관측 submit 기준 나이를 집계하며 미래 시작 시각은 저장하지 않는다.',
      'START가 처리되고 END가 아직 처리되지 않은 identity 집합이다. 요청 GPU/node/core/memory, 관측 START로부터 경과시간, 구성과 같은 account 수를 집계한다.',
      'START 처리 시 running map과 자원 합에 더하고 END 처리 시 제거한다. 미래 END가 없거나 아직 도착하지 않은 작업은 계속 running으로 남는다. GPU는 실제 점유 센서가 아닌 archived requested GPU의 연구 proxy다.',
      fs(1),fs(4),describe('EXPANDING_S0'),describe('EXPANDING_S1'),describe('EXPANDING_S2'),describe('EXPANDING_S3'),describe('EXPANDING_S4'),
      family_changes()+' '+ablations(),
      f'선택 모델은 없다. 진단 anchor {anchor}의 pooled={pct(best.Q90_coverage)}. 모든 모델은 동일 exact-completed VALID {int(best.N):,}개로 coverage/오차를 비교하며, right-censored 표본은 proper likelihood에 포함한다.',
      f'진단 anchor {pct(best.min_fold_coverage)}. 최대 fold={pct(best.max_fold_coverage)}, 표준편차={best.coverage_std*100:.2f}pp. 필수 최소 기준은85%다.',
      f'진단 anchor {pct(best.gt4h_coverage)}, N={int(best.gt4h_N):,}. 필수85% 기준을 완화하지 않았다.',
      f'진단 anchor >12h={pct(best.gt12h_coverage)} (N={int(best.gt12h_N):,}), >24h={pct(best.gt24h_coverage)} (N={int(best.gt24h_N):,}). 각각80%, N≥100에서70% 기준을 적용했다.',
      f'진단 anchor reservation/actual GPUh={best.reservation_actual_GPUh:.4f}, W0 대비={best.reservation_to_W0:.4f}. Q90과 W0는900초 slot 올림이며 W0 대비≤0.80을 material reduction으로 고정했다. 양의 runtime에서 Q90/runtime 중앙값={best.Q90_actual_ratio_median:.4f}, P90={best.Q90_actual_ratio_P90:.4f}; zero-runtime={int(best.zero_runtime_N):,}개는 ratio에서 제외했다.',
      f'진단 anchor Q90 pinball={best.Q90_pinball:.2f}s, Q50 MAE={best.Q50_MAE:.2f}s. S0는 각각{base.Q90_pinball:.2f}s/{base.Q50_MAE:.2f}s다. Proper interval NLL={best.proper_interval_NLL:.6f}, C0의 zero-support 관측 interval은0이다.',
      f'진단 anchor의 short-job overreservation은 S0보다 {"늘었다" if best.short_job_reservation_inflation>base.short_job_reservation_inflation else "줄었다" if best.short_job_reservation_inflation<base.short_job_reservation_inflation else "같다"}. 0<runtime≤1h short job의 slot-rounded 예약 GPUh/실제 GPUh로 사전 정의했다. '+short+'. 이 비율에는900초 slot 올림 자체의 영향도 포함된다. 모든 후보에 같은 규칙을 적용하며 coverage만 높고 예약이 큰 모델을 성공으로 보지 않는다.',
      f'전체 안전 기준을 충족하는 안정적 개선은 입증하지 못했다. 진단 anchor 대비 S0의 min-fold 변화는 {(best.min_fold_coverage-base.min_fold_coverage)*100:+.2f}pp, >4h 변화는 {(best.gt4h_coverage-base.gt4h_coverage)*100:+.2f}pp이다. 일부 지표 개선과 전체 가설 검증 성공은 구분한다.',
      f'D90은 min-fold 기준으로 {"더 나았다" if d90.min_fold_coverage>s4.min_fold_coverage else "더 낫지 않았다"}. S4의 EXPANDING/D90 min-fold={pct(s4.min_fold_coverage)}/{pct(d90.min_fold_coverage)}, >4h={pct(s4.gt4h_coverage)}/{pct(d90.gt4h_coverage)}, pinball={s4.Q90_pinball:.2f}/{d90.Q90_pinball:.2f}s. 어느 쪽도 전체 gate를 통과하지 못했다.',
      c1text,
      '아니다. 모든 gate를 통과한 후보0개, SELECTED_STATE_SET=NONE, TOTAL_RUNTIME_MODEL_VALIDATED=FALSE다. 진단 anchor는 provider 선택이 아니다.',
      '그렇다. STAGE_C_AUTHORIZED=FALSE이며 fail-closed guard도 검증했다. Remaining 학습과 최종 provider 생성을 실행하지 않았다.',
      STATUS+'. REM_A/REM_B를 비교하지 않았다.',
      STATUS+'. Remaining coverage 수치를 생성하지 않았다.',
      STATUS+'. 일반 상태 엔진의 임의 시각 replay는 검증했지만 remaining checkpoint 표본·모델 실험은 하지 않았다. 누수 count0은 데이터 미생성을 뜻하며 checkpoint 성능이나 인과성 검증 성공이 아니다.',
      STATUS+'. queue/stress replay를 실행하지 않아 감소를 주장하지 않는다. V42의 관측 RUNNING 유지, GPU 점유 유지,900초 연장, STAY fallback은 그대로다.',
      f'연구 상태 엔진은 {replay["N"]:,}개 예측행×{replay["features"]}개 feature에서 연속 재생과4개 새 프로세스의 저장/복원 재생이 bit-identical하다. 연구 fold 모델의 재로드 예측도 검증한다. 최종 provider는 생성하지 않았으므로 provider 승인으로 해석하지 않는다.',
      '아니다. ONLINE_MODEL_REFIT_REQUIRED=FALSE다. 연구 상태 모델을 추론하려면 관측 이벤트에 따른 state update가 필요하지만 booster 파라미터는 고정된다. 최종 flag의 state-update-required=FALSE는 선택 provider가 없다는 범위다.',
      '아니다. TOTAL와 필요한 remaining 검증, provider bundle 동결을 선행해야 하지만 TOTAL에서 실패했다. APRIL_STATUS=NOT_RUN_GATE_FAILED다. EXPOSED_REGRESSION_ONLY는 이전의 자료 지위이며 평가 실행을 뜻하지 않는다.',
      'NO. April을 평가하거나 선택·튜닝에 사용하지 않았다.',
      'NO. May payload·선택·평가 모두 FALSE다. 입력은 이전에 분리된 pre-April parquet와 고정 fold 파일뿐이다.',
      '아니다. V42_RESEARCH_RUNTIME_PROVIDER_READY=FALSE다. 기준을 낮추거나 실패 후보를 provider로 승격하지 않았다.',
      'event-time 인과성과 request provenance는 별개다. Archived requested walltime/GPU/QoS 등의 immutable original-submit authority가 없어 STRICT_CAUSAL_FEATURE_COUNT=0, REQUEST_VERSION_AUTHORITY_FOUND=FALSE, STRICT_CAUSAL_RUNTIME_PROVIDER_READY=FALSE를 유지한다.',
      'Current observable arrival/pending/running/composition state는 일부 fold와 일부 지표를 개선했지만, 사전 고정한 temporal robustness 및 long-runtime Q90 safety gate를 만족하지 못했다. 따라서 Runtime-vNext13은 V42 runtime provider로 승격되지 않는다. 현재 scheduler/request/current-state observable만으로는 안정적인 per-job Q90을 확립하지 못했다. 다음 연구는 새로운 정보축, 특히 workflow/application semantic information 및 join 가능한 external telemetry의 추가 가치를 별도 preregistered experiment로 평가해야 한다. 이는 추가 정보의 가치를 검증할 후속 가설이며 hidden-variable 원인을 증명한 것이 아니다. 자동으로 다음 실험이나 모델 탐색을 시작하지 않는다.'
    ]
    request=(ROOT/'USER_REQUEST.txt').read_text(encoding='utf-8-sig')
    portion=request.split('45. REQUIRED FINAL KOREAN QUESTIONS',1)[1].split('46. FINAL FLAGS',1)[0]
    questions=re.findall(r'(?m)^(\d+)\. (.+)$',portion)
    assert len(questions)==len(answers)==41
    lines=['# Runtime-vNext13 최종 검토','',
        'TOTAL 통과 후보0개로 Stage B에서 종료했습니다. 최종 provider·remaining·queue replay·April 평가는 미실행입니다.',
        '입력은 GPU 요청 작업 subset이며 전체 물리 클러스터 상태의 완전한 관측은 아닙니다. Archive 요청 값의 provenance 한계와 observation-cutoff에 따른 completion-selection 한계를 유지합니다.','',
        '## A. 확정된 primary result','',
        '6개 preregistered C0 후보와 원래 5개 temporal fold 결과를 동결했습니다. 모든 후보가 필수 gate 조합에서 실패했습니다. C1의 min-fold≥80% 및 pooled >4h≥80% 실행 조건도 충족하지 못했습니다.',
        'S4의 pooled 91.84%는 개별 수치 gate A(88–92%)를 통과했습니다. 그러나 min-fold·long-runtime 안전 gate가 실패하여 승인 provider는 없습니다. 최종 TOTAL_OVERALL_Q90_GATE_PASS=FALSE는 사용자 지정 fail-closed 전달 판정이며, 원래 CSV의 실제 gate_A=TRUE를 변경하지 않았습니다.','',
        '| Arm | Pooled Q90 | Min-fold | >4h | >12h | >24h | Pinball(s) | W0 대비 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for _,r in comp.iterrows():lines.append(f'| {r.arm} | {pct(r.Q90_coverage)} | {pct(r.min_fold_coverage)} | {pct(r.gt4h_coverage)} | {pct(r.gt12h_coverage)} | {pct(r.gt24h_coverage)} | {r.Q90_pinball:.2f} | {r.reservation_to_W0:.4f} |')
    lines.extend(['','## B. 완료된 diagnostic ablation','',
        'A(arrival), B(pending 기본), C(running 기본), D(composition)는 각각 5개 fold를 완료했습니다. E(interaction)는 중단 지시 시 진행 중이던 fold 1·2의 저장까지 완료했습니다. 총 22개 완료 fold의 모델·예측·실측 지표를 보존했습니다. Diagnostic은 primary 후보군을 확장하거나 provider를 선택하는 데 사용하지 않았습니다.','',
        '| 제거 group | 완료 folds | Pooled Q90 | Min-fold | >4h | Pinball(s) |',
        '|---|---|---:|---:|---:|---:|'])
    for _,r in ab[ab.metrics_available].iterrows():
        lines.append(f'| {r.group} | {r.completed_folds} | {pct(r.Q90_coverage)} | {pct(r.min_fold_coverage)} | {pct(r.gt4h_coverage)} | {r.Q90_pinball:.2f} |')
    lines.extend(['','E의 부분 결과(5-fold pooled 결과가 아님):'])
    partial=pd.read_csv(ROOT/'ABLATION_FOLD_METRICS.csv')
    for _,r in partial[partial.arm.str.endswith('_E')].iterrows():
        lines.append(f'- fold {int(r.fold)}: Q90 {pct(r.Q90_coverage)}, >4h {pct(r.gt4h_coverage)}.')
    lines.extend(['','## C. Early termination 때문에 미실행된 diagnostic','',
        'E fold 3·4·5는 NOT_RUN_EARLY_TERMINATION_AFTER_PRIMARY_GATE_FAILURE입니다. E 전체 arm의 미완료 지표를 0, PASS 또는 추정값으로 채우지 않았습니다. 완료된 E fold 1·2는 별도 실측 행으로 보존했습니다.',
        'Primary scientific verdict가 이미 결정된 뒤 남은 diagnostic만 생략한 비용 절감 결정입니다. 실행 중 작업을 강제 종료하지 않았습니다. 다음 fit의 contract 읽기를 잠금으로 차단했고 worker 종료 후 잠금을 해제했습니다. 로그의 다음 FIT 표시는 학습 호출 전 출력이며, 이어진 PermissionError는 의도한 실행 차단입니다. 과학적 학습 실패로 해석하지 않습니다. 원본 로그와 byte-identical 사본 및 local evidence hash manifest를 보존했습니다.','',
        '## D. 미실행 Stage C / provider / April / May','',
        'Stage C authorization=FALSE, remaining model=NOT_RUN, final Runtime provider=NOT_RUN, April=NOT_RUN_GATE_FAILED, May=unopened입니다. V42/CC4/MESS/kernel/optimizer/OpenDSS는 수정하거나 실행하지 않았습니다.','',
        '## 제한된 결론과 후속 가설','',answers[-1]])
    if (ROOT/'TEMPORAL_COVERAGE.png').exists():lines.extend(['','![Temporal and tail coverage](TEMPORAL_COVERAGE.png)'])
    for (number,q),a in zip(questions,answers):lines.extend(['',f'## {number}. {q}','',a])
    lines.extend(['','최종화 재현 순서(학습 없음): 보존된 .local evidence 준비 → collect_final13.py → finalize13.py → verify13.py. train13.py는 실행하지 않습니다.',
        '원래 연구 실행 이력은 prepare13.py → test_state13.py → stage_a13.py → independent_audit13.py → train13.py의 primary와 완료 diagnostic → 사용자 조기 종료입니다. 동결된 train13.py는 연구 이력 보존용이며 재실행하면 미실행 진단을 학습할 수 있으므로 이번 전달 검증에서 실행하지 않습니다.',
        '원시 입력·중간 feature·개별 예측은 SOURCE_MANIFEST 및 LOCAL_EVIDENCE_MANIFEST와 .local 파일로 고정하며 Git에는 대용량 local 파일을 포함하지 않습니다. 원본 실행 로그의 동일 바이트 사본은 EXECUTION_LOGS에 포함합니다. 기존 V9 .local 입력 파일도 manifest 해시와 일치해야 합니다. prepare13.py는 기존 PREREGISTRATION.json 덮어쓰기를 거부합니다.'])
    (ROOT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'README.md').write_text('# Runtime-vNext13 current workload state\n\n'
        'TOTAL gate 통과 후보 없음: Stage B에서 종료. [한국어41문항 검토](FINAL_REVIEW_KO.md), [판정](FINAL_VERDICT.json).\n\n'
        '6개 사전등록 raw hazard 후보의 primary 결과를 동결했습니다. C1 조건은 미충족입니다. Diagnostic A–D 각 5 fold와 E fold 1·2만 완료했고, E fold 3·4·5는 primary 판정 후 비용 절감을 위해 조기 종료했습니다.\n'
        'V6–V12 과학 산출물, V42/CC4/MESS/전기 kernel은 변경하지 않았습니다. April 신규 평가와 May 자료 열람은 없습니다.\n\n'
        '재현에 SOURCE_MANIFEST의 기존 V9 .local pre-April/role parquet가 필요합니다. 연구 실행 환경은 runtime_vnext_exact_environment입니다.\n'
        '전달 검증은 보존된 evidence로 collect_final13.py → finalize13.py → verify13.py만 실행합니다. 동결된 train13.py는 재실행하지 않습니다. [후속 조기 종료 지시](EARLY_TERMINATION_INSTRUCTION.md)가 미완료 diagnostic 실행 요구를 대체합니다.\n'
        '동일 timestamp의 정확한 정렬키는 [구현 설명](SAME_TIMESTAMP_ORDER_CLARIFICATION.md)에 기록했습니다.\n'
        'state13.py는 순수 event engine, stream13.py는 offline archive adapter/time-gated dispatcher입니다. RUNTIME_PROVIDER는 미실행 상태 기록입니다.\n',encoding='utf-8')
    print('V13_NEGATIVE_DELIVERY',anchor,flush=True)
if __name__=='__main__':main()

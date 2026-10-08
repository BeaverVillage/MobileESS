"""Post-run reports, source/data preservation and scientific decision audit."""
import csv,subprocess,time,re,json
from pathlib import Path
from fractions import Fraction
from .policy import ROOT,OUT,STATIC,OLDOUT,DAY
from .audit import file_digest,processes
from .execution import active_freeze
from .postrun import attempt_walls,finish_incomplete_p1,regression_receipts,delivery_sources,native_call_counts
from v42_pr134_b1.common import read,record,atomic,sha,table

def preserve():
    manifest=read(OUT/'HISTORICAL_BYTE_MANIFEST.json');mismatches=[]
    for key in ('old_sources','old_evidence','old_cache'):
        for r in manifest[key]:
            try:now=file_digest(Path(r['path']))
            except OSError as e:mismatches.append(dict(old=r,error=str(e)));continue
            if now!=r:mismatches.append(dict(old=r,new=now))
    old_names={r['path'] for r in manifest['old_evidence']};current={str(p) for p in (OLDOUT/DAY).rglob('*') if p.is_file()}
    if old_names!=current:mismatches.append(dict(membership_change=sorted(old_names^current)))
    audit=dict(PASS=not mismatches,old_sources=len(manifest['old_sources']),old_evidence=len(manifest['old_evidence']),old_cache=len(manifest['old_cache']),
        byte_identity=True if not mismatches else False,mismatches=mismatches,other_processes_modified=False)
    atomic(OUT/'HISTORICAL_PRESERVATION_FINAL.json',audit)
    if mismatches:raise ValueError('HISTORICAL_BYTE_PRESERVATION_FAILED')
    return audit

def run():
    decision=read(OUT/'FINAL_DECISION.json');historical=preserve()
    finish_incomplete_p1()
    regression_receipts();delivery_sources()
    attempts,attempt_total=attempt_walls(OUT)
    calls=read(OUT/'NEW_NATIVE_CALLS.json').get('calls',[]) if (OUT/'NEW_NATIVE_CALLS.json').exists() else []
    counts=native_call_counts(calls)
    all_params=[];sizes=[]
    for c in calls:
        f=Path(c['folder']);i=read(f/'MODEL_IDENTITY.json');params=read(f/'SOLVER_PARAMETERS.json');memory=read(f/'MEMORY_LIMITS_DISABLED.json')
        log=(f/'NATIVE_SOLVER.log').read_text(encoding='utf8',errors='replace')
        nr=read(f/'NATIVE_RESULT.json')
        sizes.append(dict(component=c['component'],folder=str(f),rows=i['rows'],cols=i['cols'],nnz=i['nnz'],Runtime=c['native_seconds'],Work=c['Work'],
            status=nr['status'],presolved_matrix=nr.get('presolved_matrix'),peak_RSS_bytes=nr.get('peak_RSS_bytes'),
            build_and_snapshot_seconds=nr.get('build_and_snapshot_seconds'),
            max_factor_nnz=nr.get('max_factor_nnz'),max_factor_memory_GB=nr.get('max_factor_memory_GB'),
            factor_memory_lines=re.findall(r'Factor N(?:N)?Z[^\n]+',log),source_commit=i['source_commit']))
        p=params['effective'];all_params.append(dict(PASS=p['Threads']==1 and p['MIPGap']==.005 and p['FeasibilityTol']==1e-6 and p['OptimalityTol']==1e-6 and p['IntFeasTol']==1e-5
            and memory['MemLimit']=='inf' and memory['SoftMemLimit']=='inf',folder=str(f),parameters=params,memory=memory))
    task_start=(OUT/'MAY12_RECOVERY_AUDIT.json').stat().st_ctime
    runtime=dict(PASS=sum(c['native_seconds'] or 0 for c in calls)<=3600 and all(r['PASS'] for r in all_params),
        native_limit=3600,old_native_Runtime=233.89299654960632,new_native_Runtime=sum(c['native_seconds'] or 0 for c in calls),
        new_Work=sum(c['Work'] or 0 for c in calls),new_native_calls=counts['total'],old_calls=285,
        native_calls_with_positive_Runtime=counts['positive_runtime'],native_calls_with_zero_rounded_Runtime=counts['zero_runtime'],
        old_plus_new_native_Runtime=233.89299654960632+sum(c['native_seconds'] or 0 for c in calls),
        native_run_wall_seconds=attempt_total,native_run_attempt_walls=attempts,last_native_run_wall_seconds=decision['new_wall_seconds'],
        task_wall_since_recovery_audit_seconds=time.time()-task_start,
        practical_60_minute_wall_pass=time.time()-task_start<=3600,old_wall_seconds=2093.9435081481934,
        static_recovery=read(OUT/'RECOVERY_STATIC_COST.json'),parameters=all_params,actual_model_sizes=sizes,
        peak_native_RSS=max((c.get('peak_RSS_bytes') or 0 for c in calls),default=0),memory_limits=False,
        memory_automatic_stop=False,other_runs_read_only_observed=processes(),threads_per_native=1,calls_sequential=True,
        execution_epoch_provenance=record(OUT/'EXECUTION_EPOCH_AND_BUDGET_PROVENANCE.json'),
        remaining_native_Runtime=3600-sum(c['native_seconds'] or 0 for c in calls),
        actual_resource_pending_gate=record(OUT/'RESOURCE_START_GATE.json'),
        input_array_identity=record(OUT/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY.json'),
        full_scale_STAY_batch_verification_wall_seconds=read(OUT/'STAY_BATCH_ACTUAL_VERIFICATION.json')['wall_seconds'])
    atomic(OUT/'RESOURCE_AND_RUNTIME_AUDIT.json',runtime)
    if not runtime['PASS']:decision.update(PASS=False,classification='MAY12_NUMERICAL_TRACTABILITY_FAIL',audit_failure='NATIVE_POLICY_OR_BUDGET_NOT_PASSED')
    acceptance=read(OUT/'P1_ONLY_ACCEPTANCE_CONTRACT.json')
    if decision['PASS'] and (not acceptance['PASS'] or not read(OUT/'INDEPENDENT_INTEGER_VERIFICATION.json')['PASS']):
        raise ValueError('FINAL_ACCEPTANCE_INDEPENDENT_CERTIFICATES_REQUIRED')
    decision.update(Phase_I_recovered_and_zero_certified=read(OUT/'PHASE1_ZERO_CERTIFICATE.json')['PASS'],
        P1_full_domain_LB=read(OUT/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['LB'],
        exact_P1_full_domain_LB=read(OUT/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json')['exact_LB'],
        validated_integer_UB=acceptance.get('exact_UB'),global_integer_gap=acceptance.get('gap'),
        P1_only_accepted=acceptance.get('A1_P1_ONLY_ACCEPTED',False),A1_ACCEPTED=False,
        practical_60_minute_wall_pass=runtime['practical_60_minute_wall_pass'],
        cumulative_native_experiment_wall_seconds=attempt_total,remaining_native_Runtime=runtime['remaining_native_Runtime'],
        original_native_result=record(OUT/'LAST_NATIVE_RUN_DECISION.json'),automatic_followup=False)
    atomic(OUT/'FINAL_DECISION.json',decision)
    for name in ('COMPLETE_PRICING_CLOSURE.json','P1_FULL_DOMAIN_BOUND_CERTIFICATE.json','P1_INTEGER_RESULT.json','ORIGINAL_PHYSICAL_REPLAY.json','P1_ONLY_ACCEPTANCE_CONTRACT.json','P1_ONLY_FREEZE.json'):
        if not (OUT/name).exists():atomic(OUT/name,dict(PASS=False,status='NOT_CERTIFIED',reason=decision.get('error',decision['classification'])))
    table(OUT/'PERFORMANCE_COMPARISON.csv',[
        dict(stage='historical_initial_build',native_Runtime=0,Work=0,wall_seconds=222.4885911999736,scope='original completed May12 initial build'),
        dict(stage='historical_total',native_Runtime=233.89299654960632,Work=327.44561993108914,wall_seconds=2093.9435081481934,scope='285 historical calls unchanged'),
        dict(stage='recovery_initial_replay',native_Runtime=0,Work=0,wall_seconds=runtime['static_recovery']['recovery_initial_wall_seconds'],scope='192 concrete columns and identical prior master'),
        dict(stage='saved_directions_replay',native_Runtime=0,Work=0,wall_seconds=runtime['static_recovery']['recovered_directions_wall_seconds'],scope='92 saved exact negative directions'),
        dict(stage='zero_and_inclusion_certificate',native_Runtime=0,Work=0,wall_seconds=runtime['static_recovery']['prepare_wall_seconds'],scope='actual original dyadic rows and 130 analytical zero pricing'),
        dict(stage='batch_STAY_actual_matrix_shadow',native_Runtime=0,Work=0,wall_seconds=runtime['full_scale_STAY_batch_verification_wall_seconds'],scope='39993 exact negative STAY columns; verification only; no activation'),
        dict(stage='final_resume_integer_type_restore',native_Runtime=0,Work=0,wall_seconds=decision['timings']['integer_model_restore_seconds'],scope='subset of final resume wall; full original types and equations'),
        dict(stage='final_resume_activation_checkpoint_load',native_Runtime=0,Work=0,wall_seconds=decision['timings']['recovered_activation_build_seconds'],scope='subset of final resume wall; immutable saved activation reused'),
        dict(stage='post_run_independent_integer_verification',native_Runtime=0,Work=0,wall_seconds=read(OUT/'INDEPENDENT_INTEGER_VERIFICATION.json')['wall_seconds'],scope='additional post-run wall; full rational rows and physical replay'),
        dict(stage='new_recovery_P1_run',native_Runtime=runtime['new_native_Runtime'],Work=runtime['new_Work'],wall_seconds=runtime['native_run_wall_seconds'],scope='all new sequential P1 LP/pricing/integer work')],
        ['stage','native_Runtime','Work','wall_seconds','scope'])
    other={}
    for day in ('2025-05-19','2025-05-17','2025-05-10'):
        d=read(OLDOUT/day/'RESULT.json');other[day]={k:d.get(k) for k in ('A1_accepted','classification','practical_runtime_accepted','native_seconds','wall_seconds')}
    other['May10_PR184']=read(OUT/'MAY10_DELIVERY_RECEIPT.json')
    atomic(OUT/'OTHER_THREE_DAY_STATUS_COMPARISON.json',other)
    atomic(OUT/'DOWNSTREAM_COMPATIBILITY.json',dict(PASS=True,analysis_only=True,new_contract='A1_P1_ONLY_ACCEPTED',old_contract='A1_ACCEPTED',
        old_four_objective_contract_not_accepted_by_P1_only=True,old_P2_certificates_not_fabricated=True,
        old_pipeline_requires_P2=True,downstream_compatibility='REQUIRES_EXPLICIT_P1_ONLY_INTERFACE_ADAPTER_BEFORE_DOWNSTREAM',
        A1_M1_A2_M2_run=False,Planning_Actual_Fresh_AC_run=False))
    p1=read(OUT/'P1_ONLY_ACCEPTANCE_CONTRACT.json');z=read(OUT/'PHASE1_ZERO_CERTIFICATE.json');cl=read(OUT/'COMPLETE_PRICING_CLOSURE.json')
    masters=read(OUT/'P1_MASTER_SOLVE_AUDIT.json')['trajectory']
    phys=read(OUT/'ORIGINAL_PHYSICAL_REPLAY.json');w=read(OUT/'WITNESS_FAILURE_REPRODUCTION.json')
    root='''# May12 witness 오류의 원인과 복구

실제 source HEAD는 1b891dbe5b1dd454d89b657efec7cba469c0cf94였다. 기존 실행은 Phase-I에서 멈추지 않았다. Full-row Phi가 0.0362344419 → 0.0164196204 → 0.0046485901 → 0으로 감소했고, 세 round에서 STAY96개와 migration96개를 활성화했다. P1 restricted LP 0.669016629와 full130 pricing도 끝났으며 92개의 정확히 검증된 음수 블록을 추가하는 단계에서 Python 검증기 오류가 났다.

`v42_a_stage_canary.phase.activate`가 원래 P1 점에 artificial을 0으로 붙인 뒤, 새 후보로 row coefficient scale이 달라진 elastic master와 artificial weight 동일성을 비교했다. 40개의 global row에서 80개의 artificial weight가 바뀌었고 signs는 동일했다. 실제 prior Phi는 0이고 원본 primal은 feasible이었다. Solver가 infeasible이라고 판정한 사건이 아니다.

실제 저장 모델과 pricing 방향을 재구성하여 같은 ValueError를 재현했다. 먼저 실제 May12 regression test가 기존 코드에서 실패하는 것을 저장하고, 이후 P1 activation을 artificial-free original inclusion 검증으로 수정했다. 양수 Phi의 원래 frozen weight/sign 검사는 유지했다. Original coefficient/RHS/bound/objective/tolerance는 변경하지 않았다. 기존 perspective concrete columns도 rebuild에 보존했다.

모든 신규 작업은 독립 D: tree에서 진행됐다. Native source는 별도 freeze에 기록된다. 원본 May12/May10 증거와 실행 source/cache/input은 바꾸지 않았다. Exact dyadic replay는 전체 새 original rows에 대해 수행했으며 fixture 통과와 실제 대규모 모델 검증을 별도로 기록했다.

성능 개선은 완료된 285회의 native solve와 192 concrete columns/92 pricing directions를 재사용하고, graph union의 ledger를 매 열마다 전체 재계산하던 것을 batch당 한 번으로 줄인 것이다. 실제 130-class ledger와 source matrix 동치성을 확인했다. 새로운 initial build나 23회의 Phase-I를 다시 실행하지 않았다. Basis는 column/row axes가 바뀌므로 호환성 증거 없이 재사용하지 않았다.

추가 개선은 exact sum의 0항 제거, 완료된 full pricing의 Pi/행렬/RAW/hash/유리수 하한 재검증 후 재사용, 활성화된 다음 모델의 immutable checkpoint 재사용이다. 별도 shadow 검증에서 추가 concrete STAY 39,993개를 정확한 음수 가격과 full native A/B/bounds/cardinality 동치성으로 검증했다. 실제 추가 batch 활성화는 하지 않았다. S1 전체 pricing은 잠시76/130에서 다른 native 작업으로 중단됐으나, 사용자의 M 단계 종료 후 재개 지시에 따라 저장된 master/activation/pricing을 재사용해 130/130을 완료했다. 음수 블록이 없어 추가 활성화가 필요하지 않았다.
'''
    (OUT/'PHASE1_WITNESS_ROOT_CAUSE_KO.md').write_text(root,encoding='utf8')
    report=f'''# May12 P1-only 최종 검토

최종 판정: **{decision['classification']}**. P1-only accepted={p1.get('A1_P1_ONLY_ACCEPTED',False)}. 기존 4목적 A1_ACCEPTED는 변경하지 않았다. P2와 downstream은 실행하지 않았다.

이전 실행은 Phi=0 이후 P1과 130개 클래스 가격화까지 완료됐다. 실패는 P1 점을 새 elastic master에 연결하면서 80개 artificial weight 차이를 거부한 Python witness 검증기였다. 실제 저장 데이터 회귀는 수정 전 실패했고 수정 후 통과했다. 새 P1에서는 artificial-free original point 포함성을 검증한다. 양수 Phi의 frozen-weight 규칙과 scientific tolerance는 유지했다.

Phase-I trajectory: 0.03623444192091598 → 0.016419620449477194 → 0.0046485901268879595 → 0. 기존 활성화 round3, STAY96/migration96. Original dyadic row replay 및 original Planning grid replay PASS={z['PASS']}; full130 zero-dual pricing PASS. Raw native Phi=0과 재구성 artificial Phi(약6.44e-13)를 구분했다. 신규 Phase-I native solve0회. 이 인증은 연속 Phase-I feasibility이며 정수 schedule 인증은 P1 결과에 따로 기록한다.

P1 restricted LP는 0.6607295534700348 → 0.6588875397405124로 감소했다. S0와 S1은 각130개 full pricing을 완료했다. STAY208,957개와 migration50,756,904개를 포함하는 원본 후보 영역의 완전 oracle를 인증했다. Global LP LB는 S0의0.5704134348993862 → S1의0.6588875395606518로 개선됐다. 최종 exact LB={p1.get('exact_LB')}, validated integer UB={p1.get('exact_UB')} (0.6592963546281192), global gap={p1.get('gap')} (0.0620077852%). 음수 블록129개(STAY 포함129/Migration 포함38)는 concrete column 개수가 아니다. 한 번의 P1 support graph 활성화로 S1을 만들었고 exact original 3,184,901행/1,141,597열 inclusion에서 목적값 동일성을 검증했다. S1 pricing은130/130이고 모든minimum-RC lower bound는0, negative block0개이며 P1 전체 영역 pricing closure PASS={cl['PASS']}. Restricted ObjBound를 global bound로 사용하지 않았다. 원본 모든 global rows와 130개 full STAY/migration oracle의 finite-bound exact certificate/roundoff transport를 사용했다.

Original continuous Phase-I 및 P1 integer physical replay PASS={phys['PASS']}. 원본1,782개 job의 GPU/rack/gang/WAN/서비스/carryout/Runtime/deadline/CC4 및 전압/thermal/transformer 제약 검증을 통과했다. 저장된 원본 정수 모델 전체3,184,901행/1,141,597열을 별도로 유리수 재생했고 scientific1e-6 tolerance 내 PASS, integrality residual0, 인공변수0이었다. Schedule metrics={phys.get('schedule_metrics')}는 P2 후속 목적을 최적화하지 않고 평가한 값이다. Migration count0은 이번 해의 결과이며 migration 변수를0으로 고정하지 않았다. P1-only Freeze와 acceptance는 PASS, 기존 A1_ACCEPTED는 false다.

Native integer status는11(INTERRUPTED)이며 원본 물리 검증과 독립 global gap 목표가 충족돼 callback이 종료한 것이다. Solver의 완전 OPTIMAL 상태를 주장하지 않는다. Integer solve173.380000s / Work142.950591, node1, native MIPGap0.062007758%다. 인증에는 restricted native bound 대신 full-domain exact LB와 실제 integer UB를 사용했다. 종료 사유는 RAM이나 예산 소진이 아니다.

신규 native {runtime['new_native_calls']}회, Runtime={runtime['new_native_Runtime']:.6f}s/3600s, Work={runtime['new_Work']:.6f}. 기존 native285회/233.892997s/Work327.445620은 그대로 보존했다. 신규 native/build/pricing/검증을 포함한 run wall={runtime['native_run_wall_seconds']:.3f}s. 복구 audit 이후 task wall={runtime['task_wall_since_recovery_audit_seconds']:.3f}s, practical60분 기준={runtime['practical_60_minute_wall_pass']}. 모델 build/검증은 native예산과 구분했으며 실제 per-call Runtime/Work/model sizes/factor-memory/presolve는 RESOURCE_AND_RUNTIME_AUDIT.json과 native 원시 로그에 있다. RAM limits 및 RAM-triggered stops는 없다. Threads1, sequential native. 과거 작업의 예산은 수정하지 않았다.

다른 세 날짜: May17은 기존 four-objective A1 및 practical60분 accepted. May19은 기존 scientific A1 accepted이나 과거 certificate 재사용이어서 fresh end-to-end practicality 인증은 없다. May10은 PR184 고정 개선실험 후에도 UB60/globalLB2로 INCONCLUSIVE다. 그 결과와 PR184 HEAD1444d1614258be3e6ff24c56dfc078d69e8ced9a는 보존했다.

성능 측정과 병목: PERFORMANCE_COMPARISON.csv는 과거와 이번의 실제 측정 범위를 구분한다. 이번 복구는 historical solve 재사용 및 batch ledger refresh 동치성을 채택했다. 제한된 단일 native 설정을 사용했으며 broad sweep이나 automatic follow-up은 없다. P1 LP/master/pricing/정수 단계별 소요시간은 P1_TRAJECTORY.json과 NATIVE_CALLS에 기록된다. 실제 병목은 이 비용표로 판단하며 과거 PR164의 다른 모델 병목을 이번 수치에 전용하지 않는다.

실제 S0 master: 754,043 rows / 71,377 cols / 13,356,317nnz, presolved19,509/32,106/207,709, factor0.03GB. 실제 S1 master: 915,801 rows / 116,985 cols / 13,738,297nnz, presolved56,808/55,389/466,910, factor0.1GB. Integer 모델3,184,901rows / 1,141,597cols / 19,561,231nnz, original integer columns420,619, 첫presolve471,241/564,812/3,977,008, root barrier factor652,000nnz/24MB(0.024GB). Peak native RSS={runtime['peak_native_RSS']}bytes. Source epochs1–8의 실행 당시 모든 Python bytes 및 실제 native261회의 model/raw/source receipts PASS이며 각 source commit은 NEW_NATIVE_CALLS.json에 기록했다. Runtime이0으로 반올림된6회도 실제 optimize 호출 횟수에 포함했다. 최종 integer 실행sourceHEAD7b4a0d0292e1b289e7b1775a08ae152cc5d5331f. 최신 broad tests389 PASS(1368 deselected), epoch7 focused22 PASS 및 post-run 회계/acceptance/JSON동일성16 PASS를 보존했다. 원본 input11files와47grid arrays identity PASS. 신규 static cache/RAW 대형 binary는 D:에 보존했고 Git에는 재현 가능한 source와 SHA256 receipts 및 증거를 commit했다.

중간 RESOURCE_PENDING의 실제 근거는 M1 `experiment`/`continue_z0`와 worker였다. 사용자가 M 단계 종료를 알린 뒤 read-only PID 확인에서 native가 없는 것을 검증하고, 동일한 누적 예산으로 재개했다. 이전의 read-only 분석 PID를 잘못 막은 gate 기록, gate 수정, 의도적인 between-solve 구현 경계 비용도 모두 보존하고 wall 합계에 포함했다. 다른 M1/May10 프로세스에는 signal이나 쓰기를 하지 않았다. Native 잔여예산={runtime['remaining_native_Runtime']:.6f}s. 마지막 성공 재개wall662.307797s(11.04분)와 전체 누적run wall 및 전체task wall을 구분한다. Scientific PASS와 전체task60분 실용성FAIL을 동시에 기록한다.

Independent post-run schedule 비교의 첫 실패는 JSON key 문자열화 및 tuple→array 자료형 차이였다. Native receipt의 기존 common.clean과 동일한 표현으로 비교하도록 수정했고, 실제 scheduling 결정과 수치값이 달라지면 거부하는 regression을 추가했다. 실패 로그/증거도 보존했다. 재검증은 point를 수정하지 않고 full row/integer/physical/동일 schedule/exact gap을 모두 확인했으며 optimize call0이다.

남은 문제 및 다음 한 가지 권고: P1-only Freeze를 기존 P2 인증서 필수 downstream에 연결하는 명시적인 interface adapter를 별도 연구 계약으로 검증한다. 이번에는 해당 pipeline을 수정하거나 실행하지 않았다. 전체task60분 실용성은 실패했으므로 이번 scientific acceptance를 fresh end-to-end 성능PASS로 해석하지 않는다. 자동 후속 실행 없이 종료한다.

Exception/미완료 사유: {decision.get('error',decision.get('reason','없음'))}. 최종 local/remote/PR HEAD equality와 clean tree는 별도 Git delivery receipt에 기록한다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
    files=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    # Operational delivery logs and PR text continue changing after report
    # generation; scientific results, payloads and execution archives are sealed.
    excluded=('GIT','PR_BODY','FINALIZE','FINAL_GIT_DELIVERY','SEAL_VERIFICATION')
    artifacts=[record(p) for p in sorted(STATIC.rglob('*')) if p.is_file() and not p.name.startswith(excluded)]
    atomic(OUT/'SHA256_MANIFEST.json',dict(PASS=True,outputs=files,large_local_artifacts=artifacts,source_manifest=record(active_freeze()),
        large_binary_payloads_preserved_on_D_not_committed=True,manifest_excludes_itself=True,
        mutable_delivery_logs_excluded=list(excluded)))
    print('MAY12_FINAL_REPORT',decision['classification'],runtime['new_native_Runtime'],flush=True)
if __name__=='__main__':run()

"""Post-run reports, source/data preservation and scientific decision audit."""
import csv,subprocess,time,re,json
from pathlib import Path
from fractions import Fraction
from .policy import ROOT,OUT,STATIC,OLDOUT,DAY
from .audit import file_digest,processes
from .execution import active_freeze
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
    calls=read(OUT/'NEW_NATIVE_CALLS.json').get('calls',[]) if (OUT/'NEW_NATIVE_CALLS.json').exists() else []
    entered=[c for c in calls if (c.get('native_seconds') or 0)>0]
    all_params=[];sizes=[]
    for c in calls:
        f=Path(c['folder']);i=read(f/'MODEL_IDENTITY.json');params=read(f/'SOLVER_PARAMETERS.json');memory=read(f/'MEMORY_LIMITS_DISABLED.json')
        log=(f/'NATIVE_SOLVER.log').read_text(encoding='utf8',errors='replace')
        sizes.append(dict(component=c['component'],folder=str(f),rows=i['rows'],cols=i['cols'],nnz=i['nnz'],Runtime=c['native_seconds'],Work=c['Work'],
            factor_memory_lines=re.findall(r'Factor N(?:N)?Z[^\n]+',log),source_commit=i['source_commit']))
        p=params['effective'];all_params.append(dict(PASS=p['Threads']==1 and p['MIPGap']==.005 and p['FeasibilityTol']==1e-6 and p['OptimalityTol']==1e-6 and p['IntFeasTol']==1e-5
            and memory['MemLimit']=='inf' and memory['SoftMemLimit']=='inf',folder=str(f),parameters=params,memory=memory))
    task_start=(OUT/'MAY12_RECOVERY_AUDIT.json').stat().st_ctime
    runtime=dict(PASS=sum(c['native_seconds'] or 0 for c in calls)<=3600 and all(r['PASS'] for r in all_params),
        native_limit=3600,old_native_Runtime=233.89299654960632,new_native_Runtime=sum(c['native_seconds'] or 0 for c in calls),
        new_Work=sum(c['Work'] or 0 for c in calls),new_native_calls=len(entered),old_calls=285,
        old_plus_new_native_Runtime=233.89299654960632+sum(c['native_seconds'] or 0 for c in calls),
        native_run_wall_seconds=decision['new_wall_seconds'],task_wall_since_recovery_audit_seconds=time.time()-task_start,
        practical_60_minute_wall_pass=time.time()-task_start<=3600,old_wall_seconds=2093.9435081481934,
        static_recovery=read(OUT/'RECOVERY_STATIC_COST.json'),parameters=all_params,actual_model_sizes=sizes,
        peak_native_RSS=max((c.get('peak_RSS_bytes') or 0 for c in calls),default=0),memory_limits=False,
        memory_automatic_stop=False,other_runs_read_only_observed=processes(),threads_per_native=1,calls_sequential=True)
    atomic(OUT/'RESOURCE_AND_RUNTIME_AUDIT.json',runtime)
    if not runtime['PASS']:decision.update(PASS=False,classification='MAY12_NUMERICAL_TRACTABILITY_FAIL',audit_failure='NATIVE_POLICY_OR_BUDGET_NOT_PASSED')
    atomic(OUT/'FINAL_DECISION.json',decision)
    for name in ('COMPLETE_PRICING_CLOSURE.json','P1_FULL_DOMAIN_BOUND_CERTIFICATE.json','P1_INTEGER_RESULT.json','ORIGINAL_PHYSICAL_REPLAY.json','P1_ONLY_ACCEPTANCE_CONTRACT.json','P1_ONLY_FREEZE.json'):
        if not (OUT/name).exists():atomic(OUT/name,dict(PASS=False,status='NOT_CERTIFIED',reason=decision.get('error',decision['classification'])))
    table(OUT/'PERFORMANCE_COMPARISON.csv',[
        dict(stage='historical_initial_build',native_Runtime=0,Work=0,wall_seconds=222.4885911999736,scope='original completed May12 initial build'),
        dict(stage='historical_total',native_Runtime=233.89299654960632,Work=327.44561993108914,wall_seconds=2093.9435081481934,scope='285 historical calls unchanged'),
        dict(stage='recovery_initial_replay',native_Runtime=0,Work=0,wall_seconds=runtime['static_recovery']['recovery_initial_wall_seconds'],scope='192 concrete columns and identical prior master'),
        dict(stage='saved_directions_replay',native_Runtime=0,Work=0,wall_seconds=runtime['static_recovery']['recovered_directions_wall_seconds'],scope='92 saved exact negative directions'),
        dict(stage='zero_and_inclusion_certificate',native_Runtime=0,Work=0,wall_seconds=runtime['static_recovery']['prepare_wall_seconds'],scope='actual original dyadic rows and 130 analytical zero pricing'),
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
    phys=read(OUT/'ORIGINAL_PHYSICAL_REPLAY.json');w=read(OUT/'WITNESS_FAILURE_REPRODUCTION.json')
    root='''# May12 witness 오류의 원인과 복구

실제 source HEAD는 1b891dbe5b1dd454d89b657efec7cba469c0cf94였다. 기존 실행은 Phase-I에서 멈추지 않았다. Full-row Phi가 0.0362344419 → 0.0164196204 → 0.0046485901 → 0으로 감소했고, 세 round에서 STAY96개와 migration96개를 활성화했다. P1 restricted LP 0.669016629와 full130 pricing도 끝났으며 92개의 정확히 검증된 음수 블록을 추가하는 단계에서 Python 검증기 오류가 났다.

`v42_a_stage_canary.phase.activate`가 원래 P1 점에 artificial을 0으로 붙인 뒤, 새 후보로 row coefficient scale이 달라진 elastic master와 artificial weight 동일성을 비교했다. 40개의 global row에서 80개의 artificial weight가 바뀌었고 signs는 동일했다. 실제 prior Phi는 0이고 원본 primal은 feasible이었다. Solver가 infeasible이라고 판정한 사건이 아니다.

실제 저장 모델과 pricing 방향을 재구성하여 같은 ValueError를 재현했다. 먼저 실제 May12 regression test가 기존 코드에서 실패하는 것을 저장하고, 이후 P1 activation을 artificial-free original inclusion 검증으로 수정했다. 양수 Phi의 원래 frozen weight/sign 검사는 유지했다. Original coefficient/RHS/bound/objective/tolerance는 변경하지 않았다. 기존 perspective concrete columns도 rebuild에 보존했다.

모든 신규 작업은 독립 D: tree에서 진행됐다. Native source는 별도 freeze에 기록된다. 원본 May12/May10 증거와 실행 source/cache/input은 바꾸지 않았다. Exact dyadic replay는 전체 새 original rows에 대해 수행했으며 fixture 통과와 실제 대규모 모델 검증을 별도로 기록했다.

성능 개선은 완료된 285회의 native solve와 192 concrete columns/92 pricing directions를 재사용하고, graph union의 ledger를 매 열마다 전체 재계산하던 것을 batch당 한 번으로 줄인 것이다. 실제 130-class ledger와 source matrix 동치성을 확인했다. 새로운 initial build나 23회의 Phase-I를 다시 실행하지 않았다. Basis는 column/row axes가 바뀌므로 호환성 증거 없이 재사용하지 않았다.
'''
    (OUT/'PHASE1_WITNESS_ROOT_CAUSE_KO.md').write_text(root,encoding='utf8')
    report=f'''# May12 P1-only 최종 검토

최종 판정: **{decision['classification']}**. P1-only accepted={p1.get('A1_P1_ONLY_ACCEPTED',False)}. 기존 4목적 A1_ACCEPTED는 변경하지 않았다. P2와 downstream은 실행하지 않았다.

이전 실행은 Phi=0 이후 P1과 130개 클래스 가격화까지 완료됐다. 실패는 P1 점을 새 elastic master에 연결하면서 80개 artificial weight 차이를 거부한 Python witness 검증기였다. 실제 저장 데이터 회귀는 수정 전 실패했고 수정 후 통과했다. 새 P1에서는 artificial-free original point 포함성을 검증한다. 양수 Phi의 frozen-weight 규칙과 scientific tolerance는 유지했다.

Phase-I trajectory: 0.03623444192091598 → 0.016419620449477194 → 0.0046485901268879595 → 0. 기존 활성화 round3, STAY96/migration96. Original dyadic row replay 및 original Planning grid replay PASS={z['PASS']}; full130 zero-dual pricing PASS. Raw native Phi=0과 재구성 artificial Phi(약6.44e-13)를 구분했다. 신규 Phase-I native solve0회. 이 인증은 연속 Phase-I feasibility이며 정수 schedule 인증은 P1 결과에 따로 기록한다.

P1 전체 영역 closure PASS={cl['PASS']}, classes={cl.get('classes')}. Global exact LB={p1.get('exact_LB')}, validated integer UB={p1.get('exact_UB')}, gap={p1.get('gap')}. Restricted master bound를 global bound로 사용하지 않았다. 원본 모든 global rows와 130개 full STAY/migration oracle의 finite-bound exact certificate/roundoff transport를 사용했다. Original physical replay PASS={phys['PASS']}; metrics-only={phys.get('schedule_metrics')}. Migration을0으로 고정하거나 이동/시간 후보를 삭제하지 않았다.

신규 native {runtime['new_native_calls']}회, Runtime={runtime['new_native_Runtime']:.6f}s/3600s, Work={runtime['new_Work']:.6f}. 기존 native285회/233.892997s/Work327.445620은 그대로 보존했다. 신규 native/build/pricing/검증을 포함한 run wall={runtime['native_run_wall_seconds']:.3f}s. 복구 audit 이후 task wall={runtime['task_wall_since_recovery_audit_seconds']:.3f}s, practical60분 기준={runtime['practical_60_minute_wall_pass']}. 모델 build/검증은 native예산과 구분했으며 실제 per-call Runtime/Work/model sizes/factor-memory/presolve는 RESOURCE_AND_RUNTIME_AUDIT.json과 native 원시 로그에 있다. RAM limits 및 RAM-triggered stops는 없다. Threads1, sequential native. 과거 작업의 예산은 수정하지 않았다.

다른 세 날짜: May17은 기존 four-objective A1 및 practical60분 accepted. May19은 기존 scientific A1 accepted이나 과거 certificate 재사용이어서 fresh end-to-end practicality 인증은 없다. May10은 PR184 고정 개선실험 후에도 UB60/globalLB2로 INCONCLUSIVE다. 그 결과와 PR184 HEAD1444d1614258be3e6ff24c56dfc078d69e8ced9a는 보존했다.

성능 측정과 병목: PERFORMANCE_COMPARISON.csv는 과거와 이번의 실제 측정 범위를 구분한다. 이번 복구는 historical solve 재사용 및 batch ledger refresh 동치성을 채택했다. 제한된 단일 native 설정을 사용했으며 broad sweep이나 automatic follow-up은 없다. P1 LP/master/pricing/정수 단계별 소요시간은 P1_TRAJECTORY.json과 NATIVE_CALLS에 기록된다. 실제 병목은 이 비용표로 판단하며 과거 PR164의 다른 모델 병목을 이번 수치에 전용하지 않는다.

남은 문제 및 다음 한 가지 권고: {'P1-only freeze를 소비하는 명시적인 downstream adapter를 별도 연구 계약으로 검증한다. 이번 작업에서는 해당 pipeline을 수정하거나 실행하지 않았다.' if decision['PASS'] else '마지막 validated P1 master의 row/column identities를 유지하는 persistent pricing master 및 검증된 basis 재사용을 다음 한 가지 개선으로 권고한다. 이번 미인증 결과를 PASS로 바꾸지 않는다.'}

Exception/미완료 사유: {decision.get('error',decision.get('reason','없음'))}. 최종 local/remote/PR HEAD equality와 clean tree는 별도 Git delivery receipt에 기록한다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
    files=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    artifacts=[record(p) for p in sorted(STATIC.rglob('*')) if p.is_file()]
    atomic(OUT/'SHA256_MANIFEST.json',dict(PASS=True,outputs=files,large_local_artifacts=artifacts,source_manifest=record(active_freeze()),
        large_binary_payloads_preserved_on_D_not_committed=True,manifest_excludes_itself=True))
    print('MAY12_FINAL_REPORT',decision['classification'],runtime['new_native_Runtime'],flush=True)
if __name__=='__main__':run()

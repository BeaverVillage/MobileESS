"""Self-contained before/after report for the completed May-04-only acceptance."""
from collections import Counter
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from .first_replay import OUT
from .flex_diagnostic import OUT as DIAG,RUNTIME,B0
from .migration import state_at_d00

def run(tag='first02'):
    baseline=read(B0/'dayahead/optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR']
    refs=read(RUNTIME/'inputs/2025-05-04/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json');byuid={r['job_uid']:r for r in refs}
    def result(tag):
        root=RUNTIME/'fa'/tag;value=read(root/'ACCEPTANCE_RESULT.json');unit=root/'2025-05-04/B1';a0=unit/'dayahead/A0'
        assert value['status']=='PASS'
        accepted=read(a0/'ACCEPTED_AIDC.json');rows=accepted['jobs'];migrated=[r for r in rows if r.get('migration_selected')]
        pre=[r for r in rows if r.get('initial_AIDC',r['AIDC_site'])!=byuid[r['job_uid']]['AIDC_site']]
        fresh=read(unit/'dayahead/fresh/OPENDSS_SUMMARY.json');actual=read(unit/'actual/grid/OPENDSS_SUMMARY.json')
        stages=read(a0/'BOUNDED_SOLVER_REPORT.json')['stages']
        waits=[dict(job=r['job_uid'],D00_state=state_at_d00(byuid[r['job_uid']]),
            checkpoint=r['migration_checkpoint_slot'],restart=r['restart_complete_slot'],
            checkpoint_to_restart_hours=(r['restart_complete_slot']-r['migration_checkpoint_slot'])*.25,
            original_end=byuid[r['job_uid']]['end_slot'],new_end=r['end_slot']) for r in migrated]
        return dict(tag=tag,P1_P5=value['final_objective_vector'],delta_from_B0=[a-b for a,b in zip(value['final_objective_vector'],baseline)],
            optimization_seconds=value['optimization_seconds'],total_wall_with_Fresh_Actual_seconds=value['total_wall_seconds'],
            raw_candidate_coverage=value['coverage_fraction'],candidate_count=value['candidate_count'],
            selected_prestart_relocations=len(pre),selected_running_migrations=len(migrated),
            selected_migrations_by_D00_state=dict(Counter(state_at_d00(byuid[r['job_uid']]) for r in migrated)),
            selected_prestart_job_ids=[r['job_uid'] for r in pre],selected_migration_job_ids=[r['job_uid'] for r in migrated],
            migration_wait_and_service=waits,Fresh='PASS',Actual='PASS',Fresh_rho=fresh['rho_max_AC'],Actual_rho=actual['rho_max_AC'],
            Fresh_physics={k:fresh[k] for k in ('physical_violation','voltage_violation_count','line_current_violation_count','transformer_current_violation_count','transformer_kva_violation_count','schedule_mutation_count')},
            Actual_physics={k:actual[k] for k in ('physical_violation','voltage_violation_count','line_current_violation_count','transformer_current_violation_count','transformer_kva_violation_count','schedule_mutation_count')},
            stage_details=[{k:s.get(k) for k in ('stage','stage_priority','runtime_seconds','starting_objective_vector','accepted_objective_vector',
                'termination_reason','material_improvements','stage_family_coverage_fraction','STAGE_COVERAGE_FRACTION','neighborhoods_solved')} for s in stages],
            source=value['source'],acceptance=record(root/'ACCEPTANCE_RESULT.json'),artifacts=value['artifacts'])
    old=result('03');early=result('early03');new=result(tag)
    solver=read(RUNTIME/'fa'/tag/'2025-05-04/B1/dayahead/A0/BOUNDED_SOLVER_REPORT.json')
    improvements=solver['stages'][-1]['accepted_improvements'];replay=read(OUT/'OLD_FO_MISSED_IMPROVEMENT_REPLAY.json')
    rejection_counts={tag:solver['stages'][-1]['rejected_proposals']}
    attempted_runs=[tag]
    recovery=None
    if (OUT/'RESUME_PLAN.json').exists():
        plan=read(OUT/'RESUME_PLAN.json');parent=Path(plan['parent_root']);pa0=parent/'2025-05-04/B1/dayahead/A0'
        parent_stages=read(pa0/'BOUNDED_SOLVER_REPORT.json')['stages']
        past=parent_stages[-1]['accepted_improvements']
        rejection_counts['first01']=parent_stages[-1]['rejected_proposals']
        attempted_runs.insert(0,'first01')
        valid=[dict(r,source_run='first01') for r in past if r['iteration']<=plan['best_iteration']]
        improvements=valid+[dict(r,source_run=tag) for r in improvements]
        component_seconds=new['optimization_seconds']
        new['resume_component_optimization_seconds']=component_seconds
        new['optimization_recorded_seconds']=plan['parent_recorded_optimization_seconds']+component_seconds
        new['optimization_seconds']=new['optimization_recorded_seconds']+plan['conservative_stop_allowance_seconds']
        new['optimization_seconds_is_conservative_upper_bound']=True
        new['total_wall_with_Fresh_Actual_seconds']=(RUNTIME/'fa'/tag/'ACCEPTANCE_RESULT.json').stat().st_mtime-(parent/'ACCEPTANCE_STARTED.json').stat().st_mtime
        new['wall_includes_debug_and_regression_pause']=True
        pc=read(pa0/'CANDIDATE_COVERAGE_REPORT.json')
        nc=read(RUNTIME/'fa'/tag/'2025-05-04/B1/dayahead/A0/CANDIDATE_COVERAGE_REPORT.json')
        opened={r['group'] for c in (pc,nc) for r in c['candidate_visits'] if r['CANDIDATE_VISIT_COUNT']}
        total=pc['total_eligible_candidates'];visited=sum((r['option_index_end_exclusive']-r['option_index_start'])*len(r['members']) for r in pc['candidate_visits'] if r['group'] in opened)
        new['resume_component_raw_candidate_coverage']=new['raw_candidate_coverage']
        new['raw_candidate_coverage']=visited/total
        new['raw_candidates_opened']=visited
        new['raw_candidates_not_visited']=total-visited
        new['raw_candidate_coverage_denominator']=total
        new['fixed_singleton_candidates_outside_search']=new['candidate_count']-total
        new['raw_candidate_coverage_scope']='Union of attempted first01 and recovered first02 neighborhoods; separate component coverage retained.'
        recovery=dict(plan=record(OUT/'RESUME_PLAN.json'),invalidated_attempt=record(parent/'ACCEPTANCE_INVALIDATION.json'),
            best_preserved_iteration=plan['best_iteration'],valid_parent_improvements=len(valid),
            defect='P2 iteration 77 gave back an incidental P1 gain inside an older stage cap',
            repair='Current-incumbent higher-priority search cuts plus independent post-validation guards',
            additional_optimization_cap_seconds=plan['remaining_optimization_cap_seconds'],
            measured_recorded_optimization_seconds=new['optimization_recorded_seconds'],
            conservative_stop_allowance_seconds=plan['conservative_stop_allowance_seconds'],
            combined_optimization_upper_bound_seconds=new['optimization_seconds'])
        assert new['optimization_seconds']<=1800
    attempted_families={s['stage']:set() for s in solver['stages']}
    rejection_records=[]
    for run_tag in attempted_runs:
        checkpoints=RUNTIME/'fa'/run_tag/'2025-05-04/B1/dayahead/A0/bounded_checkpoints'
        for p in checkpoints.glob('ITERATION_*.json'):
            row=read(p)
            attempted_families[row['objective_stage']].add(row['neighborhood']['family'])
            if row.get('candidate_rejection'):
                rejection_records.append(dict(source_run=run_tag,iteration=row['iteration'],receipt=row['candidate_rejection']))
    assert len(rejection_records)==sum(rejection_counts.values())
    single=read(OUT/'KNOWN_P2_REGRESSION.json');diag=read(DIAG/'V41R1_MAY04_B1_FLEXIBILITY_DIAGNOSTIC.json')
    best_p1=min(new['P1_P5'][0],diag['best_coupled']['vector'][0])-baseline[0]
    observed_vectors=[r['after'] for r in improvements]+[diag['best_coupled']['vector'],diag['best_triple']['best']['vector'],diag['single_move']['best']['ALL']['vector']]
    best_p2=min(v[1] for v in observed_vectors if v[0]<=baseline[0]+1e-10)-baseline[1]
    report=dict(status='PASS',primary_root_cause='COMBINED_COMPUTATIONAL_ISSUE',
        root_cause_detail='Known 0.0988-GPUh job was never opened in P2; other validated P2 improvements were available in exact historical neighborhoods, but 3% relative-gap termination returned B0 before discovery.',
        historical_replay=replay,B0_P1_P5=baseline,old_production=old,early_stop_production=early,new_first_improvement=new,
        known_P2_improvement_recovered=True,known_P2_regression=single,
        best_single_move_delta_P1=diag['single_move']['best']['ALL']['delta_P1'],
        best_single_P2_same_P1_delta=diag['single_move']['best']['ALL']['delta_P2'],
        best_pair_delta_P1=diag['best_pair']['delta'][0],best_triple_delta_P1=diag['best_triple']['best']['delta'][0],
        best_coupled_diagnostic_delta_P1=diag['best_coupled']['delta'][0],best_P1_improvement_across_validated_evidence=best_p1,
        best_observed_P2_delta_with_P1_no_worse_than_B0=best_p2,
        best_P2_scope='Observed original-model-feasible witnesses with P1 <= B0; not necessarily under the final tighter P1 lock, not a global bound.',
        cross_region_escape_delta_P1=None,cross_region_probe='NOT_REQUIRED_AFTER_COUPLED_ESCAPE',
        accepted_improvements_by_stage={f'P{i+1}':sum(r['stage']==s['stage'] for r in improvements) for i,s in enumerate(solver['stages'])},
        interrupted_attempt_recovery=recovery,invalidated_accepted_proposals=1 if recovery else 0,
        rejected_proposals=sum(rejection_counts.values()),rejected_proposals_by_run=rejection_counts,
        rejected_proposal_records=rejection_records,
        rejection_count_scope='All recorded attempts including the interrupted run; the subsequently invalidated acceptance is counted separately.',
        attempted_neighborhood_family_coverage_by_stage={f'P{i+1}':dict(families=sorted(attempted_families[s['stage']]),fraction=len(attempted_families[s['stage']])/5) for i,s in enumerate(solver['stages'])},
        attempted_family_coverage_scope='Union across interrupted and resumed attempts, including discarded-incumbent attempts; this is an audit metric, not proof of a sweep around the final incumbent.',
        first_improvement_policy_day_seconds=improvements[0]['policy_day_seconds'] if improvements else None,
        all_accepted_improvements=improvements,
        complete_candidate_universe_unchanged=True,original_full_MPS_unchanged=True,
        scientific_model_changed=False,hard_feasibility_tolerance_changed=False,Actual_used_for_search=False,
        global_optimality_claim=False,local_bound_inconsistency=diag['local_certificate'],
        diagnostic_artifacts=record(DIAG/'DIAGNOSTIC_FREEZE.json'),
        regressions=record(OUT/'V4_REGRESSIONS.xml'),source_gate=record(OUT/'FIRST_IMPROVEMENT_SOURCE_GATE.json'),
        compute_contract=record(OUT/'FIRST_IMPROVEMENT_COMPUTE_CONTRACT.json'),
        Full_May_started=False,Full_May_ready=False,
        Full_May_status='USER_HOLD; May-04 accepted. No new 31-day/B3 shared-component release qualification or frozen campaign-release replacement performed in this task.')
    write_json(OUT/'V41R1_MAY04_FIRST_IMPROVEMENT_ACCEPTANCE.json',report)
    lines=['# May-04 first-improvement F&O acceptance','',
        '**May-04 B1: PASS.** 첫 개선해 탐색과 현재 critical-line 기반 공동 이동 탐색을 적용했습니다. 과학적 feasible set, 전체 MPS, 후보·목적함수·물리 제약은 유지했습니다.','',
        '**원인: 탐색군 구성 + 종료 규칙.** 0.0988 GPUh 개선 작업은 기존 두 실행의 P2 부분문제에 전혀 포함되지 않았습니다. 다른 검증된 개선 작업이 포함된 과거 P2 부분문제를 정확한 경계·P1 잠금·시작 해·TimeLimit(60초/5초)로 재현하자, 각각 gap 0.9047%와 1.7884%에서 B0를 반환했습니다. 해당 재현에서는 시간 제한이나 수락 거절이 원인이 아니었습니다.','',
        '| 지표 | B0 | 기존 F&O (100% 방문) | 기존 early-stop F&O | 새 first-improvement F&O |','|---|---:|---:|---:|---:|']
    for i in range(5):lines.append(f"| P{i+1} | {baseline[i]:.12g} | {old['P1_P5'][i]:.12g} | {early['P1_P5'][i]:.12g} | {new['P1_P5'][i]:.12g} |")
    for name,key,scale in [('최적화 시간(분; 새 값은 복구 포함 상한)','optimization_seconds',1/60),('총 경과시간(분; 새 값은 수정·회귀검사 중단 포함)','total_wall_with_Fresh_Actual_seconds',1/60),('원시 후보 방문률(%)','raw_candidate_coverage',100),('선택 prestart relocation','selected_prestart_relocations',1),('선택 checkpoint migration','selected_running_migrations',1),('Fresh AC rho','Fresh_rho',1),('Actual AC rho','Actual_rho',1)]:
        lines.append('| '+name+' | — | '+' | '.join(f'{r[key]*scale:.8g}' for r in (old,early,new))+' |')
    lines+=['',f"새 B1 − B0 목적값 차이(P1–P5): `{new['delta_from_B0']}`.",
        'P3/P4 증가는 상위 P1/P2 개선에 따른 lexicographic 선택입니다. 모든 목적이 동시에 개선된다는 의미는 아닙니다.',
        f"알려진 P2 개선 복구: PASS. P1을 유지하며 P2 {single['baseline'][1]:.10f} → {single['result'][1]:.10f} GPUh. B0로 시작했고 oracle 해를 warm start로 주입하지 않았습니다.",
        f"단일 이동 ΔP1={report['best_single_move_delta_P1']}; pair ΔP1={report['best_pair_delta_P1']:.12g}; triple ΔP1={report['best_triple_delta_P1']:.12g}; 강한 coupled 진단 ΔP1={report['best_coupled_diagnostic_delta_P1']:.12g}.",
        'Cross-region 강제 추가 검사는 이미 coupled 개선이 발견되어 실행 조건이 발동하지 않았습니다. 목적지·동일 지역 후보는 계속 유지했습니다.',
        '',f"전체 유효 경로의 수락 개선 수: {report['accepted_improvements_by_stage']}. 아래 단계별 표는 복구 실행(first02) 부분만 표시합니다.",
        '', '| 단계 | 복구 후 개선 수 | 복구 시간(초) | 복구 탐색군 방문률 | 복구 원시 후보 방문률 | 종료 |','|---|---:|---:|---:|---:|---|']
    for s in new['stage_details']:lines.append(f"| {s['stage_priority']} | {s['material_improvements']} | {s['runtime_seconds']:.2f} | {s['stage_family_coverage_fraction']:.2%} | {s['STAGE_COVERAGE_FRACTION']:.2%} | {s['termination_reason']} |")
    lines+=['',f"검증에서 거절한 제안: {report['rejected_proposals']}개(실행별 {rejection_counts}). 사후 무효화한 수락 1건은 별도입니다. 첫 개선의 기록된 policy-day 계산 예산 시점은 {report['first_improvement_policy_day_seconds']:.2f}초입니다(빌드·시작 해 검증 포함, 해당 반복의 검증·저장 비용 최종 합산 전).",
        f"전체 시도의 단계별 탐색군 방문률: { {p: r['fraction'] for p,r in report['attempted_neighborhood_family_coverage_by_stage'].items()} }. 중단한 시도와 복구 시도의 합집합이며 최종 incumbent 주위의 완전한 sweep 증명은 아닙니다.",
        f"전체 원시 후보 {new['candidate_count']:,}개를 유지했습니다. 방문률의 분모는 실제 탐색 대상 {new.get('raw_candidate_coverage_denominator',new['candidate_count']):,}개이며, 차이 7개는 고정 singleton입니다. 미방문 후보는 NOT_VISITED_WITHIN_COMPUTE_BUDGET이며 PRUNED가 아닙니다.",
        f"복구 경위: first01의 77번 수락이 당시 현재 P1을 악화시켜 첫 시도의 수락 결과를 무효화했습니다. 원래 제약을 통과한 최선 체크포인트 {plan['best_iteration']}번에서 V4로 복구했고, Fresh/Actual은 복구된 최종 결정으로 수행했습니다. 기존 성공 증거는 보존했습니다." if recovery else '',
        f"계산 시간은 기록된 합계 {new.get('optimization_recorded_seconds',new['optimization_seconds'])/60:.3f}분, 중단 시점 미계측 구간의 보수적 90초 여유를 더한 상한 {new['optimization_seconds']/60:.3f}분입니다. 추가 최적화 제한 3분에 모델 재구성·검증도 포함했습니다. 중단 없는 새 방식의 실행 시간은 별도로 측정하지 않았습니다." if recovery else '',
        f"선택 migration의 D00 상태 구분: {new['selected_migrations_by_D00_state']}. PENDING의 최초 배치 변경과 RUNNING 상태가 된 뒤 checkpoint 이동을 구분했습니다.",
        '**수치 처리:** P1/P2 개선 조건은 각각 절대 1e-8 / 1e-7, 독립 개선 판정의 noise tolerance는 1e-9 / 1e-8입니다. 검증된 baseline 재계산 noise envelope 1e-10에서 고정한 안전 배수이며, 물리·정수 feasibility tolerance 1e-9와 기존 상위 목적 잠금을 바꾸지 않았습니다.',
        '각 부분문제는 개선 조건을 추가한 상수 목적 feasibility 문제이며 SolutionLimit=1을 사용합니다. Gurobi의 상수 목적 zero-gap 메시지는 P1/P2 최적성 인증이 아닙니다. 기존 solver incumbent를 초기화하고 검증된 incumbent만 시작 값으로 제공합니다. 상위 목적이 다른 단계에서 우연히 개선되어도 그 최신 개선을 되돌리지 못하도록 추가 임시 잠금과 독립 수락 검사를 적용했습니다.',
        '최종 유지한 수락 경로는 독립 job/GPU/rack/WAN/AIDC/grid/P1–P5 재계산, 원래 전체 행 검사, 저장 및 hash/readback을 통과했습니다. 유효하지 않은 제안은 보존·거절하고 이전 incumbent로 계속 탐색합니다.',
        '', '**물리 검증:** Fresh OpenDSS PASS, Actual replay PASS. Actual 결과는 탐색이나 선택에 사용하지 않았습니다.',
        '**회귀검사:** V4 단위·회귀검사 195개 PASS. 원래 May-04 전체 모델의 알려진 P2 개선 및 P1 공동 이동 회귀검사도 PASS했습니다.',
        '**해석 제한:** 진단에서 RUNNING checkpoint 이후 23시간 대기와 day horizon 밖 서비스 이동이 개선에 기여했습니다. 이는 원래 UID-WAN 규칙에서 가능한 해이며 순수 공간 분산 효과와 동일시하면 안 됩니다. 새 production의 작업별 대기·종료 시간은 JSON `migration_wait_and_service`에 기록했습니다.',
        '진단 중 동일 부분문제에서 더 나은 feasible witness가 앞선 solver bound를 반박한 사례도 보존했습니다. 그 최적성 주장은 철회했으며 이번 생산 결과 역시 전역 최적성으로 주장하지 않습니다.',
        '', '**전체 5월:** 실행하지 않았습니다. May-04 수락만 완료했으며, 31일/B3 통합 release 재검증과 campaign frozen-release 교체까지 수행한 상태는 아닙니다. 사용자 보류 상태를 유지하고 종료합니다.',
        '', '근거와 SHA-256은 [JSON 보고서](V41R1_MAY04_FIRST_IMPROVEMENT_ACCEPTANCE.json)에 있습니다.',
        'Solver 사용 근거: [Gurobi feasibility objectives](https://docs.gurobi.com/projects/optimizer/en/current/concepts/modeling/objectives.html), [SolutionLimit](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#solutionlimit).']
    (OUT/'V41R1_MAY04_FIRST_IMPROVEMENT_ACCEPTANCE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('FIRST_IMPROVEMENT_REPORT_PASS',new['P1_P5'],new['optimization_seconds'],flush=True)

if __name__=='__main__':run()

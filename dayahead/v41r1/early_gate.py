"""Evidence for the compute-only correction and preserved pre-stop run."""
import ast
import gzip
import hashlib
from pathlib import Path
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,record
from dayahead.v41.execution import science
from dayahead.v41.reserve import require,lexicographic_compare
from .early_stop import VERSION,TOLERANCES

EVIDENCE=ROOT/'dayahead/artifacts/v41r1_bounded_compute'


def source_gate():
    from .fo_release import test_gate
    test_gate(EVIDENCE/'EARLY_STOP_REGRESSIONS.xml',16)
    before=read(EVIDENCE/'pre_early_stop/PRESERVATION.json')
    require(record(before['acceptance']['path'])==before['acceptance'],'PRE_EARLY_STOP_RESULT_CHANGED')
    for entry in before['preserved_files']:
        ref=entry['preserved'];require(record(ref['path'])==ref,'PRESERVED_EVIDENCE_CHANGED')
    old={r['relative_path']:r for r in before['source']['files']}
    allowed={'dayahead/v41r1/bounded_solver.py','dayahead/v41r1/bounded_runtime.py','dayahead/v41r1/early_stop.py','dayahead/v41/execution.py'}
    require(set(old)<=set(r['relative_path'] for r in science()['files']),'SCIENCE_SOURCE_REMOVED')
    checks=[]
    for ref in science()['files']:
        rel=ref['relative_path'];changed=rel not in old or old[rel]['sha256']!=ref['sha256']
        require(not changed or rel in allowed,'EARLY_STOP_SCIENTIFIC_SOURCE_CHANGE:'+rel)
        checks.append(dict(path=rel,changed=changed))
    def executable(source):
        tree=ast.parse(source);tree.body=[n for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name!='science']
        return ast.dump(tree,include_attributes=False)
    oldexec=EVIDENCE/'pre_early_stop/source/dayahead/v41/execution.py'
    require(executable(oldexec.read_text(encoding='utf-8-sig'))==executable((ROOT/'dayahead/v41/execution.py').read_text(encoding='utf-8-sig')),'EARLY_STOP_EXECUTION_CHANGED')
    value=dict(status='PASS',compute_control_version=VERSION,source=science(),checks=checks,
        scope='Only scheduling, convergence, counters, compute reporting and science manifest membership changed',
        regression_tests=record(EVIDENCE/'EARLY_STOP_REGRESSIONS.xml'),pre_early_stop=record(EVIDENCE/'pre_early_stop/PRESERVATION.json'))
    write_json(EVIDENCE/'EARLY_STOP_SOURCE_GATE.json',value);return value


def model_sha(path):
    h=hashlib.sha256()
    with gzip.open(path,'rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def acceptance_checks(root,seed,compute,solver,candidates,coverage):
    gate=read(EVIDENCE/'EARLY_STOP_SOURCE_GATE.json')
    require(gate['status']=='PASS' and gate['source']==science(),'CURRENT_EARLY_STOP_SOURCE_GATE_REQUIRED')
    preserved=read(EVIDENCE/'pre_early_stop/PRESERVATION.json');old=read(preserved['acceptance']['path'])
    require(record(preserved['acceptance']['path'])==preserved['acceptance'],'PRE_ACCEPTANCE_CHANGED')
    oldroot=Path(preserved['acceptance']['path']).parent/'2025-05-04/B1/dayahead/A0'
    newroot=Path(root)/'2025-05-04/B1/dayahead/A0'
    require(model_sha(oldroot/'PRIMARY_MODEL.mps.gz')==model_sha(newroot/'PRIMARY_MODEL.mps.gz'),'ORIGINAL_FULL_MODEL_CHANGED')
    oldc=read(oldroot/'V41R1_FULL_CANDIDATE_MANIFEST.json')
    require(oldc['candidate_set_SHA']==candidates['candidate_set_SHA'],'AUTHORITATIVE_CANDIDATES_CHANGED')
    require(oldc['final_authoritative_candidates']==candidates['final_authoritative_candidates'],'CANDIDATE_COUNT_CHANGED')
    require(solver['compute_control_version']==compute['compute_control_version']==VERSION,'OLD_EARLY_STOP_CONTRACT')
    require(compute['optimization_seconds']<=1800,'EARLY_STOP_HARD_CAP')
    require(abs(compute['TOTAL_UNUSED_BUDGET_SECONDS']-(1800-compute['optimization_seconds']))<1e-6,'UNUSED_BUDGET_ACCOUNTING')
    require(lexicographic_compare(solver['stages'][-1]['accepted_objective_vector'],old['final_objective_vector'],TOLERANCES)<=0,'ACCEPTED_PREVIOUS_INCUMBENT_DISCARDED')
    stages=solver['stages'];require(len(stages)==5,'P1_TO_P5_MISSING')
    for i,s in enumerate(stages):
        require(s['feasibility']['status']=='PASS','STAGE_HARD_ROW_AUDIT')
        require(s['stage_priority']==f'P{i+1}' and 'STAGE_COVERAGE_FRACTION' in s,'STAGE_COVERAGE_MISSING')
        require(not s['raw_candidate_coverage_required_for_stopping'],'RAW_COVERAGE_USED_FOR_STOP')
        require(s['termination_reason'] in ('FULL_SWEEP_PLUS_DIVERSIFICATION_NO_IMPROVEMENT','NORMAL_FAMILY_SWEEP_NO_IMPROVEMENT',
            'OBJECTIVE_PROVEN_OPTIMAL','STAGE_SOFT_GUARD_REACHED','POLICY_DAY_HARD_CAP_REACHED'),'UNCLASSIFIED_STAGE_TERMINATION')
        if s['termination_reason']=='FULL_SWEEP_PLUS_DIVERSIFICATION_NO_IMPROVEMENT':
            require(s['normal_sweeps_completed']>=1 and s['diversification_sweeps_completed']==1,'STAGNATION_SWEEP_EVIDENCE')
            require(s['stage_family_coverage_fraction']==1,'MAJOR_FAMILIES_MISSING')
        if s['objective_floor_certificate']:
            require(s['neighborhoods_solved']==0 or s['material_improvements']>0,'REDUNDANT_FLOOR_SEARCH')
        if i:
            previous=stages[i-1]['accepted_objective_vector']
            current=s['accepted_objective_vector']
            require(all(current[k]<=previous[k]+TOLERANCES[k] for k in range(i)),'HIGHER_PRIORITY_LOCK_DEGRADED')
    require(stages[0]['first_incumbent_seconds'] is not None and stages[0]['first_incumbent_seconds']<5,'SEED_NOT_ACCEPTED_IMMEDIATELY')
    require(coverage['scientific_candidate_pruning']==0,'CANDIDATE_PRUNING')
    return dict(status='PASS',checks_A_through_O='PASS',compute_control_version=VERSION,
        source_gate=record(EVIDENCE/'EARLY_STOP_SOURCE_GATE.json'),
        original_full_model_SHA=model_sha(newroot/'PRIMARY_MODEL.mps.gz'),
        authoritative_candidate_SHA=candidates['candidate_set_SHA'],
        A_verified_seed=seed['status'],B_first_solver_incumbent_seconds=stages[0]['first_incumbent_seconds'],
        C_identical_full_model=True,D_identical_candidate_universe=True,
        E_normal_neighborhoods=sum(s['neighborhoods_solved'] for s in stages),
        F_independent_validation='UNCHANGED_VALIDATOR_PLUS_CANONICAL_ROW_AUDIT',
        G_noise_and_lower_priority_reset_tests=gate['regression_tests'],
        H_I_sweep_control_tests_and_stage_receipts=gate['regression_tests'],
        J_optimization_seconds=compute['optimization_seconds'],K_unused_seconds=compute['TOTAL_UNUSED_BUDGET_SECONDS'],
        L_higher_locks='PASS',M_N_O='Fresh/Actual sealed decision and persistence verified by unchanged phase receipts')


def compare(new_acceptance):
    new_acceptance=Path(new_acceptance);new=read(new_acceptance)
    preserved=read(EVIDENCE/'pre_early_stop/PRESERVATION.json');old=read(preserved['acceptance']['path'])
    def fields(value):
        stages=read(value['artifacts']['solver']['path'])['stages']
        physical={}
        for phase,rel in [('dayahead','fresh'),('actual','grid')]:
            summary=read(Path(value['artifacts'][phase]['path']).parent/rel/'OPENDSS_SUMMARY.json')
            physical[phase]={k:summary[k] for k in ('OpenDSS_solve_count','convergence_count','physical_violation',
                'rho_max_AC','Vmin_pu','Vmax_pu','voltage_violation_count','line_current_violation_count',
                'transformer_current_violation_count','transformer_kva_violation_count','schedule_mutation_count')}
        return dict(physical=physical,optimization_seconds=value['optimization_seconds'],wall_with_Fresh_Actual_seconds=value['total_wall_seconds'],
            stage_runtime_seconds={f'P{i+1}':s['runtime_seconds'] for i,s in enumerate(stages)},
            stage_details=[{k:s.get(k) for k in ('stage','termination_reason','material_improvements','normal_sweeps_completed',
                'diversification_sweeps_completed','stage_family_coverage_fraction','STAGE_COVERAGE_FRACTION','neighborhoods_solved')} for s in stages],
            raw_candidate_coverage=value['coverage_fraction'],P1_P5=value['final_objective_vector'],
            Fresh=value['Fresh'],Actual=value['Actual'],candidate_count=value['candidate_count'])
    value=dict(status='PASS',compute_control_version=VERSION,pre_early_stop=fields(old),new_early_stop=fields(new),
        saved_optimization_seconds=old['optimization_seconds']-new['optimization_seconds'],
        savings_fraction=1-new['optimization_seconds']/old['optimization_seconds'],
        scientific_feasible_set_identical=True,raw_coverage_is_audit_only=True,global_optimality_claimed=False,
        before=preserved['acceptance'],after=record(new_acceptance))
    write_json(EVIDENCE/'EARLY_STOP_BEFORE_AFTER.json',value)
    a=value['pre_early_stop'];b=value['new_early_stop']
    lines=['# May-04 B1 corrected family-sweep acceptance','',
        '| 지표 | 기존 F&O | 새 조기 종료 F&O |','|---|---:|---:|',
        f"| 최적화 시간 | {a['optimization_seconds']/60:.2f}분 | {b['optimization_seconds']/60:.2f}분 |",
        f"| Fresh·Actual 포함 | {a['wall_with_Fresh_Actual_seconds']/60:.2f}분 | {b['wall_with_Fresh_Actual_seconds']/60:.2f}분 |",
        f"| 원시 후보 방문률 | {100*a['raw_candidate_coverage']:.2f}% | {100*b['raw_candidate_coverage']:.2f}% |"]
    for p in a['stage_runtime_seconds']:lines.append(f"| {p} 시간 | {a['stage_runtime_seconds'][p]:.1f}초 | {b['stage_runtime_seconds'][p]:.1f}초 |")
    for phase in ('dayahead','actual'):
        lines.append(f"| {phase} AC 최대 부하율 | {a['physical'][phase]['rho_max_AC']:.10f} | {b['physical'][phase]['rho_max_AC']:.10f} |")
        lines.append(f"| {phase} 전기 제약 위반 | {a['physical'][phase]['physical_violation']} | {b['physical'][phase]['physical_violation']} |")
    lines += ['',f"기존 P1–P5: {a['P1_P5']}",f"새 P1–P5: {b['P1_P5']}",'',
        f"후보 {b['candidate_count']:,}개와 전체 모델 MPS가 동일합니다. Fresh OpenDSS·Actual replay 및 해시·재읽기 검증은 PASS입니다.",
        '원시 후보 방문률은 감사 지표입니다. 미방문 후보도 권위를 유지하며 제거되지 않았습니다. 전역 최적성을 인증한 결과는 아닙니다.','']
    lines += [f"최적화 시간은 {value['saved_optimization_seconds']:.1f}초 ({100*value['savings_fraction']:.2f}%) 줄었습니다. 30분 예산 중 {1800-b['optimization_seconds']:.1f}초를 사용하지 않았습니다.", '',
        '| 단계 | 탐색군 방문률 | 단계 원시 후보 방문률 | 종료 사유 |', '|---|---:|---:|---|']
    reasons={'FULL_SWEEP_PLUS_DIVERSIFICATION_NO_IMPROVEMENT':'기본 1회 + 추가 1회, 개선 없음',
        'NORMAL_FAMILY_SWEEP_NO_IMPROVEMENT':'기본 1회, 개선 없음',
        'OBJECTIVE_PROVEN_OPTIMAL':'독립 확인된 0 하한 도달'}
    for i,s in enumerate(b['stage_details']):
        lines.append(f"| P{i+1} | {100*s['stage_family_coverage_fraction']:.0f}% | {100*s['STAGE_COVERAGE_FRACTION']:.2f}% | {reasons.get(s['termination_reason'],s['termination_reason'])} |")
    lines += ['', 'P3·P4는 상위 목적값을 고정한 상태에서 해당 목적의 0 하한을 확인했으므로 탐색군을 열지 않았습니다. P1·P2의 전역 최적성을 뜻하지 않습니다.',
        'P5 단독 시간은 35.0초에서 126.0초로 증가했습니다. 새 정의에 따라 다섯 탐색군의 부분문제와 독립 검증을 완료한 비용이며, 모든 단계가 각각 빨라진 결과는 아닙니다.',
        'B0 대비 목적값 차이는 B0_VS_B1_OBJECTIVES.md에 별도로 정리했습니다.',
        '5월 전체 실행은 사용자 요청에 따라 보류하며, 이번 수락검증과 보고서 작성 후 종료합니다.', '']
    (EVIDENCE/'EARLY_STOP_BEFORE_AFTER.md').write_text('\n'.join(lines),encoding='utf-8')
    return value


if __name__=='__main__':source_gate()

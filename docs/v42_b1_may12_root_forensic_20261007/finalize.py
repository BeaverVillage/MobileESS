"""Assemble the diagnostic report from saved/static results; no optimizer."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('may12_saved_evidence',Path(__file__).with_name('forensic.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
import csv, json, hashlib, ast, sys
from collections import defaultdict

def table(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (f.OUT/name).open('w',encoding='utf-8',newline='') as o:
        w=csv.DictWriter(o,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    data={d:f.read(f.OUT/(d+'.json')) for d in f.SELECTED}
    x=data['2025-05-12'];root=x['log'];receipt=x['P1_receipt'];original=x['numerical'][0];compressed=x['numerical'][1]
    run_identity=f.read(f.RUN/'RUN_IDENTITY.json');freeze=f.read(f.RUN/'B1_PRODUCTION_FREEZE_MANIFEST.json')
    final=f.read(f.RUN/'FINAL_CAMPAIGN_RESULT.json')
    assert final['all_31_attempted'] and final['counts']['PASS']==27
    assert all(d in final['PASS_dates'] for d in f.SELECTED if d!='2025-05-12')
    certificate_checks={}
    for d in f.SELECTED:
        saved=f.RUN/'stages'/d/'A1'/'1'/'output'
        cert=f.read(saved/'A2SC_INDEPENDENT_VERIFICATION.json')
        material=f.read(saved/'A2SC_MATERIALIZATION_AUDIT.json')
        assert cert['PASS'] and cert['FULL_LP_equivalence'] and material['PASS']
        for artifact in cert['files']:
            current=f.record(artifact['path'])
            assert current==artifact,(d,'FROZEN_CERTIFICATE_FILE_HASH_MISMATCH')
        certificate_checks[d]=dict(independent_verifier=cert,materialization=material,certificate_file_hashes_match=True)
    # Refresh only small metadata, never any native computation or saved matrix.
    for d,v in data.items():
        p=f.RUN/'inputs'/d
        bundle=f.read(p/'NATIVE_INPUT.json');window=f.read(p/'WINDOWS.json')
        modeled={j['job_uid'] for j in bundle['known_population'] if j['planning_eligible'] and j['service_slots']>0}
        v['shift_prestart_domain'].update(
            modeled_allowed_start_choices=sum(len(w['allowed_starts']) for w in window if w['job_id'] in modeled),
            modeled_jobs_with_multiple_allowed_starts=sum(len(w['allowed_starts'])>1 for w in window if w['job_id'] in modeled),
            modeled_can_prestart_place=sum(j['can_prestart_place'] for j in bundle['known_population'] if j['job_uid'] in modeled),
            modeled_can_checkpoint_migrate=sum(j['can_checkpoint_migrate'] for j in bundle['known_population'] if j['job_uid'] in modeled))
        f.write(d+'.json',v)
    native=float(receipt['native_runtime']);pre=float(root['presolve_seconds']);simplex=float(root['root_seconds']);native_other_seconds=native-pre-simplex
    timeline=dict(day=x['day'],run_identity=run_identity,source_commit=freeze['Git_SHA'],native_budget=3600,
        native_Runtime=native,budget_scope='Cumulative native optimize Runtime across A1 objectives; build/compression/verification/materialization excluded',
        phases=dict(BUILD=dict(seconds_inside_native_budget=0,observed_pre_native_wall_seconds_approx=x['telemetry']['pre_native_build_proof_and_materialization_wall_seconds'],
            native_equation_build_seconds=x['native_build_stats']['model_build_seconds'],compression_seconds=x['census']['wall_seconds'],
            decomposition_complete=False,reason='Separate domain-build, capture, exact verification, IO, native materialization timings were not all saved'),
            PRESOLVE=dict(seconds=pre),ROOT_SIMPLEX=dict(seconds=simplex,method='dual simplex Method=1',iterations=root['root_iterations'],Work=root['root_Work'],completed=False),
            ROOT_BARRIER=dict(seconds=0,executed=False),CROSSOVER=dict(seconds=0,executed=False),
            OTHER=dict(seconds=native_other_seconds,reason='Native residual outside printed presolve/root durations; LP initialization/output/finalization not separately timed')),
        native_phase_total_seconds=pre+simplex+native_other_seconds,root_budget_share=simplex/native,
        callback_seconds=6.26,callback_time_is_overlapping_native_time_not_extra=True,
        logging_start_UTC=root['native_logging_start_UTC'],display_timezone='Asia/Seoul',
        rounding='Root and presolve durations printed to 0.01 seconds; OTHER inherits that rounding; telemetry/log UTC alignment approximately 1 second',
        root_progress=root['root_progress'],root_objective_progress_is_NOT_valid_LB=True,
        final_valid_LB_receipt=receipt['valid_LB'],last_printed_primal_infeasibility=root['stalling']['last']['primal_infeasibility'],
        B_and_B_began=False,native_nodes=receipt['node_count'],native_infeasibility_not_proven=True,new_optimize_calls=0)
    f.write('MAY12_ROOT_TIMELINE.json',timeline)
    census=[]
    for d,v in data.items():
        n0,n1=v['numerical'];log=v['log'];tele=v['telemetry']['P1_native_interval'];c=v['census']; row=dict(day=d,role='TARGET' if d=='2025-05-12' else 'PASS_COMPARATOR',jobs_raw=v['jobs_raw'],jobs_modeled=v['jobs_modeled'],scientific_classes=v['scientific_classes'],complete_logical_units=v['complete_logical_units'],optional_migration_units=v['optional_migration_units'])
        for label,obj in [('original',n0),('compressed_solver_input',n1),('native_presolved',log['presolved'])]:
            for key in ['rows','columns','binaries','continuous','other_integers','nnz']:row[label+'_'+key]=obj[key]
        row.update(coefficient_min=n1['coefficient_range_exact'][0],coefficient_max=n1['coefficient_range_exact'][1],RHS_min=n1['RHS_range_exact'][0],RHS_max=n1['RHS_range_exact'][1],bound_min=n1['bound_range_exact'][0],bound_max=n1['bound_range_exact'][1],
            presolve_seconds=log['presolve_seconds'],native_rows_removed=log['rows_removed'],native_cols_removed=log['columns_removed'],root_method=log['root_method'],root_phase=log['root_phase'],root_completed=log['root_completed'],root_iterations=log['root_iterations'],root_seconds=log['root_seconds'],root_Work=log['root_Work'],root_objective=log['root_objective'],first_root_objective=log['root_progress'][0]['objective'],last_root_objective=log['last_printed_root_objective'],last_primal_infeasibility=log['root_progress'][-1]['primal_infeasibility'],
            warning_count=len(log['warnings']),warnings=' | '.join(log['warnings']),barrier_seen=log['barrier_seen'],crossover_seen=log['crossover_seen'],peak_P1_RSS_GiB=tele['max_RSS_GiB'],minimum_P1_available_RAM_GiB=tele['min_available_RAM_GiB'],CPU_to_wall_ratio=tele['CPU_seconds_delta']/tele['wall_seconds'],paging='NOT_RECORDED',Kappa='NOT_RECORDED',KappaExact='NOT_RECORDED',native_build_seconds=v['native_model_build_seconds'],pre_native_wall_seconds_approx=v['telemetry']['pre_native_build_proof_and_materialization_wall_seconds'],alias_columns=c['alias_columns'],fixed_zero_columns=c['fixed_zero_columns'],bound_redundant_rows=c['bound_redundant_rows'],duplicate_rows=c['duplicate_rows'],proportional_dominated_rows=c['proportional_dominated_rows'],resource_bound_tightenings=c['resource_bound_tightenings'],grid_retained_rows=sum(r['count'] for r in v['families'] if r['model']=='A2SC' and r['kind']=='ROW' and r['group']=='grid'),weak_upper_unbounded_columns=n1['upper_unbounded_columns'],MIP_start_supplied=v['start']['supplied'],MIP_start_accepted=v['start']['accepted'])
        census.append(row)
    table('MAY12_VS_PASS_DATES_CENSUS.csv',census)
    selection=dict(comparator_dates=f.SELECTED[0:1]+f.SELECTED[2:],selection='May11/May13 required. Among remaining PASS dates, May20 is the smallest compressed-nnz model >= May12, and May01 is the largest. Selected without using excluded dates.',
        larger_PASS_comparators=['2025-05-20','2025-05-01'],no_failed_date_comparator_selection=True)
    f.write('MAY12_PRESOLVE_FORENSIC.json',dict(day=x['day'],original=original,compressed_solver_input=compressed,
        existing_native_presolve=root['presolved'],presolve_seconds=pre,rows_removed=root['rows_removed'],columns_removed=root['columns_removed'],reduction=root['presolve_reduction'],
        exported_presolved_model_available=False,presolved_matrix_or_uncrush_family_mapping_available=False,
        no_new_presolve_or_model_build=True,read_only_saved_matrices=True,existing_certificate_comparison=certificate_checks,
        native_presolved_job_state_counts=None,native_presolved_job_count_limitation='No native presolved scientific ownership/uncrush mapping saved; original modeled jobs are compared instead.',
        compare={d:dict(raw=v['log']['raw'],presolved=v['log']['presolved'],presolve_seconds=v['log']['presolve_seconds']) for d,v in data.items()},comparator_selection=selection,new_optimize_calls=0))
    grouped={}; detailed=[]
    for d,v in data.items():
        g=defaultdict(int)
        for row in v['families']:
            g[(row['model'],row['kind'],row['group'])]+=row['count'];detailed.append(row)
        grouped[d]=g
    table('MAY12_FAMILY_DETAIL.csv',detailed)
    families=[]
    for (model,kind,group),count in grouped[x['day']].items():
        others=[grouped[d].get((model,kind,group),0) for d in selection['comparator_dates']]
        r=dict(model=model,kind=kind,family_group=group,May12_count=count,May12_per_modeled_job=count/x['jobs_modeled'],PASS_comparator_max=max(others),anomalously_larger_than_all_PASS_comparators=count>max(others),
            scope='Disjoint raw or compressed matrix census, not native-presolve mapping')
        for d in selection['comparator_dates']:
            comparator_count=grouped[d].get((model,kind,group),0);r[d+'_count']=comparator_count;r[d+'_May12_ratio']=count/comparator_count if comparator_count else ''
        families.append(r)
    for key in ['modeled_allowed_start_choices','modeled_jobs_with_multiple_allowed_starts','modeled_can_prestart_place','modeled_can_checkpoint_migrate']:
        count=x['shift_prestart_domain'][key];r=dict(model='DOMAIN_METADATA',kind='SHARED_SHIFT_PRESTART_MIGRATION',family_group=key,May12_count=count,
            scope='Shared original job domains; does not double-count rows/columns or claim separate P1 blocks')
        for d in selection['comparator_dates']:r[d+'_count']=data[d]['shift_prestart_domain'][key]
        families.append(r)
    table('MAY12_FAMILY_ANOMALY.csv',families)
    f.write('MAY12_NUMERICAL_AUDIT.json',dict(day=x['day'],saved_matrix_checks=x['numerical'],existing_native_warnings=root['warnings'],root_progress_stalling=root['stalling'],
        comparator_numerical={d:dict(matrix_checks=v['numerical'],warnings=v['log']['warnings'],stalling=v['log']['stalling']) for d,v in data.items()},
        solver_parameters_from_existing_P1_receipt=receipt['solver'],
        presolved_coefficient_RHS_bound_ranges=None,presolved_range_limitation='No exported native presolved matrix/attributes or post-presolve coefficient/RHS/bound ranges were saved.',
        Kappa=None,KappaExact=None,zero_reduced_costs_at_root=None,fraction_at_bounds_at_root=None,
        missing='No saved root X, basis, RC or Kappa. PASS final integer X is explicitly not used as a root basis proxy.',
        row_parallelism_scope='Deterministic bounded sample, with exact CSR support/coefficient comparison; not all-row near-parallel proof',
        variable_family_code_metadata_issue='Non-May01 vf_names exceeds uint16 code capacity. Decoded name-family ledger is not trusted. This diagnostic independently reconstructs ownership from scientific interfaces, verifies native family counts, and transports saved exact root indices. No model/data repair is performed.',
        start_audit={d:v['start'] for d,v in data.items()},resources={d:v['telemetry'] for d,v in data.items()},new_optimize_calls=0))
    experiment=dict(number_of_experiments=1,execute=False,name='Frozen May12 P1 single root-only barrier diagnostic',
        frozen_matrix_SHA256=x['build_receipt']['compressed_matrix']['sha256'],source_commit=freeze['Git_SHA'],input_SHA256=x['source_input_SHA256'],
        one_algorithm_change='Method=1 -> Method=2',scope_stop='Root only; NodeLimit=1, same 3600-second ceiling; no later objective or day',
        unchanged='Same matrix, bounds, RHS, objective, variable types, all other solver parameters/tolerances and existing Crossover setting. Threads=1, MIPGap=.005; no start injection or formulation change.',
        record='Barrier progress/conditioning warnings, crossover time, exact root completion/time/Work, memory and saved root basis/RC when available',
        hypothesis='Separate a dual-simplex-specific convergence bottleneck from a difficulty also present under barrier/crossover; this is one preregistered run, not a sweep',
        verdict='Root completion <=3600s with valid LP result supports changing the root method; barrier/crossover timeout keeps the mechanism unresolved',
        recommendation_only_not_execution_authorization=True,optimization_calls_in_this_task=0)
    cause=dict(classification='INCONCLUSIVE',confirmed_bottleneck='ROOT_DUAL_SIMPLEX_PRIMAL_FEASIBILITY_CONVERGENCE',
        classification_scope='The time-consuming solver phase is conclusively identified. A unique causal mechanism among degeneracy, conditioning and date-specific LP geometry cannot be established from saved diagnostics alone.',
        root_seconds=simplex,root_budget_share=simplex/native,root_iterations=root['root_iterations'],root_Work=root['root_Work'],
        last_logged_primal_infeasibility=root['stalling']['last']['primal_infeasibility'],printed_dual_infeasibility_always_zero=True,
        mathematical_LP_degeneracy_proven=False,degeneracy_suspected=True,
        identical_printed_objective_intervals=root['stalling']['printed_objective_identical_intervals'],
        rationale='885048 dual-simplex iterations and 4936.57 root Work without primal feasibility, while bigger PASS models finish in 14.35/22.14/30.44 seconds. All models have one objective column and very large zero-objective blocks. No saved basis/RC/Kappa supports a definitive degeneracy or conditioning diagnosis.',
        rejected_as_primary_explanations=dict(MODEL_SIZE_ANOMALY='May13/May20/May01 are larger both before and after native presolve and finish root rapidly',PRESOLVE_BOTTLENECK='31.58s, less than 1% of native Runtime',WAN_STATE_EXPLOSION='May12 is smaller than all three larger PASS WAN blocks',JOB_STATE_EXPLOSION='Large relative to May11, smaller than the larger PASS job blocks and start domains',RESOURCE_PRESSURE='Single-core CPU/wall approximately 0.970 with >=12.24 GiB available; no guard action. Paging counters absent, so paging is not mathematically excluded',MIP_START_MISSING_NOT_ROOT_CAUSE='No start supplied on any comparator either. Missing incumbent alone does not explain divergent root completion.'),
        numerical_conditioning='Wide range warning shared by every date; May12 max coefficient smaller than May11/May13/May01. Kappa, RC, refactorization counts not recorded; conditioning cannot be certified or excluded.',
        no_May12_specific_family_size_anomaly_against_larger_PASS=True,scientific_infeasibility_not_proven=True,
        recommendation=experiment,forbidden_dates_worked_on=[],new_optimize_calls=0,model_or_formulation_modified=False)
    f.write('MAY12_ROOT_CAUSE.json',cause)
    lines=['# May12 B1 A1 P1 ROOT LP 읽기 전용 진단','', '**최종 분류: INCONCLUSIVE.** 지연된 단계는 확정했지만, LP 퇴화·수치 조건·날짜별 LP 기하 중 하나를 유일한 원인으로 확정할 저장 자료는 없다.','',
        f"완료 campaign `{run_identity['run_id']}`의 May12가 대상이다. 실행 소스 `{freeze['Git_SHA']}`, scientific SHA `{freeze['scientific_SHA']}`, 입력 SHA `{x['source_input_SHA256']}`, 압축 matrix SHA `{x['build_receipt']['compressed_matrix']['sha256']}`를 고정했다. 기준 작업 트리의 publish 커밋은 `67a352b1145410c6def8129cffcc10abf1b17adb`다. 과거 PR150/PR151 실패 모델과 혼동하지 않았다.",'',
        'May11·May13을 필수 비교하고, 나머지 PASS 중 May12 이상의 nnz를 가진 가장 작은 모델 May20과 가장 큰 모델 May01을 추가했다. May10·May17·May19의 stage/input/model은 읽거나 실행하지 않았다. 별도 May17/May19 복구 작업과 독립 작업 트리에서 병행했고, campaign·복구 파일을 변경하지 않았다.','',
        '## 1. 3,600초가 소진된 단계','',
        '| 단계 | native 예산 안 소요 시간 | 근거 |','|---|---:|---|',
        f"| BUILD | 0초 | worker의 사전 domain/build/compression/verification/materialization 약 {x['telemetry']['pre_native_build_proof_and_materialization_wall_seconds']:.2f}초는 native 3600초 바깥 |",
        f'| PRESOLVE | {pre:.2f}초 | 기존 native log |',f'| ROOT SIMPLEX | {simplex:.2f}초 | dual simplex, Method=1 |',
        '| ROOT BARRIER | 0초 | 실행 흔적 없음, Method=1 |','| CROSSOVER | 0초 | 실행 흔적 없음 |',
        f'| OTHER | {native_other_seconds:.3f}초 | Runtime에서 presolve/root를 뺀 잔여값; 초기화·종료 내부 분할은 미기록 |',
        f'| 합계 | {native:.3f}초 | native receipt |','',
        f"root에 native Runtime의 **{simplex/native:.2%}**를 사용했다. 초기 식 구축은 {x['native_build_stats']['model_build_seconds']:.2f}초, exact compression은 {x['census']['wall_seconds']:.2f}초로 별도 기록돼 있으나 사전 약 329초 전체의 세부 분할은 모두 남아 있지 않다. callback 6.26초는 native 시간에 포함되므로 더하지 않았다. native 출력은 0.01초 정밀도, worker/telemetry 정렬은 약 1초 정밀도다.",'',
        '## 2. 같은 campaign의 크기와 root 비교','',
        '| 날짜 | modeled jobs | 압축 rows / cols / nnz | presolved rows / cols / nnz | presolve 초 | root 초 / 반복 / Work |','|---|---:|---|---|---:|---|']
    for row in census:
        lines.append(f"| {row['day']} | {row['jobs_modeled']:,} | {row['compressed_solver_input_rows']:,} / {row['compressed_solver_input_columns']:,} / {row['compressed_solver_input_nnz']:,} | {row['native_presolved_rows']:,} / {row['native_presolved_columns']:,} / {row['native_presolved_nnz']:,} | {row['presolve_seconds']:.2f} | {row['root_seconds']:.2f} / {row['root_iterations']:,} / {row['root_Work']:.2f} |")
    lines+=['', 'May12 raw(압축 전) 3,703,395행/2,708,445열/26,985,809 nnz, 압축 solver 입력 3,040,170행/2,669,123열/17,558,423 nnz다. Presolved는 2,745,448행/2,583,727열/11,396,870 nnz다. May13·May20·May01은 이 세 단계 모두 더 크고 root 완료는 훨씬 빠르다. 상세 binary/continuous/other integer, 제거 수, 범위와 memory는 CSV에 있다. Native presolve는 추가 integrality를 추론했으며 그 type 변화를 원래 formulation 수정으로 해석하지 않았다.','',
        '## 3. 가족별 구조와 압축 인증','', '| 압축 계열 | May11 rows / cols | May12 rows / cols | May13 rows / cols | May20 rows / cols | May01 rows / cols |','|---|---|---|---|---|---|']
    for group in ['job_time_resource','migration','WAN_flow_state','Runtime','CC4','rack_GPU_gang','grid','global_other']:
        vals=[f"{grouped[d].get(('A2SC','ROW',group),0):,} / {grouped[d].get(('A2SC','COLUMN',group),0):,}" for d in f.SELECTED]
        lines.append('| '+group+' | '+' | '.join(vals)+' |')
    lines+=['', 'May12에서 May11 대비 가장 커진 주 블록은 job/time/resource다(열 144,792→1,595,700, 약 11.02배). WAN 열도 68,473→440,702, 약 6.44배 증가했다. 하지만 더 큰 PASS 날짜의 같은 블록은 모두 더 크므로 **May12만의 job/WAN state explosion은 확인되지 않았다**. CC4는 같은 9,552열, grid 행도 약 12.1만행으로 공통적이다. Runtime·rack/GPU/gang은 별도 계수했고 anonymous global helper 2,304열은 남겨 명시했다. Shift/prestart는 별도 disjoint P1 행 계열이 아니라 y/상태 도메인과 뒤쪽 목적에 공유되므로 별도 window/domain 기록으로 비교하고 이중 집계하지 않았다.','',
        'May12에서는 alias 38,090열, fixed-zero 1,232열, bound-safe 568,158행, duplicate 26,412행, proportional-dominated 68,655행, resource-bound 4,832건의 기존 인증이 있다. 총 663,225행 제거 및 FULL_LP 동치성은 기존 독립 verifier PASS다. 저장된 grid·WAN·job·약한 경계가 더 큰 PASS보다 특별히 많다는 증거가 없다. Native presolved family/uncrush mapping은 저장되지 않아 원래/압축 family를 presolved family로 추정하지 않았다.','',
        '일부 날짜의 variable-family 코드에는 uint16보다 큰 이름 사전이 있어 단순 디코딩을 신뢰할 수 없었다. 진단에서는 저장된 scientific interface의 first-seen ownership을 독립 재구성하고 기존 native family count와 맞춘 뒤 exact compressed roots mapping으로 옮겼다. Row-family 코드는 작은 사전이라 온전히 사용했다. 이 메타데이터 문제를 수정하거나 scientific matrix 변경의 증거로 간주하지 않았다.','',
        '## 4. LP 진행·퇴화·수치 조건','',
        f"May12는 root 885,048 반복, 4,936.57 Work로 종료됐고 마지막 출력에서 primal infeasibility {root['stalling']['last']['primal_infeasibility']:,.1f}, dual infeasibility 0이었다. 출력 objective는 0.63199057→0.66711771로 계속 바뀌었으며 동일 printed objective interval은 0개였다. 따라서 ‘로그에 objective가 완전히 멈췄다’거나 ‘degenerate pivot 개수를 측정했다’고 주장하지 않는다. Primal feasibility를 확보하지 못한 dual-simplex 수렴 병목은 확정이다. 로그의 미완료 root objective는 valid LB로 승격하지 않았고 native receipt LB 0.6316300882361616을 구분했다.",'',
        'May12의 압축 matrix coefficient 절댓값 범위는 약 1.004e-13~76,293.9453, RHS는 약 8.406e-8~1,064,300.5371이다. 큰 coefficient range warning은 다섯 날짜 모두 공통이고 May11·May13·May01의 최대 coefficient는 약 305,175.7813으로 더 크다. Numerical failure, Markowitz/refactorization 또는 barrier/crossover warning은 기존 P1 log에서 찾지 못했다. Kappa/KappaExact·root RC·root X/basis는 미기록이다. Native presolved matrix/attributes가 없어 presolved coefficient/RHS/bound 범위는 계산할 수 없다. 기존 receipt의 FeasibilityTol=1e-6, OptimalityTol=1e-6, IntFeasTol=1e-5, NumericFocus=0을 그대로 기록했다.','',
        f"목적계수는 rho 한 열에만 있고 나머지 {compressed['objective_zero_fraction']:.8%}는 0이다. rho는 121,607개 retained 행에 연결되며 upper-unbounded 열은 9,408개, 완전히 free인 열은 0이다. 같은 zero-objective 구조·약한 상한·고연결 rho는 PASS 날짜에도 있다. Root at-bound 비율과 zero RC 비율은 계산 불가이며, 저장된 PASS P1 integer incumbent at-bound 비율은 root basis 대용으로 쓰지 않았다. {compressed['sampled_row_parallelism']['sample_rows']:,}개 deterministic family-row 표본에서 exact duplicate는 0, 동일 LHS는 {compressed['sampled_row_parallelism']['identical_LHS_rows_in_sample']}개, 같은 support의 near-parallel pair는 {compressed['sampled_row_parallelism']['absolute_cosine_at_least_1_minus_1e_10_pairs']}개였다. 이 표본과 단위 의존 cosine으로 전체 redundancy나 퇴화를 확정하지 않았다.",'',
        '## 5. 자원과 시작해','',
        f"May12 P1 구간 RSS peak {x['telemetry']['P1_native_interval']['max_RSS_GiB']:.2f} GiB, 최소 가용 RAM {x['telemetry']['P1_native_interval']['min_available_RAM_GiB']:.2f} GiB, CPU/wall 비 {x['telemetry']['P1_native_interval']['CPU_seconds_delta']/x['telemetry']['P1_native_interval']['wall_seconds']:.3f}(한 코어 기준)였다. Guard·인위 감속은 없었다. Paging/hard-fault/process-commit/system-commit counters는 저장되지 않아 paging의 절대적 부재를 증명하지는 않았다. 더 큰 PASS의 RAM pressure가 더 높았다는 관찰과 함께, May12의 resource pressure를 주원인으로 지지할 자료는 없다.",'',
        'May12에는 authoritative B0 common reference 입력이 있었지만, 원래/압축 native 전 행을 검증한 B0/B1 MIP-start vector는 date output에 없다. BUILD_RECEIPT의 old_start_loaded=false, frozen source의 P1 전 Start/read-start 작업 없음, native start message 없음이 일치한다. 실제 supplied/accepted start는 둘 다 false다. 다른 PASS 날짜도 P1 start 없이 root를 완료했으므로 missing start만을 root timeout의 원인으로 선택하지 않았다. 공통 reference의 존재를 full native feasible start 존재로 바꾸어 말하지 않았다.','',
        '## 6. 결론과 다음 실험 하나','',
        '**확정:** native 예산의 98.95%가 ROOT dual simplex에서 소진됐고 root가 primal feasible LP 해를 완성하지 못했다. BUILD·presolve·barrier·crossover·단순 크기 폭증은 주 병목이 아니다. **미확정:** root basis/RC/Kappa와 paging 부재 때문에 LP 퇴화·날짜별 약한 LP 기하·conditioning 중 하나를 유일한 기제로 식별할 수 없다. 최종 분류는 INCONCLUSIVE로 둔다. TIMEOUT을 수학적 infeasibility로 해석하지 않는다.','',
        '**권고하는 실험은 하나:** frozen May12 P1 matrix/input/source를 그대로 사용하고 **Method만 1→2로 바꾼 단일 root-only 3,600초 실행**(NodeLimit=1, Threads=1, 기존 Crossover·나머지 parameter·tolerance 유지). Barrier/crossover phase별 시간·Work·완료 여부와 가능하면 root basis/RC를 기록해 dual simplex 특이적 병목인지 판별한다. Start 주입, formulation 변경, 뒤쪽 목적이나 다른 날짜 실행, sweep은 포함하지 않는다. **이번 작업에서는 실행하지 않았다.**','',
        '## 7. 진단 무변경 검증','', '저장 행렬·로그·입력·인증서만 읽었다. 새 native model build·presolve·optimize는 모두 0회다. 진단 코드에서 gurobipy 및 production module import를 fail-closed로 차단했고 AST로 optimizer/model API 호출 부재를 검사했다. 참조 파일 SHA256 전후 불변, 제외 날짜의 stage/input/model 접근 0, output namespace 격리를 별도 검증했다.']
    (f.OUT/'FINAL_REVIEW_KO.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
    sources={r['path']:r for v in data.values() for r in v['sources']}
    sources.update(f.SOURCES)
    # This task's derived JSON is intentionally refreshed above. It belongs in
    # the output manifest, not the immutable external evidence manifest.
    sources={p:r for p,r in sources.items() if not Path(p).resolve().is_relative_to(f.OUT.resolve())}
    # Include frozen production sources as evidence, but never import them.
    import subprocess
    for relative in ['v42_pr134_b1/native.py','v42_pr134_sc/materialize.py','v42_root/native.py','v42_root/factor.py']:
        payload=subprocess.check_output(['git','show',freeze['Git_SHA']+':'+relative],cwd=f.OUT.parents[1])
        sources['git:'+freeze['Git_SHA']+':'+relative]=dict(git_commit=freeze['Git_SHA'],path=relative,sha256=hashlib.sha256(payload).hexdigest(),bytes=len(payload))
    unchanged=[]
    for p,r in sources.items():
        if p.startswith('git:'):continue
        assert not any('/inputs/'+d+'/' in p.replace('\\','/') or '/stages/'+d+'/' in p.replace('\\','/') for d in f.EXCLUDED),p
        current=f.record(p);assert current==r,(p,'READ_ONLY_SOURCE_MUTATED');unchanged.append(p)
    guard_tests=[]
    for name in ['gurobipy','v42_pr134_b1.native']:
        try:__import__(name);raise AssertionError('IMPORT_GUARD_FAILED')
        except PermissionError:guard_tests.append(name)
    for p in f.OUT.glob('*.py'):
        tree=ast.parse(p.read_text(encoding='utf-8'))
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ['optimize','presolve','Model','addMVar','addConstr','addMConstr','setParam'] for n in ast.walk(tree))
    assert 'gurobipy' not in sys.modules
    for d,v in data.items():
        for model in ['A0','A2SC']:
            n=next(n for n in v['numerical'] if n['model']==model)
            for kind,key in [('ROW','rows'),('COLUMN','columns')]:assert sum(r['count'] for r in v['families'] if r['kind']==kind and r['model']==model)==n[key]
        assert v['build_receipt']['verification']['PASS']
    assert abs(timeline['native_phase_total_seconds']-native)<1e-9
    report=(f.OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8')
    assert f'| OTHER | {timeline["phases"]["OTHER"]["seconds"]:.3f}초 |' in report
    assert f'| 합계 | {timeline["native_Runtime"]:.3f}초 |' in report
    f.write('SOURCE_EVIDENCE_MANIFEST.json',dict(PASS=True,sources=list(sources.values()),files_readonly_verified=len(unchanged),source_commit=freeze['Git_SHA'],read_dates=f.SELECTED,forbidden_date_inputs_or_models_accessed=[]))
    required=['MAY12_ROOT_TIMELINE.json','MAY12_VS_PASS_DATES_CENSUS.csv','MAY12_PRESOLVE_FORENSIC.json','MAY12_FAMILY_ANOMALY.csv','MAY12_NUMERICAL_AUDIT.json','MAY12_ROOT_CAUSE.json','FINAL_REVIEW_KO.md']
    assert all((f.OUT/n).is_file() for n in required)
    f.write('VERIFICATION.json',dict(PASS=True,classification='INCONCLUSIVE',required_artifacts=required,compared_dates=f.SELECTED,
        source_files_unchanged=len(unchanged),existing_certificate_file_hashes_rechecked=True,family_row_column_census_reconciled=True,native_timeline_reconciled=True,report_timeline_matches_JSON=True,
        solver_and_production_import_guard_tests=guard_tests,optimizer_API_absence_AST=True,new_model_builds=0,new_presolve_calls=0,new_optimize_calls=0,
        scientific_model_modified=False,campaign_or_repair_modified=False,forbidden_date_work=[],recommendation_executed=False))
    artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(f.OUT.iterdir()) if p.is_file() and p.name!='SHA256_MANIFEST.json'}
    f.write('SHA256_MANIFEST.json',dict(PASS=True,files=artifacts,self_excluded=True))
    print('FINAL_DIAGNOSTIC_PASS',len(unchanged),'unchanged source files; optimize=0; INCONCLUSIVE',flush=True)

if __name__=='__main__':main()

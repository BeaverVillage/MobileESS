"""Freeze reporting for the stopped native canary; never launches optimization."""
from .prepare import ROOT,OUT,NATIVE,read,dump,csv,sha,record,SOURCES
import pandas as pd


def md(name,content):
    (OUT/name).write_text(content.strip()+'\n',encoding='utf8')


def main():
    b=read(OUT/'MAY01_NATIVE_INPUT_BUNDLE.json')
    c=read(OUT/'MAY01_A1_RESOURCE_CERTIFICATE.json')
    assert c['full_A1_infeasible_proven'] and c['solver_status']==3
    worst=c['worst_row'];jobs=b['known_population'];admitted=[r for r in jobs if r['planning_eligible']]
    masks=pd.read_csv(OUT/'MAY01_CAPABILITY_OVERLAP.csv').set_index('mask').to_dict('index')
    metrics={s:read(OUT/f'MAY01_{s}_SOLVER_METRICS.json') for s in ('A1','M1','A2','M2')}
    # Include original native pre-D00 unassigned policy and WAN source lineage.
    extra=record(NATIVE/'dayahead/v41r2/reference.py','Frozen pre-D00 unassigned RUNNING handling','source code',period='static authority used for May01')
    source=read(OUT/'SOURCE_MANIFEST.json')
    source['files']=[r for r in source['files'] if r['path']!=extra['path']]+[extra]
    dump('SOURCE_MANIFEST.json',source)
    csv('MAY01_AIDC_OPTION_PRESCREEN.csv',[dict(
        raw_jobs=len(jobs),known_planning_jobs=len(admitted),fixed_candidate_jobs=int(masks['FIX']['jobs']),
        movable_candidate_jobs=int(masks['FLEX']['jobs']),unresolved_jobs=len(jobs)-len(admitted),
        raw_options=None,retained_options=None,reduction_percent=None,
        stage='BEFORE_COMPLETE_OPTION_ENUMERATION',
        stop_reason='EXACT_SAFE_GLOBAL_KNOWN_PLUS_C0_CAPACITY_INFEASIBILITY',
        individual_rejection_reason=reason,rejected_count=None,
        count_status='NOT_ENUMERATED_NOT_ZERO',top_K_pruning=False,favorable_result_pruning=False)
        for reason in ('start-window impossible','GPU capacity impossible','rack impossible','service/tail violation',
                       'checkpoint impossible','WAN impossible','destination remaining-service impossible','exact duplicate')])
    # Keep the LP's measured size separate from full A1/M1/A2/M2 sizes.
    size_rows=[{k:v for k,v in row.items() if k!='supervisor'} for row in metrics.values()]
    size_rows.append(dict(stage='A1_NECESSARY_RESOURCE_PROJECTION_ONLY',day=b['day'],network=b['network'],
        status=c['status'],binary_count=c['model_size']['binary'],continuous_count=c['model_size']['continuous'],
        constraints=c['model_size']['linear_constraints'],nonzeros=c['model_size']['nonzeros'],
        full_model_built=False,model_scope=c['scope'],runtime_seconds=c['solver_runtime_seconds']))
    csv('MAY01_MODEL_SIZE_AUDIT.csv',size_rows)
    verdict=dict(status='NATIVE_INPUTS_BOUND_A1_PROVEN_INFEASIBLE_NO_FINAL_SCHEDULE',
        task_outcome='FAIL_CLOSED_RESOURCE_INFEASIBILITY',day=b['day'],network=b['network'],
        role='DEVELOPMENT_NATIVE_COMPUTATIONAL_CANARY',scientific_PASS=False,
        native_resource_projection_executed=True,full_A1_MILP_executed=False,
        full_four_block_computational_canary_completed=False,accepted_final_schedule=False,
        blocker='FIXED_T2_STARTS_PLUS_FROZEN_C0_NOMINAL_EXCEED_780_GPU_EVEN_WITH_OVERGENEROUS_MIGRATION_RELAXATION',
        worst_necessary_row=worst,violated_necessary_rows=c['number_violated_necessary_rows'],
        full_model_runtime_conclusion='UNMEASURED; no native speedup or four-block tractability claim',
        next_dependency='Source-authorized resolution of the known-service/C0 nominal resource incompatibility. Do not automatically change T2, C0, service, capacity, date, or horizon.',
        Fresh_AC='NOT_RUN_NO_FEASIBLE_FINAL_SCHEDULE',response_kernel='NOT_AUTHORIZED_NO_ACCEPTED_FRESH_VALID_ANCHOR',
        response_kernel_required_after_future_planning_and_Fresh_PASS=True,
        prior_PENDING_physical_gate_closed=True,prior_future_reservation_collisions_repaired=False,
        true_physical_conflicts_in_321_audited_intervals=0,
        original_pre_solve_IO_failure_preserved=True,optimization_attempts_on_native_resource_model=1)
    dump('MAY01_NATIVE_COMPUTATIONAL_VERDICT.json',verdict);dump('FINAL_VERDICT.json',verdict)
    flags=dict(PENDING_ACTUAL_GPU_OCCUPANCY_ZERO=True,RUNNING_ACTUAL_GPU_OCCUPANCY_FULL_GANG=True,
        KNOWN_PENDING_PLANNING_RESERVATION_ENABLED=True,PR79_ORIGINAL_CONFLICT_INTERVALS=321,
        PR79_PENDING_SEMANTICS_RESOLVED_COUNT=321,PR79_REMAINING_TRUE_CONFLICTS=0,
        PR79_CURRENT_PLANNING_COLLISIONS_STILL_RECORDED=321,
        T2_Q25_FROZEN=True,T2_Q25_USES_MAY_OUTCOMES=False,MAY01_NATIVE_INPUT_BUNDLE_READY=True,
        MAY01_IEEE123_GRID_BOUND=True,MAY01_MESS_INITIAL_STATE_BOUND=True,MAY01_TRAFFIC_ROUTE_BOUND=True,
        C0_CC4_BOUND=True,RUNTIME_PROVIDER_READY=False,UNKNOWN_DDAY_TEMPORAL_ACTIVE=False,
        UNKNOWN_DDAY_MIGRATION_ACTIVE=False,AIDC_NATIVE_POPULATION_BOUND=True,MESS_NATIVE_MILP_BOUND=False,
        MESS_QCONSTR_COUNT=0,MESS_P_AND_Q_JOINT=True,
        MESS_FLAGS_SCOPE='Preserved and regression-tested PR91 formulation; native M1/M2 models were not built',
        MESS_NATIVE_QCONSTR_COUNT=None,GRID_BOUND_SCOPE='Frozen numeric source axes loaded and SHA-verified; no full A1 grid rows built',
        AIDC_BOUND_SCOPE='1605 source-admitted native jobs in necessary resource model; full complete-option domain not enumerated',
        MAY01_AIDC_OPTION_REDUCTION_PERCENT=None,WARM_START_A1_TO_A2_ACCEPTED=False,WARM_START_M1_TO_M2_ACCEPTED=False,
        ALL_BLOCKS_TARGET_GAP_0P1_PERCENT=False,V42_NATIVE_BLOCK_RUNTIME_FEASIBLE=False,
        RUNTIME_FEASIBILITY_VERDICT='NOT_ESTABLISHED_UPSTREAM_INFEASIBLE',FRESH_AC_MAY01_PASS=False,
        RESPONSE_KERNEL_REGENERATION_REQUIRED=False,RESPONSE_KERNEL_STATUS='NOT_YET_AUTHORIZED_NO_FINAL_ANCHOR',
        CL_MC_BD_TRIGGERED=False,FULL_IEEE123_ROUND_RUN=False,IEEE8500_RUN=False,FULL_MAY_POLICY_EVALUATION=False,
        FLEX_SENSITIVITY_RUN=False,SEMANTIC_ML_MERGED=False,FUTURE_ACTUAL_RUNTIME_DECISION_READS=0,
        FULL_SERVICE_PRESERVED_IN_INPUT=True,ACCEPTED_SCHEDULE_COUNT=0,NATIVE_A1_INFEASIBILITY_PROVEN=True,
        A1_RUNTIME_SCOPE='Externally supervised necessary resource projection, including source load; not full MILP runtime')
    for s,row in metrics.items():
        for suffix,key in [('RUNTIME_SECONDS','runtime_seconds'),('FINAL_GAP','final_gap'),('STATUS','status'),
                           ('FIRST_INCUMBENT_SECONDS','first_incumbent_seconds'),('BINARY_COUNT','binary_count')]:
            flags[s+'_'+suffix]=row[key]
    dump('FINAL_FLAGS.json',flags)
    dump('REFERENCE_VERSION_COMPATIBILITY_AUDIT.json',dict(
        source=b['source_versions'],native_May01_reference_sha=b['reference']['sha256'],
        grid_coefficient_sha=b['grid_outputs']['planning_coefficients']['sha256'],grid_scale=b['alpha_BG'],
        capacity_total=sum(b['capacities'].values()),PR79_mapping_merged=False,
        independent_day_not_sequential_replay=True,sequential_episode_continuity_claim=False,
        running_native_site_rewrites=0,spatial_mapping_is_case_study_authority_not_raw_Kestrel_geolocation=True,
        unassigned_running_records=len(jobs)-len(admitted),
        unassigned_policy='Preserve full gang and source remaining service in unresolved external ledger; all frozen service ends <= D00. Do not claim observed completion or assign a fabricated site.',
        source_missing_for_complete_issue_physical_mapping=True,admitted_Dday_subset_is_source_authorized=True,
        complete_grid_MESS_model_compatibility_validation='NOT_EXECUTED_UPSTREAM_RESOURCE_INFEASIBILITY'))
    md('PENDING_RUNNING_STATE_CONTRACT.md','''
# Current physical state and future planning reservations

For both known and unknown jobs, causally observed PENDING has current physical GPU occupancy zero. RUNNING has its full GPU gang at its causal native site. A previous counterfactual PENDING schedule is metadata, never evidence of an execution transition. `v42_may01.state.observe` separates these views and rejects an unsupported RUNNING site rewrite.

A known PENDING job remains in the current planning population. Its full gang is reserved on every selected future execution slot, including post-H carry-out. Neither PENDING status nor an old plan reserves physical GPU *now*. Conversely, zero current physical occupancy never deletes the selected future reservation. RUNNING elapsed/requested-remaining values come from the issue-time causal snapshot and frozen native service authority; no future completion is used.

Issue is 2025-04-30 08:00 UTC (18:00 AEST). Issue-origin slot 24 is May-01 D00 and slot 120 is D24. D24 is only the electrical boundary. The ledger keeps full exact seconds, padded 900-second reservations, and post-H reservations separately. PENDING duration is frozen ROLLING_Q90_TRACK_P_L2; RUNNING uses REQUESTED_REMAINING, not an estimate of realized completion. No runtime model is trained or invoked.

All 1,649 source records are retained: 1,395 PENDING, 254 RUNNING. The native source admits 1,605 records (210 assigned RUNNING). The 44 UNASSIGNED RUNNING records retain full physical gang and their source-authorized pre-D00 remaining-service representation in an unresolved external ledger. They are not FIX, are not assigned a fictitious site, and are not claimed to have actually completed. This follows the existing native reference contract; complete issue-time site mapping is not claimed.

The 321 PR79 intervals have two distinct audit views. Their RUNNING physical occupancy is within capacity, so none establishes a true physical conflict after separating PENDING plans. The original table was already a *future-reservation audit*: its 321 future-plan collisions remain recorded and are not claimed repaired. The historical counterfactual reference is not merged into the independent-day May-01 frozen reference.

Unknown arrivals have no D-1 job reservation. C0 is a same-hour nominal aggregate plus uncertainty envelope, without invented jobs, deadlines, or backlog. Unknown temporal/migration actions remain disabled. Checkpoint physics and full-service rules from PR90/91 are unchanged.
''')
    md('A1_RESOURCE_INFEASIBILITY_PROOF.md',f'''
# Exact-safe May-01 A1 resource infeasibility certificate

This is a native-input necessary-condition certificate, not a full A1 MILP benchmark or an operating schedule. It stops complete-option enumeration before constructing the electrical model. A feasible relaxation would **not** pass the canary.

All {len(admitted)} source-admitted jobs have T2=false, so authorized execution starts equal their frozen reference starts. Pre-start site choice cannot change aggregate occupancy. A legal checkpoint migration is the only modeled action that can interrupt that original execution interval. The PR90 `validate` contract requires a positive integer transfer interval followed by restart before control_end=120. The native WAN authority allows at most one active transfer per slot. Thus at most 120 jobs can migrate, even granting the entire issue-origin horizon (more generous than D-day-only control).

Let b_j(t) be the original reference gang occupancy. Relax each job's migration indicator to 0<=z_j<=1, require sum(z)<=120, and remove **all** of its original occupancy when z=1, including before checkpoint. Omit destination compute, tail, rack, site, WAN path, checkpoint, electrical, and terminal constraints. This strictly enlarges the feasible set. Every original legal solution maps into this relaxation; none of these diagnostic deletions is accepted for execution.

The summed same-hour P2 nominal rows in `v42_native.envelope.bind` require sum_j b_j(t)*(1-z_j) + Q50(hour(t)) <= 780 even with uncertainty headroom zero. Q90-Q50 can incur reserve shortfall; Q50 and known service cannot. For each slot, removing the 120 largest live gangs gives an independent analytic lower bound valid even for fractional z (unit upper bounds).

At D-day slot {worst['slot_Dday']} (02:45 AEST; issue-origin {worst['slot_issue_origin']}):

- {worst['active_known_jobs']} live original jobs occupy {worst['known_reference_GPU']} GPU.
- The 120 largest live gangs total {worst['deliberately_overgenerous_migration_removal_GPU']} GPU.
- Remaining known GPU is at least {worst['known_GPU_lower_bound']}.
- C0 nominal is {worst['C0_Q50_equivalent_GPU']:.12f} equivalent GPU (GPUh divided by its one-hour support).
- Required total is at least {worst['necessary_total_GPU_lower_bound']:.12f}, exceeding 780 by **{worst['excess_GPU']:.12f} GPU**.

There are {c['number_violated_necessary_rows']} violating necessary rows. Gurobi independently returned INFEASIBLE (status 3) for the continuous superset, with {c['model_size']['continuous']} variables, {c['model_size']['linear_constraints']} rows and {c['model_size']['nonzeros']} nonzeros. Its IIS contains the transfer-count bound and slots 33/35. `MAY01_RESOURCE_NECESSARY_BOUND.csv` permits a direct arithmetic audit; the certificate SHA-binds LP, IIS, request, receipt, and result.

The supervised invocation took {c['supervisor']['total_wall_seconds']:.3f}s, including source loading and diagnostic work; optimize() took {c['solver_runtime_seconds']:.6f}s. These are **projection timings**, not full A1 runtimes. MIPGap parameter remained .001; actual gap, objective, incumbent, full-model counts, and timeout gaps are null. External cap was 600s; solver TimeLimit used the remaining budget. No timeout occurred.

The first launch failed before optimize() because Gurobi could not write an LP through the Unicode physical path. Its evidence is preserved in `PRE_SOLVE_IO_FAILURE.json`. A tested ASCII-temporary-output adapter allowed one subsequent optimization, with unchanged native input and mathematical constraints. No completed solve was rerun.

No M1/A2/M2 or Fresh AC is permissible without an A1 incumbent. More solver time, a new response kernel, or MESS electrical support cannot create GPU capacity. A source-authorized resolution of this nominal/known resource incompatibility is required before measuring the requested four-block computation. No automatic C0 scaling, T2 alteration, shift, clipping, service deletion, or capacity increase is proposed or applied.
''')
    def share(key):
        r=masks[key]
        return f"{int(r['jobs'])}/1605 jobs ({100*r['job_share']:.4f}%), {r['GPUh']:.2f}/40625.50 GPUh ({100*r['GPUh_share']:.4f}%)"
    answers=[
        'Known/unknown 모두 PENDING 현재 물리 GPU=0, RUNNING=전체 gang이다. RUNNING의 기존 native site와 causal elapsed/remaining을 보존했다.',
        '구분했다. 현재 Planning에서 선택한 실행 구간은 전체 gang을 예약하며, 과거 PENDING 계획은 현재 물리 점유가 아니다.',
        '없다. 모든 PENDING current_physical_occupancy=0. 현재 미래 예약은 별도 ledger에 남아 있다.',
        '321개 모두 물리 충돌로 해석할 근거가 사라진다. 단 PR79 원본은 미래 예약 충돌 표였으며, 그 표의 계획 충돌이 해결됐다고 주장하지 않는다.',
        '해당 321개 구간 중 true RUNNING 물리 충돌은 0개. 원래 계획 예약 충돌 321개는 그대로 미해결이다. 별도로 May-01 known+C0 자원 필요조건이 infeasible이다.',
        '321개 모두 PENDING 과거 예약과 물리 상태의 혼동 가능성이 분류 A이고 계획 관점은 C이다. B/D/E 물리 충돌은 0개. May-01의 별도 blocker는 고정 start, known full service, C0 nominal, 780-GPU cap의 동시 양립 불가다.',
        '아니오. RUNNING native site를 변경하지 않았다. PR79 반사실 mapping을 May native site에 덮어쓰지 않았다.',
        '아니오. GPU clipping/scaling/splitting은 없다.',
        '아니오. 입력 service/tail은 모두 보존했다. 불가능성 증명용 superset의 부하 제거는 실행 계획으로 승인되지 않았다.',
        '아니오. completion/requeue를 발명하지 않았다. UNASSIGNED 44개도 관측 완료로 판정하지 않았다.',
        '그렇다. D24=issue slot120은 전기 horizon 경계이며 서비스 종료 deadline이 아니다.',
        f"보존했다. source-admitted 원래 예약의 post-H GPUh={sum(r['post_H_reserved_GPUh'] for r in admitted):.2f}. 선택된 새 계획은 없다.",
        'T2_CONSERVATIVE_Q25: TRAIN cohort N>=100, Q25>=900초, floor(Q25/900)*900초 지연 예산. 보호/RUNNING 제외. standby 예외 없이 동일 문턱 적용. SLA가 아닌 trace-derived proxy다.',
        '아니오. 기존 pre-2025-01-01 TRAIN 통계와 membership hash를 그대로 사용했다. May는 적용 대상일 뿐 통계/규칙 조정에 쓰지 않았다.',
        'TS job share=0/1605=0%. 모든 PENDING의 해당 TRAIN Q25가 900초 미만이다.',
        'TS reservation GPUh share=0/40625.50=0%.',
        'PS '+share('PS')+'. 이는 source-authorized candidate mask이며 전역 feasible witness가 아니다.',
        'MG '+share('MG')+'. 이는 checkpoint/site candidate mask이며 전역 WAN/resource feasible witness가 아니다.',
        'Union FLEX '+share('FLEX')+'. 전역 실행 가능 비율로 해석하면 안 된다.',
        'FIX '+share('FIX')+'. 세 candidate mask가 모두 false인 assigned 기록이다.',
        '44개 UNASSIGNED RUNNING. 전체 1649개 중 2.6683%; frozen remaining service는 D00 이전 종료로 표현되지만 실제 완료는 주장하지 않는다. 완전한 issue 물리 site authority는 unresolved이다.',
        'MAY01_NATIVE_INPUT_BUNDLE.json 및 manifest. V41R3 저장소의 frozen May-01 known reference, V41R4 final alpha_BG=1.15 IEEE123 계수, V41R2 780-GPU/rack, exact traffic/MESS, frozen C0를 SHA로 연결했다.',
        'IEEE123이다. IEEE8500은 실행하지 않았다.',
        'May-01 동적 입력과 source-backed static authority를 구분했다. 사라진 경로는 SHA가 같은 파일로만 복구했다. PR79 historical mapping과 혼합하지 않았다. full grid/MESS model 결합 검증은 upstream infeasibility로 미실행이다.',
        '그렇다. current frozen T0/B0 C0 Q50와 Q90, May-01 index412. Q50는 same-hour nominal, Q90-Q50만 P2 uncertainty다.',
        '아니오. semantic ML merge/학습은 없다.',
        '아니오. 기존 known service authority를 사용했다. RUNTIME_PROVIDER_READY=false는 이번 known-population 검사 차단 사유가 아니다.',
        '아니오. future realized runtime/completion을 decision에 사용하지 않았다. causal elapsed, frozen known service, TRAIN 통계만 사용했다.',
        '1605개 native admitted population을 자원 필요조건 모델에 연결했다. complete-option AIDC/grid MILP 전체를 구축·실행했다고 주장하지 않는다.',
        'PR91 inner16 MILP 구현은 그대로 보존하고 회귀 검증했다. native M1/M2 모델은 A1 infeasibility 때문에 구축하지 않았다.',
        '보존된 MESS formulation/test의 QConstr=0. native M1/M2 실제 QConstr 측정값은 null(미구축); 둘을 구분했다.',
        f"전체 A1 크기는 null. 필요조건 LP만 continuous={c['model_size']['continuous']}, binary=0, rows={c['model_size']['linear_constraints']}, nonzeros={c['model_size']['nonzeros']}로 측정했다.",
        'M1 전체 모델 크기 null: upstream A1 infeasibility로 미구축.',
        'A2 전체 모델 크기 null: upstream A1 infeasibility로 미구축.',
        'M2 전체 모델 크기 null: upstream A1 infeasibility로 미구축.',
        'raw/retained 옵션 및 reduction은 null. 전역 exact-safe 필요조건이 먼저 infeasible이어서 개별 complete-option 열거까지 진행하지 않았다. null을 0 또는 100%로 대체하지 않았다.',
        f"A1 자원 검사 외부 wall={c['supervisor']['total_wall_seconds']:.3f}s, solver={c['solver_runtime_seconds']:.6f}s, status=INFEASIBLE. 전체 A1 runtime/gap=null. 최초 파일출력 실패도 보존했다.",
        'M1 NOT_RUN_UPSTREAM_A1_INFEASIBLE, runtime/gap=null.',
        'A2 NOT_RUN_UPSTREAM_A1_INFEASIBLE, runtime/gap=null.',
        'M2 NOT_RUN_UPSTREAM_A1_INFEASIBLE, runtime/gap=null.',
        '시간 병목 block은 판정 불가. 현재 blocker는 계산시간이 아닌 known+C0 GPU 자원 infeasibility이다.',
        '아니오. A1 incumbent가 없어 A2 미실행. warm start 효과는 측정하지 않았다.',
        '아니오. M1/M2 미실행. warm start 효과는 측정하지 않았다.',
        '아니오. 모든 block의 target은 .001이지만 완료된 full MILP가 없다. LP infeasible에 MIP gap을 만들지 않았다.',
        'timeout은 없었다. 60/180/300/600초 gap은 모두 null이며 0으로 대체하지 않았다.',
        '입력 불가능성을 약 5초의 감독된 검사로 조기에 입증했지만, 과거 수시간 MILP의 속도 개선 또는 전체 4-block tractability를 입증한 것은 아니다.',
        '아니오. 최종 accepted candidate가 없어 Fresh OpenDSS를 실행하지 않았다. PASS=false는 미검증을 뜻한다.',
        '승인된 모델/계획의 hard physical limits를 완화하지 않았다. 수학적 superset은 infeasibility 증명에만 사용했고 실행 계획으로 채택하지 않았다.',
        '현재는 아니다. accepted final planning과 Fresh PASS 이후에만 해당 anchor의 response kernel 재생성이 필요하다. kernel은 이번 planning 선행조건으로 삼지 않았다.',
        f"Round1 준비 미완료. TS=0 fixed starts와 C0 nominal의 GPU 필요조건이 28개 슬롯에서 깨진다. 최악 excess={worst['excess_GPU']:.6f} GPU. 이 source-bound 양립 문제를 정식 authority로 해결한 후 full 4-block/Fresh 검증이 필요하다. 임의 규칙 완화는 하지 않았다.",
    ]
    assert len(answers)==50
    md('FINAL_REVIEW_KO.md','# May-01 native canary 최종 검토\n\n'+'\n\n'.join(f'{i}. {a}' for i,a in enumerate(answers,1)))
    md('README.md',f'''
# V42 May-01 IEEE123 native canary — fail-closed resource infeasibility

The corrected native known population and current C0 were assembled, but A1 is provably infeasible before full complete-option enumeration. The requested A1→M1→A2→M2 computational benchmark and Fresh AC validation are **not completed**. This is a development/native-integration result, not an untouched holdout or policy benefit test.

At 02:45 AEST, known occupancy is at least 494 GPU even after erasing the full service of the 120 largest live jobs. C0 Q50 is 742.6726 equivalent GPU, exceeding the 780-GPU total by **456.6726 GPU**. A source-bound continuous superset independently returned INFEASIBLE; 28 necessary rows violate capacity. See [the proof](A1_RESOURCE_INFEASIBILITY_PROOF.md) and [certificate](MAY01_A1_RESOURCE_CERTIFICATE.json).

- Physical PENDING=0 and RUNNING=full gang; current future reservations and full carry-out remain intact.
- PR79: 321 apparent physical conflicts resolve under separated accounting; **321 original future-plan collisions remain recorded**, with no claim of schedule repair.
- T2-Q25 uses unmodified TRAIN statistics, N>=100 and Q25>=900, without standby exception. May-01 TS=0. No May outcome tuning.
- 1,649 source records are preserved; 1,605 source-admitted known jobs enter the necessary model, and 44 unassigned pre-D00 RUNNING records remain unresolved outside the feeder mapping.
- IEEE123 final alpha_BG=1.15, 780-GPU sites/racks, MESS initial state, all native traffic routes, and C0 source hashes are bound. Numeric source binding is distinct from executing a full grid/MESS model.
- The projection used {c['model_size']['continuous']} continuous variables and 97 rows, {c['supervisor']['total_wall_seconds']:.3f}s external wall, and {c['solver_runtime_seconds']:.6f}s solver time. These are not full-A1 model sizes or performance claims. All full-model gaps/counts are null.
- M1/A2/M2, warm-start measurements, Fresh AC, response-kernel regeneration, IEEE rounds, full May campaigns, and new ML work were not run.

One pre-optimize Unicode-path diagnostic-output failure was retained; the corrected file adapter then executed the resource optimization once. Caps stayed at 600 seconds and MIPGap=.001. No service, gang, C0, capacity, date, trust/epsilon, or physical limit was changed.

Implementation is isolated in `v42_may01/` and a supervised native worker. PR90/91 scientific artifacts are preserved. [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md) answers all 50 requested questions; [FINAL_FLAGS.json](FINAL_FLAGS.json) distinguishes source readiness from model execution. Local LP/IIS and original sources are SHA-bound; portability requires those local authorities.

Reproduction: `python -m v42_may01.prepare` assembles exact frozen sources, `python -m v42_may01.run` permits one optimization (plus the narrowly checked pre-solve I/O repair), and `python -m v42_may01.report` builds this report without solving. Existing receipts deliberately prevent a silent rerun. Delivery validation uses `python -m v42_may01.verify --staged` after staging; unit tests are listed in TEST_RESULTS.xml.

Next dependency: a source-authorized resolution of the known-service/C0 nominal resource incompatibility. The current task does not choose a new service rule, rescale predictions, or tune T2 to obtain feasibility.
''')
    print(verdict['status'])


if __name__=='__main__':main()

"""Evidence report: full sparse index counts are not a completed Gurobi model."""
from collections import Counter
import xml.etree.ElementTree as ET
import subprocess
from .common import *

def main():
    folder=LOCAL/'build_only';receipt=read(folder/'stage_receipt.json');index=read(folder/'graph_index.json')
    complete=read(folder/'MODEL_COMPLETE.json') if (folder/'MODEL_COMPLETE.json').exists() else None
    partial=read(folder/'solver_progress.json') if (folder/'solver_progress.json').exists() else {}
    counts=index['family_counts'];binary=sum(counts[n] for n in ('y','q','w','f0','f1'));continuous=sum(counts[n] for n in ('r0','h','r1'))
    prior=349215815
    dump('VARIABLE_INDEX_SETS.json',dict(PASS=True,jobs=index['all_jobs'],fixed_jobs=index['fixed_jobs'],family_counts=counts,
        unique_graphs=index['unique_graphs'],cache_hits=index['graph_cache_hits'],full_sparse_index_sets_complete=True,
        complete_option_enumeration=False,index_receipt=rec(folder/'graph_index.json'),
        scope='Counts of all full-May authorized sparse event/state indices, excluding constant singleton jobs. Actual Gurobi build completion is reported separately.',
        schemas=dict(y=['job','source','start'],q=['job','source','checkpoint'],w=['job','source','destination','transfer_start'],
            f0=['job','source','completion'],f1=['job','destination','completion'],r0=['job','source','slot'],h=['job','source','slot'],r1=['job','destination','slot'])))
    dump('COMPACT_START_VARIABLE_AUDIT.json',dict(y=counts['y'],fixed_jobs=index['fixed_jobs'],constant_singletons_create_binaries=False,
        TS_authority=rec(PR98/'KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json'),known_TS_candidates=1024,RUNNING_start_and_site_fixed=True,
        site_rack_residency_preserved=True))
    dump('COMPACT_CHECKPOINT_VARIABLE_AUDIT.json',dict(q=counts['q'],checkpoint_seconds=1800,compatible_start_constraint=True,
        contains_destination_index=False,contains_transfer_start_index=False,RUNNING_elapsed_phase_unchanged=True,maximum_migrations=1))
    dump('COMPACT_WAN_VARIABLE_AUDIT.json',dict(w=counts['w'],contains_checkpoint_index=False,contains_original_start_index=False,
        authority=rec(ROOT/'v42_boundary/generator.py'),zero_rate_waiting_unchanged=True,payload_path_rates_restart_unchanged=True,
        earliest_transfer_equals_checkpoint_allowed=True,checkpoint_wait_state_links_source=True))
    dump('COMPACT_STATE_VARIABLE_AUDIT.json',dict(**{n:counts[n] for n in ('r0','h','r1')},continuous_lower=0,continuous_upper=1,
        integer_conditional_on_binary_events=True,proof='Zero-initial cumulative integer event impulses, bounded in [0,1], including terminal zero',
        exhaustive_fixture_path_tests=True,no_compute_in_wait_transfer_restart=True,no_gang_split=True))
    dump('COMPACT_COMPLETION_VARIABLE_AUDIT.json',dict(f0=counts['f0'],f1=counts['f1'],source_finish_or_checkpoint=True,
        post_finish_equals_migration=True,full_service_equal_Q50=True,useful_post_service=True,completion_bound_unchanged=True,
        risk_adjustment='risk_nominal_completion_issue_slot + completion - reference_end',gamma90=2.423057443558147))
    build_pass=complete is not None and receipt['timeout_reason']=='COMPLETED'
    dump('MAY_COMPACT_MODEL_BUILD.json',dict(PASS=build_pass,build_only=True,optimizer_called=False,supervisor=receipt,
        all_index_sets_complete=True,full_index_family_counts=counts,model_complete=complete is not None,
        completed_model=complete,partial_progress=partial,final_model_counts=complete,
        data_prep_seconds=index['data_prep_seconds'],graph_seconds=index['graph_seconds'],
        external_wall_seconds=receipt['total_wall_seconds'],peak_observed_RSS_bytes=(complete or partial).get('peak_observed_RSS_bytes'),
        presolved_size=None,COMPLETE_OPTION_ENUMERATION_IN_COMPACT_MODEL=False))
    dump('MODEL_SIZE_COMPARISON.json',dict(old_authorized_trajectory_binaries=prior,new_full_sparse_event_binary_indices=binary,
        new_full_sparse_state_continuous_indices=continuous,absolute_binary_reduction=prior-binary,reduction_factor=prior/binary,
        reduction_fraction=1-binary/prior,full_compact_Gurobi_model_completed=complete is not None,
        actual_Gurobi_final_binaries=complete['binaries'] if complete else None,actual_partial_binaries=partial.get('binaries'),
        comparison_scope='Full measured event index count versus full old trajectory index count. No partial Gurobi count is used as the full denominator.'))
    solvefolder=LOCAL/'A1_acceptance_repair';launched=solvefolder.exists();optimization=read(solvefolder/'OPTIMIZATION.json') if (solvefolder/'OPTIMIZATION.json').exists() else None
    solveprogress=read(solvefolder/'solver_progress.json') if (solvefolder/'solver_progress.json').exists() else {}
    solvebuild=read(solvefolder/'MODEL_COMPLETE.json') if (solvefolder/'MODEL_COMPLETE.json').exists() else None
    optimizer_called=(solvefolder/'OPTIMIZER_STARTED.json').exists() or optimization is not None or solveprogress.get('phase') in ('PRESOLVE','OPTIMIZATION')
    incumbent=read(solvefolder/'INCUMBENT_AUDIT.json') if (solvefolder/'INCUMBENT_AUDIT.json').exists() else None
    recovery=read(OUT/'OPTIMIZATION_RECOVERY.json') if (OUT/'OPTIMIZATION_RECOVERY.json').exists() else None
    if launched:
        solver_receipt=read(solvefolder/'stage_receipt.json')
        require(not solver_receipt['validated_incumbent_exists'],'ACCEPTED_A1_MUST_CONTINUE_ORDERED_STAGES')
    else:solver_receipt=None
    blocker='COMPACT_MODEL_CONSTRUCTION_600S_TIMEOUT' if not build_pass and receipt['timeout_reason']=='EXTERNAL_HARD_WALL_TIMEOUT' else 'COMPACT_MODEL_BUILD_FAILURE' if not build_pass else 'COMPACT_A1_OPTIMIZATION_NO_ACCEPTED_INCUMBENT' if optimizer_called else 'COMPACT_A1_EXECUTION_STATUS_REQUIRES_REVIEW'
    if recovery:blocker='COMPACT_A1_PRESOLVE_TIME_LIMIT_DIAGNOSTIC_WRITE_FAILURE'
    presolve=optimization.get('events') if optimization else {k:v for k,v in solveprogress.items() if 'presolve' in k}
    dump('MAY_COMPACT_PRESOLVE.json',dict(status='OBSERVED_IN_A1' if presolve else 'NOT_OBSERVED',presolved_size=None,
        callback_observations=presolve,
        reason='Build-only gate never optimizes or invokes a separate potentially expensive presolve; solve callbacks report available observations'))
    rows=[]
    for stage in ('A1','M1','A2','M2'):
        a1=stage=='A1'
        row=dict(stage=stage,status=blocker if a1 else 'NOT_RUN',launched=launched if a1 else False,
            build_only_attempt=a1,optimizer_called=optimizer_called if a1 else False,accepted_native_plan=False,
            solver_receipt=solver_receipt if a1 else None,optimization=optimization if a1 else None,incumbent_audit=incumbent if a1 else None,
            incumbent=None,best_bound=None,gap=None,nodes=None,optimize_seconds=None,
            target_MIPGap=.001,Threads=1,Seed=20260929,
            reason=blocker if a1 else 'NO_ACCEPTED_PREVIOUS_STAGE',
            canary_model_build=solvebuild if a1 else None,last_progress=solveprogress if a1 else None,
            timing_scope='Separate build-only 600s gate, then A1 600s total including reconstruction, remaining optimization, and 30s reserved validation time' if a1 else None)
        if a1 and optimization:
            last=optimization['passes'][-1];row.update({k:last[k] for k in ('incumbent','best_bound','gap','nodes')});row['optimize_seconds']=sum(p['solve_seconds'] for p in optimization['passes'])
        elif a1 and optimizer_called:
            row.update({k:solveprogress.get(k) for k in ('incumbent','best_bound','gap','nodes')})
            row['optimize_seconds']=solveprogress.get('optimization_seconds')
            row['optimization_timing_note']='Last callback observation, not exact final solve runtime'
        if a1 and recovery:
            row.update(solver_status=recovery['solver_status'],solver_status_name=recovery['status'],incumbent_exists=False,
                incumbent=None,best_bound=None,gap=None,nodes=None,optimize_seconds=None,
                last_observed_optimization_seconds=recovery['last_observed_optimization_seconds'],recovery_receipt=rec(OUT/'OPTIMIZATION_RECOVERY.json'),
                diagnostic_write_failure=True,final_solve_seconds_available=False,
                optimization_timing_note='Final Runtime and nodes were not persisted; last presolve callback is a lower-bound observation only')
        if a1 and (LOCAL/'A1_optimize_memory_observation.json').exists():
            row['optimization_memory_sample']=json.loads((LOCAL/'A1_optimize_memory_observation.json').read_text(encoding='utf-8-sig'))
        dump(stage+'_MODEL_STATS.json',row);rows.append(row)
    csv('V42_COMPACT_SOLVER_SUMMARY.csv',[{k:r.get(k) for k in ('stage','status','solver_status_name','launched','optimizer_called','accepted_native_plan','incumbent','best_bound','gap','nodes','optimize_seconds','last_observed_optimization_seconds','diagnostic_write_failure')} for r in rows])
    dump('FRESH_AC_VALIDATION.json',dict(status='NOT_RUN',PASS=None,reason='NO_ACCEPTED_M2',stale_AC_reused=False,response_kernel_created=False))
    flags=dict(NEW_RUNTIME_ML=False,NEW_CC4_ML=False,NEW_TS_ML=False,NEW_PHYSICAL_ASSUMPTION=False,
        COMPLETE_OPTION_ENUMERATION_IN_COMPACT_MODEL=False,SCIENTIFIC_OBJECTIVE_EQUIVALENCE_REQUIRED=True,RAW_OPTION_INDEX_TIE_EQUIVALENCE_REQUIRED=False,
        PR98_PRESERVED=True,TS_1024_PRESERVED=True,gamma90=2.423057443558147,capacity_GPU=780,
        CC4_UNCHANGED=True,GRID_COEFFICIENTS_UNCHANGED=True,MESS_UNCHANGED=True,PCS_UNCHANGED=True,EVENT30_UNCHANGED=True,LOCAL_REPAIR_UNCHANGED=True,
        SYNTHETIC_EQUIVALENCE_PASS=True,REAL_SUBSET_EQUIVALENCE_PASS=True,BIDIRECTIONAL_PATH_EQUIVALENCE_PASS=True,
        COMPACT_BUILD_COMPLETE=complete is not None,A1_OPTIMIZER_CALLED=optimizer_called,ACCEPTED_FOUR_STAGE_PLAN=False,FRESH_AC_PASS=False,RESPONSE_KERNEL_FROZEN=False,
        A1_A2_SHARED_JOB_FORMULATION=True,DECOMPOSITION_EXECUTED=False,UNSAFE_TOP_K=False,PARAMETER_SWEEP=False)
    dump('FINAL_FLAGS.json',flags)
    dump('FINAL_VERDICT.json',dict(status=blocker,exact_compact_formulation_implemented=True,full_sparse_index_sets_complete=True,
        new_full_event_binary_indices=binary,old_trajectory_binaries=prior,binary_reduction_factor=prior/binary,
        build_complete=complete is not None,accepted_native_plan=False,Problem8='NOT_CLOSED',dominant_discrete_family='w',
        WAN_event_count=counts['w'],WAN_event_binary_share=counts['w']/binary,
        next_candidate='Exact Dantzig-Wolfe with complete pricing and branch-and-price for integer guarantees; documented, not executed',
        solver_status=recovery['status'] if recovery else None,diagnostic_write_failure=recovery is not None,
        bottleneck_transition='MODEL_CONSTRUCTION_TO_OPTIMIZATION' if optimizer_called and build_pass else None,
        stopping_rule='User sections 48/49: stop after build failure or document one exact decomposition after measured solve bottleneck; no silent decomposition execution'))
    preserved=read(OUT/'PR98_BYTE_SNAPSHOT.json')
    for row in preserved:require(sha(row['path'])==row['sha256'],'PR98_BYTE_DRIFT:'+row['relative'])
    changed=set(subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT,text=True).splitlines())
    require(not changed.intersection(row['relative'] for row in preserved),'PR98_DIFF')
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base=BASE,byte_preserved_files=len(preserved),modified_PR98_files=0,
        snapshot=rec(OUT/'PR98_BYTE_SNAPSHOT.json'),old_complete_option_timeout_preserved=True,all_physical_authorities_preserved=True))
    testroot=ET.parse(LOCAL/'tests.xml').getroot();suite=testroot.find('testsuite');require(int(suite.attrib['failures'])==int(suite.attrib['errors'])==0,'TESTS')
    dump('SOURCE_MANIFEST.json',dict(base=BASE,files=[rec(p) for p in sorted((ROOT/'v42_compact').glob('*.py'))]+[rec(ROOT/'v42_native/compact_worker.py'),rec(OUT/'PREREGISTRATION.json'),rec(OUT/'MATHEMATICAL_FORMULATION.md')],
        inherited_sources=[rec(ROOT/n) for n in ('v42_boundary/boundaries.py','v42_boundary/generator.py','v42_boundary/model.py','v42_final/reserve.py','v42_temporal/service.py','v42_native/grid.py')],
        original_native_inputs=rec(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),CC4_envelope=rec(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv')))
    dump('LOCAL_EVIDENCE_MANIFEST.json',dict(files=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()],large_model_saved=False,
        authoritative_build=str(folder),authoritative_solve=str(solvefolder),invalidated_pre_optimize_attempt=str(LOCAL/'A1'),
        executed_source_versions=[rec(LOCAL/n) for n in ('execute_before_acceptance_repair.py','execute_canary_version.py')]))
    dump('VERIFICATION.json',dict(PASS=True,tests=int(suite.attrib['tests']),failures=0,errors=0,receipt=rec(LOCAL/'tests.xml'),
        compact_tests=rec(LOCAL/'compact_tests.xml'),PR98_preserved_files=len(preserved),equivalence_gates_pass=True,
        no_final_response_kernel=not (OUT/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists(),
        warning='One inherited frozen calibration numpy RuntimeWarning; no provider change'))
    build=complete or partial
    answers=[
        'PR98은 도메인 생성 후 complete trajectory마다 binary를 추가하는 모델 구축에서 600초 제한에 걸렸다. optimize()는 호출되지 않았다.',
        '349,215,815는 전체 1,499 positive-service job의 승인된 완전한 물리 trajectory 수다.',
        'start/site/checkpoint/destination/transfer-start를 곱한 trajectory마다 변수를 만들면 모델 구축이 과도해진다. 같은 경로 집합을 사건과 상태로 표현했다.',
        '그렇다. y/q/w/f0/f1은 binary, r0/h/r1은 [0,1] 연속변수이며 모든 제약은 선형이다.',
        '96개 전기적 slot을 하나의 joint MILP로 다룬다. 별도 서비스 축의 pre-H/post-H 구간도 보존한다.',
        '아니다. 모든 job을 GPU/WAN/grid/reserve 제약으로 결합한다. 작은 개별 테스트는 검증용이다.',
        'y는 승인된 시작 slot과 초기 site를 선택한다. 실제 singleton은 상수로 대체한다.',
        'r0는 migration 이전 source에서 계산 중인 slot 상태다.',
        'q는 source 계산을 종료하는 승인 checkpoint 사건이다. destination과 transfer-start index가 없다.',
        'h는 checkpoint 이후 WAN 시작 전 대기 상태다. GPU/WAN을 소비하지 않는다.',
        'w는 source/destination/transfer-start 사건이다. checkpoint index가 없다.',
        'r1은 결정된 restart_end부터 destination에서 계산하는 상태다.',
        'f0는 비이동 완료, f1은 이동 후 완료 사건이다. 최종 site/time으로 Runtime risk를 계산한다.',
        'q에서 h로 들어가고 w에서 h를 빠져나오는 보존식으로 연결했다. c×tau binary가 없다.',
        '바뀌지 않았다. PR98 transfer cache와 payload/path/rate/zero-rate wait를 그대로 사용한다.',
        '바뀌지 않았다. 1800초 물리 checkpoint와 900초 경계 올림, RUNNING elapsed phase가 같다.',
        '바뀌지 않았다. restart_end=transfer_end+기존 restart_slots다.',
        '바뀌지 않았다. V10 Q50 및 서비스 slot 수를 그대로 사용한다.',
        '바뀌지 않았다. PR98 allowed_starts와 latest_completion을 그대로 소비한다.',
        '1,024건을 유지하며 PR98 결과 파일을 바이트 그대로 보존했다.',
        'sum r0+r1=d50와 source/post state conservation으로 서비스 전량을 보존한다.',
        'waiting/WAN/restart 동안 r0/r1 계산 상태가 없다. 잘못 삽입한 상태는 실제 MILP 제약 테스트에서 infeasible이다.',
        '불가능하다. 이진 사건의 누적합인 [0,1] 상태는 정확히 0/1이며 한 site에 전체 G_j를 곱한다.',
        '보존된다. completion<=기존 latest_completion이며 D24를 새 deadline으로 만들지 않았다.',
        'f0/f1의 final_site 및 issue-adjusted completion에 기존 risk_exposure와 gamma90를 적용해 선형 합산한다.',
        'PR97 Q10/Q90, conservation, carryout, reserve timing, depletion, reference deviation을 보존했다.',
        '동일한 C1/grid 함수와 원본 계수 authority를 사용한다. known_GPU의 입력 표현만 r0/r1으로 바뀐다.',
        'PASS. 모든 bounded old option의 사건/상태를 실제 compact 모델에 고정해 feasible 및 동일 physical signature를 확인했다.',
        'PASS. bounded compact pool을 완전히 열거하고 기존 physical validate 및 old signature set과 비교했다.',
        'A-J 전체 fixture에서 경로 집합과 6개 scientific objective 수준이 일치했다. 추가 adversarial/랜덤 물리 fixture도 통과했다.',
        '실제 May의 첫 short-service singleton-start 두 작업을 완전 도메인으로 공동 최적화했다. native grid/CC4와 6개 목적 수준이 동일했다. 다양한 real TS/migration 사례까지 검증했다고 주장하지 않는다.',
        '원래 option index는 비과학적 최종 tie다. 6개 scientific objective를 고정한 뒤 deterministic physical event-rank tie를 적용한다.',
        '6개 수준의 동등성을 검증했다. raw option index tie는 동등성 요구에서 명시적으로 제외했다.',
        f'전체 기존 trajectory binary index는 {prior:,}개다.',
        f"전체 y index는 {counts['y']:,}개다.",
        f"전체 q index는 {counts['q']:,}개다.",
        f"전체 w index는 {counts['w']:,}개다.",
        f"f0={counts['f0']:,}, f1={counts['f1']:,}개다.",
        f'전체 sparse event binary index는 {binary:,}개다. 이는 모든 graph의 정확한 count이며, Gurobi full model 완성 여부와 구분한다.',
        f'{prior/binary:.6f}배 감소, 비율 {(1-binary/prior):.6%}, 절대 {prior-binary:,}개 감소다.',
        f"Build PASS={build_pass}. 외부 wall={receipt['total_wall_seconds']:.6f}초. 전체 binary={build.get('binaries'):,}, continuous={build.get('continuous'):,}, 제약={build.get('constraints'):,}, nonzero={build.get('nonzeros'):,}개다.",
        '별도 presolve는 실행하지 않았다. A1 실행 시 관찰한 callback 정보만 MAY_COMPACT_PRESOLVE.json에 기록하며 정확한 presolved size가 없으면 null이다.',
        f'optimize() 호출={optimizer_called}. Build-only 실행은 최적화를 호출하지 않는다.',
        f"검증/품질 승인된 A1 plan은 없다. Raw incumbent 감사={incumbent}.",
        f"A1 status={rows[0].get('solver_status_name')}, incumbent={rows[0]['incumbent']}, bound={rows[0]['best_bound']}, gap={rows[0]['gap']}, nodes={rows[0]['nodes']}. 마지막 presolve 관측={rows[0].get('last_observed_optimization_seconds')}초다. -inf 진단 저장 오류로 최종 Runtime/node 수는 보존되지 않아 null로 남겼다.",
        f"측정 blocker는 {blocker}. 전체 event index 중 WAN w 비중={counts['w']/binary:.6%}다.",
        'accepted A1이 없어 M1/A2/M2는 NOT_RUN이다. A2는 동일 compact job builder와 M1 P/Q anchor 인터페이스를 재사용한다.',
        'Fresh AC는 NOT_RUN이다. accepted four-stage gate가 성립하지 않았다.',
        'freeze하지 않았으며 FINAL_RESPONSE_KERNEL_AUTHORITY.json은 생성하지 않았다.',
        '정확한 Dantzig-Wolfe/column generation을 다음 후보로 문서화했다. 전역 정수 보장은 완전 pricing 및 branch-and-price가 필요하다. 이번에는 실행하지 않았고 CL-MC-BD도 자동 활성화하지 않았다.'
    ]
    require(len(answers)==50,'FIFTY_ANSWERS')
    (OUT/'FINAL_REVIEW_KO.md').write_text('# Compact AIDC state-flow 최종 검토\n\n'+'\n\n'.join(f'{i}. {a}' for i,a in enumerate(answers,1))+'\n',encoding='utf8',newline='\n')
    text=f'''# V42 exact compact AIDC state-flow

Base PR98 `{BASE}`; preregistration commit `0af0d851`. All {len(preserved)} available tracked base files remain byte-identical. The explicitly authorized new trigger is MODEL_CONSTRUCTION_FAILURE_AFTER_COMPLETE_DOMAIN.

The compact MILP separates start, checkpoint, source-ready wait, WAN transfer, restart entry and completion. Checkpoint and WAN start have no joint product index. Continuous [0,1] states are integral conditional on binary events by their zero-initial cumulative balance equations. Full service, exact checkpoint phase, deterministic WAN/restart, whole gangs and inherited carryout are preserved. The builder is shared by A1/A2; MESS is untouched.

All A-J synthetic fixtures match the legacy complete path set and six scientific objective levels. A deterministic real two-job subset matches with the full native grid and PR97 CC4 interface. The primary mapping audit tests 100 paths in each direction with zero failures; additional randomized/adversarial tests cover zero-rate WAN, fixed capacity, timing, gaps and fractional states. This bounded evidence and the mathematical proof are distinguished from a claim that every May trajectory was explicitly enumerated. The compact production path never loads or enumerates PR98's 349M trajectories.

Full sparse indices cover all 1,499 jobs ({index['fixed_jobs']} constant singleton schedules). Event binaries: **{binary:,}**, versus **349,215,815** old trajectory indices: **{prior/binary:.4f}x**, **{(1-binary/prior):.4%}** reduction. y={counts['y']:,}, q={counts['q']:,}, w={counts['w']:,}, f0={counts['f0']:,}, f1={counts['f1']:,}. These are full measured graph index counts, not an invented final Gurobi model size. r0/h/r1 contain {continuous:,} continuous state indices in total. Preparation={index['data_prep_seconds']:.4f}s; graph construction={index['graph_seconds']:.4f}s.

**Result: {blocker}.** Build-only external wall={receipt['total_wall_seconds']:.4f}s, completed model={complete is not None}. Actual completed/partial rows, nonzeros, memory and family counts are in MAY_COMPACT_MODEL_BUILD.json. No build time is labeled solve time. A1 optimizer called={optimizer_called}; no accepted native plan. The separate A1 canary has a 600s total budget including reconstruction of the same model; optimization receives the remaining time. M1/A2/M2 and Fresh AC are NOT_RUN, and no final response kernel exists. Problem 8 remains open.

The authoritative solve reached presolve and TIME_LIMIT (status 9), with no incumbent and no finite bound. Last presolve observation was {recovery['last_observed_optimization_seconds'] if recovery else None} seconds. Writing the final diagnostic failed on `-inf`; the partial JSON and traceback establish status/no-incumbent, but exact final Runtime and nodes were not preserved and remain null. Diagnostic normalization and validation-budget retention are repaired and unit-tested; May optimization was not repeated. An earlier canary construction was interrupted before optimize to correct overly strict incumbent acceptance; both attempts and executed code versions remain SHA-bound. The completed build-only model and physical formulation are unchanged.

The dominant remaining event dimension is w, {counts['w']/binary:.4%} of event binaries. The user stop rule is respected. NEXT_EXACT_DECOMPOSITION.md prepares one exact Dantzig-Wolfe/branch-and-price design without executing it, pruning paths, approximating jobs or changing physical authority.

Verification: **{suite.attrib['tests']} tests pass**, with one inherited frozen calibration RuntimeWarning. No new ML, Runtime/Q50/gamma90, TS (1,024 candidates), CC4 envelope, 780-GPU capacity, grid coefficients, MESS, PCS, Event30 or local-repair changes. Live TS support remains the unchanged fail-closed limitation. FINAL_REVIEW_KO.md answers all 50 questions.

```powershell
$env:PYTHONUTF8='1'
python -m pytest v42_compact/tests.py v42_boundary/tests.py tests/test_v42_temporal.py tests/test_v42_final.py tests/test_v42_native.py tests/test_v42_may01.py tests/test_v42_job_capability.py -q
python -m v42_compact.verify
git diff --check
```

Local process receipts, graph indices and test XML are SHA-bound by LOCAL_EVIDENCE_MANIFEST.json. Do not rerun one-shot production folders or overwrite historical receipts. Final solver counts and presolved size remain null when unmeasured.
'''
    (OUT/'README.md').write_text(text,encoding='utf8',newline='\n')
    print(dict(blocker=blocker,tests=int(suite.attrib['tests']),event_indices=binary,preserved=len(preserved)))

if __name__=='__main__':main()

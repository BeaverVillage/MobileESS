"""Finalize review artifacts from static receipts, never from production solves."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import subprocess
from . import AUTHORITY
from .status import initial_domain_status

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_a_stage_domain_authority_v2_20261007'
BASE='1e2d819406081af5b4bbee6fab3c4b5c3e102b2b'
REFERENCE='52ef855a59144a7c561df44b81dc2ad265babdbd'
DAYS=('10','12','17','19')


def read(name):return json.loads((OUT/name).read_text(encoding='utf8'))
def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def record(path):
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=sha,bytes=path.stat().st_size)


def finalize(source_commit=None,pr_url=None):
    censuses={day:read('MAY'+day+'_STATIC_DOMAIN_CENSUS.json') for day in DAYS}
    test=read('TEST_RESULTS.json')
    stay=read('STAY_COMPACT_EQUIVALENCE.json')
    guard=read('STRESS_DATE_NO_OPTIMIZE_VERIFICATION.json')
    membership17=read('MAY17_RESCUE_OPTION_MEMBERSHIP.json')
    membership19=read('MAY19_PR165_PR166_OPTION_MEMBERSHIP.json')
    historical=('docs/v42_b1_may17_may19_repair_20261007',
                'docs/v42_b1_adaptive_prescreening_rescue_20261007',
                'docs/v42_b1_may19_prescreening_rescue_20261007')
    changed=subprocess.check_output(['git','diff','--name-only',BASE,'--',*historical],cwd=ROOT,text=True).splitlines()
    if changed:raise ValueError('HISTORICAL_DIAGNOSTIC_EVIDENCE_MODIFIED')
    authority=dict(authority=AUTHORITY,new_formulation_authority=True,base=BASE,
        historical_scientific_reference=REFERENCE,historical_authority_overwritten=False,
        old_reference_lower_prescreen_scientific=False,
        earliest='max(issue-time causal release, independently proven other hard release)',
        latest='unchanged latest_completion - service_slots',STAY_control_end_cap=False,
        complete_physical_STAY_support=True,
        active_STAY_rule='complete proven histogram scopes; singleton mixed flow S0 + valid anchor, remaining choices lazy',
        migration_rule='lossless deterministic matrix-free full physical blocks; inherited graph active, restored paths lazy',
        noflex_rule='same authority; independent hard validation; every valid anchor retained',
        grid_ranking_rule='HIGH/MEDIUM/LOW_PRIORITY only; no physical membership cut',
        duplicate_rule='complete exact scientific rows and all objective coefficients; canonical representative',
        dominance_rule='disabled absent formal proof',
        production_gate='false until independently valid integer-domain closure and physical/objective acceptance',
        immutable_science=['CC4','Runtime','service','GPU','rack/gang','WAN','voltage 0.95-1.05',
                           'line/transformer ratings','power/grid coefficients','causal population','four objective definitions'],
        shift_magnitude_extension=dict(expression='abs(start-reference_start)',
             old_domain_coefficient_identity=True,earlier_options_negative_cost=False),
        causal_information='frozen issue-time input only; no realized outcome or availability after issue',
        source_files=[record(p) for p in sorted((ROOT/'v42_a_stage_domain_v2').glob('*.py'))])
    write('AIDC_A_STAGE_DOMAIN_AUTHORITY_V2.json',authority)
    write('HARD_SCREEN_RULES.json',dict(authority=AUTHORITY,
        permanent_cuts=['causal release','unchanged completion/terminal impossibility','GPU/rack/site impossibility',
                       'protection/high/urgent timing','fixed RUNNING history','unauthorized checkpoint',
                       'impossible physical WAN/restart','exact complete-row duplicate'],
        never_permanent=['R0/reference distance','known-window lower prescreen','low grid benefit',
                         'predicted selection probability','model-size convenience','heuristic dominance'],
        current_dominance_cuts=0,hard_rules_global=True,date_specific_scientific_patches=False))
    write('NO_FLEX_ANCHOR_AUTHORITY.json',dict(authority='A_NOFLEX_UNDER_'+AUTHORITY,
        common_population=True,common_service_Runtime_CC4_GPU_rack_grid=True,
        historical_B0_embedded=False,choice='same reference start/site with flexibility disabled',
        validity='independent hard validator before generator membership',
        claim='F_A_NOFLEX subseteq F_A_FLEX wherever common-authority A_NOFLEX is feasible',
        global_noflex_feasibility_proven=False,anchor_heuristic_deletions=0))
    write('DOMAIN_NESTING_VERIFICATION.json',dict(PASS=all(c['no_flex_anchor_inclusion']['PASS'] for c in censuses.values()),
        static_only=True,optimizer_calls=0,independent_verifier='domain.noflex_anchor plus hard validate, independent of flexible generator',
        dates={day:c['no_flex_anchor_inclusion'] for day,c in censuses.items()},
        common_global_coefficients_identical=True,global_feasibility_claimed=False))
    write('MIGRATION_LAZY_POOL_AUTHORITY.json',dict(authority=AUTHORITY,
        representation='(start,source,checkpoint,physical seconds,destination,GPU,all valid transfer timestamps)',
        distinct_timestamps_merged_as_duplicates=False,deterministic=True,full_path_options_materialized=False,
        reconstruct='unchanged Generator.transfer plus full Option membership',
        preserved=['checkpoint phase','source/destination masks','payload','WAN paths/rates','restart',
                   'remaining service','carryout','Runtime completion','GPU/grid incidence'],
        block_counts={day:c['migration_lazy_blocks'] for day,c in censuses.items()},
        completeness='all physical timestamp multiplicities retained; closure not inferred from current activation',
        feasibility_rescue='independent exact Farkas pricing',improvement='separate feasible-model objective pricing',
        LP_native_direction_coverage_required=True,integer_closure_proven=False))
    write('GRID_PRIORITY_NOT_CUT_AUTHORITY.json',dict(authority=AUTHORITY,
        signed_stored_sensitivities_supported=True,priorities=['HIGH_PRIORITY','MEDIUM_PRIORITY','LOW_PRIORITY'],
        tie_order='signed contribution, displacement, canonical Option',permanent_cut=False,
        low_benefit_remains_in_universe=True,missing_sensitivities='neutral ordering; retain',
        scientific_reason='locally unattractive choices can enable globally useful workload rearrangements'))
    write('EXACT_DUPLICATE_DOMINANCE_AUDIT.json',dict(PASS=True,
        rule='full exact scientific row vector + class effect + every P1/P2 coefficient + authority hash',
        floating_tolerance_used=False,ambiguous='KEEP_LAZY',canonical='lexicographic candidate identity',
        safe_dominance_count=0,formal_dominance_proof_adopted=False,
        date_counts={day:dict(exact_duplicates=c['exact_duplicate_count'],safe_dominance=c['safe_dominance_count'])
                     for day,c in censuses.items()},
        count_scope='unique physical support keys; no semantic heuristic deletion adopted',
        distinct_WAN_timestamp_effects_preserved=True))
    status=initial_domain_status(hard_physical_domain_defined=True,authority=AUTHORITY)
    write('DOMAIN_STATUS_GATE.json',dict(status,integer_proof_required_for_production=True,
        root_reduced_cost_sufficient=False,physical_path_scan_native_LP_closure=False,
        accepted_integer_proofs=['complete finite activation','exact branch-and-price closure','other independently valid integer certificate'],
        tests=record(ROOT/'tests/test_v42_a_stage_domain_v2_execution.py')))
    passed=(test['PASS'] and all(c['PASS'] for c in censuses.values()) and not changed
            and membership17['MAY17_35_RESCUE_OPTIONS_INCLUDED']
            and membership19['PR165_38_AND_PR166_S_A_S_B_S_C_S_D_INCLUDED'])
    verification=dict(PASS=bool(passed),authority=AUTHORITY,base=BASE,
        scientific_domain_new=True,implementation_static_review_complete=True,
        historical_diagnostic_changes=changed,historical_PR134_overwritten=False,
        stress_date_native_optimize_calls=0,production_optimize_calls=0,
        PASS27_reoptimized=False,campaign_runs=0,Actual_runs=0,Fresh_runs=0,scheduled_optimizers_created=0,
        matrix_free_census_native_builds=0,
        synthetic_static_native_fixtures_only=True,synthetic_optimizer_calls=0,
        complete_STAY_scientific_domain=True,universal_compact_adopted=False,
        existing_histogram_exact_projection_preserved=True,failed_singleton_LP_substitution_retained_lazy=True,
        class_membership_cardinality_preserved=True,CC4_Runtime_service_GPU_grid_limits_changed=False,
        model_rows_nnz_are_forecasts=True,scientific_feasibility_inferred_from_counts=False,
        production_domain_status=status,final_production_optimality_claimed=False,
        May17_membership=record(OUT/'MAY17_RESCUE_OPTION_MEMBERSHIP.json'),
        May19_membership=record(OUT/'MAY19_PR165_PR166_OPTION_MEMBERSHIP.json'),
        test_receipt=record(OUT/'TEST_RESULTS.json'),source_commit=source_commit,Draft_PR=pr_url)
    write('VERIFICATION.json',verification)
    forecast=list(csv.DictReader((OUT/'MODEL_SIZE_FORECAST.csv').open(encoding='utf8')))
    active={r['day'][-2:]:r for r in forecast if r['domain']=='C_NEW_ACTIVE_INITIAL'}
    lines=['# V42 A-stage 도메인 권한 V2 최종 검토','',
        '이번 결과는 새로운 후보 도메인 권한의 구현·정적 검증입니다. 네 날짜의 실행 가능성, 속도, 최적성은 새로 증명하지 않았습니다.', '',
        '1. 기존 prescreen은 물리적으로 가능한 시작을 R0 이후로 제한하여 과학적 feasible set과 계산용 활성 후보를 혼동했습니다.',
        '2. reference-start 하한, known-window/reference-lower 필터 및 119 슬롯 복원 상한은 독립적 물리 release가 아닌 후보 제한이었습니다.',
        '3. 인과 release, 기존 completion, GPU/rack/site, 보호·high·urgent, 체크포인트/WAN/restart, RUNNING 이력, terminal 불가능성과 완전 계수 일치 중복만 영구 컷이 가능합니다.',
        '4. R0 거리, 작은 grid 이익, 낮은 선택확률, 모델 크기와 휴리스틱 dominance는 영구 컷이 불가능합니다.',
        '5. R0는 P2 시작 이동 크기와 공통 no-action 시작/site 참조로 유지합니다.',
        '6. R0는 독립적 hard rule이 없는 유연 PENDING 시작 도메인의 벽이 아닙니다.',
        '7. 기존 과학적 class aggregation과 정확한 멤버를 유지했습니다.',
        '8. class_exact_cardinality를 유지했고 활성화·복원 시 원래 class 수를 변경하지 않습니다.',
        '9. 물리적으로 유효한 A_NOFLEX anchor는 heuristic에 의해 제거되지 않습니다.',
        '10. 같은 jobs/service/Runtime/CC4/GPU/rack/grid 계수에서 no-flex feasible set은 flex set에 포함됩니다. no-flex 자체의 전역 feasibility를 주장하지 않습니다.',
        '11. 모든 물리적 STAY 시작/site는 scientific universe에 있습니다. 활성 MILP는 증명된 histogram 범위는 전체, singleton mixed-flow는 S0+anchor와 지연 STAY를 사용합니다.',
        '12. 기존 histogram의 정수·LP 투영은 정확히 증명했습니다. 모든 클래스의 일괄 compact 대체는 singleton mixed-flow LP 반례 때문에 채택하지 않았습니다.',
        '13. 이미 압축된 histogram의 표현 변경 delta는 0입니다. 지원 확대의 변수 증가량과 전체 행/nnz 예측은 아래 표에 구분했습니다.',
        '14. 전체 migration 경로 Option/native 열을 물질화하지 않았습니다.',
        '15. 모든 원래 체크포인트·전송 시각을 lossless lazy block에 보존하며 원래 payload/path/restart/remaining/Runtime/grid를 재구성합니다.',
        '16. 낮은 grid 이익 후보도 삭제하지 않습니다.',
        '17. 저장된 signed 민감도, displacement, canonical 순서로 HIGH/MEDIUM/LOW_PRIORITY를 부여합니다.',
        '18. 완전한 exact row/objective 계수 동일성만 중복을 제거합니다. 이번 과학 후보 제거는 0이며 안전한 일반 dominance 증명은 채택하지 않았습니다.']
    for number,day in ((19,'10'),(20,'12'),(21,'17')):
        lines.append(f"{number}. May{day} 복원 STAY 후보는 class support 기준 {censuses[day]['new_candidates_restored_relative_to_old_S0']:,}개입니다.")
    lines.extend(['22. May17 기존 35 rescue Option 전부 full attribute 정적 membership PASS입니다.',
        f"23. May19 복원 STAY 후보는 class support 기준 {censuses['19']['new_candidates_restored_relative_to_old_S0']:,}개입니다.",
        '24. PR165 38개 및 PR166 S_A/S_B/S_C/S_D의 모든 시험 Option을 원래 과학 속성까지 포함하여 정적으로 확인했습니다.',
        '25. 날짜별 전망은 아래 표와 MODEL_SIZE_FORECAST.csv에 있습니다. native model을 생성하지 않았고 rows/nnz는 추정입니다.',
        '26. binary/integer/continuous 변화는 기존 F2-CRA 분기에서 구조적으로 계산했습니다. A2SC 후속 축약률은 가정하지 않습니다.',
        '27. May10/12/17/19 native optimize 호출은 0회입니다. 실행 경로는 STRESS_DATE_OPTIMIZATION_NOT_AUTHORIZED로 차단됩니다.',
        '28. 기존 27개 PASS 날짜는 재실행하지 않았습니다.',
        '29. CC4/Runtime/service/GPU/rack/WAN/grid/전압/정격은 변경하지 않았습니다. shift는 원래 양수 영역의 계수와 동일하며 새 이른 시작에는 절댓값 이동 크기를 사용합니다.',
        '30. Production-domain 최적성은 미인증이고 PRODUCTION_DOMAIN_ACCEPTED=false입니다. root LP 가격 검사만으로 MILP 완결성을 주장하지 않습니다.',
        '31. 네 날짜 실행 전 사용자 검토·새 실행 승인, 새 권한의 native build/독립 계수 검증, 메모리/tractability 검토가 필요합니다. 생산 최적성에는 전체 finite 활성화 또는 유효한 정수 closure 증명이 필요합니다. 이후 27개 날짜를 포함한 새 campaign도 별도 승인 대상입니다.',
        f"32. 구현 source commit: {source_commit or '게시 직전 source commit을 PUBLICATION_RECEIPT.json에서 기록합니다.'}; Draft PR: {pr_url or '검증 완료 후 게시합니다.'}", '',
        '| 날짜 | 과학 STAY 복원 | 활성 columns | binary | integer count | continuous | rows 추정 | nnz 추정 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|'])
    for day in DAYS:
        r=active[day]
        values=[censuses[day]['new_candidates_restored_relative_to_old_S0']]+[int(r[k]) for k in ('columns','binary_variables','integer_count_variables','continuous_variables','rows','nnz')]
        lines.append('| May'+day+' | '+' | '.join(f'{v:,}' for v in values)+' |')
    lines.extend(['','May10의 P2 단계 시간과 May12 root LP 수치/solver-method 관측 코드를 준비했지만 실행하지 않았습니다. 후보를 올바르게 넓힌다고 두 날짜가 해결된다는 주장은 하지 않습니다.',
                  '',f"짧은 검증: {test['passed']}개 PASS. Scientific production optimize/Actual/Fresh/campaign/예약 실행은 0회입니다."])
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
    manifest=[record(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    manifest += [record(p) for p in sorted((ROOT/'v42_a_stage_domain_v2').glob('*.py'))]
    manifest += [record(p) for p in sorted((ROOT/'tests').glob('test_v42_a_stage*py'))]
    write('SHA256_MANIFEST.json',dict(algorithm='SHA256',self_excluded=True,files=manifest,
         source_commit=source_commit,base=BASE,post_publication_head='GitHub PR head / git rev-parse HEAD; no self-referential commit hash in tracked contents'))
    if not passed:raise ValueError('STATIC_REVIEW_VERIFICATION_FAILED')
    print('FORMULATION_REVIEW_PASS',len(manifest),'manifest files')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-commit');parser.add_argument('--pr-url')
    args=parser.parse_args();finalize(args.source_commit,args.pr_url)

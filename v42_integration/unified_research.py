"""Reviewed PR snapshot; measured experiments keep their original lineage."""
import json
import subprocess
import xml.etree.ElementTree as ET
from .unified_contract import REPORT, load_contracts, digest, file_sha
from .m_engine import _write, file_record


def read(name, default=None):
    p = REPORT/name
    return json.loads(p.read_text(encoding='utf8')) if p.exists() else default


def regression():
    p = REPORT/'UNIFIED_REGRESSION_TESTS.xml'
    if not p.exists():
        return dict(status='NOT_RUN', reason='REGRESSION_XML_MISSING')
    cases = list(ET.parse(p).getroot().iter('testcase'))
    failed = [c.get('classname', '')+'.'+c.get('name', '') for c in cases
              if c.find('failure') is not None or c.find('error') is not None]
    skipped = [c.get('classname', '')+'.'+c.get('name', '') for c in cases if c.find('skipped') is not None]
    result = dict(status='PASS' if cases and not failed else 'FAIL', total=len(cases),
        passed=len(cases)-len(failed)-len(skipped), skipped=len(skipped), failed=failed,
        skipped_tests=skipped, actual_native_calls=0, profile='EXPLICIT_NATIVE0_SOLVER_GUARD',
        skipped_not_claimed_PASS=True, junit=file_record(p))
    _write(REPORT/'UNIFIED_REGRESSION_RESULTS.json', result)
    return result


def final_report():
    common = load_contracts()
    b, r = common['bindings'], regression()
    measured = read('AIDC_SITE_ONLY_VALIDATION_RESULT.json', {})
    ledger = read('UNIFIED_NATIVE_RUNTIME_LEDGER.json', {})
    ac = read('PR230_FRESH16_SUMMARY.json', {})
    same_known = measured.get('same_actual_Known_execution') is True
    gate = dict(bindings=b, snapshot='USER_STOPPED_RESEARCH_FOR_PR_REVIEW',
        active_scope='DDAY_KNOWN_BASELINE_UNKNOWN_SITE_ONLY_AND_MESS_S1_EXACT_COMPRESSION',
        Native0_regression=r['status'], physical='IEEE123_ORIGINAL_11_SVR_AND_ORIGINAL_LIMITS',
        AIDC_real_prefix_slots=measured.get('same_input', {}).get('slots'),
        AIDC_actual_Known_execution_identical=same_known,
        AIDC_actual_changed_UIDs=measured.get('changed_executed_site_UIDs'),
        AIDC_changed_actual_prefix_GPUh=measured.get('changed_actual_prefix_compute_GPUh'),
        AIDC_performance_improvement='NOT_DEMONSTRATED',
        AIDC_comparison=measured.get('comparison', []),
        AIDC_historical_A1_executed=False, new_Known_A1_Heavy='HOLD',
        Actual_global_MILP_calls=0, CC4_anonymous_hard_GPU=0,
        source_initial_state_scope='FROZEN_DDAY_MODEL_ASSUMPTION_NOT_LIVE_KESTREL_QUEUE',
        MESS_full96_integer_and_LP_equivalence='MEASURED_PASS',
        MESS_same_model_native_calls=2, MESS_solver_speedup='NOT_DEMONSTRATED',
        MESS_vectorized_proof_kernel='MEASURED_FULL96_PASS',
        MESS_original4x24_global_gap_certified=False,
        cached_sparse_model_build='PRESERVED_UNVALIDATED_PROTOTYPE_OUTSIDE_PR_SOURCE',
        four_stage_heavy='HOLD_NOT_RUN', S2_to_S7='HOLD_NOT_RUN',
        time_shifting='DORMANT_USER_HOLD', runtime_repair='DORMANT_USER_HOLD',
        checkpoint_migration='DORMANT_USER_HOLD',
        new_four_hour_Actual='NOT_RUN', new_Full96_Actual='NOT_RUN', new_Fresh_AC='NOT_RUN',
        integrated_PASS=False, historical_PR230_Fresh16=ac.get('status', 'NOT_RUN'),
        historical_Fresh16_certificate_transferred=False,
        freeze='REVIEWABLE_CODE_AND_SCOPED_DIAGNOSTICS',
        paper_performance_claim_authorized=False, campaign_HOLD=True, IEEE8500_run=False)
    _write(REPORT/'UNIFIED_VALIDATION_GATE.json', gate)
    _write(REPORT/'A1_M1_A2_M2_HANDOFF_AUDIT.json', dict(bindings=b,
        architecture='ORIGINAL_COORDINATOR_PLUS_COMMON_LINEAGE_CHECKS',
        stages=['A1', 'M1', 'A2', 'M2'],
        interface_regression='PASS' if r['status']=='PASS' else 'NOT_CERTIFIED',
        real_four_stage_execution='USER_HOLD_NOT_RUN', integrated_PASS=False,
        reason='USER_STOPPED_RESEARCH;STANDALONE_CERTIFICATES_REMAIN_DISTINCT',
        old_Known_anchor_execution_authority=False, historical_certificates_transferred=False))
    audit = read('SINGLE_BRANCH_PARALLEL_EXECUTION_AUDIT.json', {})
    audit.update(final_bindings=b, shared_contract_file_shas=common['contract_file_shas'],
        numerical_case_equality_across_historical_experiments=False,
        current_scope='COMMON_CONTRACT;EACH_RESULT_RETAINS_ORIGINAL_NUMERIC_CASE',
        contract_revision_audit=file_record(REPORT/'CONTRACT_REVISION_AUDIT.json'),
        integrated_PASS=False, new_branch_or_PR_created_for_snapshot=False)
    _write(REPORT/'SINGLE_BRANCH_PARALLEL_EXECUTION_AUDIT.json', audit)
    ledger['linked_cumulative_projections'] = [dict(path=p['path'], historical_seconds=p['used_seconds'],
        new_conservative_seconds=ledger.get('conservative_solve_seconds', 0),
        cumulative_seconds=p['used_seconds']+ledger.get('conservative_solve_seconds', 0),
        limit_seconds=p['limit_seconds']) for p in ledger.get('historical_ledgers', [])]
    ledger.update(campaign_HOLD=True, research_execution='USER_STOPPED_FOR_PR', usage_reset=False)
    _write(REPORT/'UNIFIED_NATIVE_RUNTIME_LEDGER.json', ledger)
    _write(REPORT/'COMMON_GRID_PQ_CONTRIBUTION_AUDIT.json', dict(bindings=b,
        net_load='ORIGINAL_C1_AIDC_CONSUMPTION_MINUS_SIGNED_MESS_INJECTION_ONCE_EACH',
        AIDC='OBSERVED_JOB_OCCUPANCY', MESS='ORIGINAL_DISTINCT_PCS_CONTROLS',
        inactive_MESS_Q='FULL_FOUR_VEHICLE_REPLAY_PRESERVED',
        same_numeric_AIDC_MESS_case_certified=False, original_integrated_physics='NOT_RUN',
        AIDC_result=file_record(REPORT/'AIDC_SITE_ONLY_VALIDATION_RESULT.json'),
        MESS_result=file_record(REPORT/'MESS_EXACT_COMPRESSION_BENCHMARK.json')))
    answers = [
        'IEEE123, 12 AIDC/780 GPU, 기존11 SVR·7 RegControl·LDC·정격·전압 한계를 보존했다.',
        'PR230 슬롯10·12의 signed affine 전압 위반은 동일P/Q의 원본AUTO Fresh16에서 재현되지 않았다. 중앙secant/LDC 구간을 큰 편차에 적용한 근사이며 개별probe tap상태는 저장되지 않았다.',
        'PR223 Fresh96는 다른A2/M2·전력trace이다. 과거 계획이나 현재사이트 배치 실험으로 인증을 이전하지 않았다.',
        '단일checkout·단일브랜치에서 AIDC/MESS를 병렬개발했다. Heavy는 Supervisor가 하나씩 실행했다.',
        '공통계약과 실험별 Source/Case/Anchor를 분리했다. 과거 실험을 최신Case로 재표기하지 않았다.',
        '과거886 Pending명령을 소급 실행하지 않았다. 현재D-day의 결정적Known 우선규칙을 사용했고 C0/C1의1546개Known 상태행·신규86개시작이 동일했다. 독립진단 기준이며 A1최적성 인증이 아니다.',
        '60분Time-shifting은 비활성이다. 기존계약/코드를 보존했고 현재 비교의 추가지연은0이다.',
        '실제2시간 재생에서 Unknown신규시작·변경UID·변경GPUh가 모두0이다. 사이트 선택에 따른 성능개선은 입증되지 않았다.',
        'C1은 권한이 열린 현재이벤트에서 후보추가P/Q를 원본C1로 계산하고 모든선로/상의 예상최대부하율을 최소화한다. GPU/Rack·확정예약·원래계통검사를 적용한다.',
        'CC4 익명Q50/Q90는 GPU확정점유가 아니다. Running·Known예약·확정Unknown예약을 UID별union으로 보호했다.',
        '실제완료 관측 전 Running을 종료하지 않는다. Runtime상한이 없으므로 Unknown을 Known미래예약 앞에 안전하다고 단정하지 않는다.',
        '새Runtime Repair/Backfill 개발은 중단했다. 원본Event Replay의 실제Runtime·완료·GPU release를 유지했다.',
        'Checkpoint Migration은 비활성이다. 기존연구코드·결과는 보존한다.',
        'MESS는 원래24개 위치/도로/Bus/Phase를 사용한다. S1은 원래MESS01/03과5개 후보지다.',
        'S1은7711변수·836244행·23258846NNZ이다. 계통814560행(97.407%)은 차량/후보지 축소에도96×8485행으로 생성된다.',
        '슬롯당 전압838×2·변압기전류153·변압기kVA153×16·선로263×16이다. 정확한중복/동일LHS/외부box 증명으로478537행을 제거하고21684개 물리행·변수영역을 유지했다.',
        '제약836244→357707(57.22%), NNZ23258846→10083750(56.65%) 감소를 실제CSR에서 확인했다. 정수/LP가능영역 양방향포함과 전체원래행·4대물리 replay가 PASS다.',
        '동일모델·동일START로 원본20초/압축20초를 비교했다. UB0.6412659669740282, 압축LB0.46657758806291993, 축소gap27.241%다. 원래4대×24 GLOBAL 인증은 아니다.',
        'AIDC소비와 MESS주입을 각1회만 반영하고 비활성MESS의 비영Q/SOC를 원래4대물리로 검사했다.',
        'A1–M1–A2–M2 인터페이스는 Native0검사했다. 실제전체Heavy는 사용자HOLD이며 통합PASS를 선언하지 않았다.',
        '실제2시간 C0/C1 signed선로부하율은 둘다0.5201161496609195다. Known실행·P/Q가 동일하고 신규Unknown이 없어 개선을 주장할 수 없다.',
        'C1의781판단 중566번은 아직시작권한이 없었다. 나머지215번의2580사이트 후보는 현재GPU379건·미래firmKnown/Runtime상한부재2201건으로 거부돼 계통점수까지 도달하지 않았다. 보수적보장불가이며 물리적불가능의 증명은 아니다.',
        f"누적Native {ledger.get('Gurobi_Native_seconds')}초·AC {ledger.get('AC_wall_seconds')}초를 원장에 보존했다. C1 P95 .093766초는781전체판단 분포다. 동일Full96 CSR의proof kernel147.347→18.566초(7.936배)이며 Solver속도 개선은 미입증이다.",
        f"최종Native0 회귀 {r.get('passed','NOT_RUN')} PASS/{r.get('skipped','NOT_RUN')} skip이다. skip은 성공이 아니다. 새4시간/Full96 Actual·새FreshAC·통합성능은 NOT_RUN이다.",
        '사용자 요청으로 개발/실험을 중단하고 PR스냅샷을 정리한다. 미완성후속코드는 복구가능한 별도자료로 보존한다. 논문성능/연구완료를 주장하지 않는다.'
    ]
    intro = ('사용자 중단 요청에 따른 PR검토 스냅샷이다. AIDC 실제사이트 효과는 미검증이며 '
        'MESS 동등성·압축량·proof kernel 개선을 확인했다.\n\n'
        f"공통Science {b['science_sha']}, Case {b['case_sha']}. 개별실측은 원래Case를 따른다.\n\n")
    (REPORT/'FINAL_UNIFIED_REVIEW_KO.md').write_text(intro+'\n\n'.join(
        f'{i}. {answer}' for i, answer in enumerate(answers, 1))+'\n', encoding='utf8')
    root = REPORT.parents[1]
    tracked = subprocess.check_output(['git','ls-files','*.py'],cwd=root,text=True).splitlines()
    extra = [str(p.relative_to(root)).replace('\\','/') for folder in ('tools','tests','v42_integration')
             for p in (root/folder).glob('*.py')]
    code = {p:file_sha(root/p) for p in sorted(set(tracked+extra)) if (root/p).is_file()}
    _write(REPORT/'FINAL_CODE_SCIENCE_RESULT_FREEZE.json',dict(base_commit=common['base_commit'],
        bindings=b,final_code_sha=digest(code),source_files=code,scope=gate['freeze'],
        research_stopped=True,certified_new_full96=False,
        regression=file_record(REPORT/'UNIFIED_REGRESSION_RESULTS.json'),
        result=file_record(REPORT/'UNIFIED_VALIDATION_GATE.json'),historical_certificate_transfer=False))
    print(json.dumps(dict(regression=r['status'],passed=r.get('passed'),skipped=r.get('skipped'),
        AIDC_Known_same=same_known,AIDC_site_effect='NOT_DEMONSTRATED',
        MESS_equivalence='PASS',integrated_PASS=False),indent=2))


if __name__ == '__main__':
    final_report()

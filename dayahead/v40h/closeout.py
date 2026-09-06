"""Static closeout artifacts. Never executes a May scientific case."""
from pathlib import Path
from dataclasses import replace
import difflib
import subprocess
import xml.etree.ElementTree as ET
import numpy as np
from dayahead.paper_analysis.storage import read, write_json
from .identity import REL, CAMPAIGN, require, file_record, verify_file
from .policy import INTERPRETATION
from .freeze import seal_source, initialize_campaign, verify_scientific_freeze, scientific_status


def primary_examples(repo):
    """Small deterministic synthetic regressions, not B3 May execution."""
    from tests.dayahead.test_v40g_segments import context96
    from tests.dayahead.test_v40a_coordination import trajectory
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
    from .feedback import solve_feedback
    from .recourse import solve_fixed_route
    from .primary import preserve
    context, pending = context96()
    a1 = solve_feedback([pending], trajectory(), context)
    context.coefficients = context.coefficients[:2]
    authority = MessElectricalAuthority.from_repository()
    initial = replace(trajectory().slots[0], battery_energy_kwh=authority.initial_energy_kwh,
        soc_fraction=authority.initial_energy_kwh / authority.capacity_kwh)
    mf = solve_fixed_route(np.ones((2, 12)), MessTrajectory(tuple(replace(initial, slot=t) for t in range(2))), context)
    _, guard = preserve({'rho': .5 - 5e-8}, .5 - 5e-8, {'rho': .5}, lambda v: v['rho'])
    value = {'scope': 'Synthetic A1 one-job / MF two-slot deterministic test; no May B3 run',
        'A1': {k: v for k, v in a1.items() if k.startswith('A1_')},
        'MF': {k: v for k, v in mf.items() if k.startswith('MF_')},
        'A1_strict_primary_guard': a1['strict_primary_guard'], 'MF_lower_priority_stages': mf['lower_priority_stages'],
        'tiny_primary_gain_regression': guard, 'B2_B3_May_execution_count': 0}
    require(a1['status'] == mf['status'] == 'PASS', 'PRIMARY_EXAMPLES_FAILED')
    write_json(Path(repo) / REL / 'STRICT_PRIMARY_REGRESSION_REPORT.json', value)
    return value


def claim_boundary(repo):
    repo = Path(repo); root = repo / REL
    command = ['rg', '-n', '-i', '--max-columns', '500', '--max-columns-preview', '-g', '*.md', '-g', '*.py',
        'global.{0,50}optim|optim.{0,50}nonlinear|AC.{0,30}global', 'dayahead', 'pfr', 'tests']
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, encoding='utf-8')
    require(result.returncode in (0, 1), 'CLAIM_WORDING_SCAN_FAILED')
    (root / 'SURROGATE_WORDING_SCAN.txt').write_text(result.stdout, encoding='utf-8')
    flagged = [{'path': name, 'classification': 'AMBIGUOUS_SCOPE_REQUIRES_LATER_DOCUMENTATION_CORRECTION',
        'reason': 'global_optimality_certified field does not name the affine/polyhedral surrogate scope; it cannot establish nonlinear AC global optimality.'}
        for name in ('dayahead/v40a/feedback.py', 'dayahead/v40a/recourse.py', 'dayahead/v40g_segments/feedback.py')]
    write_json(root / 'SURROGATE_CLAIM_BOUNDARY.json', {'status': 'DOCUMENTED', 'interpretation': INTERPRETATION,
        'flagged_legacy_wording': flagged, 'explicit_false_nonlinear_AC_optimum_claim_confirmed': False,
        'scan_scope': 'Repository Python and Markdown including historical reports; this is a wording review, not a claim that all external papers were searched.',
        'legacy_bytes_modified': False, 'scan': file_record(root / 'SURROGATE_WORDING_SCAN.txt')})
    (root / 'SURROGATE_CLAIM_BOUNDARY.md').write_text(
        'Planning은 동결된 affine/polyhedral 배전계통 surrogate 안에서의 최적화입니다. '
        'MILP optimum 또는 bounded incumbent는 이 모델 범위에만 적용됩니다.\n\n'
        'Fresh는 결정 후 정확한 3상 OpenDSS 물리 검증이며, Actual은 동결된 결정을 실제 외생 입력으로 평가하는 정확한 OpenDSS 실행입니다. '
        'Planning 해를 비선형 AC 전력조류의 전역 최적해로 주장하지 않습니다.\n\n'
        'May 결과를 이용한 surrogate 재조정 또는 새 trust region은 추가하지 않았습니다. '
        '기존 코드의 범위가 불명확한 global_optimality_certified 문구 3곳은 별도 JSON에 후속 문서 수정 대상으로 기록했습니다.\n', encoding='utf-8')


def finalize(repo):
    repo = Path(repo).resolve(); root = repo / REL
    testroot = ET.parse(root / 'TEST_RESULTS.xml').getroot()
    suites = [testroot] if testroot.tag == 'testsuite' else list(testroot)
    counts = {k: sum(int(x.attrib.get(k, 0)) for x in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    require(counts['tests'] > 0 and counts['failures'] == counts['errors'] == counts['skipped'] == 0, 'STATIC_TESTS_NOT_ALL_PASS')
    frozen = seal_source(repo); identity = initialize_campaign(repo)
    scan = read(root / 'PRE_DAY_COMPLETE_RECLASSIFICATION.json')
    primary = read(root / 'STRICT_PRIMARY_REGRESSION_REPORT.json')
    claim_boundary(repo)
    original = (repo / 'dayahead/tools/run_v35r3e_r1_beam.py').read_text(encoding='utf-8').splitlines(True)
    hardened = (repo / 'dayahead/v40h/beam_driver.py').read_text(encoding='utf-8').splitlines(True)
    (root / 'M1_INTEGRITY_ONLY_CHANGES.diff').write_text(''.join(difflib.unified_diff(original, hardened,
        fromfile='preserved_inherited_beam.py', tofile='v40h/beam_driver.py')), encoding='utf-8')
    statuses = {k: 'FIXED' for k in ('P0_01_OLD_REUSE', 'P0_02_RECURSIVE_CERT', 'P0_03_M1_CACHE_IDENTITY',
        'P0_04_ELECTRICAL_GENERATION_PROVENANCE', 'P0_05_B1_GENERATION_IDENTITY', 'P0_06_MIGRATION_SEGMENTS',
        'P0_07_PRE_DAY_COMPLETE', 'P1_01_STRICT_PRIMARY_PRESERVATION')}
    statuses.update(P1_02_SURROGATE_CLAIM_BOUNDARY='DOCUMENTED', UNASSIGNED_44_CASE_BLOCKER='OPEN',
        V40G_FROZEN_COMMIT=frozen['git_commit'], V40G_WORKTREE_SCIENCE_CLEAN='YES', B2_B3_AUTHORIZED='NO', FULL_MAY_AUTHORIZED='NO')
    report = {**statuses, 'status_scope': 'FIXED means implementation and static regression closure, not authorization or validation of an unexecuted May campaign.',
        'OLD_RESULT_REUSE_P0': 'FIXED', 'DAY_CERTIFICATE_RECURSIVE_VALIDATION_P0': 'FIXED', 'M1_STAGE_CACHE_IDENTITY_P0': 'FIXED',
        'CORRECTED_MAY_OLD_REUSE_COUNT': 0, 'CORRECTED_MAY_INITIAL_RUN_REQUIRED_COUNT': 124,
        'new_runs_required': {c: 31 for c in ('B0', 'B1', 'B2', 'B3')}, 'STALE_STAGE_RESTORE_ALLOWED': 'NO',
        'CURRENT_IDENTITY_RESUME_TEST': 'PASS', 'OLD_IDENTITY_REJECTION_TEST': 'PASS', 'V40G_FINAL_IDENTITY_BOUND': 'PASS',
        'V40G_method_SHA': frozen['V40G_method_SHA'], 'V40G_source_SHA': frozen['V40G_source_SHA'], 'V40G_config_SHA': frozen['V40G_config_SHA'],
        'execution_identity_SHA': identity['identity_SHA'], 'source_file_count': frozen['source_status']['source_count'],
        'tests': counts, 'source_freeze': file_record(root / 'FINAL_SCIENTIFIC_SOURCE_FREEZE.json'),
        'matrix': file_record(repo / CAMPAIGN / 'CORRECTED_MAY_EXECUTION_MATRIX.json'), 'pre_day_complete_scan': scan,
        'primary_regressions': primary, 'preserved_V40G_file_count': frozen['preserved_V40G_files'],
        'GENERATION_OUTPUT_CLOSURE': identity['identity']['inputs']['generation_output_closure'],
        'new_electrical_certified_days': 31 - len(identity['identity']['inputs']['missing_electrical_generation_days']),
        'production_readiness': 'HOLD', 'remaining_prerequisites': [
            'Resolve authoritative execution sites for the existing 44 cases and the 78 additionally blocked cases (122 distinct cases).',
            'Generate and attest all 31 new electrical outputs under the frozen source before execution. Historical output hashes are not retroactive generation proof.',
            'Seal a complete output-bound execution identity and reinitialize all 124 RUN_REQUIRED rows in a preserved new revision before launching.',
            'Obtain separate authorization; B2/B3 and full May remain prohibited.'],
        'MAY_31DAY_AUTHORIZED': 'NO', 'B2_B3_science_runs_this_hardening': 0, 'full_Fresh_campaign_runs': 0,
        'worktree_scope': 'All Python scientific source and tests in dayahead, pfr, tests are committed and clean. Historical generated artifacts are preserved; repository-wide git status is not claimed clean.'}
    write_json(root / 'V40H_FINAL_STATUS.json', report)
    lines = ['# V40H 사전 무결성 보강 결과', '', '코드 수정과 정적 검증은 완료했습니다. May 운영 실행은 HOLD입니다.', '',
        '| 항목 | 상태 |', '|---|---|']
    lines += [f'| {k} | {v} |' for k, v in statuses.items()]
    lines += ['', f"회귀시험 {counts['tests']}개 통과. 새 행렬은 B0/B1/B2/B3 각각 31개, 총 124개 RUN_REQUIRED이며 기존 결과 재사용은 0입니다.", '',
        'PRE_DAY_COMPLETE 기존 6,366행 중 확실한 오분류는 May-03 UID 8749975의 B1/B3 두 행입니다. 6,364행은 실행 site·지연 증거가 없어 제외 근거가 부족합니다. '
        '새로 완료가 입증된 제외 행은 0개입니다. 기존 44개 차단 case 외에 78개가 추가되며, case 중복 제거 후 총 122개입니다.', '',
        'UID 8749975는 13슬롯부터 11,904초 실행하면 26.2266667슬롯에 끝납니다. D-day 서비스 2,004초가 남으므로 PRE_DAY_COMPLETE가 될 수 없습니다. '
        'site를 추정하지 않고 COUNTERFACTUAL_ACTUAL_EXECUTION_SITE_AUTHORITY_MISSING으로 차단합니다.', '',
        'UID 8666895는 AIDC05 [0,25) + AIDC01 [28,110)의 107슬롯을 보존하며 [25,28)은 계산 0입니다. 동결된 V40G segment 증거는 보존했습니다.', '',
        'A1과 MF의 primary incumbent, bound, 최종 재계산 rho 및 하위 목적에 의한 저하는 STRICT_PRIMARY_REGRESSION_REPORT.json에 기록했습니다. '
        '두 단계의 하위 목적에 의한 저하는 0이며 MF는 원래 단일 primary 단계입니다.', '',
        '전기계수 생성 인증은 생성 전에 입력 identity를 캡처하고 종료 후 다시 검증합니다. 기존 파일에 현재 소스 해시를 덧붙여 생성 provenance로 인정하지 않습니다. '
        '31일 신규 계수 생성은 이번 허용 범위 밖이므로 새 인증은 0/31입니다. 현재 freeze는 입력·소스 동결이며 완전한 생성 출력 동결은 아직 아닙니다. '
        '출력 생성 후 별도 revision의 완전한 실행 identity가 필요하며 현재 launcher는 이를 요구합니다.', '',
        f"동결 Git commit: `{frozen['git_commit']}`. 과학 소스 {frozen['source_status']['source_count']}개는 모두 추적되며 변경이 없습니다. "
        '과거 산출물과 기존 데이터 변경은 보존했으므로 저장소 전체가 clean하다고 주장하지 않습니다.', '',
        'Planning/Fresh/Actual의 해석 범위는 SURROGATE_CLAIM_BOUNDARY.md를 따릅니다. 비선형 AC 전역 최적해를 주장하지 않습니다.', '',
        'B2_B3_AUTHORIZED = NO; FULL_MAY_AUTHORIZED = NO.']
    (root / 'V40H_FINAL_REVIEW.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    verify_scientific_freeze(repo)
    print({k: report[k] for k in ('V40G_FROZEN_COMMIT', 'V40G_WORKTREE_SCIENCE_CLEAN', 'GENERATION_OUTPUT_CLOSURE', 'production_readiness', 'tests')}, flush=True)
    return report

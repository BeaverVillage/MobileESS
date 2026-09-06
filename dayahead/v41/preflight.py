"""Evidence-only V41 preflight; never imports ML, solvers, or Actual readers.

This command records the mandatory section-17 stop, not an executable campaign.
Run: python -m dayahead.v41.preflight
Verify the resulting evidence without rewriting it: add --verify.
"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dayahead/artifacts/v41r1_terminal_residual'
BASE = '7532a78dbe0c50e7737af53d0acc8017d7be2fc3'
BRANCH = 'codex/v41-final-ml-interface-may-campaign'
GAP = 'NO_SEMANTICALLY_VALID_EXISTING_GPUH_SHORTFALL_COEFFICIENT'
S5 = Path('C:/codex_mobileess_workspace/MobileESS_v40s5r1_rolling_origin_runtime')
R6 = Path('C:/codex_mobileess_workspace/MobileESS_v40r6r1_risk_calibrated_gpuwork')
REQUEST = Path('C:/Users/kjw39/.codex/attachments/cf6868dc-24b2-4156-98d5-7add2a743546/pasted-text.txt')
S5REL = 'dayahead/artifacts/v40s5r1_rolling_origin_runtime'
R6REL = 'dayahead/artifacts/v40r6r1_risk_calibrated_rolling_gpuwork'
CORE_DIRS = ('v40a', 'v40d_actual', 'v40e', 'v40f', 'v40g', 'v40g_segments', 'v40h', 'v40i')
OBJECTIVE_FILES = ('dayahead/v40g/optimizer.py', 'dayahead/v40h/feedback.py',
                   'dayahead/v40f/optimizer.py', 'dayahead/v40a/feedback.py',
                   'dayahead/v28r2/variable_registry.py', 'dayahead/v33x/headroom_stage1.py')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def git(*args, repo=ROOT, binary=False):
    data = subprocess.check_output(['git', '-C', str(repo), *args])
    return data if binary else data.decode('utf-8').strip()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(name, value):
    path = OUT / name
    if isinstance(value, str):
        data = value.encode('utf-8')
    else:
        data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if path.exists():
        require(path.read_bytes() == data, 'EXISTING_EVIDENCE_WOULD_CHANGE:' + name)
        return
    # Exclusive creation prevents a repeated preflight from replacing evidence.
    with path.open('xb') as stream:
        stream.write(data)


def record(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': sha(path), 'bytes': path.stat().st_size}


def base_files():
    return git('ls-tree', '-r', '--name-only', BASE).splitlines()


def base_snapshot():
    return {name: sha(ROOT / name) for name in base_files()}


def assignments(path):
    """Read literal constants without importing scientific modules."""
    values = {}
    for node in ast.parse(Path(path).read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = value
    return values


def objective_calls(path):
    source = Path(path).read_text(encoding='utf-8')
    return [{'line': n.lineno, 'expression': ast.get_source_segment(source, n)}
            for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr in ('setObjective', 'setObjectiveN')]


def reference(repo, prefix, rel, expected_head, classification):
    head = git('rev-parse', 'HEAD', repo=repo)
    require(head == expected_head, prefix + '_HEAD_DRIFT')
    require(not git('status', '--porcelain', repo=repo), prefix + '_TREE_DIRTY')
    receipt_path = repo / rel / (prefix + '_FINAL_COMMIT_RECEIPT.json')
    receipt = load(receipt_path)
    require(receipt['classification'] == classification, prefix + '_CLASSIFICATION_DRIFT')
    science = receipt['scientific_commit']
    git('merge-base', '--is-ancestor', science, head, repo=repo)
    owned = git('ls-tree', '-r', '--name-only', head, '--', rel, 'dayahead/' + prefix.lower()).splitlines()
    # Verify exact Git blobs and working bytes, including model/receipt artifacts.
    stream = subprocess.check_output(['git', '-C', str(repo), 'cat-file', '--batch'],
        input=''.join(head + ':' + p + '\n' for p in owned).encode('utf-8'))
    offset = 0
    hashes = {}
    for path in owned:
        end = stream.index(b'\n', offset)
        header = stream[offset:end].split()
        require(len(header) == 3 and header[1] == b'blob', prefix + '_BLOB_MISSING:' + path)
        size = int(header[2]); blob = stream[end + 1:end + 1 + size]; offset = end + size + 2
        hashes[path] = hashlib.sha256(blob).hexdigest()
        require(sha(repo / path) == hashes[path], prefix + '_WORKTREE_BLOB_MISMATCH:' + path)
    for path, digest in receipt.get('owned_SHA256', {}).items():
        require(sha(repo / path) == digest, prefix + '_RECEIPT_HASH_MISMATCH:' + path)
    return {'reference_worktree': str(repo), 'receipt_commit': head, 'scientific_commit': science,
        'receipt': record(receipt_path), 'classification': classification, 'classification_unchanged': True,
        'reference_only_not_optimizer_base': True, 'byte_verified_git_files': hashes,
        'receipt_owned_hashes_verified': len(receipt.get('owned_SHA256', {}))}


def issue(day):
    local = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))) - timedelta(hours=6)
    return local.isoformat(), local.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def plan_rows():
    rows = []
    for number in range(1, 32):
        day = f'2025-05-{number:02d}'
        aest, utc = issue(day)
        for policy in ('B0', 'B1', 'B2', 'B3'):
            rows.append(dict(target_day=day, policy=policy, issue_time_aest=aest, issue_time_utc=utc,
                runtime_model='ROLLING_Q90_TRACK_P_L2', future_workload='H4_R85_B2', H24='OFF',
                historical_cap_quantile='0.99', cap_rule='min(raw,historical,physical)',
                A0_required_reserve_interface='V41', A1_required_reserve_interface='V41',
                snapshot_path=f'frozen_artifacts/v41_may_campaign/snapshots/V41_ML_SNAPSHOT_{day}.json',
                snapshot_sha256='', snapshot_status='NOT_MATERIALIZED',
                production_q_seconds='5576.44921875', PF='0.95', Q_control='NO', mode='both',
                scientific_commit='', state='PENDING', execution_gate='BLOCKED_SECTION_17',
                result_path=f'frozen_artifacts/v41_may_campaign/{day}/{policy}',
                log_path=f'logs/v41_may_campaign/{day}/{policy}'))
    return rows


def build():
    require(git('rev-parse', 'HEAD') == BASE, 'INITIALIZATION_REQUIRES_EXACT_OPTIMIZER_BASE')
    require(git('branch', '--show-current') == BRANCH, 'V41_BRANCH_REQUIRED')
    require(not git('diff', BASE, '--name-only'), 'INHERITED_TRACKED_FILES_CHANGED')
    OUT.mkdir(parents=True, exist_ok=True)
    require(not (OUT / 'V41_START_STATE.json').exists(), 'ALREADY_INITIALIZED_USE_VERIFY')
    write('.gitattributes', '* -text\n')
    write('USER_REQUEST.txt', REQUEST.read_text(encoding='utf-8'))
    before = base_snapshot()
    write('V41_START_STATE.json', {'working_name': 'V41_FINAL_ML_INTERFACE_MAY_CAMPAIGN',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'base': BASE, 'branch': BRANCH,
        'worktree': str(ROOT), 'isolated_worktree': True, 'base_clean_before_edits': True,
        'original_user_request': record(REQUEST), 'stored_user_request': record(OUT / 'USER_REQUEST.txt'),
        'execution_started': False})
    write('V41_PROTECTED_SCOPE_START.json', {'base_commit': BASE, 'inherited_file_sha256': before})
    s5 = reference(S5, 'V40S5R1', S5REL, 'c6daa3d3dd4be4c97d3e312bb4efc40283461a7d',
        'V40S5R1_ROLLING_DIRECT_RUNTIME_SAFETY_FAIL')
    r6 = reference(R6, 'V40R6R1', R6REL, '4309a4e5ea2c7893f79bcc7e747ca7d13fc5de42',
        'V40R6R1_JOINT_GPUWORK_RESERVE_FAIL')
    write('V41_S5R1_REFERENCE_FREEZE.json', s5)
    write('V41_R6R1_REFERENCE_FREEZE.json', r6)
    core = {d: git('rev-parse', BASE + ':dayahead/' + d) for d in CORE_DIRS}
    comparisons = {}
    for label, commit in [('V40L_HEAD', 'e24492aa2e3404548cd4efc9f23e8168c0839b3b'),
                          ('S5R1', s5['receipt_commit']), ('R6R1', r6['receipt_commit'])]:
        other = {d: git('rev-parse', commit + ':dayahead/' + d) for d in CORE_DIRS}
        comparisons[label] = {'commit': commit, 'optimization_core_identical': core == other,
                              'core_tree_ids': other}
    write('V41_OPTIMIZER_BASE_AUTHORITY.json', {'commit': BASE,
        'branch': 'codex/v40m-actual-authority72-closure',
        'reason': 'V40G joint objective + V40H hardened A0/M1/A1/MF/Fresh/campaign infrastructure + V40I generation/Actual authority + latest non-ML V40M evidence closure.',
        'latest_core_change': git('log', '--all', '-1', '--format=%H %s', '--', 'dayahead/v40h', 'dayahead/v40g'),
        'not_an_experimental_runtime_or_workload_base': True,
        'core_tree_ids': core, 'parallel_reference_comparison': comparisons,
        'execution_ready_claim': False})
    policy = assignments(ROOT / 'dayahead/v40h/policy.py')['OBJECTIVE_HIERARCHY']
    expressions = {p: {'source': record(ROOT / p), 'objective_calls': objective_calls(ROOT / p)} for p in OBJECTIVE_FILES}
    names = [p for p in base_files() if p.startswith('dayahead/') and p.endswith('.py') and '/artifacts/' not in p]
    pattern = re.compile(r'\bpenalty\b|\bdebt\b|shortfall|backlog|future[_ ]reserve', re.I)
    hits = []
    for name in names:
        for line, value in enumerate((ROOT / name).read_text(encoding='utf-8-sig').splitlines(), 1):
            if pattern.search(value):
                hits.append({'file': name, 'line': line, 'text': value.strip()})
    write('V41_OBJECTIVE_SEARCH_EVIDENCE.json', {'searched_files': names, 'pattern': pattern.pattern,
        'read_errors': [], 'matches': hits, 'note': 'Keyword matches are evidence candidates, not coefficients. Current objective calls and dimensional review decide reuse.'})
    write('V41_RESERVE_PENALTY_AUTHORITY_AUDIT.json', {'status': 'BLOCKED', 'reason_code': GAP,
        'request_section': 17, 'existing_hierarchy': policy, 'source_evidence': expressions,
        'current_producer': 'dayahead/v40h/b1.py:produce_joint_b1 -> dayahead/v40g/optimizer.py:solve',
        'current_feedback': 'dayahead/v40h/pipeline.py:b3 -> dayahead/v40h/feedback.py:solve_feedback',
        'coefficient': None, 'unit': None, 'semantically_valid_existing_coefficient_found': False,
        'rejected_substitutes': [
            {'term': 'rho_max coefficient 1', 'unit': 'dimensionless loading ratio', 'reason': 'Not GPUh debt or unmet service.'},
            {'term': 'migration count', 'unit': 'job migration count', 'reason': 'Separate lexicographic priority; not service shortfall.'},
            {'term': 'complete reference deviation', 'unit': 'GPU-slots symmetric interval/site difference', 'reason': 'Charges relocation/time deviation, including fully served jobs; not GPUh debt.'},
            {'term': 'stable tie', 'unit': 'arbitrary deterministic index', 'reason': 'Ordering only.'},
            {'term': 'V28R2 terminal backlog', 'unit': 'node-hours', 'reason': 'Hard equality to reference; model minimizes eta. No backlog penalty to reuse.'},
            {'term': 'V33X leverage_expression', 'unit': 'electrical sensitivity weighted headroom', 'reason': 'Legacy different formulation; not GPUh unmet service and not current objective.'}],
        'new_coefficient_created': False, 'optimizer_changed': False,
        'required_to_continue': 'Existing approved source file/variable, value and unit with valid GPUh service-shortfall semantics; otherwise a new explicit scientific objective decision is required.'})
    selection = load(S5 / S5REL / 'V40S5R1_SELECTION_FREEZE.json')
    features = ['requested_seconds', 'num_gpus_req', 'num_nodes_req', 'num_cores_req',
                'requested_memory_mib', 'partition', 'qos', 'submit_hour', 'submit_dow']
    write('V41_RUNTIME_Q90_FREEZE.json', {'status': 'SPECIFICATION_FROZEN_NOT_INTEGRATED',
        'model_id': 'ROLLING_Q90_TRACK_P_L2', 'track': 'P', 'config_id': 'L2', 'quantile': 0.90,
        'configuration': selection['config'], 'fixed_parameters': selection['fixed_parameters'],
        'features': features, 'source_preprocessing': record(S5 / 'dayahead/v40s5r1/common.py'),
        'source_fitting': record(S5 / 'dayahead/v40s5r1/models.py'),
        'preprocessing': 'Exact S5R1 Preprocess: train-history medians, numeric log1p, missing indicators, issue-history category vocabulary with __UNKNOWN__, unmodified clock features.',
        'membership': 'end < issue AND runtime > 0 AND finite AND feature-eligible; all matured expanding history',
        'applicability': 'Day-Ahead PENDING only; RUNNING authority unchanged',
        'duration_slots': 'ceil(Q90_seconds / 900) exactly once; no multiplier, UARP, walltime cap or manual correction',
        'provenance_assumption': 'D1_SCHEDULER_REQUEST_STATE_PROXY_V1',
        'original_submission_provenance_verified': False, 'May_predictions_generated': False})
    prereg = load(R6 / R6REL / 'V40R6R1_PREREGISTRATION.json')
    write('V41_H4_R85B2_FREEZE.json', {'status': 'SPECIFICATION_FROZEN_NOT_INTEGRATED',
        'model_id': 'H4_R85_B2', 'base': 'Frozen R6 B2 L0 upper', 'unit': 'arriving GPU-service work [GPUh]',
        'source_hyperparameters': record(R6 / 'dayahead/artifacts/v40r6_multihorizon_cumulative_gpuwork/V40R6_HYPERPARAMETER_FREEZE.json'),
        'calibration': prereg['calibration'], 'source_calibration': record(R6 / 'dayahead/v40r6r1/calibration.py'),
        'window_slots': 16, 'window_starts': list(range(81)), 'H24_OFF': True,
        'optimizer_disabled_horizons': ['H1', 'H8', 'H24', '15min_exact_burst'],
        'raw_field': 'H4_RAW_R85_B2_GPUh', 'actionable_field': 'H4_ACTIONABLE_RESERVE_GPUh',
        'May_predictions_generated': False, 'research_classification_changed': False})
    write('V41_ACTIONABLE_CAP_CONTRACT.json', {'status': 'SPECIFICATION_FROZEN_NOT_INTEGRATED',
        'RAW': 'H4_RAW_R85_B2_GPUh', 'historical_quantile': 0.99,
        'historical_pool': 'Fully mature historical actual H4 windows available strictly before issue',
        'historical_order_statistic': 'k=min(max(ceil((n+1)*0.99),1),n); sorted_values[k-1]; no interpolation',
        'empty_historical_pool': 'BLOCK; no invented fallback',
        'physical_cap': '0.25 * sum(eligible future-service GPU capacity over 16 slots)',
        'capacity_authority_candidate': 'context.capacity.site_capacity with context.capacity.eligible_racks; dayahead/v40d_actual/inputs.py:capacity',
        'future_service_eligibility_binding': 'NOT_VERIFIED; cannot substitute total installed capacity',
        'actionable': 'min(RAW,CAP_HIST,CAP_PHYS)', 'retain_separate_fields': ['RAW', 'CAP_HIST', 'CAP_PHYS', 'ACTIONABLE_RESERVE'],
        'forecast_accuracy_improvement_claim': False, 'May_objective_based_tuning': False})
    write('V41_RESERVE_INTERFACE_CONTRACT.json', {'status': 'BLOCKED_SECTION_17',
        'headroom_GPU': 'h[t] = sum_i(G_cap[i,t] - G_known[i,t]) respecting eligibility',
        'H_available_GPUh': '0.25 * sum(h[k:k+16])', 'constraint': 'H_available[k] + xi[k] >= H4_ACTIONABLE_RESERVE[k]',
        'xi_lower_bound': 0, 'coefficient': None, 'coefficient_authority': GAP,
        'preferred_aggregation': 'existing_GPUh_debt_coefficient * mean(xi); only if compatible with existing scaling',
        'runtime_wired': False, 'H4_wired': False, 'reserve_constraint_implemented': False,
        'A0_A1_shared_snapshot_required': True, 'B0_B1_B2_B3_shared_snapshot_required': True})
    write('V41_POLICY_REGISTRY_FREEZE.json', {'source': record(ROOT / 'dayahead/v40g/authority.py'),
        'B0': 'RW/reference AIDC, MESS OFF', 'B1': 'Joint temporal + spatial/migration AIDC, MESS OFF',
        'B2': 'Exact B0 AIDC, MESS optimization', 'B3': 'A0 exact B1 -> M1 -> A1 -> MF',
        'B3_A0_AIDC_OPTIMIZE_CALLS': 0, 'A1_new_RUNNING_migrations': 0, 'objective_hierarchy': policy,
        'M1_MF_Fresh_unchanged': True, 'policy_redefined': False,
        'concurrency_source': record(ROOT / 'dayahead/v40h/policy.py'),
        'Gurobi_threads': 4, 'campaign_worker_count': 'NOT_SELECTED; no campaign launched'})
    authority = {'scope': 'V41 only', 'user_authorized': True, 'prior_holds_edited': False,
        'prior_experiments_May_reads': 0, 'V41_May_scientific_access': 'AUTHORIZED',
        'V41_May_source_data_opened': False, 'actual_order': 'Day-Ahead decision -> hash -> freeze receipt -> Actual',
        'run_gate': 'BLOCKED_SECTION_17', 'reason': GAP, 'source': record(OUT / 'USER_REQUEST.txt')}
    write('V41_MAY_ACCESS_AUTHORITY.json', authority)
    write('V41_EXECUTION_AUTHORITY.json', {**authority,
        'authorized_actions': ['ML integration', 'May01 B0/B1 Day-Ahead and Actual', 'Full May B0/B1/B2/B3 Day-Ahead and Actual'],
        'execution_eligibility': False, 'authorization_is_not_a_pass_certificate': True})
    rows = plan_rows(); buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
    write('V41_MAY_CAMPAIGN_PLAN.csv', buf.getvalue())
    write('V41_MAY_CAMPAIGN_PROPAGATION_AUDIT.json', {'status': 'BLOCKED_NOT_RUNTIME_VERIFIED',
        'planned_days': 31, 'planned_policy_days': 124, 'planned_DayAhead_phases': 124, 'planned_Actual_phases': 124,
        'requested_configuration_consistency': '124/124', 'runtime_propagation_pass_count': 0,
        'runtime_propagation_not_verified_count': 124, 'snapshot_count': 0, 'executed_units': 0,
        'plan_only_not_launch_ready': True, 'blocker': GAP})
    transition = ROOT / 'dayahead/artifacts/v40m_authority72_closure/V40M_AUTHORITY_TRANSITION_MATRIX.json'
    write('V41_INHERITED_ACTUAL_AUTHORITY_STATUS.json', {'source': record(transition),
        'historical_counts': load(transition)['new'], 'V41_case_membership_recomputed': False,
        'meaning': '72 historical policy-day blockers are not 72 UIDs or a newly measured V41 failure count. New runtime may change affected membership. Preserve this evidence and revalidate before execution.'})
    write('V41_MAY01_PILOT_DECISION.json', {'status': 'NOT_RUN_BLOCKED_SECTION_17', 'reason': GAP,
        'issue_time_UTC': issue('2025-05-01')[1], 'B0_DA': 'NOT_RUN', 'B0_ACTUAL': 'NOT_RUN',
        'B1_DA': 'NOT_RUN', 'B1_ACTUAL': 'NOT_RUN', 'nesting': 'NOT_TESTED', 'objective_identity': 'NOT_TESTED',
        'pilot_reuse_eligible': False, 'integration_result_invalidations': 0})
    write('V41_OPERATIONAL_SELECTION_RATIONALE.md',
        '# V41 운영 선택과 실행 중단 근거\n\n'
        '요청에 따라 runtime은 Rolling Q90 Track-P L2, 미래 작업량은 H4 R85_B2, H24는 OFF로 명세를 고정했다. '
        '이는 새로운 V41 운영 인터페이스 선택이며 S5R1/R6R1 FAIL 판정을 바꾸지 않는다. '
        '아직 예측 생성이나 최적화 연결은 실행하지 않았다.\n\n'
        '현재 B1/A0는 V40H producer가 V40G joint optimizer를 호출하고 A1은 V40H feedback을 사용한다. '
        '주목적은 무차원 rho_max이며 하위 목적은 migration 수, 기준 스케줄 GPU-slot 대칭 편차, 동률 해소다. '
        'GPUh 서비스 부족 벌점 계수는 없다. 과거 V28R2 backlog도 벌점이 아니라 기준값과의 강제 등식이다.\n\n'
        '따라서 사용자 지시문 17번의 “If NO semantically valid existing coefficient exists: STOP BEFORE MAY CAMPAIGN”을 적용했다. '
        '새 계수, 0 계수, migration 계수, 임의 단위 변환을 대입하지 않았다. '
        '기존 승인 계수의 파일·변수·값·단위 또는 별도의 명시적 과학적 목적함수 결정이 있어야 재개할 수 있다.\n\n'
        'extreme raw reserve forecasts are saturated before optimization by causally historical and physically actionable capacity limits. '
        '이는 예측 정확도 개선 주장이 아니며, raw와 actionable을 분리 저장하는 명세다.\n\n'
        'V40M의 미해결 Actual 사례 72개는 과거 증거로 보존한다. V41 runtime 적용 후 같은 사례 수라고 단정하지 않는다. '
        '실행 권한 부여 자체가 누락된 Actual 실행 위치 근거를 생성하지 않는다.\n')
    after = base_snapshot()
    write('V41_PROTECTED_SCOPE_END.json', {'base_commit': BASE, 'inherited_file_sha256': after})
    changed = [p for p in before if before[p] != after[p]]
    require(not changed, 'PROTECTED_BYTES_CHANGED')
    write('V41_PROTECTED_SCOPE_DIFF.json', {'status': 'PASS', 'inherited_files_checked': len(before),
        'changed_files': changed, 'reference_byte_identity_pass': True,
        'protected_scope_includes': ['all inherited tracked files', 'S5R1/R6R1 tracked source and evidence', 'older scientific history untouched in original worktrees'],
        'optimizer_scientific_code_modified': False})
    print(json.dumps({'status': 'BLOCKED_SECTION_17', 'artifact_root': str(OUT), 'reason': GAP}, ensure_ascii=False))


def verify():
    results = []
    def check(name, value):
        require(value, name); results.append(name)
    check('V41 isolated branch', git('branch', '--show-current') == BRANCH)
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    check('inherited bytes unchanged', base_snapshot() == load(OUT / 'V41_PROTECTED_SCOPE_START.json')['inherited_file_sha256'])
    for tag in ('S5R1', 'R6R1'):
        ref = load(OUT / ('V41_' + tag + '_REFERENCE_FREEZE.json'))
        repo = Path(ref['reference_worktree'])
        check(tag + ' HEAD unchanged', git('rev-parse', 'HEAD', repo=repo) == ref['receipt_commit'])
        check(tag + ' receipt identity', sha(ref['receipt']['path']) == ref['receipt']['sha256'])
        check(tag + ' source/artifact bytes unchanged', all(sha(repo / p) == h for p, h in ref['byte_verified_git_files'].items()))
    gap = load(OUT / 'V41_RESERVE_PENALTY_AUTHORITY_AUDIT.json')
    check('mandatory coefficient stop retained', gap['coefficient'] is None and gap['status'] == 'BLOCKED')
    for name, data in gap['source_evidence'].items():
        check('objective source and expressions: ' + name, sha(ROOT / name) == data['source']['sha256'] and objective_calls(ROOT / name) == data['objective_calls'])
    check('May01 fixed-AEST issue exact', issue('2025-05-01')[1] == '2025-04-30T08:00:00Z')
    with (OUT / 'V41_MAY_CAMPAIGN_PLAN.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    check('124 unique requested policy-days', rows == plan_rows() and len({(r['target_day'], r['policy']) for r in rows}) == 124)
    check('no absent snapshot presented as integrated', all(not r['snapshot_sha256'] and r['execution_gate'] == 'BLOCKED_SECTION_17' for r in rows))
    constants = assignments(ROOT / 'dayahead/v36/contracts.py')
    check('q and PF preserved', constants['Q_SELECTED_SECONDS'] == 5576.44921875 and constants['PF'] == 0.95)
    check('user authorization distinguished from readiness', load(OUT / 'V41_EXECUTION_AUTHORITY.json')['user_authorized'] and not load(OUT / 'V41_EXECUTION_AUTHORITY.json')['execution_eligibility'])
    check('no false pilot PASS', load(OUT / 'V41_MAY01_PILOT_DECISION.json')['status'] == 'NOT_RUN_BLOCKED_SECTION_17')
    check('no false propagation PASS', load(OUT / 'V41_MAY_CAMPAIGN_PROPAGATION_AUDIT.json')['runtime_propagation_pass_count'] == 0)
    result = {'status': 'PASS', 'scope': 'Evidence-only preflight checks; not the 76 requested live integration tests',
        'passed': len(results), 'failed': 0, 'checks': results, 'integration_execution': 'BLOCKED',
        'all_integration_tests_pass': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify()
    else:
        build()

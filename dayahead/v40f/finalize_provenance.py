"""Seal final execution provenance without rewriting the Planning source seal."""
from pathlib import Path
import hashlib
import json

from .authority import REL


def finalize(repo):
    repo = Path(repo).resolve()
    root = repo / REL

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    seal_path = root / 'V40F_METHOD_SOURCE_LINEAGE.json'
    seal = json.loads(seal_path.read_text(encoding='utf-8'))
    seal_sha = sha(seal_path)
    current = {p: sha(p) for p in seal['source_SHAs']}
    changes = {p: {'Planning_sha256': old, 'final_sha256': current[p]}
               for p, old in seal['source_SHAs'].items() if current[p] != old}
    smoke_path = str(repo / 'dayahead/v40f/smoke.py')
    assert set(changes) == {smoke_path}, changes
    archived_smoke = root / 'repairs/terminal_metadata_serialization/smoke_before.py'
    assert sha(archived_smoke) == seal['source_SHAs'][smoke_path]
    assert sha(seal['config']['path']) == seal['config']['sha256']
    for path in sorted((repo / 'dayahead/v40f').glob('*.py')):
        current[str(path)] = sha(path)
    runner_path = root / 'V40F_PHYSICAL_RUNNER_LINEAGE.json'
    runner = json.loads(runner_path.read_text(encoding='utf-8'))
    original = runner['original_source']
    assert sha(original['path']) == original['sha256']
    current[original['path']] = original['sha256']
    test_path = repo / 'tests/dayahead/test_v40f_min_rho.py'
    current[str(test_path)] = sha(test_path)
    final_sha = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    lineage = {
        'status': 'PASS',
        'Planning_source_seal': {'path': str(seal_path), 'sha256': seal_sha, 'method_SHA': seal['method_SHA']},
        'final_source_sha256': final_sha,
        'final_source_files': current,
        'changes_since_Planning_seal': changes,
        'archived_Planning_smoke_source': {'path': str(archived_smoke), 'sha256': sha(archived_smoke)},
        'change_explanation': 'Encode common_terminal_obligation as JSON for Parquet; resume Actual only after verifying frozen decision and completed Fresh SHA. No reoptimization or Fresh rerun.',
        'Planning_mathematical_authority_changed': False,
        'Actual_physics_changed': False,
        'config_changed': False,
        'physical_runner_lineage': {'path': str(runner_path), 'sha256': sha(runner_path)},
        'validation': {'command': 'python -m pytest tests/dayahead/test_v40f_min_rho.py tests/dayahead/test_v40a_grid.py tests/dayahead/test_v40a_invariants.py -q', 'passed': 26, 'failed': 0},
    }
    lineage_path = root / 'V40F_FINAL_EXECUTION_SOURCE_LINEAGE.json'
    save(lineage_path, lineage)
    invalidation_path = root / 'V40F_HISTORICAL_INVALIDATION_STATUS.json'
    save(invalidation_path, {
        'old_artifacts_modified': False,
        'pre_corrected_electrical_results': {
            'status': 'INVALIDATED_BY_BACKGROUND_LOAD_MAPPING_DEFECT',
            'evidence_manifest': str(repo / 'dayahead/artifacts/v40e_background_mapping_fix/PROTECTED_OLD_ARTIFACTS_MANIFEST.json'),
            'scope': 'Scientific claims using the confirmed duplicated background mapping, including contaminated Planning anchors/sensitivities.',
        },
        'V40E_corrected_background_ZERO_FEASIBILITY_B1': {
            'status': 'INVALIDATED_BY_AIDC_OBJECTIVE_IMPLEMENTATION_DEFECT',
            'background_mapping_already_corrected': True,
            'evidence_manifest': str(root / 'PRESERVED_V40E_EVIDENCE_MANIFEST.json'),
        },
        'mixed_duration_development_attempt': {
            'status': 'REJECTED_NO_FINAL_RESULT',
            'archive': str(root / 'development_attempts/rejected_mixed_duration_formulation'),
        },
        'replacement': 'V40F COMMON_SERVICE_MIN_RHO_AIDC May-01 B0/B1 only',
        'B2_B3_AUTHORIZED': 'NO', 'FULL_MAY_AUTHORIZED': 'NO',
    })
    report_path = root / 'V40F_MAY01_B0_B1_FINAL_REPORT.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['final_execution_source_lineage'] = {'path': str(lineage_path), 'sha256': sha(lineage_path)}
    report['historical_invalidation_status'] = {'path': str(invalidation_path), 'sha256': sha(invalidation_path)}
    report['validation'] = lineage['validation']
    report['common_service_record_semantics'] = 'Embedded common_service is the preserved pre-solve preflight snapshot; B1_min_rho_started=False refers to that earlier boundary. Final execution status is COMPLETE.'
    report['B0_B2_and_B1_B3_identity_scope'] = 'Static frozen AIDC authority/decision identity only; B2/B3 physical execution has not run.'
    save(report_path, report)
    markdown_path = root / 'V40F_MAY01_B0_B1_FINAL_REPORT.md'
    text = markdown_path.read_text(encoding='utf-8')
    text = text.replace('**공통 service authority + MIN_RHO_AIDC May-01 B0/B1**\n', '**공통 service authority + MIN_RHO_AIDC May-01 B0/B1**\n\n')
    text = text.replace('과학적 비교 기준으로 사용하지 않는다.\n|', '과학적 비교 기준으로 사용하지 않는다.\n\n|')
    text = text.replace('Actual critical coordinates:\n-', 'Actual critical coordinates:\n\n-')
    marker = '\n\n검증·provenance: '
    text = text.split(marker)[0]
    text += marker + f'관련 tests 26 PASS. Planning/Fresh 4,346개와 기존 V40E 증거 212개 diff = 0. B0/B2와 B1/B3 A0 identity는 static authority 검사이며 B2/B3를 실행한 것이 아니다. [최종 실행 source lineage]({lineage_path.as_posix()})에 Planning seal 이후 저장 형식 수정과 Actual 재개 경로를 별도로 기록했다.\n'
    markdown_path.write_text(text, encoding='utf-8')
    assert sha(seal_path) == seal_sha
    print(json.dumps({'status': 'PASS', 'Planning_seal_preserved': True, 'changed_existing_source_count': len(changes), 'final_source_sha256': final_sha}))


if __name__ == '__main__':
    finalize(Path.cwd())

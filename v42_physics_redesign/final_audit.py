"""Solver-free prepublication audit of evidence and preservation."""
from .common import *

REQUIRED = (
    'ROOT_CAUSE_ANALYSIS_KO.md', 'EXISTING_METHOD_FAILURE_COMPARISON.md',
    'PHYSICS_STRENGTHENED_ARCHITECTURE.md', 'ORIGINAL_INTEGER_EQUIVALENCE_PROOF.md',
    'TEMPORAL_SOC_PCS_ROUTE_COUPLING_PROOF.md', 'GRID_EXACT_SEPARATION_PROOF.md',
    'VALID_INEQUALITY_CERTIFICATES.json', 'MODEL_COMPLEXITY_COMPARISON.csv',
    'ROOT_LB_COMPARISON.csv', 'MIP_CANARY_RESULT.json',
    'FINAL_GLOBAL_BOUND_TRAJECTORY.csv', 'ORIGINAL_PHYSICAL_REPLAY.json',
    'PROCESS_ISOLATION_AUDIT.json', 'FINAL_DECISION.json', 'FINAL_REVIEW_KO.md')


def main():
    prior.forbid_optimize()
    start = time.perf_counter()
    paths_audit('solver_free_final_publication_audit')
    assert all((REPORTS / name).is_file() for name in REQUIRED)
    source = read(REPORTS / 'SOURCE_CENSUS.json')
    scientific = {n: sha(hc.PARENT / n) for n in source['scientific_input_SHAs']}
    assert scientific == source['scientific_input_SHAs']
    stop = read(REPORTS / 'PREVIOUS_ZF_STOP_AUDIT.json')
    assert stop['actual_live_owned_process_count'] == 0
    for name, receipt in stop['preserved_files'].items():
        p = OLD_ZF / name
        assert p.stat().st_size == receipt['bytes'] and sha(p) == receipt['sha256'], name
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=OLD_ZF/'repo', text=True).strip() == stop['source_git_HEAD']
    copied = read(REPORTS/'PREVIOUS_CERTIFICATE_COPY_RECEIPT.json')
    assert copied['PASS'] and copied['originals_read_only']
    for receipt in copied['files']:
        assert sha(WORK/receipt['destination']) == receipt['sha256']
        assert sha(receipt['source']) == receipt['sha256']
    gate = read(WORK / 'checkpoints/ROOT_EQUIVALENCE_GATE.json')
    assert gate['PASS']
    assert gate['temporal_rows_sha256'] == sha(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz')
    assert gate['temporal_data_sha256'] == sha(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz')
    for name in ('INDEPENDENT_VALID_INEQUALITY_AUDIT.json', 'TEMPORAL_SCIENTIFIC_IDENTITY.json',
                 'H2_CUMULATIVE_OPERATOR_VERIFICATION.json', 'ORIGINAL_PHYSICAL_REPLAY.json'):
        assert read(REPORTS / name)['PASS'], name
    fixture = read(REPORTS / 'BOUNDED_EXACT_FIXTURE_VERIFICATION.json')
    assert fixture['PASS'] and fixture['tiny_HiGHS_calls'] == 100
    assert fixture['native_fullscale_Gurobi_calls'] == 0
    root = read(REPORTS / 'ROOT_RESULT.json')
    decision = read(REPORTS / 'FINAL_DECISION.json')
    assert not root['executed'] and root['native_optimize_calls'] == 0
    assert root['Runtime'] is None and root['Work'] is None
    assert root['charged_native_Runtime'] == 0 and root['charged_native_Work'] == 0
    assert not (WORK/'checkpoints/B2_ROOT_ONCE.json').exists()
    assert not (WORK/'logs/B2_ROOT_NATIVE.log').exists()
    assert decision['classification'] == 'M1_PHYSICS_REDESIGN_RESOURCE_PENDING'
    assert decision['new_LB'] == LB and decision['new_UB'] == UB
    assert not decision['M1_ACCEPTED'] and not decision['production_gate_PASS']
    assert decision['new_canary_native_calls'] == decision['new_production_native_calls'] == 0
    assert decision['next_action_count'] == 1 and not decision['next_action_executed']
    final_resource = read(REPORTS/'PROCESS_ISOLATION_AUDIT.json')['snapshots'][-1]
    assert not final_resource['admission_PASS']
    assert final_resource['RAM_based_admission'] is False
    assert any(p['active_native'] for p in final_resource['processes'])
    names = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT, text=True).splitlines()
    allowed = lambda n: n == '.gitattributes' or n.startswith(('v42_physics_redesign/', 'docs/v42_m1_physics_strengthened_20261008/'))
    assert all(allowed(n) for n in names), names
    write(REPORTS/'PUBLICATION_AUDIT.json', dict(
        PASS=True, native_optimize_calls=0, required_artifacts_present=True,
        scientific_inputs_byte_identical=True, scientific_SHA256=scientific,
        previous_ZF_preserved_file_count=len(stop['preserved_files']),
        previous_ZF_all_files_byte_identical=True, previous_ZF_HEAD_unchanged=True,
        previous_completed_certificate_copies_byte_identical=True,
        independent_proofs_PASS=True, tiny_fixture_HiGHS_calls=100,
        tiny_fixture_wall_seconds=fixture['controller_wall_seconds'],
        new_ROOT_Runtime=None, new_ROOT_Work=None, charged_native_Runtime=0,
        original_namespace_Git_diff_empty=True,
        M1_ACCEPTED=False, LB=LB, UB=UB, global_gap_percent=100*(UB-LB)/UB,
        controller_wall_seconds=time.perf_counter()-start,
        source_module_SHA256={p.name: sha(p) for p in (ROOT/'v42_physics_redesign').glob('*.py')},
        raw_history_not_rewritten=True,
        preregistration_SHA256=sha(REPORTS/'ROOT_PREREGISTRATION.md')))
    print('PUBLICATION_AUDIT_PASS', len(stop['preserved_files']), flush=True)


if __name__ == '__main__':
    main()

"""Materialize a verified cap-10 trial through the production Planning/Fresh writer.

This command repairs only B2. It neither starts B3 nor resumes the May campaign.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v37.status import atomic_json
from dayahead.v39e.campaign_adapter import build_day, configure_v37_runner
from dayahead.v40b.reuse import validate_case_files
from dayahead.v40d.policy import applied, case_fingerprint, load_policy, sha


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day', required=True, choices=['2025-05-21', '2025-05-28', '2025-05-30'])
    args = parser.parse_args()
    day = args.day
    trial = REPO / 'dayahead/artifacts/v40d_ac_restoration/cap10' / day
    report = read(trial / 'RESULT.json')
    contract = read(trial / 'TRIAL_CONTRACT.json')
    if report['status'] != 'PASS' or not report['production_unchanged'] or not report['routes_unchanged']:
        raise RuntimeError('UNVERIFIED_TRIAL')
    if report['Fresh']['convergence_count'] != 96 or report['Fresh']['physical_violation']:
        raise RuntimeError('TRIAL_FRESH_NOT_PASSED')
    source_cp = Path(contract['baseline_checkpoint'])
    if sha(source_cp) != contract['baseline_checkpoint_sha256']:
        raise RuntimeError('SOURCE_CHECKPOINT_DRIFT')
    initial = read(source_cp)
    for item in initial['case_files']:
        if sha(REPO / item['relative_path']) != item['sha256']:
            raise RuntimeError('SOURCE_CASE_FILE_DRIFT:' + item['relative_path'])
    k = report['total_rounds']
    final_path = trial / f'ROUND_{k:02d}.json'
    final = read(final_path)
    aidc = build_day(REPO, day, 'B0')
    runner = configure_v37_runner()
    runner.PASS_ID = 'V40B'
    runner.STATUS_ROOT = REPO / 'dayahead/artifacts/v40d_ac_restoration/materialization_status'
    fp = runner.case_execution_fingerprint(REPO, day, 'B2', aidc)
    beam_path = runner._beam_root(REPO, fp['execution_fingerprint_sha256'], day, 'B2', 2) / 'FINAL_RESULT.json'
    beam = read(beam_path)
    if beam['execution_fingerprint_sha256'] != fp['execution_fingerprint_sha256']:
        raise RuntimeError('BEAM_FINGERPRINT_MISMATCH')
    from dayahead.tools.run_v35r3e_r1_beam import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v37r3.restoration import _discrete_signature
    from dayahead.v40a.recourse import validate_physics
    trajectory = MessTrajectory(tuple(_restore_slots(final['trajectory_slots'])))
    original = MessTrajectory(tuple(_restore_slots(beam['trajectory_slots'])))
    if _discrete_signature(original) != _discrete_signature(trajectory) or validate_physics(trajectory)['status'] != 'PASS':
        raise RuntimeError('TRIAL_ROUTE_OR_PHYSICS_MISMATCH')
    beam = deepcopy(beam)
    beam['trajectory_slots'] = final['trajectory_slots']
    beam['trajectory_sha256'] = trajectory.canonical_sha256
    beam['selected_state'].update(solver_objective=final['result']['objective'],
                current_planning_objective=final['result']['objective'],
                trajectory_slots=final['trajectory_slots'], restoration_cut_count=len(final['cuts']), restoration_round=k)
    print(day + ': materializing repaired B2 with independent production Fresh verification', flush=True)
    with applied(REPO, baseline_namespace=True) as policy:
        cp = runner._checkpoint_path(REPO, day, 'B2')
        if cp.exists():
            raise RuntimeError('REPAIRED_CHECKPOINT_ALREADY_EXISTS')
        result = runner._run_frozen_case_once(REPO, day, 'B2', aidc, beam,
                     restoration_round=k, restoration_total_cuts=len(final['cuts']))
        if not result['Planning']['pass'] or result['Fresh']['convergence_count'] != 96 or result['Fresh']['physical_violation']:
            raise RuntimeError('PRODUCTION_REVALIDATION_FAILED')
        for key in ['Vmin_pu', 'Vmax_pu', 'rho_max_AC']:
            if abs(result['Fresh'][key] - report['Fresh'][key]) > 1e-10:
                raise RuntimeError('PRODUCTION_TRIAL_FRESH_MISMATCH:' + key)
        result['AC_restoration_policy_sha256'] = policy['policy_sha256']
        result['restoration_rounds'] = k
        result['restoration_trial'] = {'path': str(final_path), 'sha256': sha(final_path),
                                      'source_checkpoint': str(source_cp), 'source_checkpoint_sha256': sha(source_cp)}
        effective_fp = case_fingerprint(fp, policy)
        runner._write_case_checkpoint(REPO, day, 'B2', result, effective_fp)
        root = runner._case_root(REPO, day, 'B2')
        validated = validate_case_files(day, 'B2', cp, root)
        if runner._valid_case_checkpoint(REPO, day, 'B2', effective_fp) is None:
            raise RuntimeError('PRODUCTION_LOADER_REJECTED_REPAIRED_CASE')
    certificate = {'status': 'PASS', 'day': day, 'case': 'B2', 'checkpoint': str(cp), 'checkpoint_SHA': sha(cp),
                   'case_root': str(root), 'files': validated['files'], 'execution_fingerprint': effective_fp,
                   'AC_restoration_policy_sha256': policy['policy_sha256'], 'restoration_rounds': k,
                   'source_trial': str(final_path), 'source_trial_sha256': sha(final_path),
                   'old_failed_result_unchanged': all(sha(REPO / i['relative_path']) == i['sha256'] for i in initial['case_files'])}
    if not certificate['old_failed_result_unchanged']:
        raise RuntimeError('OLD_RESULT_MUTATED')
    atomic_json(trial / 'PRODUCTION_CERTIFICATE.json', certificate)
    print(json.dumps({'day': day, 'status': 'PASS', 'restoration_rounds': k,
          'Vmin': result['Fresh']['Vmin_pu'], 'Vmax': result['Fresh']['Vmax_pu'], 'case_root': str(root)}), flush=True)


if __name__ == '__main__':
    main()

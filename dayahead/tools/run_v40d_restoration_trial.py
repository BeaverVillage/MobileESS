"""Continue recorded B2 P/Q restoration in an isolated, auditable output directory."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import numpy as np
from dayahead.tools.run_v35r3e_r1_beam import _restore_slots, _service_mapping
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v35.execution import daily_traffic_authority
from dayahead.v37.context import load_day_context
from dayahead.v37.contracts import CACHE_ROOT, PHASE, SOURCE_DATA_REPOSITORY
from dayahead.v37.status import atomic_json
from dayahead.v37r3.restoration import (
    _discrete_signature, extract_ac_violations, frozen_trajectory,
    local_fresh_ac_restoration_cuts, restoration_cut_from_payload,
    solve_fixed_discrete_recourse,
)
from dayahead.v39e.campaign_adapter import build_day
from dayahead.v40a.recourse import validate_physics


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day', required=True, choices=['2025-05-21', '2025-05-28', '2025-05-30'])
    parser.add_argument('--max-rounds', type=int, default=10)
    parser.add_argument('--label', default='cap10')
    args = parser.parse_args()
    if not 6 <= args.max_rounds <= 20:
        parser.error('The bounded trial requires 6..20 total restoration rounds.')
    if not args.label.replace('_', '').isalnum():
        parser.error('label must contain only letters, digits and underscores')
    day = args.day
    output = REPO / 'dayahead/artifacts/v40d_ac_restoration' / args.label / day
    output.mkdir(parents=True, exist_ok=False)
    cps = list((REPO / CACHE_ROOT / 'V40B/restoration').glob(f'*/{day}/B2/ROUND_05.json'))
    if len(cps) != 1:
        raise RuntimeError('EXPECTED_ONE_BASELINE_CHECKPOINT')
    cp = cps[0]
    initial = read(cp)
    protected = {str(cp): sha(cp)}
    for entry in initial['case_files']:
        path = REPO / entry['relative_path']
        if sha(path) != entry['sha256']:
            raise RuntimeError('BASELINE_FILE_DRIFT:' + str(path))
        protected[str(path)] = entry['sha256']
    execution = read(REPO / 'dayahead/artifacts/v40b_v40a_may_launch/V40B_EXECUTION_FREEZE.json')
    for rel in execution['source_files']:
        path = REPO / rel
        protected[str(path)] = sha(path)
    atomic_json(output / 'TRIAL_CONTRACT.json', {
        'schema': 'V40D_RESTORATION_CAP_TRIAL_V1', 'day': day, 'case': 'B2',
        'max_rounds': args.max_rounds, 'baseline_round': 5,
        'baseline_checkpoint': str(cp), 'baseline_checkpoint_sha256': sha(cp),
        'authorization': 'User requested pausing May and repairing restoration on 2026-09-06.',
        'scientific_revision': True, 'May_failure_informed_development': True,
        'voltage_limits': [0.95, 1.05], 'margins_changed': False,
        'route_search_calls': 0, 'production_outputs_overwritten': False,
        'script_sha256': sha(Path(__file__)), 'protected_files': protected,
    })
    started = time.perf_counter()
    print(f'{day}: loading frozen inputs', flush=True)
    aidc = build_day(REPO, day, 'B0')
    _, electrical = load_day_context(REPO, day)
    _, _, route_table, _ = daily_traffic_authority(
        REPO, REPO / CACHE_ROOT / 'traffic', PHASE, day, {'status': 'PASS', 'May_numeric_reads_before_admission': 0},
    )
    trajectory = MessTrajectory(tuple(_restore_slots(initial['trajectory_slots'])))
    signature = _discrete_signature(trajectory)
    cuts = [restoration_cut_from_payload(c) for c in initial['cuts']]
    margins = read(REPO / 'dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_CUT_VALIDATION.json')['margins']
    rows = []
    try:
        frozen = frozen_trajectory(day, 'B2', aidc, trajectory, round_index=5)
        fresh = run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY, context=electrical,
                                 voltage=electrical.voltage, trajectory=frozen, output=output / 'initial_fresh')
        for key in ['Vmin_pu', 'Vmax_pu', 'voltage_violation_count', 'rho_max_AC']:
            if abs(float(fresh.summary[key]) - float(initial['result']['Fresh'][key])) > 1e-10:
                raise RuntimeError('INITIAL_FRESH_REPLAY_MISMATCH:' + key)
        for k in range(6, args.max_rounds + 1):
            if not fresh.summary['physical_violation']:
                break
            before = time.perf_counter()
            print(f'{day}: round {k}/{args.max_rounds}; voltage violations={fresh.summary["voltage_violation_count"]}', flush=True)
            atomic_json(output / 'STATUS.json', {'status': 'RUNNING', 'round': k, 'max_rounds': args.max_rounds,
                        'stage': 'P_Q_RESTORATION', 'updated_utc': datetime.now(timezone.utc).isoformat()})
            generated, audit = local_fresh_ac_restoration_cuts(
                source_repo=SOURCE_DATA_REPOSITORY, electrical=electrical, voltage=electrical.voltage,
                frozen=frozen, fresh=fresh, violations=extract_ac_violations(fresh), iteration_index=k, margins=margins,
            )
            cuts.extend(generated)
            full = solve_fixed_discrete_recourse(repo=REPO, case='B2', aidc=aidc, electrical=electrical,
                        route_table=route_table, service_to_pcc=_service_mapping(), selected_trajectory=trajectory,
                        restoration_cuts=cuts)
            trajectory = full.trajectory
            if _discrete_signature(trajectory) != signature:
                raise RuntimeError('ROUTE_CHANGED')
            physics = validate_physics(trajectory)
            if physics['status'] != 'PASS':
                raise RuntimeError('PHYSICS_FAILURE:' + str(physics))
            frozen = frozen_trajectory(day, 'B2', aidc, trajectory, round_index=k)
            fresh = run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY, context=electrical,
                        voltage=electrical.voltage, trajectory=frozen, output=output / f'round_{k:02d}_fresh')
            row = {'round': k, 'Fresh': fresh.summary, 'solver_status': full.solver_status,
                   'objective': full.objective, 'solver_seconds': full.solve_seconds,
                   'wallclock_seconds': time.perf_counter() - before, 'new_cuts': len(generated),
                   'total_cuts': len(cuts), 'physics': physics, 'discrete_signature': signature,
                   'derivative_anchor_error': audit['maximum_anchor_reproduction_error_pu']}
            rows.append(row)
            atomic_json(output / f'ROUND_{k:02d}.json', {'status': 'FRESH_COMPLETE', 'day': day, 'case': 'B2',
                        'restoration_round': k, 'trajectory_slots': [r.to_dict() for r in trajectory.slots],
                        'cuts': [c.payload() for c in cuts], 'runtime_rows': rows,
                        'arithmetic': list(full.restoration_cut_arithmetic), 'result': row})
            print(json.dumps({'day': day, **{key: row[key] for key in ['round', 'solver_status', 'wallclock_seconds']},
                  'Vmin': fresh.summary['Vmin_pu'], 'Vmax': fresh.summary['Vmax_pu'],
                  'violations': fresh.summary['voltage_violation_count']}), flush=True)
        unchanged = all(sha(Path(p)) == value for p, value in protected.items())
        result = {'status': 'PASS' if not fresh.summary['physical_violation'] and unchanged else 'FAIL',
                  'day': day, 'case': 'B2', 'total_rounds': rows[-1]['round'] if rows else 5,
                  'Fresh': fresh.summary, 'production_unchanged': unchanged,
                  'physics': validate_physics(trajectory), 'routes_unchanged': _discrete_signature(trajectory) == signature,
                  'route_search_calls': 0, 'wallclock_seconds': time.perf_counter() - started, 'rounds': rows}
        atomic_json(output / 'RESULT.json', result)
        atomic_json(output / 'STATUS.json', {key: result[key] for key in ['status', 'day', 'total_rounds', 'production_unchanged']})
        print('RESULT ' + json.dumps({k: v for k, v in result.items() if k not in ['rounds', 'Fresh']}), flush=True)
    finally:
        electrical.voltage.close()
        electrical.current.close()


if __name__ == '__main__':
    main()

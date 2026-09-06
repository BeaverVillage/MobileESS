"""May-01 B0/B1 segment counterfactual; no policy solve or MESS search."""
from pathlib import Path
import inspect
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, reference
from .authority import REL, OLD, initialize, context
from .canonical import import_frozen, identities, planning_power, terminal, terminal_audit, wan_audit, require
from .b3 import bind_b1


def prepare(repo):
    from dayahead.v38.authority import load_wan_authority
    from dayahead.v40a.grid import evaluate_grid, controls_from_trajectory
    from dayahead.v40d_actual.physical_audit import c1_recalculation
    repo = Path(repo).resolve(); root = initialize(repo); dst = root / 'smoke/2025-05-01'
    dst.mkdir(parents=True, exist_ok=True); old = repo / OLD / 'smoke/2025-05-01'
    write_json(root / 'EXECUTION_AUTHORIZATION.json', {'B2_B3_AUTHORIZED': 'NO', 'FULL_MAY_AUTHORIZED': 'NO',
        'V40G_ACTUAL_SCIENCE_INTERPRETATION': 'HOLD', 'authorized_counterfactual': ['2025-05-01 B0', '2025-05-01 B1']})
    ctx = context(repo); wan = load_wan_authority(repo)
    jobs = {c: import_frozen(read(old / 'PRE_MESS_JOBS.json')[c]) for c in ('B0', 'B1')}
    write_json(dst / 'PRE_MESS_JOBS.json', jobs)
    reference_jobs = import_frozen(read(root / 'common_service/COMMON_B0_REFERENCE_JOBS.json'))
    planning = {}; terminals = {}
    try:
        weather = pd.read_parquet(next(p for p in ctx.input_shas if p.endswith('gfs_d1_weather.parquet')))
        for case in ('B0', 'B1'):
            power = planning_power(jobs[case], ctx)
            compare = {}
            with np.load(old / (case + '_PRE_MESS_AIDC.npz')) as prior:
                for k in power:
                    compare[k] = {'bit_identical': np.array_equal(power[k], prior[k]), 'max_error': float(np.max(abs(power[k] - prior[k])))}
            np.savez_compressed(dst / (case + '_PRE_MESS_AIDC.npz'), **power)
            grid = evaluate_grid(ctx.coefficients, controls_from_trajectory(ctx.coefficients, power['pcc'], ()), ctx.nodes)
            require(grid['status'] == 'PASS', 'CANONICAL_PLANNING_GRID_FAIL')
            write_json(dst / (case + '_CORRECTED_PLANNING_GATE.json'), grid)
            audit = terminal_audit(reference_jobs, jobs[case])
            terminals[case] = [terminal(r) for r in jobs[case]]
            c1 = c1_recalculation(repo, {'IT': power['it'], 'PCC_P': power['pcc'], 'PCC_Q': power['qcc']}, weather)
            c1['thermal_input'] = 'FROZEN_GFS_D1_WEATHER'
            planning[case] = {'status': 'PASS', **identities(jobs[case]), 'prior_array_comparison': compare,
                'terminal_audit': audit, 'WAN': wan_audit(jobs[case], wan), 'independent_C1': c1,
                'grid': grid, 'planning_optimize_calls': 0}
        bind_b1(old / 'JOINT_AIDC/ACCEPTED_AIDC.json', old / 'B1_PRE_MESS_AIDC.npz', ctx, dst / 'B3_A0_STATIC_REUSE')
    finally:
        ctx.electrical.voltage.close(); ctx.electrical.current.close()
    migrations = []
    for row in jobs['B1']:
        if not row['migration_selected']: continue
        a, b = row['compute_segments']; e = row['migration_events'][0]; g = row['requested_GPU']
        compute = g * sum(s['end'] - s['start'] for s in (a, b)); required = g * row['safe_duration_slots']
        migrations.append({'job_uid': row['job_uid'], 'requested_GPU': g, 'source_site': a['site'], 'destination_site': b['site'],
            'source_compute_interval': [a['start'], a['end']], 'checkpoint': e['checkpoint'],
            'interruption_interval': [e['interruption_start'], e['interruption_end']],
            'transfer_interval': [e['transfer_start'], e['transfer_end']], 'restart_interval': [e['ready'], e['restart_end']],
            'destination_compute_interval': [b['start'], b['end']], 'total_compute_GPU_slots': compute,
            'common_T_DA_required_GPU_slots': required, 'difference': compute - required,
            'payload_bytes': e['payload_bytes'], 'fixed_path_id': e['fixed_path_id'], 'terminal': terminal(row)})
    require(len(migrations) == 10 and all(r['difference'] == 0 for r in migrations), 'TEN_MIGRATION_SERVICE_AUDIT')
    write_json(root / 'MIGRATION_10_SEGMENT_AUDIT.json', migrations)
    pd.DataFrame([{k: v for k, v in r.items() if k != 'terminal'} for r in migrations]).to_csv(root / 'MIGRATION_10_SEGMENT_AUDIT.csv', index=False)
    write_json(root / 'TERMINAL_PLANNING_SEGMENTS.json', terminals)
    write_json(root / 'PLANNING_SEGMENT_POWER_GATE.json', {'status': 'PASS', 'cases': planning})
    write_json(dst / 'V40GS_PRE_MESS_INTEGRATED_GATE.json', {'CASE_SEMANTICS_GATE': 'PASS', 'cases': ['B0', 'B1'],
        'B0_reference_decision_preserved': True, 'B1_accepted_decision_preserved': True, 'A0_optimize_calls': 0})
    print('SEGMENT PREPARE PASS: 10 migrations; 0 compute GPU-slot difference; B1/A0 exact reuse', flush=True)


def physical(repo):
    from dayahead.v40e import smoke as previous
    repo = Path(repo).resolve(); root = repo / REL; out = root / 'smoke/2025-05-01'
    require(not any((out / c / 'CORRECTED_ACTUAL_RESULT.json').exists() for c in ('B0', 'B1')), 'PRESERVE_COMPLETED_SEGMENT_PHYSICS')
    src = inspect.getsource(previous.b0_b1).replace('V40E_', 'V40GS_')
    src = src.replace('from dayahead.v40d_actual.job_replay import replay_jobs,validate_jobs',
        'from dayahead.v40d_actual.job_replay import validate_jobs\n    from dayahead.v40g_segments.actual import replay_jobs')
    src = src.replace('from dayahead.v40d_actual.power_replay import power_from_execution', 'from dayahead.v40g_segments.actual import power_from_execution')
    src = src.replace('from dayahead.v40d_actual.capacity_audit import write_runtime_audits', 'from dayahead.v40g_segments.actual import write_runtime_audits')
    src = src.replace("'accepted_A0_assignment_and_WAN','checks')",
        "'accepted_A0_assignment_and_WAN','checks','common_terminal_obligation','compute_segments','actual_compute_segments','frozen_WAN_transfer','migration_events','terminal_segment_state')")
    # Before either Fresh or Actual is reachable, reconstruct and certify the
    # loaded numeric arrays from the frozen canonical job segments again.
    anchor = "    ids=tuple(sorted(MESS_INITIAL));"
    validation = "    from dayahead.v40g_segments.canonical import planning_power, require\n    for c in ('B0','B1'):\n        rebuilt=planning_power(jobs[c],context)\n        for key in rebuilt:require(np.array_equal(rebuilt[key],arrays[c][key]),'FRESH_CANONICAL_ARRAY_DRIFT:'+key)\n"
    require(anchor in src, 'PHYSICAL_ADAPTER_ANCHOR')
    src = src.replace(anchor, validation + anchor)
    ns = dict(previous.__dict__); ns['REL'] = REL; ns['planning_context'] = lambda r, d: context(r)
    exec(compile(src, '<V40G_canonical_segment_counterfactual>', 'exec'), ns)
    write_json(root / 'PHYSICAL_RUNNER_LINEAGE.json', {'original_source': reference(Path(inspect.getsourcefile(previous.b0_b1))),
        'adapted_source': src, 'electrical_physics_changed': False, 'same_frozen_decisions': True,
        'all_power_bound_to_canonical_segments': True, 'Actual_optimization_forbidden': True, 'B2_B3_reachable': False})
    ns['b0_b1'](repo)


if __name__ == '__main__':
    import sys
    {'prepare': prepare, 'physical': physical}[sys.argv[1]](Path.cwd())

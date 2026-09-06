"""Independent evaluator for the existing B1 choices and five V41 priorities."""
from collections import defaultdict
import numpy as np
from dayahead.v40g.domain import options, Option, deviation
from dayahead.v40g_segments.canonical import import_frozen, planning_power
from dayahead.v40a.grid import evaluate_grid, controls_from_trajectory
from .reserve import require, diagnostics, OBJECTIVE_HIERARCHY


def evaluate(reference, selected, context):
    refs = {r['job_uid']: r for r in reference}; choices = {r['job_uid']: r for r in selected}
    require(set(refs) == set(choices) and len(refs) == len(reference) == len(selected), 'OBJECTIVE_UID_AXIS')
    groups = defaultdict(list)
    for uid, row in sorted(refs.items()):
        opts = options(row, context.capacity, context.wan, context.elapsed)
        costs = tuple(deviation(row, opt) for opt in opts)
        key = (row['requested_GPU'], row['safe_duration_slots'], opts, costs,
               uid if any(o.migrated for o in opts) else '', row['AIDC_site'] if row['state_at_issue'] == 'RUNNING' else '')
        groups[key].append(uid)
    migration = 0; dev = 0; tie = 0; components = []
    for i, key in enumerate(sorted(groups, key=lambda k: tuple(groups[k]))):
        for uid in groups[key]:
            row = choices[uid]
            if row.get('migration_selected'):
                active = [t + 24 for t, b in enumerate(row['frozen_WAN_transfer']['bytes_by_slot']) if b]
                opt = Option(row['AIDC_site'], row['start_slot'], row['end_slot'],
                             row['migration_checkpoint_slot'], min(active), max(active) + 1)
            else:
                opt = Option(row['AIDC_site'], row['start_slot'], row['end_slot'])
            require(opt in key[2], 'OBJECTIVE_DECISION_OUTSIDE_B1_DOMAIN:' + uid)
            k = key[2].index(opt)
            migration += int(opt.migrated); dev += key[3][k]; tie += (i + 1) * (k + 1)
            components.append(dict(job_id=uid, cohort_index=i, option_index=k,
                migration_count=int(opt.migrated), reference_schedule_deviation=key[3][k], tie_break=(i+1)*(k+1)))
    power = planning_power(import_frozen(selected), context)
    controls = controls_from_trajectory(context.coefficients, power['pcc'], ())
    grid = evaluate_grid(context.coefficients, controls, context.nodes)
    reserve = diagnostics(context.v41_ml_snapshot, context.capacity, power['gpu'])
    return dict(OBJECTIVE_VECTOR=[grid['rho_max'], reserve['mean_xi_GPUh'], migration, dev, tie],
        objective_hierarchy=list(OBJECTIVE_HIERARCHY), grid=grid, reserve_diagnostics=reserve,
        job_objective_components=components,
        active_weighted_sum=False, scalar_penalty_coefficient=None,
        AIDC_energy_kWh=float(power['pcc'].sum() * .25), GPU_slots=int(power['gpu'].sum()),
        objective_terms_not_in_authoritative_hierarchy=['energy_cost', 'compute_cost', 'scalar_SLA_debt_penalty'])

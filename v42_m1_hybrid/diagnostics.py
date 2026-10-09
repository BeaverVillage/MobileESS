"""Read-only physical observations; point diagnostics are not global proofs."""
from collections import Counter
from fractions import Fraction
import numpy as np
from v42_m1_research.check_ub import dispatch_difference, physical_replay
from v42_unified.audit import ROOT, write
from .case import REPORTS
from .neighborhood import grid_candidates


def inspect(case, point, decomp):
    point = np.asarray(point, dtype=np.float64)
    lifted = case.lift(point)
    full = case.original_A
    activity = np.asarray(full @ lifted).ravel()
    rhs = case.original_d['rhs']; senses = case.original_d['sense']
    names = case.original_d['row_names']
    observed_slack = np.where(senses == '<', rhs-activity,
                             np.where(senses == '>', activity-rhs, np.abs(activity-rhs)))
    wanted = {'NormalAmps', 'line_thermal_face', 'transformer_kVA', 'voltage_lower',
              'voltage_upper', 'PCS16', 'soc_balance', 'soc_terminal', 'terminal_location'}
    families = Counter(str(n).split('[', 1)[0] for n in names)
    observations = {}
    for family in sorted(wanted):
        axis = np.asarray([i for i, n in enumerate(names) if str(n).split('[', 1)[0] == family], dtype=np.int64)
        if not len(axis):
            continue
        top = axis[np.argsort(observed_slack[axis])[:12]]
        observations[family] = dict(rows=len(axis), observed_near_active_rows=int(np.sum(observed_slack[axis] <= 1e-7)),
            smallest_observed_slack=[dict(original_row=int(i), name=str(names[i]),
                binary64_activity=float(activity[i]), binary64_rhs=float(rhs[i]),
                binary64_slack=float(observed_slack[i])) for i in top])
    coupling_families = Counter(str(case.d['row_names'][i]).split('[', 1)[0] for i in decomp.coupling_rows)
    targets, grid = grid_candidates(case, point, ROOT / 'docs/v42_m1_joint_gap_research/GRID_ROW_PQ_PROJECTION_PROOF.json')
    receipt = dict(PASS=True, case_sha=case.case_sha,
        physical_replay=physical_replay(case, lifted),
        original_fleet_dispatch_change=dispatch_difference(case, case.point, point),
        original_full_row_families=dict(families), coupling_row_families=dict(coupling_families),
        accepted_point_grid_and_PCS_observations=observations,
        exact_source_projected_line_same_dispatch=grid['source_rows'],
        signed_candidate_targets_at_accepted_point=targets,
        row_slacks_are_binary64_point_diagnostics_not_exact_global_certificates=True,
        projected_line_requirements_are_same_dispatch_only_not_global_LB=True,
        full_model_replay_and_exact_bound_authority='INDEPENDENT_FINAL_VERIFICATION.json',
        physical_coupling_that_limits_integer_hull_global_LB='NOT_PROVEN_WITHOUT_COMPLETED_INTEGER_PRICING_CERTIFICATES_AND_ABLATION',
        individual_vehicle_convex_hull_is_insufficient='NOT_PROVEN',
        Native_optimize_calls=0)
    if not receipt['physical_replay']['PASS']:
        raise ValueError('ACCEPTED_POINT_PHYSICAL_DIAGNOSTIC_REPLAY_FAILED')
    write(REPORTS / 'FULL96_PHYSICAL_DIAGNOSTICS.json', receipt)
    return receipt

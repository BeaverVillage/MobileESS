"""Opt-in offline interpretation of existing signed-PQ/SOC/rebound scores.

No new scorer physics, wider Beam, solver, route elimination or UB claim.
The current operational candidate generator is untouched.
"""
from collections import Counter,defaultdict
import numpy as np


def candidate_metrics(candidate,critical_rows,*,near_margin=.025):
    baseline=np.asarray([r["current_loading"] for r in critical_rows],dtype=float)
    impact=np.asarray(candidate["signed_critical_impact"],dtype=float)
    rebound=np.asarray(candidate["charge_rebound_risk"],dtype=float)
    if impact.shape!=baseline.shape or rebound.shape!=baseline.shape or not np.isfinite(np.r_[baseline,impact,rebound]).all():
        raise ValueError("MESS_LOOKAHEAD_LITERAL_EXISTING_CRITICAL_VECTOR_AXIS_REQUIRED")
    prediction=baseline+impact+rebound
    moves=candidate["original_moves"];arrival=min((m["connect"] for m in moves),default=None)
    departure=min((m["depart"] for m in moves),default=None)
    slots=np.asarray([r["slot"] for r in critical_rows]);near=baseline>=baseline.max()-near_margin
    early=near & (slots<arrival) if arrival is not None else np.zeros(len(slots),dtype=bool)
    best=int(np.argmax(prediction));base_best=int(np.argmax(baseline))
    md=critical_rows[best]["metadata"];before=critical_rows[base_best]["metadata"]
    short=float(candidate.get("lookahead",{}).get("terminal_recovery_shortfall",0.))
    path_charge=np.asarray(candidate.get("lookahead",{}).get("charge_rebound",np.zeros(len(slots))),dtype=float)
    if path_charge.shape!=baseline.shape:raise ValueError("MESS_EXISTING_SOC_RECHARGE_VECTOR_AXIS_REQUIRED")
    existing=float(candidate["Minimax_heuristic_score"])
    return dict(unit=candidate["unit"],path_signature=candidate["path_signature"],MOVE_count=candidate["MOVE_count"],
        first_departure=departure,first_new_destination_connect=arrival,
        destinations=[m["destination"] for m in moves],existing_Minimax_score=existing,
        actual_logged_score_minus_reconstructed_global_peak=existing-float(prediction.max()),
        reconstructed_existing_signed_PQ_plus_rebound_peak=float(prediction.max()),
        critical_before=dict(asset=before.get("asset"),phase=before.get("phase"),slot=int(slots[base_best])),
        predicted_new_critical=dict(asset=md.get("asset"),phase=md.get("phase"),slot=int(slots[best])),
        critical_asset_phase_slot_switch=(before.get("asset"),before.get("phase"),int(slots[base_best]))!=(md.get("asset"),md.get("phase"),int(slots[best])),
        near_critical_rows_before_destination_connect=int(early.sum()),
        early_near_critical_peak_after_heuristic=float(prediction[early].max()) if early.any() else None,
        nonrelieved_early_near_critical_rows=int(np.count_nonzero(early & (impact>=-1e-9))),
        maximum_positive_rebound=float(max(0.,rebound.max())),sum_positive_rebound=float(np.maximum(rebound,0).sum()),
        existing_path_charge_rebound_max=float(max(0.,path_charge.max())),
        existing_path_charge_rebound_sum=float(np.maximum(path_charge,0).sum()),
        existing_path_charge_rebound_already_in_signed_impact_not_added_twice=True,
        travel_energy_kWh=float(candidate.get("travel_energy_kWh",0.)),
        terminal_recovery_shortfall=short,
        experimental_lexicographic_rank=[existing,float(prediction[early].max()) if early.any() else float(prediction.max()),
            float(np.maximum(impact[near]+rebound[near],0).sum()),short,float(np.maximum(rebound,0).sum())],
        late_destination_cannot_affect_prior_slots=True,
        predeparture_origin_PQ_redispatch_and_joint_vehicles_can_still_help=True,
        lateness_is_not_a_hard_infeasibility_or_bound_proof=True,
        signed_PQ_SOC_rebound_were_already_in_predecessor=True,
        individual_forced_route_FULL_UB=None,Native_optimize_calls=0)


def duplicate_groups(records):
    exact=Counter((r["unit"],r["path_signature"]) for r in records)
    protected={(r["unit"],r["path_signature"]) for r in records
        if r["MOVE_count"]==0 or float(r.get("actual_DIRECT_selected_lambda",0.))>.5}
    groups=defaultdict(list)
    for r in records:
        key=(r["unit"],r["MOVE_count"],tuple(r["destinations"]),r["first_departure"])
        groups[key].append(r["path_signature"])
    return dict(candidate_records=len(records),unique_exact_unit_paths=len(exact),
        repeated_exact_path_occurrences=sum(n-1 for n in exact.values()),
        repeated_exact_unit_paths=sum(n>1 for n in exact.values()),
        protected_STAY_or_selected_unit_paths=len(protected),
        protected_repeat_occurrences=sum(n-1 for k,n in exact.items() if k in protected),
        exploratory_repeat_occurrences=sum(n-1 for k,n in exact.items() if k not in protected),
        protected_repetitions_are_required_incumbent_STAY_retention_not_candidate_waste=True,
        departure_destination_MOVE_groups=len(groups),
        distinct_unit_paths_per_coarse_group=[dict(unit=k[0],MOVE_count=k[1],destinations=list(k[2]),
            first_departure=k[3],unique_paths=len(set(v)),appearances=len(v)) for k,v in groups.items()],
        coarse_group_is_not_an_exact_route_equivalence_class=True,
        no_candidate_pruned_from_offline_duplicates=True)


def offline_outcome_scope(pool_outcomes):
    values=np.asarray([float(r["actual_joint_UB"]) for r in pool_outcomes])
    return dict(pools=len(values),distinct_joint_FULL_UBs=len(set(map(float,values))),
        independent_forced_route_UB_labels_available=False,
        score_to_FULL_UB_predictive_improvement="NOT_CERTIFIED",
        correlation=None,correlation_reason="POOL_OUTCOME_CONSTANT" if len(set(values))<=1 else "INDIVIDUAL_ROUTE_OUTCOMES_NOT_OBSERVED",
        restriction="Joint outcome belongs to the whole four-vehicle pool; never assign it to every alternative route.",
        new_UB=None,Native_optimize_calls=0)

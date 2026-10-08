"""Read-only UB interpretation after completed neighborhoods; Native optimize=0.

This module owns no solver, callback, parameter, ledger or research model.
Physical and objective changes are observed jointly; individual causal effects
remain NOT_PROVEN without separate counterfactual optimization.
"""
import hashlib
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from v42_unified.audit import ROOT, M_HEAD, git, write
from .check_ub import validate_candidate, vector_sha


WINDOWS = {'INITIAL_0_15': (0, 16), 'PRECRITICAL_0_65': (0, 66),
           'CRITICAL_66_95': (66, 96), 'FULL_0_95': (0, 96)}


def read_point(path):
    with np.load(path, allow_pickle=False) as z:
        key = 'point' if 'point' in z.files else 'x'
        return z[key].copy()


def _receipt(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        # No polling or reading an incomplete result as a completed experiment.
        return None


def _source(path):
    return dict(path=str(path), SHA256=hashlib.sha256(Path(path).read_bytes()).hexdigest())


def _completed_json(path):
    raw = git('show', f'{M_HEAD}:{path}')
    return json.loads(raw), dict(head=M_HEAD, path=path, SHA256=hashlib.sha256(raw).hexdigest(),
                                 access='completed immutable Git object')


def summarize(case, point):
    original = case.lift(point)
    values = dict(zip(map(str, case.original_d['names']), map(float, original)))
    sites, initial, arcs, battery, _ = case.graph
    units = {}
    for u in sorted(initial):
        chosen = [k for k in range(len(arcs)) if values.get(f'arc[{u},{k}]', 0.) > .5]
        path = [arcs[k] for k in chosen]
        modes = [values[f'charge_mode[{u},{t}]'] for t in range(96)]
        charge = np.asarray([sum(values.get(f'Pch[{u},{s},{t}]', 0.) for s in sites) for t in range(96)])
        discharge = np.asarray([sum(values.get(f'Pdis[{u},{s},{t}]', 0.) for s in sites) for t in range(96)])
        reactive = np.asarray([sum(values.get(f'Q[{u},{s},{t}]', 0.) for s in sites) for t in range(96)])
        soc = np.asarray([values[f'SOC[{u},{t}]'] for t in range(97)])
        connected, route_id = [], []
        travel = np.zeros(96)
        moves = []
        for a in path:
            if a[-1] is not None:
                r = a[-1]
                travel[a[1]] += r.energy_kwh
                moves.append(dict(route_id=r.route_id, source=a[0], destination=a[2],
                                  depart=a[1], arrive=r.arrive, connect=a[3],
                                  energy_kwh=r.energy_kwh, driving_slots=r.arrive-a[1],
                                  connection_wait_slots=a[3]-r.arrive,
                                  unavailable_slots=a[3]-a[1]))
        for t in range(96):
            matches = [a for a in path if a[1] <= t < a[3]]
            if len(matches) != 1:
                raise ValueError('ATTRIBUTION_REQUIRES_ONE_REAL_PATH_PER_UNIT_PER_SLOT')
            a = matches[0]
            connected.append(a[0] if a[-1] is None else None)
            route_id.append(None if a[-1] is None else a[-1].route_id)
        windows = {}
        for label, (a, b) in WINDOWS.items():
            # All quantities retain their original physical units.
            E_ch = float(battery.dt_hours*np.sum(charge[a:b]))
            E_dis = float(battery.dt_hours*np.sum(discharge[a:b]))
            E_move = float(np.sum(travel[a:b]))
            energy_delta = battery.eta_charge*E_ch-E_dis/battery.eta_discharge-E_move
            windows[label] = dict(charge_AC_kWh=E_ch, discharge_AC_kWh=E_dis,
                stored_charge_kWh=battery.eta_charge*E_ch,
                SOC_draw_discharge_kWh=E_dis/battery.eta_discharge,
                net_P_injection_kWh=E_dis-E_ch, travel_energy_kWh=E_move,
                Q_signed_kvar_hours=float(battery.dt_hours*np.sum(reactive[a:b])),
                Q_absolute_kvar_hours=float(battery.dt_hours*np.sum(abs(reactive[a:b]))),
                SOC_start_kWh=float(soc[a]), SOC_end_kWh=float(soc[b]),
                energy_balance_difference_kWh=float(soc[b]-soc[a]-energy_delta),
                connected_slots=sum(s is not None for s in connected[a:b]),
                unavailable_slots=sum(s is None for s in connected[a:b]),
                max_charge_kw=float(np.max(charge[a:b], initial=0.)),
                max_discharge_kw=float(np.max(discharge[a:b], initial=0.)),
                max_absolute_Q_kvar=float(np.max(abs(reactive[a:b]), initial=0.)))
        role_sites = {}
        for t in range(66, 96):
            s = connected[t]
            if s is None:
                continue
            record = role_sites.setdefault(s, dict(connected_slots=[], charge_AC_kWh=0.,
                         discharge_AC_kWh=0., Q_signed_kvar_hours=0., Q_absolute_kvar_hours=0.))
            record['connected_slots'].append(t)
            record['charge_AC_kWh'] += float(battery.dt_hours*charge[t])
            record['discharge_AC_kWh'] += float(battery.dt_hours*discharge[t])
            record['Q_signed_kvar_hours'] += float(battery.dt_hours*reactive[t])
            record['Q_absolute_kvar_hours'] += float(battery.dt_hours*abs(reactive[t]))
        units[u] = dict(initial_site=initial[u], move_count=len(moves), moves=moves,
                        windows=windows, critical_service_roles=role_sites,
                        SOC_min_kWh=float(soc.min()), SOC_max_kWh=float(soc.max()),
                        SOC_terminal_kWh=float(soc[-1]),
                        SOC_at_slots_kWh={str(t): float(soc[t]) for t in (0, 16, 66, 79, 81, 85, 95, 96)},
                        raw_slot_series=dict(Pch_kw=charge.tolist(), Pdis_kw=discharge.tolist(),
                            Q_kvar=reactive.tolist(), P_net_kw=(discharge-charge).tolist(),
                            SOC_kWh=soc.tolist(), charge_mode=modes,
                            connected_site=connected, transit_route_id=route_id,
                            travel_energy_departure_kWh=travel.tolist()))
    return dict(point_sha256=vector_sha(point), objective=float(case.d['objective']@point+float(case.d['constant'])),
                units=units, fleet_move_count=sum(v['move_count'] for v in units.values()),
                fleet_travel_energy_kWh=sum(v['windows']['FULL_0_95']['travel_energy_kWh'] for v in units.values()),
                fleet_unavailable_slots=sum(v['windows']['FULL_0_95']['unavailable_slots'] for v in units.values()),
                original_96_slot_energy_route_coupling_preserved=True)


def compare(case, before, after, old_summary=None, new_summary=None):
    old = old_summary or summarize(case, before)
    new = new_summary or summarize(case, after)
    changes = {'charge_mode': [], 'node_activity': [], 'route_flow': []}
    for j, name in enumerate(map(str, case.d['names'])):
        family = name.split('[', 1)[0]
        if family in changes and before[j] != after[j]:
            changes[family].append(dict(name=name, before=float(before[j]), after=float(after[j]),
                                        slot=int(name[:-1].split(',')[-1]) if family != 'route_flow' else None))
    deltas = {}
    for u in old['units']:
        a, b = old['units'][u], new['units'][u]
        am = {r['route_id']: r for r in a['moves']}
        bm = {r['route_id']: r for r in b['moves']}
        windows = {}
        for window in WINDOWS:
            windows[window] = {k: b['windows'][window][k]-a['windows'][window][k]
                              for k in a['windows'][window]}
        changed_locations = [dict(slot=t, before=a['raw_slot_series']['connected_site'][t],
                                  after=b['raw_slot_series']['connected_site'][t]) for t in range(96)
                             if a['raw_slot_series']['connected_site'][t] != b['raw_slot_series']['connected_site'][t]]
        deltas[u] = dict(added_moves=[bm[k] for k in sorted(set(bm)-set(am))],
                         removed_moves=[am[k] for k in sorted(set(am)-set(bm))],
                         changed_connection_slots=changed_locations, windows_delta=windows,
                         SOC_at_slots_delta_kWh={k: b['SOC_at_slots_kWh'][k]-a['SOC_at_slots_kWh'][k]
                                               for k in a['SOC_at_slots_kWh']})
    exchanges = []
    for t in range(66, 96):
        before_roles, after_roles = {}, {}
        for u in old['units']:
            for roles, summary in ((before_roles, old), (after_roles, new)):
                s = summary['units'][u]['raw_slot_series']['connected_site'][t]
                if s is not None:
                    roles.setdefault(s, []).append(u)
        for s in set(before_roles) & set(after_roles):
            if before_roles[s] != after_roles[s]:
                exchanges.append(dict(slot=t, site=s, before_units=before_roles[s], after_units=after_roles[s]))
    delta_rho = old['objective']-new['objective']
    return dict(before_objective=old['objective'], after_objective=new['objective'],
                observed_rho_improvement=delta_rho,
                mode_change_count=len(changes['charge_mode']), node_activity_change_count=len(changes['node_activity']),
                route_flow_raw_change_count=len(changes['route_flow']),
                route_flow_material_change_count=sum(abs(r['before']-r['after']) > 1e-8 for r in changes['route_flow']),
                early_mode_changes=[r for r in changes['charge_mode'] if r['slot'] < 66],
                critical_mode_changes=[r for r in changes['charge_mode'] if 66 <= r['slot'] <= 95],
                discrete_changes=changes, per_unit= deltas,
                critical_same_time_site_role_substitutions=exchanges,
                fleet_travel_energy_delta_kWh=new['fleet_travel_energy_kWh']-old['fleet_travel_energy_kWh'],
                fleet_unavailable_slot_delta=new['fleet_unavailable_slots']-old['fleet_unavailable_slots'],
                same_actual_route_pattern=all(not r['added_moves'] and not r['removed_moves'] for r in deltas.values()),
                causal_decomposition='NOT_PROVEN',
                route_vs_mode_vs_PQ_vs_SOC_individual_contribution='NOT_PROVEN',
                route_grid_benefit_minus_energy_connection_cost_causal_balance='NOT_PROVEN',
                interpretation='Joint feasible plans compared descriptively; no mixed-coordinate counterfactual is admitted as feasible.')


def historical_comparison():
    root = 'docs/v42_m1_gap_rootcause_20261007/'
    local, s1 = _completed_json(root+'UB_LOCAL_NEIGHBORHOOD_RESULT.json')
    bits, s2 = _completed_json(root+'UB_DISCRETE_CHANGE_AUDIT.json')
    fixed, s3 = _completed_json(root+'UB_FIXED_DISCRETE_REOPT.json')
    r183, s4 = _completed_json('docs/v42_m1_route_mode_benders_20261008/VALID_UB_CHANGE.json')
    replay, s5 = _completed_json('docs/v42_m1_route_mode_benders_20261008/BEST_FULL_REPLAY.json')
    return dict(PR169=dict(baseline_UB=local['baseline_UB'], validated_UB=local['new_valid_UB'],
                          changed_bits=bits['changed_by_family'],
                          original_integer_replay_PASS=local['original_all_integer_replay']['PASS'],
                          physical_replay_PASS=local['physical_replay']['PASS'],
                          observed_fixed_assignment_recourse_gain=fixed['delta_UB'],
                          success_observation='Joint mode/location/movement/dispatch changes improved the static incumbent.',
                          individual_causal_contributions='NOT_PROVEN', sources=[s1, s2, s3]),
                PR183=dict(baseline_UB=r183['old_UB'], validated_UB=r183['new_UB'],
                           changed_mode_bits=r183['changed_charge_mode_bits'],
                           changed_node_bits=r183['changed_node_activity_bits'],
                           changed_route_flow_bits=r183['changed_integer_route_flow_bits'],
                           changed_binary_names=r183['changed_binary_names'],
                           original_matrix_and_physical_replay_PASS=replay['PASS'],
                           success_observation='One early mode decision changed with the same route pattern and joint continuous P/Q/SOC reoptimization.',
                           recourse_speed_generalization='NOT_PROVEN; one new assignment was historically TIME_LIMIT.',
                           pure_mode_causal_contribution_without_recourse='NOT_PROVEN', sources=[s4, s5]))


def active_grid_summary(case, point, *, diagnostic_epsilon=1e-7):
    """Descriptive active original grid rows, never a new lower-bound proof."""
    started = perf_counter()
    rho = next(j for j, n in enumerate(case.d['names']) if str(n) == 'rho_max')
    residual = case.A@point-case.d['rhs']
    names = list(map(str, case.d['names']))
    families = np.asarray([str(n).split('[', 1)[0] for n in case.d['row_names']])
    grid = ('line_thermal_face', 'voltage_lower', 'voltage_upper', 'transformer_kVA', 'NormalAmps')
    senses = case.d['sense']
    signed = np.where(senses == '>', -residual, residual)
    counts = {f: dict(total_rows=int(np.count_nonzero(families == f)),
                      near_active_rows=int(np.count_nonzero((families == f) & (abs(signed) <= diagnostic_epsilon))))
              for f in grid}
    rho_coefficient = case.A[:, rho].toarray().ravel()
    row_ids = np.flatnonzero(np.isin(families, grid) & (senses == '<') & (rho_coefficient < 0))
    required = point[rho]+residual[row_ids]/(-rho_coefficient[row_ids])
    selected = row_ids[np.argsort(-required, kind='stable')[:12]]
    rows = []
    active_line_times = {}
    active_line_axes = {}
    for i in np.flatnonzero((families == 'line_thermal_face') & (abs(signed) <= diagnostic_epsilon)):
        a, b = case.A.indptr[i:i+2]
        tt, axes = set(), set()
        for j in case.A.indices[a:b]:
            name = names[j]
            if name.startswith('response_line_'):
                fields = name.split('[', 1)[1][:-1].split(',')
                tt.add(int(fields[0])); axes.add(fields[1])
        for t in tt:
            active_line_times[str(t)] = active_line_times.get(str(t), 0)+1
        for axis in axes:
            active_line_axes[axis] = active_line_axes.get(axis, 0)+1
    for i in selected:
        a, b = case.A.indptr[i:i+2]
        times, responses, sites = set(), set(), set()
        sparse_terms = []
        for j, w in zip(case.A.indices[a:b], case.A.data[a:b]):
            name = names[j]
            sparse_terms.append(dict(column=int(j), name=name, coefficient=float(w)))
            if '[' not in name:
                continue
            family, fields = name.split('[', 1)
            fields = fields[:-1].split(',')
            if family.startswith('response_'):
                times.add(int(fields[0]))
                responses.add(family+':'+fields[1])
            elif family.startswith('injection_'):
                times.add(int(fields[-1])); sites.add(fields[0])
            elif family in ('Pch', 'Pdis', 'Q'):
                times.add(int(fields[-1])); sites.add(fields[1])
        rows.append(dict(row=int(i), family=str(families[i]), slots=sorted(times),
            response_axes=sorted(responses), service_sites_direct_in_row=sorted(sites),
            RHS=float(case.d['rhs'][i]), sense=str(senses[i]),
            native_raw_signed_residual=float(signed[i]), rho_coefficient=float(rho_coefficient[i]),
            rho_required_at_this_same_dispatch=float(point[rho]+residual[i]/(-rho_coefficient[i])),
            exact_original_sparse_coefficients=sparse_terms))
    return dict(performed=True, point_sha256=vector_sha(point), rho=float(point[rho]),
                formulation='frozen exact-equivalent C3A grid rows; original full matrix is independently replayed separately',
                original_grid_family_activity=counts, most_constraining_rho_rows=rows,
                active_line_thermal_slot_histogram=active_line_times,
                active_line_response_axis_histogram=active_line_axes,
                active_line_precritical_row_count=sum(v for k, v in active_line_times.items() if int(k) < 66),
                active_line_critical_row_count=sum(v for k, v in active_line_times.items() if 66 <= int(k) <= 95),
                original_FULL_NormalAmps_rows=int(sum(str(n).split('[', 1)[0] == 'NormalAmps' for n in case.original_d['row_names'])),
                normalamps_authority_unchanged=True,
                active_row_diagnostic_epsilon=diagnostic_epsilon,
                epsilon_is_descriptive_only_scientific_tolerance_unchanged=True,
                row_requirements_are_same_dispatch_values_not_global_LB=True,
                different_plans_have_different_continuous_dispatch=True,
                causal_role_of_grid_active_set_shift='NOT_PROVEN', additional_Native_Runtime=0.,
                active_grid_analysis_wall_seconds=perf_counter()-started)


def _strict_replay(case, point):
    replay = validate_candidate(case, point)
    exact = bool(replay['C3A'].get('exact_binary_0_1') and replay['original_full_matrix'].get('exact_binary_0_1'))
    return dict(source_scientific_tolerance_replay=replay,
                strict_all_original_discrete_exact_0_1=exact,
                strict_full_integer_and_original_physics_PASS=bool(replay['PASS'] and exact),
                physical_validation_tolerances_changed=False)


def _best_completed(case, reports, label):
    result = _receipt(reports/(label+'_RESULT.json'))
    if result is None or result.get('case_sha') != case.case_sha:
        return None
    candidates = []
    sources = []
    for path in sorted(reports.glob(label+'_CAPTURE_*.npz'))+[reports/(label+'_RAW_POINT.npz')]:
        if not path.exists():
            continue
        point = read_point(path)
        checked = _strict_replay(case, point)
        sources.append(dict(**_source(path), **checked))
        if checked['strict_full_integer_and_original_physics_PASS']:
            candidates.append((checked['source_scientific_tolerance_replay']['objective'], point, path, checked))
    if not candidates:
        return dict(result=result, status='NO_STRICT_VALIDATED_RAW_POINT', sources=sources)
    candidates.sort(key=lambda r: r[0])
    objective, point, path, checked = candidates[0]
    return dict(result=result, status='COMPLETED_STRICT_INTEGER_PHYSICAL_PASS', objective=objective,
                point=point, point_source=_source(path), validation=checked, sources=sources)


def finalize(case, runpath):
    """One bounded read; U2 is included only after its completed result exists."""
    started = perf_counter()
    runpath = Path(runpath).resolve()
    if runpath.drive.upper() != 'D:' or not runpath.is_relative_to(ROOT.resolve()):
        raise ValueError('D_V42_ATTRIBUTION_RUN_PATH_REQUIRED')
    reports = ROOT/'docs/v42_m1_joint_gap_research'
    baseline_validation = _strict_replay(case, case.point)
    if not baseline_validation['strict_full_integer_and_original_physics_PASS']:
        raise ValueError('ATTRIBUTION_BASELINE_MUST_BE_STRICT_ORIGINAL_INTEGER_VALIDATED')
    baseline = summarize(case, case.point)
    stages = dict(BASELINE_PR188=dict(summary=baseline, validation=baseline_validation,
                                    active_grid=active_grid_summary(case, case.point)))
    comparisons = {}
    points = {'BASELINE_PR188': case.point}
    for label in ('U1', 'U2'):
        stage = _best_completed(case, reports, label)
        if stage is None:
            stages[label] = dict(status='NOT_FINISHED_OR_RESULT_NOT_AVAILABLE', native_reexecuted=False)
            continue
        point = stage.pop('point', None)
        if point is not None:
            points[label] = point
            stage['summary'] = summarize(case, point)
            stage['active_grid'] = active_grid_summary(case, point)
            comparisons['BASELINE_TO_'+label] = compare(case, case.point, point, baseline, stage['summary'])
        stages[label] = stage
    if 'U1' in points and 'U2' in points:
        comparisons['U1_TO_U2'] = compare(case, points['U1'], points['U2'], stages['U1']['summary'], stages['U2']['summary'])
    recourse = _receipt(reports/'FIXED_RECOURSE_RESULT.json')
    if recourse and recourse.get('case_sha') == case.case_sha:
        recourse = dict(performed=True, original_assignment_fixed=True,
            native_Runtime_recorded_preexisting=recourse['native_Runtime'],
            baseline_UB=recourse['before_validated_UB'], final_validated_UB=recourse['best_validated_UB'],
            observed_admitted_UB_improvement=recourse['UB_improvement'],
            raw_recourse_objective=recourse['restricted_neighborhood_ObjBound'],
            strict_original_replay_result_recorded=recourse['final_original_replay_PASS'],
            bound_not_global=True, interpretation='Baseline fixed assignment showed no material admitted improvement; this does not isolate new-route recourse contribution.')
    else:
        recourse = dict(performed=False, status='NOT_RUN_OR_RESULT_NOT_AVAILABLE')
    best_label = min(points, key=lambda k: float(case.d['objective']@points[k]+float(case.d['constant'])))
    result = dict(schema='V42_M1_UB_MODE_ROUTE_ATTRIBUTION_V1', performed=True,
        case_sha=case.case_sha, runpath=str(runpath), Native_optimize_calls=0,
        additional_Native_Runtime=0., additional_Native_Work=0.,
        original_4_units_24_sites_96_slots=True, original_matrix_and_physics_unchanged=True,
        existing_experiment_solver_callback_parameters_ledger_modified=False,
        attribution_state='COMPLETED_NEIGHBORHOOD_RESULTS' if 'U2' in points else 'COMPLETED_U1_ONLY_U2_PENDING',
        point_stages=stages, comparisons=comparisons,
        fixed_assignment_recourse_observation=recourse,
        best_strict_validated_stage=best_label, best_strict_validated_UB=float(case.d['objective']@points[best_label]+float(case.d['constant'])),
        historical_success_comparison=historical_comparison(),
        causal_questions=dict(early_charging_caused_late_discharge_gain='NOT_PROVEN',
            one_or_two_mode_bit_counterfactual='NOT_RUN',
            four_fleet_role_swap_individual_grid_benefit='NOT_PROVEN',
            continuous_recourse_of_new_route_with_other_modes_fixed='NOT_RUN',
            dispatch_benefit_net_of_travel_connection_loss='NOT_PROVEN'),
        interpretation='Actual feasible-plan differences are measured. Separate counterfactual optima and individual effects were not solved or certified.',
        analysis_wall_seconds=perf_counter()-started)
    write(reports/'UB_MODE_ROUTE_ATTRIBUTION.json', result)
    return result

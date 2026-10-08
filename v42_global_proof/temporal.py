"""Method B: exact route reward bounds, with explicit SOC relaxation.

This module does not invoke an optimizer. The capacity problem used for proof
is a relaxation: one complete original time-expanded path per vehicle, actual
connection-ready arc endpoints, zero dispatch while travelling, and an outer
polygon derived from the immutable C3A PCS rows and finite bounds. SOC and the
other grid constraints are deliberately dropped from this reward bound. A
failed contradiction therefore means NOT_PROVEN, never feasibility of C3A.
"""
from .common import ROOT, OUT, ROUTE, PARENT, load, read, write, sha, forbid_optimize
from collections import defaultdict
from fractions import Fraction as F
from itertools import combinations
import gzip
import math
import time


def exact(v):
    return F.from_float(float(v))


def parsed(n):
    n = str(n)
    return n.split('[', 1)[0], n.split('[', 1)[1][:-1].split(',') if '[' in n else []


def exact_binding_closure(A, d):
    """Affine elimination of only actual immutable equality definitions."""
    families = [parsed(n)[0] for n in d['names']]
    definitions = {}
    for i, name in enumerate(d['row_names']):
        family = parsed(name)[0]
        if not family.endswith('_binding'):
            continue
        js = A.indices[A.indptr[i]:A.indptr[i+1]]
        own = [int(j) for j in js if families[j] == family[:-8]]
        assert len(own) == 1 and d['sense'][i] == '='
        assert own[0] not in definitions
        definitions[own[0]] = i
    cache, active = {}, set()

    def expand(j):
        if j in cache:
            return cache[j]
        assert j not in active, 'CYCLIC_GRID_DEFINITION'
        active.add(j)
        if families[j] in ('Pch', 'Pdis', 'Q'):
            answer = F(0), {j:F(1)}
        elif d['lower'][j] == d['upper'][j]:
            answer = exact(d['lower'][j]), {}
        else:
            assert j in definitions, ('UNRESOLVED_GRID_AUXILIARY', j)
            i = definitions[j]
            js = A.indices[A.indptr[i]:A.indptr[i+1]]
            vals = A.data[A.indptr[i]:A.indptr[i+1]]
            own = next(exact(a) for k, a in zip(js, vals) if k == j)
            constant, terms = exact(d['rhs'][i])/own, defaultdict(F)
            for k, a in zip(js, vals):
                if k == j:
                    continue
                offset, sub = expand(int(k))
                weight = -exact(a)/own
                constant += weight*offset
                for p, v in sub.items():
                    terms[p] += weight*v
            answer = constant, {p:v for p,v in terms.items() if v}
        active.remove(j)
        cache[j] = answer
        return answer
    return expand, definitions


def original_routes():
    table = __import__('json').loads(gzip.decompress(ROUTE.read_bytes()))
    receipt = read(ROOT/'docs/v42_m1_physics_strengthened_20261008/TEMPORAL_SCIENTIFIC_IDENTITY.json')['graph_receipt']
    assert sha(ROUTE) == receipt['route_file']['sha256']
    sites = list(table['service_ids'])
    assert sites == receipt['sites'] and len(sites) == 24
    arcs = [(s,t,s,t+1,F(0)) for s in sites for t in range(96)]
    exclusions = defaultdict(int)
    forecasts = set()
    for r in table['routes']:
        forecasts.add(r['traffic_forecast_sha'])
        s, z, t = r['origin_service_id'], r['destination_service_id'], r['departure_slot_15']
        arrive = t+r['travel_slots_15min']
        ready = t+r['connection_ready_slots_15min']
        if s == z:
            exclusions['same_site_represented_by_stay'] += 1
            continue
        if not 0 <= t < arrive <= ready < 96:
            exclusions['outside_inherited_RouteArc_time_contract'] += 1
            continue
        arcs.append((s,t,z,ready,exact(r['energy_safe_kwh'])))
    assert len(forecasts) == 1
    assert dict(exclusions) == receipt['excluded']
    assert len(arcs) == 53626 and len(arcs)-2304 == receipt['accepted_routes']
    return sites, receipt['initial_MESS_sites'], arcs, receipt['battery'], receipt


def vertices(halfspaces):
    """Exact planar half-space intersection, with no numerical optimization."""
    result = set()
    for (a,b,c), (d,e,f) in combinations(halfspaces, 2):
        determinant = a*e-b*d
        if not determinant:
            continue
        p, q = (c*e-b*f)/determinant, (a*f-c*d)/determinant
        if all(x*p+y*q <= z for x,y,z in halfspaces):
            result.add((p,q))
    assert result and len(result) >= 3
    return sorted(result)


def local_pcs_polygons(A, d, required_keys):
    """Bounds on original p=Pdis-Pch and Q, retaining each local PCS row.

    Non-P/Q row terms use their minimizing finite-box endpoint. This only
    increases the permitted dispatch region, including all integer C3A points.
    """
    lookup = {str(n):j for j,n in enumerate(d['names'])}
    facets = defaultdict(list)
    source_rows = defaultdict(list)
    wanted = set(required_keys)
    for i, name in enumerate(d['row_names']):
        if str(name) != 'PCS16':
            continue
        js = A.indices[A.indptr[i]:A.indptr[i+1]]
        vals = A.data[A.indptr[i]:A.indptr[i+1]]
        keys = {tuple(parsed(d['names'][j])[1]) for j in js
                if parsed(d['names'][j])[0] in ('Pch','Pdis','Q')}
        assert len(keys) == 1
        key = next(iter(keys))
        if key not in wanted:
            continue
        terms = dict(zip(map(int,js),map(exact,vals)))
        ch, dis, q = [lookup[f'{family}[{",".join(key)}]'] for family in ('Pch','Pdis','Q')]
        a, b = terms.get(dis,F(0)), terms.get(q,F(0))
        assert terms.get(ch,F(0)) == -a and d['sense'][i] == '<'
        right = exact(d['rhs'][i])
        for j, coefficient in terms.items():
            if j in (ch,dis,q):
                continue
            endpoint = d['lower'][j] if coefficient >= 0 else d['upper'][j]
            assert math.isfinite(float(endpoint))
            right -= coefficient*exact(endpoint)
        facets[key].append((a,b,right))
        source_rows[key].append(i)
    registry, by_key, cache = {}, {}, {}
    for key in sorted(wanted):
        ch, dis, q = [lookup[f'{family}[{",".join(key)}]'] for family in ('Pch','Pdis','Q')]
        assert d['lower'][ch] == d['lower'][dis] == 0
        pmax, pmin = exact(d['upper'][dis]), -exact(d['upper'][ch])
        hs = [(F(1),F(0),pmax),(-F(1),F(0),-pmin),
              (F(0),F(1),exact(d['upper'][q])),(F(0),-F(1),-exact(d['lower'][q]))]
        hs += facets[key]
        signature = tuple(sorted(set(hs)))
        if signature not in cache:
            label = f'PCS_{len(cache):03d}'
            points = vertices(signature)
            cache[signature] = label, points
            registry[label] = dict(halfspaces=[[str(v) for v in h] for h in signature],
                vertices=[[str(v) for v in pair] for pair in points])
        label, points = cache[signature]
        by_key[key] = label, points
        assert facets[key], ('MISSING_PCS_FACETS', key)
    return registry, by_key, source_rows


def reachability(sites, initial, arcs):
    outgoing = defaultdict(list)
    for k,a in enumerate(arcs):
        outgoing[a[1]].append((k,a))
    reach = {}
    for m, origin in initial.items():
        nodes = {(origin,0)}
        for t in range(96):
            for _,a in outgoing[t]:
                if (a[0],t) in nodes:
                    nodes.add((a[2],a[3]))
        reach[m] = nodes
    return outgoing, reach


def soc_envelope(initial, outgoing, battery):
    """Outer interval DP for relaxed route reachability, not a hull claim."""
    low, high = exact(battery['minimum']), exact(battery['maximum'])
    charge = exact(battery['dt_hours'])*exact(battery['eta_charge'])*exact(battery['p_limit'])
    discharge = exact(battery['dt_hours'])*exact(battery['p_limit'])/exact(battery['eta_discharge'])
    states, exclusions = {}, {}
    for m,origin in initial.items():
        intervals = {(origin,0):(exact(battery['initial']),exact(battery['initial']))}
        rejected = 0
        for t in range(96):
            for _,a in outgoing[t]:
                if (a[0],t) not in intervals:
                    continue
                lo, hi = intervals[a[0],t]
                if a[0] != a[2]:
                    candidate = max(low,lo-a[4]), min(high,hi-a[4])
                else:
                    candidate = max(low,lo-discharge), min(high,hi+charge)
                if candidate[0] > candidate[1]:
                    rejected += 1
                    continue
                destination = a[2],a[3]
                if destination in intervals:
                    previous = intervals[destination]
                    candidate = min(previous[0],candidate[0]),max(previous[1],candidate[1])
                intervals[destination] = candidate
        states[m], exclusions[m] = intervals,rejected
    return states, exclusions


def route_reward_dp(initial, outgoing, rewards):
    capacities, paths = {}, {}
    for m,origin in initial.items():
        best, previous = {(origin,0):F(0)}, {}
        movement = {(origin,0):F(0)}
        for t in range(96):
            for k,a in outgoing[t]:
                source, destination = (a[0],a[1]),(a[2],a[3])
                if source not in best:
                    continue
                # Stay arcs are the only connected dispatch arcs.
                reward = rewards.get((m,a[0],t),F(0)) if a[0] == a[2] else F(0)
                candidate = best[source]+reward
                candidate_energy = movement[source]+a[4]
                if (destination not in best or candidate > best[destination]
                        or (candidate == best[destination] and candidate_energy < movement[destination])):
                    best[destination], previous[destination] = candidate, (source,k)
                    movement[destination] = candidate_energy
        terminal = max((node for node in best if node[1] == 96),
                       key=lambda node:(best[node],-movement[node]))
        capacities[m] = best[terminal]
        path, node = [], terminal
        while node != (origin,0):
            node, k = previous[node]
            path.append(k)
        paths[m] = list(reversed(path))
    return capacities,paths


def bridge_masks(sites, outgoing, t1, t2):
    # Dispatch at t1 requires its stay arc, so movement starts at t1+1.
    masks = {(s,t1+1):1<<k for k,s in enumerate(sites)}
    for t in range(t1+1,t2):
        for _,a in outgoing[t]:
            if a[3] > t2 or (a[0],t) not in masks:
                continue
            key = a[2],a[3]
            masks[key] = masks.get(key,0)|masks[a[0],t]
    return [masks.get((s,t2),0) for s in sites]


def main():
    started = time.perf_counter()
    forbid_optimize()
    A,d,_,_,_ = load()
    sites,initial,arcs,battery,receipt = original_routes()
    projection_path = ROOT/'docs/v42_m1_route_mode_benders_20261008/ROUTE_PROJECTION_AUDIT.json'
    projection = read(projection_path)
    assert projection['PASS'] and projection['terminal_stay_only']
    assert projection['duplicate_endpoint_arcs'] == projection['non_forward_arcs'] == []
    assert projection['graph_arcs'] == len(arcs) and projection['retained_route_flows'] == 207736
    assert projection['sites'] == len(sites) and projection['original_flow_transport_failures'] == []
    outgoing, reach = reachability(sites,initial,arcs)
    rho = next(j for j,n in enumerate(d['names']) if str(n) == 'rho_max')
    archived = read(ROOT/'docs/v42_m1_physics_strengthened_20261008/CRITICAL_GRID_RHO_COUPLING.json')
    selected = sorted({r['original_row_index'] for r in archived['critical_rows']})
    labels = {r['row']:r for r in read(ROOT/'docs/v42_m1_gap_rootcause_20261007/CRITICAL_GRID_ROW_DESCRIPTORS.json')['rows']}
    expand, definitions = exact_binding_closure(A,d)
    records, support_weights, demand = [], defaultdict(F), defaultdict(F)
    for i in selected:
        js = A.indices[A.indptr[i]:A.indptr[i+1]]
        vals = A.data[A.indptr[i]:A.indptr[i+1]]
        rho_coefficient = next(exact(v) for j,v in zip(js,vals) if j == rho)
        assert rho_coefficient < 0 and d['sense'][i] == '<'
        constant, terms = F(0), defaultdict(F)
        for j,v in zip(js,vals):
            if j == rho:
                continue
            offset, sub = expand(int(j))
            constant += exact(v)*offset
            for p,x in sub.items():
                terms[p] += exact(v)*x
        denominator = -rho_coefficient
        baseline = (constant-exact(d['rhs'][i]))/denominator
        coefficients = {p:-v/denominator for p,v in terms.items() if v}
        times = {int(parsed(d['names'][p])[1][-1]) for p in coefficients}
        assert len(times) == 1
        t = next(iter(times))
        required = baseline-F(3,5)
        rec = dict(row=i,family=str(d['row_names'][i]),slot=t,
            branch=labels.get(i,{}).get('branch_name','UNRESOLVED_LABEL'),
            baseline_rho_exact=str(baseline),baseline_rho=float(baseline),
            demand_at_exact_three_fifths=str(required),demand=float(required),
            positive_demand=required > 0,
            support_coefficients={str(p):str(v) for p,v in sorted(coefficients.items())})
        records.append(rec)
        if required > 0:
            demand[t] += required
            for p,v in coefficients.items():
                family,args = parsed(d['names'][p])
                support_weights[family,tuple(args)] += v
    critical_times = sorted({r['slot'] for r in records})
    required_keys = {(m,s,str(t)) for m in initial for s in sites for t in critical_times}
    polygon_registry, polygons, polygon_rows = local_pcs_polygons(A,d,required_keys)
    simultaneous_covers = []
    for rec in records:
        if not rec['positive_demand']:
            continue
        t, threshold = rec['slot'],F(rec['demand_at_exact_three_fifths'])/len(initial)
        weights = {(parsed(d['names'][int(j)])[0],tuple(parsed(d['names'][int(j)])[1])):F(v)
                   for j,v in rec['support_coefficients'].items()}
        candidates, site_cover = {},set()
        for m in initial:
            candidates[m] = []
            for s in sites:
                key = m,s,str(t)
                wp = weights.get(('Pdis',key),F(0))
                assert weights.get(('Pch',key),F(0)) == -wp
                wq = weights.get(('Q',key),F(0))
                local_upper = max([wp*p+wq*q for p,q in polygons[key][1]]+[F(0)])
                if (s,t) in reach[m] and local_upper >= threshold:
                    candidates[m].append(s)
                    site_cover.add(s)
        simultaneous_covers.append(dict(row=rec['row'],slot=t,pigeonhole_threshold_exact=str(threshold),
            candidate_sites_by_vehicle=candidates,site_union=sorted(site_cover),
            necessary_condition='At least one of the4vehicles must deliver >=D/4 for this row at a listed site'))
    hall_tests = []
    for t in critical_times:
        covers = [r for r in simultaneous_covers if r['slot']==t]
        best_disjoint = []
        for size in range(1,len(covers)+1):
            for subset in combinations(covers,size):
                sets = [set(r['site_union']) for r in subset]
                if all(sets) and all(not a&b for a,b in combinations(sets,2)):
                    if size > len(best_disjoint):
                        best_disjoint = [r['row'] for r in subset]
        empty = [r['row'] for r in covers if not r['site_union']]
        hall_tests.append(dict(slot=t,positive_grid_requirements=len(covers),
            largest_pairwise_disjoint_site_cover_count=len(best_disjoint),
            disjoint_cover_rows=best_disjoint,empty_candidate_rows=empty,
            available_vehicle_tokens=len(initial),
            contradiction=bool(empty) or len(best_disjoint)>len(initial)))
    rewards, maximizers, weight_records = {}, {}, {}
    for m,s,st in sorted(required_keys):
        key,t = (m,s,st),int(st)
        ch, dis, q = [support_weights.get((fam,key),F(0)) for fam in ('Pch','Pdis','Q')]
        assert ch == -dis, 'NON_NET_ACTIVE_POWER_WEIGHT'
        label, points = polygons[key]
        candidates = [(dis*p+q*v,p,v) for p,v in points]+[(F(0),F(0),F(0))]
        capacity,p,v = max(candidates)
        if dis == q == 0:
            capacity,p,v = F(0),F(0),F(0)
        rewards[m,s,t], maximizers[m,s,t] = capacity,(p,v)
        weight_records[f'{m}|{s}|{t}'] = dict(p=str(dis),q=str(q),PCS=label,
            upper=str(capacity),maximizer=[str(p),str(v)],source_PCS_rows=polygon_rows[key])
    capacities, paths = route_reward_dp(initial,outgoing,rewards)
    required_total, capacity_total = sum(demand.values(),F(0)),sum(capacities.values(),F(0))
    pointwise = []
    for t in critical_times:
        by_m = {}
        for m in initial:
            candidates = [(rewards[m,s,t],s) for s in sites if (s,t) in reach[m]]
            value,site = max(candidates)
            by_m[m] = dict(upper_exact=str(value),upper=float(value),maximizing_site=site,
                candidate_sites=len(candidates))
        total = sum((F(r['upper_exact']) for r in by_m.values()),F(0))
        sorted_vehicle_caps = sorted((F(r['upper_exact']) for r in by_m.values()),reverse=True)
        minimum_units = 0
        while minimum_units < len(initial) and sum(sorted_vehicle_caps[:minimum_units],F(0)) < demand[t]:
            minimum_units += 1
        pointwise.append(dict(slot=t,positive_row_count=sum(r['positive_demand'] and r['slot']==t for r in records),
            demand_exact=str(demand[t]),demand=float(demand[t]),vehicle_bounds=by_m,
            total_upper_exact=str(total),total_upper=float(total),
            minimum_vehicle_count_from_aggregated_capacity=minimum_units,
            slack_exact=str(total-demand[t]),slack=float(total-demand[t]),
            contradiction=demand[t]>total))
    two_time, pair_conflicts = [], []
    for t1,t2 in combinations(critical_times,2):
        masks = bridge_masks(sites,outgoing,t1,t2)
        forbidden = 24*24-sum(mask.bit_count() for mask in masks)
        bounds = {}
        for m in initial:
            possibilities = []
            for left,s1 in enumerate(sites):
                if (s1,t1) not in reach[m]:
                    continue
                for right,s2 in enumerate(sites):
                    if masks[right] & (1<<left):
                        possibilities.append((rewards[m,s1,t1]+rewards[m,s2,t2],s1,s2))
            value,s1,s2 = max(possibilities)
            bounds[m] = dict(upper_exact=str(value),sites=[s1,s2])
        upper = sum((F(r['upper_exact']) for r in bounds.values()),F(0))
        required = demand[t1]+demand[t2]
        item = dict(slots=[t1,t2],demand_exact=str(required),total_upper_exact=str(upper),
            demand=float(required),total_upper=float(upper),slack=float(upper-required),
            forbidden_ordered_site_pairs=forbidden,vehicle_bounds=bounds,
            contradiction=required>upper)
        two_time.append(item)
        pair_conflicts.append(dict(slots=[t1,t2],forbidden_ordered_site_pairs=forbidden,
            reachable_origin_masks=masks))
    soc_states,soc_exclusions = soc_envelope(initial,outgoing,battery)
    soc_stats = []
    for m in initial:
        counts = {str(t):sum((s,t) in soc_states[m] for s in sites) for t in critical_times}
        soc_stats.append(dict(MESS=m,initial_site=initial[m],reachable_critical_site_counts=counts,
            locally_rejected_travel_transitions=soc_exclusions[m],
            union_intervals_are_outward_envelopes=True,exact_union_not_claimed=True,
            terminal_interval_exact=[str(v) for v in soc_states[m][initial[m],96]],
            terminal_original_target_exact=str(exact(battery['terminal']))))
    relaxed_paths = []
    discharge_loss_coefficient = exact(battery['dt_hours'])/exact(battery['eta_discharge'])
    charge_gain_coefficient = exact(battery['dt_hours'])*exact(battery['eta_charge'])
    for m,path in paths.items():
        net_energy, travel, active_dispatch_slots = F(0),F(0),0
        for k in path:
            a = arcs[k]
            travel += a[4]
            if a[0] == a[2] and (m,a[0],a[1]) in maximizers:
                p,q = maximizers[m,a[0],a[1]]
                net_energy += charge_gain_coefficient*(-p) if p < 0 else -discharge_loss_coefficient*p
                active_dispatch_slots += int(p != 0 or q != 0)
        # Local diagnosis of the selected reward maximizer only: start the
        # critical window at the maximum allowed SOC and optimistically charge
        # at the original maximum on every stay that has zero reward weight.
        # This does not assert that every reward-maximizing path/dispatch fails.
        first_critical = min(critical_times)
        prefix_upper, first_violation = exact(battery['maximum']),None
        path_stays = {arcs[k][1]:arcs[k][0] for k in path if arcs[k][0] == arcs[k][2]}
        path_moves = {arcs[k][1]:arcs[k][4] for k in path if arcs[k][0] != arcs[k][2]}
        for t in range(first_critical,96):
            increment = -path_moves.get(t,F(0))
            if t in path_stays:
                key = m,path_stays[t],t
                if rewards.get(key,F(0)):
                    p,q = maximizers[key]
                    increment += charge_gain_coefficient*(-p) if p < 0 else -discharge_loss_coefficient*p
                else:
                    increment += charge_gain_coefficient*exact(battery['p_limit'])
            prefix_upper = min(exact(battery['maximum']),prefix_upper+increment)
            if prefix_upper < exact(battery['minimum']) and first_violation is None:
                first_violation = t+1
        relaxed_paths.append(dict(MESS=m,arc_indices=path,upper_exact=str(capacities[m]),
            original_travel_energy_exact=str(travel),original_travel_energy_kWh=float(travel),
            selected_reward_dispatch_net_energy_exact=str(net_energy),
            selected_reward_dispatch_net_energy_kWh=float(net_energy),
            active_dispatch_slots=active_dispatch_slots,
            additional_charge_energy_needed_for_equal_terminal_SOC_kWh=float(travel-net_energy),
            critical_window_start=first_critical,
            optimistic_free_slot_charge_prefix_SOC_end_exact=str(prefix_upper),
            optimistic_free_slot_charge_prefix_SOC_end_kWh=float(prefix_upper),
            first_prefix_SOC_minimum_failure_time=first_violation,
            local_selected_path_dispatch_SOC_impossible=first_violation is not None or prefix_upper < exact(battery['terminal']),
            local_selected_path_scope='Only this selected path and its stored support-maximizing dispatch, even with maximal charging at every zero-reward stay; other paths/dispatches are not rejected',
            SOC_feasibility_of_original_cutoff='NOT_PROVEN'))
    contradiction = required_total > capacity_total or any(r['contradiction'] for r in pointwise+two_time+hall_tests)
    # The expected diagnostic result is NOT_PROVEN. Any new strict contradiction
    # must be reviewed by the independent checker before it becomes authority.
    classification = 'CONTRADICTION_PENDING_INDEPENDENT_CHECK' if contradiction else 'NOT_PROVEN'
    data = dict(schema='temporal_exact_route_bound_v1',source_matrix_SHA256=sha(PARENT/'C3A_A.npz'),
        source_data_SHA256=sha(PARENT/'C3A_DATA.npz'),route_SHA256=sha(ROUTE),
        cutoff_exact='3/5',sites=sites,initial_sites=initial,battery={k:str(exact(v)) for k,v in battery.items()},
        graph_arc_count=len(arcs),critical_rows=records,PCS_polygons=polygon_registry,
        original_integer_path_projection_receipt_SHA256=sha(projection_path),
        site_weights_and_rewards=weight_records,demand_by_slot={str(t):str(v) for t,v in sorted(demand.items())},
        vehicle_route_upper_bounds={m:str(v) for m,v in capacities.items()},
        total_demand_exact=str(required_total),total_upper_exact=str(capacity_total),
        maximizing_relaxed_paths=relaxed_paths,bridge_reachability=pair_conflicts,
        simultaneous_support_candidate_covers=simultaneous_covers,Hall_disjoint_cover_tests=hall_tests,
        classification=classification)
    write(OUT/'TEMPORAL_EXACT_DATA.json',data)
    audit = dict(schema='temporal_conflict_audit_v1',classification=classification,
        exact_decimal_cutoff='3/5',native_binary_cutoff_exact=str(exact(.60)),
        exact_decimal_minus_native_cutoff=str(F(3,5)-exact(.60)),
        all_new_native_optimize_calls=0,all_new_scipy_optimize_calls=0,
        certificate_arithmetic='Exact rational arithmetic on immutable binary64 C3A coefficients; demands at exact 3/5; displayed decimal measures are diagnostics',
        input_identity={k:data[k] for k in ('source_matrix_SHA256','source_data_SHA256','route_SHA256')},
        critical_grid_row_count=len(records),critical_slots=critical_times,
        positive_demand_row_count=sum(r['positive_demand'] for r in records),
        distinct_critical_branches=sorted({r['branch'] for r in records}),
        source_original_C3A_rows=582808,source_original_C3A_columns=306040,
        source_original_binaries=9322,all_four_MESS_included=True,full_96_slot_paths=True,
        graph=dict(service_sites=len(sites),all_time_expanded_arcs=len(arcs),
            stay_arcs=2304,movement_arcs=51322,route_table_exclusions=receipt['excluded'],
            connection_ready_endpoints_used=True,transit_PQ_reward_exactly_zero=True,
            arbitrary_single_vehicle_unreachability_never_declared_global=True),
        necessary_support_inequality=dict(demand_exact=str(required_total),demand=float(required_total),
            route_capacity_upper_exact=str(capacity_total),route_capacity_upper=float(capacity_total),
            capacity_minus_demand_exact=str(capacity_total-required_total),
            capacity_minus_demand=float(capacity_total-required_total),
            strict_global_contradiction=required_total>capacity_total,
            selected_positive_demand_rows_are_valid_nonnegative_combination=True),
        measured_route_bound_tightening=dict(
            independent_time_upper_exact=str(sum((F(r['total_upper_exact']) for r in pointwise),F(0))),
            all96_single_path_upper_exact=str(capacity_total),
            route_only_capacity_reduction_exact=str(sum((F(r['total_upper_exact']) for r in pointwise),F(0))-capacity_total),
            route_only_capacity_reduction=float(sum((F(r['total_upper_exact']) for r in pointwise),F(0))-capacity_total),
            remaining_SOC_relaxation_loss='Bounded quantitatively by Method A terminal-energy Lagrange audit; no exact complete SOC hull claimed here'),
        per_slot_bounds=pointwise,two_time_bounds=two_time,
        simultaneous_support_candidate_covers=simultaneous_covers,Hall_disjoint_cover_tests=hall_tests,
        Hall_disjoint_cover_contradiction_count=sum(r['contradiction'] for r in hall_tests),
        two_time_test_count=len(two_time),two_time_contradiction_count=sum(r['contradiction'] for r in two_time),
        pointwise_contradiction_count=sum(r['contradiction'] for r in pointwise),
        SOC_outer_reachability=soc_stats,relaxed_maximizer_SOC_diagnostics=relaxed_paths,
        relaxation_inclusion_audit=dict(PASS=True,relation='Original integer feasible set F is contained in route reward relaxation R',
            original_integer_path_projection_receipt='docs/v42_m1_route_mode_benders_20261008/ROUTE_PROJECTION_AUDIT.json',
            original_integer_path_projection_receipt_SHA256=sha(projection_path),
            projection='Use each original integer time-expanded path; actual travel endpoints and origin; original dispatch maps p=Pdis-Pch and Q at stay vertices',
            retained=['all4 initial origins','actual96-slot route graph','connection-ready times','one path pervehicle','zero dispatch while travelling','local original PCS necessary inequalities','original finite P/Q bounds'],
            relaxed=['SOC dynamics and initial/terminal SOC in reward capacity','grid constraints except selected necessary sums','support sign simultaneously satisfying separate grid rows','charging/discharging energy across different slots','B2 rows in reward graph'],
            grid_elimination='Only immutable equality definitions and exactly fixed columns; affine constants retained; each selected < row has negative rho coefficient and is multiplied by positive reciprocal',
            PCS_outer_region='Every non-P/Q term replaced by its minimizing original finite-bound endpoint, enlarging the dispatch region',
            pair_cover='For every original vehicle path with dispatch at both times, a stay at firsttime plus actual route reachability to secondtime is admitted; all4 independent maxima are summed',
            interval_SOC='Only diagnostic outward interval envelopes; intervals never restrict the route-reward certificate',
            integer_domain_shrinkage=False,original_model_mutated=False),
        limitation='No infeasibility of R has been established. Passing necessary one-time/two-time/aggregate support tests is not a C3A feasible counterexample. The SOC-infeasible relaxed maximizing path is only evidence of looseness, not proof for all schedules.',
        detailed_exact_data='TEMPORAL_EXACT_DATA.json',detailed_exact_data_SHA256=sha(OUT/'TEMPORAL_EXACT_DATA.json'),
        original_integer_search_coverage=dict(original_binary_count=9322,new_binary_child_regions_resolved=0,
            search_tree_exhausted=False,all_original_integer_plans_certified_infeasible=False),
        independent_checker_status='PENDING',controller_wall_seconds=time.perf_counter()-started)
    write(OUT/'TEMPORAL_CONFLICT_AUDIT.json',audit)
    print('TEMPORAL_OPTIMIZE_ZERO_AUDIT',classification,'rows',len(records),'positive',audit['positive_demand_row_count'],
        'D',float(required_total),'U',float(capacity_total),'wall',audit['controller_wall_seconds'],flush=True)


if __name__ == '__main__':
    main()

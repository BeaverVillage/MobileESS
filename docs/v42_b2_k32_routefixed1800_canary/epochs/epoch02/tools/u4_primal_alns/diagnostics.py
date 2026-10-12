"""Frozen U4 and K32 signed diagnostics with bounded original-row access.

No Gurobi, scipy FULL CSR, solve, integer rounding, or candidate feasibility
repair occurs here. K32 remains an infeasible-for-FULL diagnostic point.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
import gc
import hashlib
import heapq
import json
from pathlib import Path
import time
import numpy as np
from tools.time_decomposed_lb.grid import SelectiveAuthority, FAMILIES, write, sha
from tools.b2_root_lp_tightening.fractional_grid_oracle import metadata
from tools.u4_primal_alns.verify import load_case, vector_sha, SOURCE, CASE_SHA, SOURCE_SHA
from tools.u4_primal_alns.neighborhood import _signed_ranking

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'docs/v42_b2_u4_primal_alns_600x3'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def physical_summary(case, original):
    names = case.original_d['names']
    units = {}
    for unit in sorted(case.graph[1]):
        columns = {str(n): j for j,n in enumerate(names) if '['+unit+',' in str(n)}
        modes = [(int(n.rsplit(',',1)[-1][:-1]), float(original[j])) for n,j in columns.items()
            if n.startswith('charge_mode[')]
        soc = [(int(n.rsplit(',',1)[-1][:-1]), float(original[j])) for n,j in columns.items()
            if n.startswith('SOC[')]
        ch = sum(float(original[j]) for n,j in columns.items() if n.startswith('Pch['))
        dis = sum(float(original[j]) for n,j in columns.items() if n.startswith('Pdis['))
        q = [float(original[j]) for n,j in columns.items() if n.startswith('Q[')]
        moves = []
        stay = []
        for k, arc in enumerate(case.graph[2]):
            j = columns.get(f'arc[{unit},{k}]')
            if j is not None and original[j] == 1.:
                if arc[-1] is None:
                    stay.append(dict(site=arc[0], slot=arc[1]))
                else:
                    moves.append(dict(arc=k, route_id=str(arc[-1].route_id), source=arc[0],
                        destination=arc[2], depart=arc[1], arrive=int(arc[-1].arrive),
                        connect=arc[3], energy_kwh=float(arc[-1].energy_kwh)))
        units[unit] = dict(initial_site=case.graph[1][unit], selected_move_count=len(moves),
            selected_moves=moves, stay=stay, mode_one_slots=[t for t,v in sorted(modes) if v == 1.],
            mode_count=len(modes), Pch_kW_slot_sum=ch, Pdis_kW_slot_sum=dis,
            charge_AC_kWh=.25*ch, discharge_AC_kWh=.25*dis, abs_Q_kvar_slot_sum=sum(abs(v) for v in q),
            max_abs_Q_kvar=max(map(abs,q)), SOC_min=min(v for t,v in soc), SOC_max=max(v for t,v in soc),
            SOC_initial=dict(soc)[0], SOC_terminal=dict(soc)[96],
            total_travel_kWh=sum(r['energy_kwh'] for r in moves))
    return units


def _recompute_helpers(authority, original):
    result = original.copy()
    done, visiting = set(), set()
    def value(j):
        if j not in authority.helper_defs or j in done:
            return float(result[j])
        require(j not in visiting, 'HELPER_CYCLE')
        visiting.add(j)
        i = authority.helper_defs[j]
        result[j] = float(authority.maps['rhs'][i])-sum(w*value(k) for k,w in authority.terms(i) if k != j)
        visiting.remove(j)
        done.add(j)
        return float(result[j])
    for j in authority.helper_defs:
        value(j)
    return result


def scan(authority, point, coefficients):
    summaries = {f:dict(rows=0, positive_over_1e8=0, maximum_raw_violation=-float('inf'),
        highest_normalized_values=[]) for f in FAMILIES}
    candidates = defaultdict(list)
    for t, ids in sorted(authority.security_by_slot.items()):
        # Source rows are copied in bounded one-slot strips. This is not a
        # scipy CSR allocation or a second FULL sparse matrix.
        lo, hi = min(ids), max(ids)+1
        starts = np.asarray(authority.maps['indptr'][lo:hi+1], dtype=np.int64)
        left, right = int(starts[0]), int(starts[-1])
        terms = authority.maps['data'][left:right]*point[authority.maps['indices'][left:right]]
        require(np.all(np.diff(starts)>0), 'EMPTY_SOURCE_ROW_SCAN')
        activity = np.add.reduceat(terms, starts[:-1]-left)
        for i in ids:
            name = str(authority.maps['row_names'][i]); f = name.split('[',1)[0]
            sign = 1 if authority.maps['sense'][i] == '<' else -1
            raw = sign*(float(activity[i-lo])-float(authority.maps['rhs'][i]))
            source_terms = authority.terms(i)
            rho_c = sum(sign*w for j,w in source_terms if j == authority.rho)
            scale = -rho_c if rho_c < 0 else (float(metadata(name, coefficients)['scale']) if f == 'transformer_kVA' else 1.)
            score = raw/scale
            loading = float(point[authority.rho])+score if rho_c < 0 else None
            s = summaries[f]; s['rows'] += 1; s['positive_over_1e8'] += int(raw > 1e-8)
            s['maximum_raw_violation'] = max(s['maximum_raw_violation'],raw)
            heap = candidates[f]
            if len(heap) < 128 or (score,-i) > heap[0][:2]:
                record = dict(original_row=i, name=name, family=f, slot=t, metadata=metadata(name,coefficients),
                    raw_violation=raw, normalized_violation=score, priority_scale=scale,rho_scaled_loading=loading)
                if len(heap) < 128:
                    heapq.heappush(heap,(score,-i,record))
                else:
                    heapq.heapreplace(heap,(score,-i,record))
        del terms, starts, activity
    for f, heap in candidates.items():
        rows = [entry[2] for entry in heap]
        rows.sort(key=lambda r:(-r['normalized_violation'],r['original_row']))
        summaries[f]['highest_normalized_values'] = rows[:16]
        # Keep only bounded candidates per family after the scan.
        candidates[f] = rows[:128]
    return summaries, candidates


def pcs_vertices(authority):
    ids = [i for i,n in enumerate(authority.maps['row_names']) if str(n).split('[',1)[0] == 'PCS16'][:16]
    require(len(ids) == 16, 'SOURCE_PCS16_MISSING')
    planes = []
    for i in ids:
        row = authority.terms(i)
        p = sum((F(v) for j,v in row if str(authority.maps['names'][j]).startswith('Pdis[')),F(0))
        q = sum((F(v) for j,v in row if str(authority.maps['names'][j]).startswith('Q[')),F(0))
        rhs = F(float(authority.maps['rhs'][i]))-sum((F(v) for j,v in row if
            str(authority.maps['names'][j]).startswith('arc[')), F(0))
        planes.append((p,q,rhs))
    planes += [(F(1),F(0),F(300)),(F(-1),F(0),F(300))]
    vertices = set()
    for i,(a,b,c) in enumerate(planes):
        for p,q,r in planes[:i]:
            det = a*q-b*p
            if det:
                x,y = (c*q-b*r)/det,(a*r-c*p)/det
                if all(s*x+t*y<=u for s,t,u in planes):
                    vertices.add((x,y))
    require(vertices, 'EMPTY_EXACT_PCS_SUPPORT')
    return sorted(vertices), ids


def main():
    started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    case=load_case(native=False)
    original=case.lift(case.point)
    unit_transport_comparison = {}
    for unit in sorted(case.graph[1]):
        with (np.load(ROOT/f'docs/v42_physical_global_lb_pilot/UNIT_{unit}_AXES.npz',allow_pickle=False) as a,
              np.load(ROOT/f'docs/v42_physical_global_lb_pilot/UNIT_{unit}_START.npz',allow_pickle=False) as p):
            ids = a['columns']
            difference = abs(original[ids]-p['point'])
            q = np.array([str(case.original_d['names'][j]).startswith('Q[') for j in ids])
            require(np.array_equal(original[ids[~q]],p['point'][~q]) and np.max(difference[q]) < 1e-10,
                'INHERITED_RAW00_VS_FINAL_NONQ_PHYSICAL_DRIFT:'+unit)
            unit_transport_comparison[unit] = dict(nonQ_bit_equal=True,Q_max_abs_difference=float(np.max(difference[q])),
                same_rho_but_distinct_raw00_vs_final_vector=True,authoritative_point='FINAL_FULL_POINT.npz')
    u4 = physical_summary(case,original)
    kdir=ROOT/'docs/v42_critical_grid_cg/iteration01'
    with np.load(kdir/'JOINT_INCUMBENT.npz',allow_pickle=False) as p:
        joint=p['x'].copy()
    with np.load(kdir/'JOINT_AXES.npz',allow_pickle=False) as a:
        columns=a['columns'].copy()
    kdense=np.zeros_like(case.point); kdense[columns]=joint
    koriginal=case.lift(kdense)
    k32=physical_summary(case,koriginal)
    with np.load(Path(r'D:\v42_svr11_may_20261011_16\models\2025-05-01\COEFFICIENTS.npz'),allow_pickle=False) as z:
        coefficients={k:z[k].copy() for k in ('node_names','branch_names','transformer_ratings')}
    authority=SelectiveAuthority()
    try:
        original=_recompute_helpers(authority,original)
        koriginal=_recompute_helpers(authority,koriginal)
        urows, ucandidates=scan(authority,original,coefficients)
        krows, kcandidates=scan(authority,koriginal,coefficients)
        quota=dict(line_thermal_face=12,transformer_kVA=4,NormalAmps=2,voltage_upper=4,voltage_lower=4)
        selected=[]
        for family, count in quota.items():
            seen=set()
            for r in ucandidates[family]:
                key=(r['slot'],r['metadata']['asset'],r['metadata']['phase'])
                if key in seen: continue
                selected.append(r); seen.add(key)
                if len(seen)>=count: break
        original_names={str(n):j for j,n in enumerate(authority.maps['names'])}
        packets=[]; raw_ids=set()
        for r in selected:
            projected=authority.project(r['original_row'],r['slot'])
            row=dict(name=projected['name'],original_row=r['original_row'],family=r['family'],
                slot=r['slot'],rhs=projected['rhs'], coeff={str(original_names[n]):v for n,v in projected['coeff'].items()},
                priority_scale=str(F(r['priority_scale'])),helper_rows=projected['helper_rows'],
                source_row_sha256=projected['source_row_sha256'], eliminated_constant=projected['eliminated_constant'],
                metadata=r['metadata'],source_sense=projected['original_sense'], source_rhs_hex=projected['original_rhs_hex'])
            packets.append(row); raw_ids.update(projected['helper_rows']);raw_ids.add(r['original_row'])
        vertices,pcs_ids=pcs_vertices(authority);raw_ids.update(pcs_ids)
        raw_rows=[authority.raw(i) for i in sorted(raw_ids)]
        raw_columns={j for row in raw_rows for j,h in row['terms']}
        raw=dict(source=SOURCE_SHA,case_sha=CASE_SHA,source_files=authority.records,rows=raw_rows,
            columns={str(j):dict(name=str(authority.maps['names'][j]), lower_hex=float(authority.maps['lower'][j]).hex(),
                upper_hex=float(authority.maps['upper'][j]).hex(),type=str(authority.maps['types'][j])) for j in sorted(raw_columns)},
            PCS16_original_rows=pcs_ids, Native_optimize_calls=0,FULL_CSR_constructed=False)
        write(OUT/'SIGNED_SELECTION_SOURCE_RAW.json',raw)
        context=dict(source=SOURCE_SHA,case_sha=CASE_SHA,initial_point_sha256=vector_sha(case.point),
            original_rho_column=authority.rho,critical_exact_rows=packets,
            PCS16_vertices_exact=[[str(p),str(q)] for p,q in vertices],
            source_raw_packet_sha256=sha(OUT/'SIGNED_SELECTION_SOURCE_RAW.json'), Native_optimize_calls=0,
            exact_helpers_and_all_source_coefficients_preserved=True,
            current_U4_grid_scan=urows, K32_grid_scan=krows)
        write(OUT/'SIGNED_SELECTION_CONTEXT.json',context)
        ranked=_signed_ranking(case,case.point,context)
        unit_targets={u:next(c for c in ranked if c['unit']==u) for u in sorted(case.graph[1])}
        urank=sorted(unit_targets,key=lambda u:(-unit_targets[u]['score'],u))
        pairs=[(a,b) for i,a in enumerate(urank) for b in urank[i+1:]]
        pairs.sort(key=lambda p:(-sum(unit_targets[u]['score'] for u in p),p))
        n2=[dict(candidate_id=f'N2_{u}_primary', selected_units=[u], variant='primary', requested_cap_seconds=150,
            hamming_radius=48, frozen_signed_score=unit_targets[u]['score'], frozen_target=unit_targets[u]) for u in urank]
        n2 += [dict(candidate_id=f'N2_{u}_expanded', selected_units=[u], variant='expanded', requested_cap_seconds=150,
            hamming_radius=48, frozen_signed_score=unit_targets[u]['score'], frozen_target=unit_targets[u]) for u in urank]
        n3=[dict(candidate_id=f'N3_{a}_{b}',selected_units=[a,b],variant='primary',requested_cap_seconds=200,
            hamming_radius=96,frozen_signed_score=sum(unit_targets[u]['score'] for u in (a,b)),
            frozen_targets=[unit_targets[a],unit_targets[b]]) for a,b in pairs]
        prereg=dict(source=SOURCE_SHA,case_sha=CASE_SHA,initial_point_sha256=vector_sha(case.point),N2=n2,N3=n3,
            Native_optimize_calls=0, finite_policy=True, fixed_radii={'N1':384,'N2':48,'N3':96},
            per_method_cumulative_native_seconds=600, requested_caps={'N1':600,'N2':150,'N3':200},
            score_formula='max(0,current-unit-contribution - signed PCS16 support)/(1+normalized-slack/.01)/(1+ETA/16+travel-kWh/1080)',
            family_ordering='Direct-rho objective rows first; dimensioned hard voltage/current rows retained as signed guards without cross-family score comparison.',
            expanded_policy='After four distinct single-unit primary candidates, try each unit once with16additional slots either side; same48radius, no parameter sweep.',
            no_early_exit_after_one_small_neighborhood=True, independent_starting_U4_for_each_method=True,
            own_validated_center_refresh=True, no_cross_algorithm_seeding=True,
            K32_advice_only_no_UB_or_Global_LB_promotion=True)
        write(OUT/'CANDIDATE_PREREGISTRATION.json',prereg)
        report=dict(PASS=True,source=SOURCE_SHA,case_sha=CASE_SHA,U4_original_physical=u4,
            inherited_UNIT_START_vs_authoritative_FINAL=unit_transport_comparison,
            U4_grid=urows,K32_original_physical=k32,K32_grid=krows,
            K32_integer_incumbent_rho=float(kdense[np.flatnonzero(case.d['names']=='rho_max')[0]]),
            K32_FULL_feasible=False,K32_new_UB=False,K32_new_LB=False,
            K32_incumbent_sha256=sha(kdir/'JOINT_INCUMBENT.npz'),K32_axes_sha256=sha(kdir/'JOINT_AXES.npz'),
            selected_critical_rows=selected,unit_candidate_ranking=[unit_targets[u] for u in urank],
            pair_candidate_ranking=[dict(units=list(p),score=sum(unit_targets[u]['score'] for u in p)) for p in pairs],
            signed_support_is_instantaneous_proxy=True,DAG_eta_is_not_SOC_PCS_grid_feasibility=True,
            full_security_rows_scanned=814560,Native_optimize_calls=0,FULL_CSR_constructed=False,
            initial_point_sha256=vector_sha(case.point),wall_seconds=time.perf_counter()-started)
        write(OUT/'U4_K32_SIGNED_DIAGNOSTICS.json',report)
        print(json.dumps(dict(PASS=True,wall_seconds=report['wall_seconds'],U4={u:{k:v for k,v in s.items() if k not in ('stay','selected_moves')}
            for u,s in u4.items()},unit_order=urank,critical_rows=len(packets),K32_grid_violations={f:s['positive_over_1e8'] for f,s in krows.items()})))
    finally:
        authority.close()
        del case,original,koriginal
        gc.collect()


if __name__=='__main__':
    main()

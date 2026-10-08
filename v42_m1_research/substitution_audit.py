"""Read-only, optimize=0 cross-fleet diagnostics from completed PR188 points.

Raw fractional LP points are diagnostic observations, never integer witnesses,
global lower bounds, or certified physically feasible operations.  In particular
no primal point is inferred from a stored dual multiplier.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import pickle
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse

from .history import ROOT, M188, C3A, git_blob

REPORT = ROOT / 'docs/v42_m1_joint_gap_research/CROSS_MESS_SUBSTITUTION_AUDIT.json'
BASE = 'docs/v42_m1_group_branching_20261008/'
C3 = 'docs/v42_m1_ultracompact_exact_20261006/'
C2 = 'docs/v42_m1_supercompact_exact_20261006/'
B2 = 'docs/v42_m1_b2_root_validation_20261008/'
GRID = {'line_thermal_face', 'transformer_kVA', 'voltage_upper', 'voltage_lower'}
TOL = 1e-8


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _npz(raw):
    with np.load(io.BytesIO(raw), allow_pickle=False) as z:
        return {k: z[k].copy() for k in z.files}


def _axis(name):
    name = str(name)
    if '[' not in name:
        return name, []
    f, suffix = name.split('[', 1)
    return f, suffix[:-1].split(',')


def _slot(name):
    f, a = _axis(name)
    if not a:
        return -1
    if f.startswith('response_'):
        return int(a[0])
    if f in {'Pch', 'Pdis', 'Q', 'injection_P', 'injection_Q', 'SOC',
             'charge_mode', 'node_activity'}:
        return int(a[-1])
    return -1


def _replay(A, d, x):
    """Unrounded numerical relaxed replay at the unchanged scientific tolerance."""
    if x.shape != (A.shape[1],) or not np.isfinite(x).all():
        raise ValueError('SAVED_PRIMAL_AXIS_OR_FINITE_DRIFT')
    residual = A @ x - d['rhs']
    violation = np.maximum(0., np.where(d['sense'] == '=', abs(residual),
                          np.where(d['sense'] == '<', residual, -residual)))
    bounds = max(0., float(np.max(d['lower'] - x)),
                 float(np.max(x - d['upper'])))
    mask = d['types'] != 'C'
    return dict(PASS=bool(violation.max(initial=0.) <= TOL and bounds <= TOL),
                scope='NUMERICAL_RELAXED_ROW_REPLAY_NOT_INTEGER_OR_EXACT_CERTIFICATE',
                tolerance=TOL, rows=A.shape[0], columns=A.shape[1],
                maximum_row_violation=float(violation.max(initial=0.)),
                maximum_bound_violation=bounds,
                maximum_original_integrality_error=float(np.max(
                    abs(x[mask] - np.rint(x[mask])), initial=0.)),
                violations_above_scientific_tolerance=int(np.count_nonzero(violation > TOL)),
                raw_objective_diagnostic=float(d['objective'] @ x + float(d['constant'])),
                exact_certificate_replay=False, integer_feasibility_claim=False)


def _lift(x, columns, aliases, n):
    y = np.zeros(n)
    y[columns] = x
    defined = set(map(int, columns))
    for row in reversed(aliases):
        j = row['column']
        if j in defined:
            raise ValueError('DUPLICATE_TRANSPORT_DEFINITION')
        y[j] = row['constant']
        for k, weight in row['terms'].items():
            k = int(k)
            if k not in defined or weight != 1.:
                raise ValueError('UNSUPPORTED_FROZEN_TRANSPORT')
            y[j] += weight * y[k]
        defined.add(j)
    if len(defined) != n:
        raise ValueError('INCOMPLETE_FROZEN_TRANSPORT')
    return y


def _fractions(d, x):
    result = {}
    for f in ('node_activity', 'charge_mode', 'route_flow'):
        cols = np.array([j for j, n in enumerate(d['names']) if _axis(n)[0] == f])
        v = x[cols]
        result[f] = dict(columns=len(cols),
                        fractional_at_1e_8=int(np.count_nonzero(abs(v - np.rint(v)) > TOL)),
                        positive_at_1e_8=int(np.count_nonzero(v > TOL)))
    return result


def _unit_axes(original_d, graph):
    sites, initial, arcs, _, _ = graph
    units = list(initial)
    pq = {u: {f: [[] for _ in range(96)] for f in ('Pch', 'Pdis', 'Q')} for u in units}
    soc = {u: {} for u in units}
    routes = {u: [] for u in units}
    for j, name in enumerate(original_d['names']):
        f, a = _axis(name)
        if f in {'Pch', 'Pdis', 'Q'}:
            pq[a[0]][f][int(a[-1])].append((j, a[1]))
        elif f == 'SOC':
            soc[a[0]][int(a[1])] = j
        elif f == 'arc':
            k = int(a[1])
            if not 0 <= k < len(arcs):
                raise ValueError('ORIGINAL_ROUTE_GRAPH_AXIS_DRIFT')
            routes[a[0]].append((j, k))
    if any(set(soc[u]) != set(range(97)) for u in units):
        raise ValueError('FULL_0_TO_96_SOC_AXIS_REQUIRED')
    return pq, soc, routes


def _fleet(y, graph, axes):
    _, initial, arcs, _, _ = graph
    pq, soc, routes = axes
    result = {}
    for u in initial:
        p = {f: np.array([sum(y[j] for j, _ in pq[u][f][t])
                         for t in range(96)]) for f in ('Pch', 'Pdis', 'Q')}
        energy = np.zeros(96)
        stay = np.zeros(96)
        travel = np.zeros(96)
        fractional = 0
        for j, k in routes[u]:
            a = arcs[k]
            t = a[1]
            v = y[j]
            fractional += int(abs(v - np.rint(v)) > TOL)
            if a[-1] is None:
                stay[t] += v
            else:
                travel[t] += v
                energy[t] += v * a[-1].energy_kwh
        result[u] = dict(
            Pch_by_slot=p['Pch'].tolist(), Pdis_by_slot=p['Pdis'].tolist(),
            Q_by_slot=p['Q'].tolist(), net_injected_P_by_slot=(p['Pdis']-p['Pch']).tolist(),
            SOC_0_to_96=[float(y[soc[u][t]]) for t in range(97)],
            weighted_departure_travel_energy_kWh=energy.tolist(),
            stay_flow_mass_by_slot=stay.tolist(), travel_departure_flow_mass_by_slot=travel.tolist(),
            original_route_columns=len(routes[u]), fractional_original_route_flows=fractional,
            active_support_site_slots_66_to_95={f: int(sum(abs(y[j]) > TOL
                for t in range(66,96) for j, _ in pq[u][f][t])) for f in p},
            critical_66_to_95={f: dict(sum=float(p[f][66:96].sum()),
                abs_sum=float(abs(p[f][66:96]).sum()), maximum_abs=float(abs(p[f][66:96]).max())) for f in p},
            physical_feasible_operation_claim=False)
    return result


def _grid_axes(A, d):
    slots = np.array([_slot(n) for n in d['names']])
    rows, times, families = [], [], []
    for i, name in enumerate(d['row_names']):
        f = _axis(name)[0]
        if f not in GRID:
            continue
        a, b = A.indptr[i:i+2]
        ts = set(map(int, slots[A.indices[a:b]])) - {-1}
        if len(ts) != 1:
            raise ValueError('GRID_NATIVE_TIME_AXIS_NOT_UNIQUE')
        rows.append(i); times.append(ts.pop()); families.append(f)
    return np.array(rows), np.array(times), np.array(families)


def _grid(A, d, x, axes):
    rows, times, families = axes
    residual = A[rows] @ x - d['rhs'][rows]
    slack = np.where(d['sense'][rows] == '<', -residual, residual)
    active = rows[abs(slack) <= TOL]
    critical = rows[(abs(slack) <= TOL) & (times >= 66) & (times <= 95)]
    return dict(active_rows=active.tolist(), active_66_to_95_rows=critical.tolist(),
                total_original_grid_rows=len(rows), diagnostic_active_definition='abs(raw affine slack) <= 1e-8; no normalization',
                active_rows_count=len(active), active_66_to_95_count=len(critical),
                active_by_family={f: int(np.count_nonzero((abs(slack) <= TOL) & (families == f))) for f in sorted(GRID)},
                diagnostic_raw_primal_only=True)


def _difference(before, after, selected_unit, y0, y1, original_d):
    units = list(before)
    result = {}
    for u in units:
        result[u] = {}
        for f in ('Pch', 'Pdis', 'Q', 'net_injected_P'):
            delta = np.asarray(after[u][f+'_by_slot']) - before[u][f+'_by_slot']
            result[u][f] = dict(full96_L1=float(abs(delta).sum()), critical_66_to_95_L1=float(abs(delta[66:96]).sum()),
                               critical_66_to_95_signed_sum=float(delta[66:96].sum()), maximum_abs=float(abs(delta).max()))
        s = np.asarray(after[u]['SOC_0_to_96']) - before[u]['SOC_0_to_96']
        result[u]['SOC'] = dict(full97_L1=float(abs(s).sum()), maximum_abs=float(abs(s).max()),
                               initial_delta=float(s[0]), terminal_delta=float(s[-1]))
        cols = np.array([j for j,n in enumerate(original_d['names'])
                         if _axis(n)[0]=='arc' and _axis(n)[1][0]==u])
        delta = y1[cols]-y0[cols]
        result[u]['route'] = dict(L1=float(abs(delta).sum()), changed_at_1e_8=int(np.count_nonzero(abs(delta)>TOL)))
    other = [u for u in units if u != selected_unit]
    other_pq = sum(result[u][f]['critical_66_to_95_L1'] for u in other for f in ('Pch','Pdis','Q'))
    other_routes = sum(result[u]['route']['changed_at_1e_8'] for u in other)
    # Site-resolved changes are checked directly, not inferred from aggregate totals.
    site = {}
    for j, n in enumerate(original_d['names']):
        f, a = _axis(n)
        if f in {'Pch','Pdis','Q'} and 66 <= int(a[-1]) <= 95:
            v = abs(float(y1[j]-y0[j]))
            key = a[0]+':'+a[1]
            site.setdefault(key, {k:0. for k in ('Pch','Pdis','Q')})[f] += v
    return dict(per_unit=result, selected_unit=selected_unit,
                other_fleet_critical_PQ_L1=other_pq, other_fleet_changed_route_columns=other_routes,
                site_resolved_critical_PQ_L1=site,
                observed_other_fleet_redistribution=bool(other_pq>TOL and other_routes>0),
                support_substitution_existence_proved=False,
                scope='NUMERICAL_BEFORE_AFTER_OF_STORED_FRACTIONAL_POINTS; NOT_A_CAUSAL_OR_INTEGER_PROOF')


def finalize(runpath):
    """Write the dedicated audit; read only saved objects in the exact D case."""
    start = perf_counter()
    runpath = Path(runpath).resolve()
    if ROOT.resolve().drive.upper() != 'D:' or runpath.drive.upper() != 'D:':
        raise ValueError('D_DRIVE_REQUIRED')
    os.environ.update(TEMP=str(ROOT/'tmp'), TMP=str(ROOT/'tmp'), PYTHONDONTWRITEBYTECODE='1')
    sources = {}
    def raw(path):
        data = git_blob(M188, path)
        sources[path] = dict(head=M188, sha256=_sha(data), bytes=len(data))
        return data
    def data(path):
        return _npz(raw(path))
    def js(path):
        return json.loads(raw(path).decode('utf-8-sig'))

    identity = json.loads((ROOT/'docs/v42_m1_joint_gap_research/SCIENTIFIC_MODEL_IDENTITY.json').read_text(encoding='utf8'))
    Araw, draw = raw(C3+'C3A_A.npz'), raw(C3+'C3A_DATA.npz')
    if _sha(Araw) != identity['C3A_matrix_sha256'] or _sha(draw) != identity['C3A_data_sha256']:
        raise ValueError('FROZEN_SCIENTIFIC_CASE_DRIFT')
    if identity['scientific_C3A_head'] != C3A or identity['completed_M_head'] != M188:
        raise ValueError('COMPLETED_SOURCE_AUTHORITY_REQUIRED')
    if (identity['day'],identity['jobs'],identity['units'],identity['slots']) != ('2025-05-01',1499,4,96):
        raise ValueError('MAY01_FOUR_FLEET_CASE_REQUIRED')
    A, d = sparse.load_npz(io.BytesIO(Araw)), _npz(draw)
    source_identity = js(BASE+'SOURCE_IDENTITY.json')
    for k, v in source_identity['original_arrays_SHA256'].items():
        if _sha(np.ascontiguousarray(d[k]).tobytes()) != v:
            raise ValueError('ORIGINAL_ARRAY_BIT_IDENTITY_DRIFT:'+k)
    for name, value in source_identity['scientific_source_files_SHA256'].items():
        if name in {'C3A_A.npz','C3A_DATA.npz'} and sources[C3+name]['sha256'] != value:
            raise ValueError('PR188_SOURCE_MATRIX_TRANSPORT_DRIFT')
    T = sparse.load_npz(io.BytesIO(raw(B2+'artifacts/TEMPORAL_VALID_ROWS.npz')))
    td = data(B2+'artifacts/TEMPORAL_VALID_ROW_DATA.npz')
    if T.shape != (651,A.shape[1]) or T.nnz != 1302:
        raise ValueError('SAVED_B2_ROW_DIMENSION_DRIFT')
    BA = sparse.vstack([A,T],format='csr')
    bd = dict(d,rhs=np.r_[d['rhs'],td['rhs']],sense=np.r_[d['sense'],td['sense']])
    c1 = data(C2+'C1_DATA.npz')
    columns = data(C2+'C2_RETAINED_AXES.npz')['columns']
    aliases = js(C2+'C2_ELIMINATION_CERTIFICATES.json')
    if (sources[C2+'C2_ELIMINATION_CERTIFICATES.json']['sha256'] != identity['alias_sha256'] or
        sources[C2+'C2_RETAINED_AXES.npz']['sha256'] != identity['retained_columns_sha256']):
        raise ValueError('CURRENT_CASE_TRANSPORT_SOURCE_IDENTITY_DRIFT')
    for field in ('names','objective','types'):
        if not np.array_equal(c1[field][columns],d[field]):
            raise ValueError('FROZEN_TRANSPORT_AXIS_DRIFT:'+field)
    copies = {}
    for receipt in identity['D_frozen_copies']:
        name = Path(receipt['original_path']).name
        path = Path(receipt['local_path'])
        if path.drive.upper() != 'D:' or _sha(path.read_bytes()) != receipt['sha256']:
            raise ValueError('D_FROZEN_INPUT_IDENTITY_DRIFT:'+name)
        copies[name] = path
    census = js(C2+'CURRENT_ORIGINAL_MODEL_CENSUS.json')['identity']
    if (_sha(copies['FULL_A.npz'].read_bytes()) != census['matrix_sha256'] or
        _sha(copies['FULL_DATA.npz'].read_bytes()) != census['data_sha256']):
        raise ValueError('ORIGINAL_MATRIX_INPUT_IDENTITY_DRIFT')
    OA = sparse.load_npz(copies['FULL_A.npz'])
    with np.load(copies['FULL_DATA.npz'],allow_pickle=False) as z:
        od = {k:z[k].copy() for k in z.files}
    transported_names = np.array([str(n).replace('route_flow[','arc[',1)
                                  for n in c1['names'][:OA.shape[1]]])
    if not np.array_equal(transported_names,od['names']):
        raise ValueError('ORIGINAL_PHYSICAL_COORDINATE_PREFIX_DRIFT')
    if (not np.array_equal(c1['objective'][:OA.shape[1]],od['objective']) or
        c1['constant'].tobytes()!=od['constant'].tobytes()):
        raise ValueError('ORIGINAL_PHYSICAL_OBJECTIVE_TRANSPORT_DRIFT')
    with copies['DATA.pkl'].open('rb') as stream:
        frozen_data = pickle.load(stream)
    bundle = dict(frozen_data[0]); bundle['route_table'] = dict(bundle['route_table'],path=str(copies['ROUTE_TABLE.json.gz']))
    if bundle['day'] != '2025-05-01' or len(frozen_data[1]) != 1499:
        raise ValueError('FROZEN_AIDC_DAY_OR_JOB_IDENTITY_DRIFT')
    if _sha(copies['DATA.pkl'].read_bytes()) != identity['frozen_bundle_sha256']:
        raise ValueError('CURRENT_AIDC_BUNDLE_IDENTITY_DRIFT')
    for p, expected in identity['common_physics_sha256'].items():
        if _sha((ROOT/p).read_bytes()) != expected or _sha(raw(p)) != expected:
            raise ValueError('COMPLETED_COMMON_PHYSICS_DRIFT:'+p)
    # This common data decoder creates no native optimization model.
    from v42_unified.mess_replay import graph_from_bundle
    graph = graph_from_bundle(bundle)
    axes = _unit_axes(od,graph)
    ga = _grid_axes(A,d)
    ysize = len(c1['names'])
    points = {}
    for label, path in [
        ('C3A_ROOT','docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz'),
        ('B2_ROOT',B2+'B2_ROOT_RAW.npz')]:
        x = data(path)['x']
        y = _lift(x,columns,aliases,ysize)[:OA.shape[1]]
        points[label] = dict(primal=x,original=y,
            rho=float(d['objective']@x+float(d['constant'])),
            C3A_relaxed=_replay(A,d,x), original_full_relaxed=_replay(OA,od,y),
            fractional_counts=_fractions(d,x),fleet=_fleet(y,graph,axes),grid=_grid(A,d,x,ga))
        if label == 'B2_ROOT':points[label]['B2_relaxed'] = _replay(BA,bd,x)
    comparison = js(BASE+'FRACTIONAL_SOLUTION_COMPARISON.json')
    for f, record in points['B2_ROOT']['fractional_counts'].items():
        claim = next(v for v in comparison['baseline_B2']['family'] if v['family']==f)
        if record['fractional_at_1e_8'] != claim['fractional_count']:
            raise ValueError('ARCHIVED_FRACTIONAL_COUNT_RECOMPUTATION_DRIFT:'+f)
    historical = []
    for child in ('C01/z0','C01/z1','C01_CONTINUATION/z0','C02/z0','C02/z1'):
        prefix = BASE+'children/'+child+'/'
        model = js(prefix+'MODEL_IDENTITY.json')
        if (model['rows'],model['columns'],model['nnz']) != (*BA.shape,BA.nnz):
            raise ValueError('CHILD_RECONSTRUCTED_MODEL_DIMENSION_DRIFT')
        oi = model['objective_identity']
        if oi['candidate_objective_SHA256'] != _sha(d['objective'].tobytes()+d['constant'].tobytes()) or oi['details']['names']['candidate_SHA256'] != _sha(d['names'].tobytes()):
            raise ValueError('CHILD_MODEL_ORIGINAL_OBJECTIVE_AXIS_DRIFT')
        col, value = model['selected_column'],model['selected_value']
        if d['types'][col]!='B' or (d['lower'][col],d['upper'][col])!=(0.,1.) or value not in (0,1):
            raise ValueError('CHILD_NOT_AN_ORIGINAL_BINARY_SPLIT')
        cd = dict(bd,lower=d['lower'].copy(),upper=d['upper'].copy())
        cd['lower'][col]=cd['upper'][col]=value
        x = data(prefix+'RAW.npz')['x']
        y = _lift(x,columns,aliases,ysize)[:OA.shape[1]]
        before=points['B2_ROOT']; fleet=_fleet(y,graph,axes); grid=_grid(A,d,x,ga)
        selected_unit = _axis(d['names'][col])[1][0]
        delta = _difference(before['fleet'],fleet,selected_unit,before['original'],y,od)
        bactive, aactive = set(before['grid']['active_rows']),set(grid['active_rows'])
        historical.append(dict(child=child,source_RAW_path=prefix+'RAW.npz',
            stored_child_model_receipt=model, independently_reconstructed_model=dict(
                original_C3A_rows_retained=True,same_saved_B2_rows=651,one_bound_fix=dict(column=col,value=value),
                coefficient_matrix_bit_identity_to_saved_source=True,
                limitation='The native model itself was not archived; reconstruction is checked against frozen axes, row artifacts and stored model receipt.'),
            selected_variable=str(d['names'][col]),selected_raw_value=float(x[col]),
            baseline_rho=before['rho'],child_raw_rho=float(d['objective']@x+float(d['constant'])),
            raw_rho_delta=float(d['objective']@(x-before['primal'])),
            child_relaxed_row_replay=_replay(BA,cd,x),original_full_relaxed=_replay(OA,od,y),
            fractional_counts=_fractions(d,x),fleet=fleet,grid=grid,
            active_grid_change=dict(added_count=len(aactive-bactive),removed_count=len(bactive-aactive),
                added_rows=sorted(aactive-bactive),removed_rows=sorted(bactive-aactive)),
            observed_redistribution=delta,certified_global_LB_gain=None,
            cut_or_split_escape_proved=False,original_integer_feasibility_proved=False,
            global_optimality_proved=False))
    current=dict(status='NOT_RUN',reason='No saved current count-leaf primal X is available. Dual Pi cannot identify a primal substitution.',
                 Native_optimize_calls=0,primal_inferred_from_dual=False,current_runpath=str(runpath))
    current['inspected_leaf_artifacts']=[]
    for i in (0,1):
        for suffix in ('parent_dual','native_dual'):
            path=runpath/f'leaf_{i}_{suffix}.npz'
            entry=dict(leaf=i,path=str(path),exists=path.exists())
            if path.exists():
                saved=path.read_bytes(); z=_npz(saved)
                entry.update(sha256=_sha(saved),keys=list(z),primal_present=any(k in z for k in ('x','X','point')))
                if entry['primal_present']:
                    # Do not silently treat an unexpected future artifact as the
                    # absent primal of this preregistered dual-only experiment.
                    current['reason']='Unexpected saved primal requires an explicit count-row/model identity replay before substitution can be assessed.'
            current['inspected_leaf_artifacts'].append(entry)
    result_path=runpath/'RESEARCH_TRACK_RESULTS.json'
    if result_path.exists():
        results=json.loads(result_path.read_text(encoding='utf8'))
        if results.get('case_sha') != identity['case_sha']:
            raise ValueError('CURRENT_RESEARCH_CASE_IDENTITY_DRIFT')
        current['saved_track_results_sha256']=_sha(result_path.read_bytes())
        current['note']='Existing final result metadata does not replace absent primal evidence.'
    # Deliberately no glob over other experiments or unfinished M workspaces.
    for record in points.values():
        record.pop('primal');record.pop('original')
    result=dict(schema='V42_CROSS_MESS_SUBSTITUTION_STORED_AUDIT_V1',PASS=True,
        PASS_scope='Completed-source byte identity, frozen inverse coordinate transport without repairs, and independent numerical diagnostic recomputation; not fractional primal feasibility or a new bound proof.',
        native_optimize_calls=0,source_writes=0,active_research_processes_modified=False,
        scientific_case_sha=identity['case_sha'],source_authority=dict(C3A=C3A,completed_M188=M188),
        input_identity=dict(day='2025-05-01',jobs=1499,units=4,slots=96,
            C3A_matrix_sha256=_sha(Araw),C3A_data_sha256=_sha(draw),
            frozen_AIDC_bundle_sha256=identity['frozen_bundle_sha256'],route_table_sha256=identity['route_table_sha256'],
            original_matrix_sha256=census['matrix_sha256'],original_data_sha256=census['data_sha256']),
        sources=sources,baseline_points=points,historical_children=historical,current_count_leaf_substitution=current,
        interpretation=dict(
            observed_cross_fleet_PQ_and_route_redistribution=True,
            same_complete_C3A_and_original_full_row_inputs_checked=True,
            whole_day_SOC_initial_and_terminal_coordinates_reconstructed=True,
            standalone_critical_window_operation_claim=False,
            raw_LP_objective_changes_are_not_certified_global_LB_changes=True,
            fractional_flow_reduction_is_not_integer_feasibility=True,
            universal_cross_MESS_substitution_or_cut_escape='NOT_PROVEN',
            all_saved_fractional_points_are_integer_feasible=False,
            M1_ACCEPTED=False),
        validation_wall_seconds=perf_counter()-start,non_native_only=True)
    # Observation truth must be recomputed rather than copied from a PASS label.
    result['interpretation']['observed_cross_fleet_PQ_and_route_redistribution']=all(
        c['observed_redistribution']['observed_other_fleet_redistribution'] for c in historical)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('runpath')
    args=parser.parse_args()
    receipt=finalize(args.runpath)
    print(json.dumps(dict(PASS=receipt['PASS'],native_optimize_calls=0,report=str(REPORT),
                         current_count_leaf_substitution=receipt['current_count_leaf_substitution']['status'])))

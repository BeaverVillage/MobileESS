"""Read existing historical LP evidence; never build or optimize a native model.

The saved original point is a diagnostic proxy, not the requested fresh C3A LP.
All outputs use HISTORICAL_PROXY names and retain that distinction explicitly.
"""
import os
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                  MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from v42_strengthening.analysis import graph_inputs

SOURCE = Path('C:/Users/kjw39/Documents/Codex/2026-10-03/'
              'single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL')
PARENT = ROOT / 'docs/v42_m1_ultracompact_exact_20261006'
COMPACT = ROOT / 'docs/v42_m1_supercompact_exact_20261006'
TOL = 1e-8
EXPECTED = {
    SOURCE / 'LP_reduced_POINT.npz':
        '81991b5804b92264e1317b9a4f44f0a740fce1bd04384af5fbcf42bd64cac038',
    SOURCE / 'FULL_A.npz':
        '35bdc6e7c2664b763d3d0456b7296b7c8830d7c7c39a61a3cb32e699f8bb2024',
    SOURCE / 'FULL_DATA.npz':
        'ba6eacea23b71db0b5c6d4e18d6370942906ce2790276127139dbc2ece1d2912',
    PARENT / 'C3A_A.npz':
        '45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8',
    PARENT / 'C3A_DATA.npz':
        '20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467',
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_data(path):
    with np.load(path) as archive:
        return {key: archive[key] for key in archive.files}


def stats(values):
    values = np.asarray(values, dtype=float)
    mass = np.minimum(values, 1-values)
    fractional = (values > TOL) & (values < 1-TOL)
    return dict(binary_count=len(values), fractional_count=int(fractional.sum()),
                fractionality_rate=float(fractional.mean()) if len(values) else 0.,
                max_min_x_1mx=float(mass.max(initial=0)),
                sum_min_x_1mx=float(mass.sum()),
                mean_min_x_1mx=float(mass.mean()) if len(values) else 0.)


def response_ids(names):
    answer = []
    for name in names:
        match = re.fullmatch(
            r'response_line_(?:P|Q|correction)\[(\d+),(\d+)\]', name)
        if match:
            answer.append((int(match[1]), int(match[2])))
    return answer


def main():
    source_paths = list(EXPECTED) + [SOURCE / 'REDUCTION_AXES.npz',
        SOURCE / 'DATA.pkl', COMPACT / 'C2_RETAINED_AXES.npz',
        PARENT / 'C3_RETAINED_AXES.npz', PARENT / 'ALL_COLUMN_DECISIONS.csv']
    before = {str(path): sha(path) for path in source_paths}
    for path, expected in EXPECTED.items():
        assert before[str(path)] == expected, path
    full = load_data(SOURCE / 'FULL_DATA.npz')
    x = load_data(SOURCE / 'LP_reduced_POINT.npz')['values']
    assert x.shape == full['names'].shape
    d = load_data(PARENT / 'C3A_DATA.npz')
    A = sparse.load_npz(PARENT / 'C3A_A.npz')
    full_A = sparse.load_npz(SOURCE / 'FULL_A.npz')
    original_keep = load_data(SOURCE / 'REDUCTION_AXES.npz')['keep']
    c2_axes = load_data(COMPACT / 'C2_RETAINED_AXES.npz')
    c3_rows = load_data(PARENT / 'C3_RETAINED_AXES.npz')['rows']
    sites, initial, arcs, battery, graph_receipt = graph_inputs()

    # Independently reconstruct only compact node mass, without Compact().
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    nodes = set()
    original_names = list(map(str, full['names']))
    original_index = dict(zip(original_names, range(len(x))))
    for column, name in enumerate(original_names):
        match = re.fullmatch(r'arc\[([^,]+),(\d+)\]', name)
        if not match:
            continue
        unit, arc_index = match[1], int(match[2])
        source, depart, destination, connect = arcs[arc_index][:4]
        outgoing[unit, source, depart].append(column)
        incoming[unit, destination, connect].append(column)
        nodes.update([(unit, source, depart), (unit, destination, connect)])
    nodes = sorted(nodes, key=lambda key: (key[0], key[2], key[1]))
    node_values = [sum(x[j] for j in (incoming[key] if key[2] == 96
                                     else outgoing[key])) for key in nodes]
    names = [name.replace('arc[', 'route_flow[', 1) if name.startswith('arc[')
             else name for name in original_names]
    names += [f'node_activity[{unit},{site},{slot}]'
              for unit, site, slot in nodes]
    retained = c2_axes['columns']
    assert np.array_equal(np.asarray(names)[retained], d['names'])
    point = np.r_[x, node_values][retained]
    residual = A @ point - d['rhs']
    row_violation = np.where(d['sense'] == '=', abs(residual),
                            np.where(d['sense'] == '<', residual, -residual))
    maximum = float(row_violation.max(initial=0))
    bound = float(max((d['lower']-point).max(initial=0),
                      (point-d['upper']).max(initial=0)))
    assert np.isfinite(point).all() and maximum <= TOL and bound <= TOL

    import csv
    ledger = {int(row['column']): row for row in csv.DictReader(
        (PARENT / 'ALL_COLUMN_DECISIONS.csv').open(encoding='utf-8'))}
    families = defaultdict(list)
    for column in np.flatnonzero(d['types'] != 'C'):
        family = ledger[int(column)]['family']
        assert family in ('node_activity', 'charge_mode')
        families[family].append(point[column])
    assert sum(len(v) for v in families.values()) == 9322

    def value(name):
        # Missing original columns are native unreachable physical constants 0.
        return float(x[original_index[name]]) if name in original_index else 0.

    cuts = defaultdict(list)
    for unit in sorted(initial):
        for slot in range(96):
            charge = sum(value(f'Pch[{unit},{site},{slot}]') for site in sites)
            discharge = sum(value(f'Pdis[{unit},{site},{slot}]') for site in sites)
            mode = value(f'charge_mode[{unit},{slot}]')
            stay = sum(value(f'arc[{unit},{k*96+slot}]')
                       for k in range(len(sites)))
            for family, violation in [
                ('AGGREGATE_CHARGE_MODE', charge-300*mode),
                ('AGGREGATE_DISCHARGE_MODE', discharge-300*(1-mode)),
                ('AGGREGATE_CONNECTED_POWER', charge+discharge-300*stay),
            ]:
                cuts[family].append(dict(signed_violation=violation,
                                        MESS=unit, slot=slot, site='ALL'))
            for k, site in enumerate(sites):
                violation = value(f'Pch[{unit},{site},{slot}]') \
                    + value(f'Pdis[{unit},{site},{slot}]') \
                    - 300*value(f'arc[{unit},{k*96+slot}]')
                cuts['LOCAL_CONNECTED_POWER'].append(dict(
                    signed_violation=violation, MESS=unit, slot=slot, site=site))
    cut_summary = {}
    for family, records in cuts.items():
        ranked = sorted(records, key=lambda record: (
            -record['signed_violation'], record['MESS'], record['slot'], record['site']))
        cut_summary[family] = dict(candidate_count=len(records),
            violated_count=sum(row['signed_violation'] > TOL for row in records),
            maximum_signed_violation=ranked[0]['signed_violation'], top_10=ranked[:10])

    critical = []
    alias_counts = Counter()
    for row, name in enumerate(d['row_names']):
        if str(name) != 'line_thermal_face':
            continue
        columns = A.indices[A.indptr[row]:A.indptr[row+1]]
        metadata = [str(d['names'][j]) for j in columns
                    if str(d['names'][j]) != 'rho_max']
        ids = response_ids(metadata)
        alias_counts['NO_RESPONSE_IDS' if not ids else
            'MIXED_RESPONSE_IDS' if len(set(ids)) > 1 else 'ONE_RESPONSE_ID'] += 1
        if abs(residual[row]) > TOL:
            continue
        # Recover target line through immutable row axes, never alias column names.
        original_C0_row = int(c2_axes['C1_original_rows'][
            c2_axes['rows'][c3_rows[row]]])
        assert original_C0_row < len(original_keep)
        full_native_row = int(original_keep[original_C0_row])
        assert str(full['row_names'][full_native_row]) == 'line_thermal_face'
        original_columns = full_A.indices[
            full_A.indptr[full_native_row]:full_A.indptr[full_native_row+1]]
        original_metadata = [str(full['names'][j]) for j in original_columns
                             if str(full['names'][j]) != 'rho_max']
        original_ids = response_ids(original_metadata)
        assert len(set(original_ids)) == 1
        slot, line = original_ids[0]
        critical.append(dict(C3A_row=row, original_C0_row=original_C0_row,
            FULL_native_row=full_native_row, slot=slot, native_line_index=line,
            signed_slack=float(-residual[row]),
            original_native_variables=original_metadata,
            C3A_alias_variables=metadata, mixed_alias_ids=len(set(ids)) > 1))

    after = {str(path): sha(path) for path in source_paths}
    assert before == after
    np.savez_compressed(OUT / 'HISTORICAL_PROXY_POINT.npz', x=point,
        original_types=d['types'], source_role=np.asarray('HISTORICAL_PROXY_ONLY'))
    objective = float(d['objective'] @ point + float(d['constant']))
    report = dict(
        classification='HISTORICAL_PROXY_ONLY_NOT_FRESH_LP_RESULT',
        PASS=True, optimize_calls=0, native_model_build_calls=0,
        source=str(SOURCE / 'LP_reduced_POINT.npz'),
        source_hashes=before, all_input_hashes_unchanged=True,
        fresh_LP_point_replacement=False, fresh_LP_duals_available=False,
        selected_C3A_optimality_not_reproven=True,
        original_continuous_point_columns=len(x), compact_nodes_added=len(nodes),
        selected_columns=len(point), selected_names_byte_exact=True,
        forward_mapping='Original physical columns copied; each compact node is '
            'outgoing unit arc mass (incoming at terminal); saved C2 retained '
            'column axis applied. No constructor or solver call.',
        independent_C3A_relaxed_replay=dict(PASS=True,
            max_row_violation=maximum, max_bound_violation=bound,
            objective=objective, tolerance=TOL),
        fractionality_definition='1e-8 < x < 1-1e-8',
        discrete_family_authority='PR162 ALL_COLUMN_DECISIONS.csv and typed axis',
        fractionality_total=stats(point[d['types'] != 'C']),
        fractionality_by_family={family: stats(v) for family,v in families.items()},
        battery=asdict(battery), original_graph_receipt=graph_receipt,
        candidate_violation_summary=cut_summary,
        candidate_validity_not_inferred_from_point=True,
        aggregate_connected_is_sum_of_local_connected_cuts=True,
        critical_line_rows=len(critical), critical_rows=critical,
        critical_time_line_counts=dict(Counter(
            f"{r['slot']},{r['native_line_index']}" for r in critical)),
        mixed_alias_critical_rows=sum(r['mixed_alias_ids'] for r in critical),
        all_thermal_row_alias_ID_census=dict(alias_counts),
        aggregate_connected_violations_at_critical_time_window=sum(
            r['signed_violation'] > TOL and r['slot'] >= 66
            for r in cuts['AGGREGATE_CONNECTED_POWER']),
        aggregate_connected_violations_before_critical_time_window=sum(
            r['signed_violation'] > TOL and r['slot'] < 66
            for r in cuts['AGGREGATE_CONNECTED_POWER']),
        causal_limit='Cut violations alone do not prove a rho bound increase. '
            'No cut loop or selective-integrality test was executed for this '
            'historical proxy. Critical rows and fractions here are historical '
            'evidence only; the requested fresh LP point was not recovered.',
        historical_proxy_point_SHA256=sha(OUT / 'HISTORICAL_PROXY_POINT.npz'),
    )
    (OUT / 'HISTORICAL_PROXY_AUDIT.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
        encoding='utf-8')
    print('HISTORICAL_PROXY_ONLY', objective, maximum,
          report['fractionality_total'], 'critical_rows', len(critical), flush=True)


if __name__ == '__main__':
    main()

"""Independent Source18r physical row transport audit; no optimizer import.

Uses the sealed C3A CSR and one PR209 vehicle CSR at a time.  It never loads
the FULL CSR, regenerates a model, or changes any production formulation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
import json
from pathlib import Path
import re
import time

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
PHYSICAL = {'route_flow', 'node_activity', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q'}
UNITS = ('MESS01', 'MESS02', 'MESS03', 'MESS04')


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def audit(source, old):
    started = time.perf_counter()
    A = sparse.load_npz(source / 'C3A_A.npz')
    data_file = np.load(source / 'C3A_DATA.npz')
    d = {k: data_file[k] for k in data_file.files}
    c2_file = np.load(source / 'CURRENT_C2_AXES.npz')
    c2 = {k: c2_file[k] for k in c2_file.files}
    c3_file = np.load(source / 'CURRENT_C3A_AXES.npz')
    c3 = {k: c3_file[k] for k in c3_file.files}
    require(np.array_equal(c3['columns'], np.arange(A.shape[1])), 'C3A local column axis drift')
    original_columns = c2['columns']
    original_rows = c2['rows'][c3['rows']]
    retained = {int(j): i for i, j in enumerate(original_columns)}
    aliases = {int(s['column']): s for s in read(source / 'CURRENT_C2_ALIASES.json')}
    families = [str(n).split('[', 1)[0] for n in d['names']]
    physical = np.asarray([f in PHYSICAL for f in families])
    bad = np.zeros(A.shape[0], dtype=bool)
    row_of_entry = np.repeat(np.arange(A.shape[0]), np.diff(A.indptr))
    bad[row_of_entry[~physical[A.indices]]] = True
    rows = np.flatnonzero(~bad)
    del row_of_entry
    selected_original = {int(original_rows[i]): int(i) for i in rows}
    fraction_cache = {}

    def rat(x):
        x = float(x)
        if x not in fraction_cache:
            fraction_cache[x] = F(x)
        return fraction_cache[x]

    expansion_cache = {}

    def expand(j):
        if j in expansion_cache:
            return expansion_cache[j]
        if j in retained:
            result = (F(0), {retained[j]: F(1)})
        else:
            require(j in aliases, f'Unaccounted eliminated column {j}')
            step = aliases[j]
            constant = rat(step['constant'])
            coefficients = defaultdict(F)
            for k, value in step['terms'].items():
                offset, expression = expand(int(k))
                value = rat(value)
                constant += value * offset
                for q, coefficient in expression.items():
                    coefficients[q] += value * coefficient
            result = (constant, {q: v for q, v in coefficients.items() if v})
        expansion_cache[j] = result
        return result

    def project(columns, values, rhs):
        expected = defaultdict(F)
        expected_rhs = rat(rhs)
        for j, value in zip(columns, values):
            offset, expression = expand(int(j))
            value = rat(value)
            expected_rhs -= value * offset
            for q, coefficient in expression.items():
                expected[q] += value * coefficient
        expected = {q: v for q, v in expected.items() if v}
        return expected, expected_rhs

    def compare(original_id, columns, values, rhs, sense):
        i = selected_original[original_id]
        expected, expected_rhs = project(columns, values, rhs)
        a, b = A.indptr[i:i + 2]
        actual = {int(j): rat(v) for j, v in zip(A.indices[a:b], A.data[a:b])}
        require(expected == actual, f'Physical coefficient transport drift original row {original_id}')
        require(expected_rhs == rat(d['rhs'][i]) and str(sense) == str(d['sense'][i]),
                f'Physical RHS/sense transport drift original row {original_id}')

    proof = read(source / 'EXACT_PHYSICAL_PRESCREEN.json')
    arcs = proof['arcs']
    outgoing, incoming = defaultdict(list), defaultdict(list)
    nodes = set()
    matched = set()
    per_unit = []
    original_physical_names = {}
    c3_certificates = read(source / 'CURRENT_C3A_ROW_CERTIFICATES.json')
    c2_retained_rows = set(map(int, c2['rows']))
    c3_replayed = set()
    physical_c2_tautologies = 0
    for unit in UNITS:
        unit_data = np.load(old / f'UNIT_{unit}_DATA.npz')
        D = {k: unit_data[k] for k in unit_data.files}
        unit_axes = np.load(old / f'UNIT_{unit}_AXES.npz')
        axes = {k: unit_axes[k] for k in unit_axes.files}
        G = sparse.load_npz(old / f'UNIT_{unit}_A.npz')
        for j, name in zip(axes['columns'], D['names']):
            j = int(j)
            original_physical_names[j] = str(name)
            route = re.fullmatch(r'arc\[([^,]+),(\d+)\]', str(name))
            if route:
                require(route[1] == unit, 'Vehicle axis drift')
                k = int(route[2]); s, t, z, v = arcs[k][:4]
                require(0 <= t < v <= 96, 'Non-DAG physical route')
                outgoing[unit, s, t].append(j); incoming[unit, z, v].append(j)
                nodes.update(((unit, s, t), (unit, z, v)))
        checked = 0
        energy_slots = set()
        for local, identity in enumerate(axes['rows']):
            identity = int(identity)
            if identity not in selected_original:
                continue
            a, b = G.indptr[local:local + 2]
            compare(identity, axes['columns'][G.indices[a:b]], G.data[a:b],
                    D['rhs'][local], D['sense'][local])
            if str(D['row_names'][local]).split('[', 1)[0] == 'energy_balance':
                soc_slots = [int(str(D['names'][j]).split(',')[-1][:-1])
                             for j in G.indices[a:b] if str(D['names'][j]).startswith('SOC[')]
                require(len(soc_slots) == 2 and max(soc_slots) == min(soc_slots) + 1,
                        'Original energy slot axis drift')
                energy_slots.add(min(soc_slots))
            matched.add(identity); checked += 1
        require(energy_slots == set(range(96)), 'Vehicle 96-slot energy coverage drift')
        original_row_position = {int(identity): local for local, identity in enumerate(axes['rows'])}
        projected_cache = {}

        def projected_original(identity):
            require(identity in original_row_position, 'Deletion proof crosses physical owner or lacks provenance')
            if identity not in projected_cache:
                local = original_row_position[identity]
                a, b = G.indptr[local:local + 2]
                coefficients, rhs = project(axes['columns'][G.indices[a:b]], G.data[a:b], D['rhs'][local])
                sense = str(D['sense'][local])
                if sense == '>':
                    coefficients = {j: -v for j, v in coefficients.items()}; rhs = -rhs; sense = '<'
                projected_cache[identity] = coefficients, rhs, sense
            return projected_cache[identity]

        tautologies = 0
        for identity in original_row_position:
            if identity not in c2_retained_rows:
                coefficients, rhs, sense = projected_original(identity)
                require(not coefficients and (rhs == 0 if sense == '=' else rhs >= 0),
                        'C2 eliminated physical definition is not exact tautology')
                tautologies += 1
        physical_c2_tautologies += tautologies
        deleted = Counter()
        for certificate in c3_certificates:
            target = int(c2['rows'][int(certificate['row'])])
            if target not in original_row_position:
                continue
            require(target not in c3_replayed, 'Duplicate physical deletion certificate')
            target_coefficients, target_rhs, target_sense = projected_original(target)
            combined, combined_rhs = defaultdict(F), F(0)
            support = certificate['support']
            if certificate['kind'] == 'FLOW_EQUALITY_SUM':
                require(target_sense == '=', 'Flow-sum target must be equality')
                support = [{'row': row, 'weight': '1'} for row in support]
            for term in support:
                weight = F(term['weight'])
                if not weight:
                    continue
                if 'bound' in term:
                    column = int(term['bound'])
                    require(physical[column] and weight >= 0 and target_sense == '<',
                            'Invalid physical bound support')
                    endpoint = term['endpoint']
                    require(endpoint in ('lower', 'upper'), 'Unknown bound endpoint')
                    sign = -1 if endpoint == 'lower' else 1
                    coefficient = F(sign)
                    rhs = sign * rat(d['lower'][column] if sign == -1 else d['upper'][column])
                    coefficients = {column: coefficient}
                else:
                    identity = int(c2['rows'][int(term['row'])])
                    coefficients, rhs, sense = projected_original(identity)
                    require(sense == '=' or weight >= 0, 'Negative inequality multiplier')
                    require(target_sense != '=' or sense == '=', 'Equality requires equality support')
                combined_rhs += weight * rhs
                for column, coefficient in coefficients.items():
                    combined[column] += weight * coefficient
            combined = {j: v for j, v in combined.items() if v}
            require(combined == target_coefficients and
                    (combined_rhs == target_rhs if target_sense == '=' else combined_rhs <= target_rhs),
                    f'Exact physical C3A deletion implication failed at original row {target}')
            c3_replayed.add(target); deleted[certificate['kind']] += 1
        per_unit.append({'unit': unit, 'retained_original_physical_rows_exactly_replayed': checked,
                         'original_energy_slots_exactly_replayed': len(energy_slots),
                         'C2_deleted_physical_definitions_exact_tautologies': tautologies,
                         'C3A_deleted_physical_rows_exact_implications': dict(deleted)})
        del G, D, axes, projected_cache
    compact_nodes = sorted(nodes, key=lambda x: (x[0], x[2], x[1]))
    full_identity = read(source / 'ORIGINAL_DOMAIN_EQUIVALENCE.json')
    full_n, full_r = full_identity['original_columns'], full_identity['original_rows']
    require(len(compact_nodes) + full_n == full_identity['compact_columns'], 'Compact DAG node coverage drift')
    require(len(compact_nodes) + full_r == full_identity['compact_rows'], 'Compact node link row coverage drift')
    def equality_signature(coefficients, rhs):
        pivot = coefficients[min(coefficients)]
        return tuple((j, v / pivot) for j, v in sorted(coefficients.items())), rhs / pivot

    retained_flow_equalities = set()
    for i in rows:
        if str(d['row_names'][i]).split('[', 1)[0] != 'flow':
            continue
        a, b = A.indptr[i:i + 2]
        coefficients = {int(j): rat(v) for j, v in zip(A.indices[a:b], A.data[a:b])}
        require(d['sense'][i] == '=' and coefficients, 'Retained physical flow equality drift')
        retained_flow_equalities.add(equality_signature(coefficients, rat(d['rhs'][i])))
    links = 0
    deleted_links_tautologies, deleted_links_flow_implications = 0, 0
    for offset, (unit, site, t) in enumerate(compact_nodes):
        identity = full_r + offset
        dependencies = incoming[unit, site, t] if t == 96 else outgoing[unit, site, t]
        if identity not in selected_original:
            require(identity not in c2_retained_rows, 'Unexpected C3A deletion of node link')
            coefficients, rhs = project([full_n + offset] + dependencies, [1.] + [-1.] * len(dependencies), 0.)
            if not coefficients:
                require(rhs == 0, 'Deleted compact link is not a tautology')
                deleted_links_tautologies += 1
            else:
                require(equality_signature(coefficients, rhs) in retained_flow_equalities,
                        'Deleted compact node link lacks exact retained flow implication')
                deleted_links_flow_implications += 1
            continue
        compare(identity, [full_n + offset] + dependencies, [1.] + [-1.] * len(dependencies), 0., '=')
        matched.add(identity); links += 1
    require(matched == set(selected_original), 'Reduced physical row provenance incomplete')
    require(len(c3_replayed) == len(c3_certificates) == 71540,
            'Physical C3A deletion certificate coverage incomplete')
    retained_original_physical = [j for j in retained if j in original_physical_names]
    require(all(families[retained[j]] in PHYSICAL for j in retained_original_physical), 'Physical family mapping drift')
    for original, name in original_physical_names.items():
        if original in retained:
            actual = str(d['names'][retained[original]])
            expected = name.replace('arc[', 'route_flow[') if name.startswith('arc[') else name
            require(actual == expected, 'Physical name transport drift')
        else:
            require(original in aliases, 'Missing original physical decision without inverse alias')
            expand(original)
    bound_packet = read(source / 'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json')
    c3_bounds = read(source / 'CURRENT_C3A_BOUND_PROOFS.json')
    require(all(str(b['name']).split('[', 1)[0] not in PHYSICAL for b in c3_bounds),
            'C3A unexpectedly tightened physical bounds')
    require(read(source / 'ORIGINAL_DOMAIN_EQUIVALENCE.json')['PASS'], 'Source18r domain receipt failure')
    return {
        'PASS': True, 'schema': 'V42_JOINT_INDEPENDENT_PHYSICAL_TRANSPORT_AUDIT_V1',
        'native_optimize_calls': 0, 'full_matrix_loaded': False,
        'physical_rows': len(rows), 'physical_columns': int(physical.sum()),
        'physical_binary': int(np.count_nonzero(physical & (d['types'] == 'B'))),
        'physical_nnz': int(np.sum(np.diff(A.indptr)[rows])),
        'retained_original_physical_rows_exactly_replayed': len(rows) - links,
        'retained_node_activity_links_exactly_replayed': links,
        'C2_deleted_original_physical_definitions_exact_tautologies': physical_c2_tautologies,
        'C3A_deleted_physical_rows_exact_Farkas_or_flow_sum_replayed': len(c3_replayed),
        'C2_deleted_node_links_exact_tautologies': deleted_links_tautologies,
        'C2_deleted_node_links_exact_retained_flow_implications': deleted_links_flow_implications,
        'per_unit': per_unit, 'node_activity_graph_nodes': len(compact_nodes),
        'all_96_slots_retained': all(item['original_energy_slots_exactly_replayed'] == 96 for item in per_unit),
        'compact_coordinate_rule': 'C2 columns; C2 rows indexed by C3A rows (C3A columns are local identity)',
        'pre_C2_bound_methods': dict(Counter(b['proof'] for b in bound_packet)),
        'C3A_physical_bounds_tightened': 0,
        'bound_implication_scope': 'Source18r independently replayed exact SOC/PCS/source-flow implication receipts; mathematical derivation in MATH_REVIEW_KO.md',
        'solver_bound_exact_certificate': False,
        'elapsed_seconds': time.perf_counter() - started,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--old', type=Path, default=ROOT / 'docs/v42_physical_global_lb_pilot')
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/v42_joint_critical_grid_lb_pilot/PHYSICAL_RELATION_AUDIT.json')
    args = parser.parse_args()
    result = audit(args.source, args.old)
    require(result['all_96_slots_retained'], '96-slot energy row coverage drift')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

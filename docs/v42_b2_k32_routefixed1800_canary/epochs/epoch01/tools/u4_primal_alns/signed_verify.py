"""Independent Source NPZ selected-row and signed physical projection audit.

Streams original sparse array members, never creates a FULL CSR or solver.
"""
from collections import defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from time import perf_counter
import argparse
import zipfile

import numpy as np

from . import verify as v


def selected_array(z, name, positions):
    """Read sorted selected scalar offsets with bounded forward-only skips."""
    wanted = sorted(set(map(int, positions)))
    result = {}
    with z.open(name+'.npy') as stream:
        version = np.lib.format.read_magic(stream)
        shape, order, dtype = np.lib.format._read_array_header(stream, version)
        v.require(not order and len(shape) == 1 and not dtype.hasobject, 'STREAMED_NPY_AXIS_DRIFT')
        cursor = 0
        for i in wanted:
            v.require(0 <= i < shape[0], 'STREAMED_ORIGINAL_ARRAY_INDEX')
            skip = (i-cursor)*dtype.itemsize
            while skip:
                n = min(skip, 1048576)
                v.require(len(stream.read(n)) == n, 'SOURCE_NPY_TRUNCATED_SKIP')
                skip -= n
            block = stream.read(dtype.itemsize)
            v.require(len(block) == dtype.itemsize, 'SOURCE_NPY_TRUNCATED_VALUE')
            result[i] = np.frombuffer(block, dtype=dtype)[0].item()
            cursor = i+1
    return result


def audit(context_path=None, raw_path=None, expected_point_sha=None, output=None):
    began = perf_counter()
    raw_path = Path(raw_path or v.DOCS/'SIGNED_SELECTION_SOURCE_RAW.json')
    context_path = Path(context_path or v.DOCS/'SIGNED_SELECTION_CONTEXT.json')
    expected_point_sha = expected_point_sha or v.INITIAL_VECTOR_SHA
    raw, context = v.read(raw_path), v.read(context_path)
    v.require(raw['source'] == context['source'] == v.SOURCE_SHA and raw['case_sha'] == context['case_sha'] == v.CASE_SHA
              and context.get('center_point_sha256', context.get('initial_point_sha256')) == expected_point_sha
              and context['source_raw_packet_sha256'] == v.file_sha(raw_path), 'SIGNED_SOURCE_CASE_U4_PACKET_BINDING')
    for path, expected in raw['source_files'].items():
        v.require(v.file_sha(path) == expected, 'SIGNED_ORIGINAL_FULL_SOURCE_FILE_SHA_DRIFT')
    rows = {r['original_row']: r for r in raw['rows']}
    v.require(len(rows) == len(raw['rows']), 'DUPLICATE_RAW_ORIGINAL_ROWS')
    with zipfile.ZipFile(v.SOURCE/'FULL_A.npz') as z:
        pointers = selected_array(z, 'indptr', [j for i in rows for j in (i, i+1)])
        offsets = [j for i in rows for j in range(pointers[i], pointers[i+1])]
        indices = selected_array(z, 'indices', offsets)
        weights = selected_array(z, 'data', offsets)
    with zipfile.ZipFile(v.SOURCE/'FULL_DATA.npz') as z:
        row_names = selected_array(z, 'row_names', rows)
        senses = selected_array(z, 'sense', rows)
        rhs = selected_array(z, 'rhs', rows)
        ids = list(map(int, raw['columns']))
        names = selected_array(z, 'names', ids)
        lower = selected_array(z, 'lower', ids)
        upper = selected_array(z, 'upper', ids)
        types = selected_array(z, 'types', ids)
    for i, row in rows.items():
        terms = [[indices[j], float(weights[j]).hex()] for j in range(pointers[i], pointers[i+1])]
        v.require(row['name'] == row_names[i] and row['sense'] == senses[i]
                  and row['rhs_hex'] == float(rhs[i]).hex() and row['terms'] == terms,
                  'RAW_SELECTED_ROW_NOT_ORIGINAL_SOURCE_BYTE_VALUES')
    for key, record in raw['columns'].items():
        j = int(key)
        v.require(record['name'] == names[j] and record['lower_hex'] == float(lower[j]).hex()
                  and record['upper_hex'] == float(upper[j]).hex() and record['type'] == types[j],
                  'RAW_ORIGINAL_COLUMN_BOUND_NAME_TYPE_DRIFT')
    definitions = {}
    for i, row in rows.items():
        family = row['name'].split('[', 1)[0]
        if family.startswith(('response_', 'injection_')) and family.endswith('_binding'):
            v.require(row['sense'] == '=', 'ORIGINAL_HELPER_MUST_EQUALITY')
            candidates = [j for j, h in row['terms'] if float.fromhex(h) == 1.
                          and names[j].split('[', 1)[0]+'_binding' == family]
            v.require(len(candidates) == 1 and candidates[0] not in definitions, 'UNIQUE_ORIGINAL_HELPER_PIVOT')
            definitions[candidates[0]] = i
    cache, visiting = {}, set()

    def expand(j):
        if j in cache:
            return cache[j]
        if j not in definitions:
            v.require(not (names[j].split('[', 1)[0].startswith(('response_', 'injection_'))),
                      'INCOMPLETE_ORIGINAL_HELPER_CLOSURE')
            return F(0), {j:F(1)}, set()
        v.require(j not in visiting, 'SOURCE_HELPER_CYCLE')
        visiting.add(j)
        i = definitions[j]
        c, coefficients, used = F(float(rhs[i])), defaultdict(F), {i}
        for k, h in rows[i]['terms']:
            if k == j:
                continue
            cc, pieces, deps = expand(k)
            weight = -F(float.fromhex(h))
            c += weight*cc
            for leaf, value in pieces.items():
                coefficients[leaf] += weight*value
            used.update(deps)
        visiting.remove(j)
        result = c, {k:a for k,a in coefficients.items() if a}, used
        cache[j] = result
        return result

    proofs = []
    for packet in context['critical_exact_rows']:
        i = packet['original_row']
        sign = F(1) if senses[i] == '<' else F(-1)
        v.require(senses[i] in ('<', '>'), 'SIGNED_ORIGINAL_SECURITY_SENSE')
        constant, coefficients, used = F(0), defaultdict(F), set()
        for j, h in rows[i]['terms']:
            c, pieces, deps = expand(j)
            weight = sign*F(float.fromhex(h))
            constant += weight*c
            for leaf, value in pieces.items():
                coefficients[leaf] += weight*value
            used.update(deps)
        exact = {str(k):a for k,a in coefficients.items() if a}
        v.require(exact == {k:F(a) for k,a in packet['coeff'].items()}
                  and sign*F(float(rhs[i]))-constant == F(packet['rhs'])
                  and constant == F(packet['eliminated_constant']) and sorted(used) == packet['helper_rows'],
                  'EXACT_SIGNED_HELPER_ELIMINATION_CONSTANT_OR_RHS_DRIFT')
        v.require(packet['name'] == row_names[i] and packet['source_sense'] == senses[i]
                  and packet['source_rhs_hex'] == float(rhs[i]).hex(), 'SIGNED_ORIGINAL_ROW_PROVENANCE_DRIFT')
        for key in exact:
            name = names[int(key)]
            if name != 'rho_max':
                v.require(name.startswith(('Pch[', 'Pdis[', 'Q['))
                          and int(name.rsplit(',',1)[1][:-1]) == packet['slot'], 'SIGNED_CROSS_TIME_OR_NONPHYSICAL_LEAF')
        proofs.append(dict(original_row=i, family=packet['family'], slot=packet['slot'],
                           exact_physical_terms=len(exact), helper_rows=len(used), PASS=True))
    # Independently reconstruct the actual stored PCS16 polygon at connected=1.
    planes = []
    for i in raw['PCS16_original_rows']:
        row = rows[i]
        p = F(0)
        q = F(0)
        ch = F(0)
        b = F(float(rhs[i]))
        connected = []
        for j, h in row['terms']:
            weight = F(float.fromhex(h))
            name = names[j]
            if name.startswith('Pdis['):
                p += weight
            elif name.startswith('Pch['):
                ch += weight
            elif name.startswith('Q['):
                q += weight
            elif name.startswith('arc['):
                connected.append(j)
                b -= weight
            else:
                raise ValueError('PCS16_ORIGINAL_UNEXPECTED_COLUMN')
        v.require(row['name'] == 'PCS16' and senses[i] == '<' and len(connected) == 1 and ch == -p,
                  'PCS16_ORIGINAL_PHYSICAL_PNET_AND_CONNECTED_GATE')
        planes.append((p,q,b))
    v.require(len(planes) == 16, 'PCS16_LITERAL_FACE_COUNT')
    planes += [(F(1),F(0),F(300)), (F(-1),F(0),F(300))]
    vertices = set()
    for a,b,c in planes:
        for p,q,r in planes:
            determinant = a*q-b*p
            if determinant:
                x,y = (c*q-b*r)/determinant,(a*r-c*p)/determinant
                if all(u*x+w*y <= z for u,w,z in planes):
                    vertices.add((x,y))
    v.require(vertices == {tuple(map(F, point)) for point in context['PCS16_vertices_exact']},
              'EXACT_SOURCE_PCS16_VERTEX_SUPPORT_DRIFT')
    result = dict(PASS=True, source_sha=v.SOURCE_SHA, case_sha=v.CASE_SHA,
        center_point_sha256=expected_point_sha,
        context_sha256=v.file_sha(context_path), source_raw_sha256=v.file_sha(raw_path),
        original_selected_rows_verified=len(rows), original_source_columns_verified=len(ids),
        exact_projected_security_rows=proofs, original_helper_definitions=len(definitions),
        exact_source_PCS16_vertices=len(vertices), all_signs_constants_and_RHS_exact=True,
        signed_score_semantics='Instantaneous original physical support, current exact center contribution and actual Source ETA/energy ranking; heuristic only, no SOC/grid/full-route feasibility claim.',
        full_CSR_constructed=False, Native_optimize_calls=0, wall_seconds=perf_counter()-began)
    v.write(output or v.DOCS/'SIGNED_SELECTION_INDEPENDENT_NATIVE0.json', result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path)
    parser.add_argument('--raw', type=Path)
    parser.add_argument('--point-sha')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.context, args.raw, args.point_sha, args.output)
    print(json.dumps(dict(PASS=True, rows=result['original_selected_rows_verified'],
                         projections=len(result['exact_projected_security_rows']),
                         wall_seconds=result['wall_seconds'])))


if __name__ == '__main__':
    main()

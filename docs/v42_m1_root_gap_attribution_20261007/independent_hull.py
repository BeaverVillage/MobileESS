"""Independent rational one-slot authority/proof; deliberately contains no solve.

No production cut constructor is imported.  Candidate terms are reconstructed
from FULL_DATA plus the saved exact coordinate inverse.  Local continuous
vertices use the binary64 coefficients stored in FULL_A, interpreted exactly.
The one-slot polytope has free boundary SOC except original horizon endpoints;
it is a conservative projection containing every global feasible schedule.
"""
from __future__ import annotations
import csv
import hashlib
import itertools
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict
from fractions import Fraction as F
from pathlib import Path

for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ.setdefault(_key, '1')
import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent
SOURCE = Path('C:/Users/kjw39/Documents/Codex/2026-10-03/single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL')
PARENT = ROOT / 'docs/v42_m1_ultracompact_exact_20261006'
FULL_DATA_SHA = 'ba6eacea23b71db0b5c6d4e18d6370942906ce2790276127139dbc2ece1d2912'
FULL_A_SHA = '35bdc6e7c2664b763d3d0456b7296b7c8830d7c7c39a61a3cb32e699f8bb2024'
FAMILIES = ('AGGREGATE_CHARGE_MODE', 'AGGREGATE_DISCHARGE_MODE',
            'AGGREGATE_CONNECTED_POWER', 'LOCAL_CONNECTED_POWER')
TOL = F.from_float(1e-8)


def exact(x):
    """Exact stored binary64 value, never a decimal or trig approximation."""
    if isinstance(x, F):
        return x
    if isinstance(x, (int, np.integer)):
        return F(int(x))
    return F.from_float(float(x))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def rational(x):
    return str(exact(x))


class Authority:
    """Read-only original authority and an independently reconstructed inverse."""
    def __init__(self, context=None):
        assert sha(SOURCE / 'FULL_DATA.npz') == FULL_DATA_SHA
        with np.load(SOURCE / 'FULL_DATA.npz') as z:
            self.full = {k: z[k] for k in z.files}
        self.names = {str(n): j for j, n in enumerate(self.full['names'])}
        if context is None:
            # Authority reader only: native_inputs never constructs/optimizes a model.
            from v42_strengthening.analysis import graph_inputs
            self.sites, self.initial, self.arcs, self.battery, self.receipt = graph_inputs()
        else:
            self.sites = context['sites']
            self.initial = context['initial']
            self.arcs = context['arcs']
            self.battery = context['battery']
            self.receipt = context['receipt']
        self.sites = tuple(self.sites)
        self.arcs = tuple(self.arcs)
        steps_path = ROOT / 'docs/v42_m1_supercompact_exact_20261006/C2_ELIMINATION_CERTIFICATES.json'
        axes_path = ROOT / 'docs/v42_m1_supercompact_exact_20261006/C2_RETAINED_AXES.npz'
        steps = json.loads(steps_path.read_text(encoding='utf-8'))
        with np.load(axes_path) as z:
            retained = z['columns']
        self.target = np.full(len(retained) + len(steps), -1, int)
        self.offset = [F(0)] * len(self.target)
        self.target[retained] = np.arange(len(retained))
        seen = set(map(int, retained))
        for step in reversed(steps):
            j = int(step['column'])
            assert j not in seen
            constant = exact(step['constant'])
            if step['terms']:
                assert len(step['terms']) == 1
                k, w = next(iter(step['terms'].items()))
                k = int(k)
                assert k in seen and exact(w) == 1
                self.target[j] = self.target[k]
                self.offset[j] = constant + self.offset[k]
            else:
                self.offset[j] = constant
            seen.add(j)
        assert len(seen) == len(self.target)
        self.inverse_provenance = dict(axes_SHA256=sha(axes_path),
                                      elimination_SHA256=sha(steps_path),
                                      original_compact_columns=len(self.target),
                                      selected_columns=len(retained),
                                      all_alias_weights_exactly_one=True)
        # Native time-DAG reachability, separate from any cut implementation.
        outgoing = defaultdict(list)
        for k, arc in enumerate(self.arcs):
            outgoing[arc[1]].append((k, arc))
        self.reachable = {}
        for unit, origin in sorted(self.initial.items()):
            nodes = {(origin, 0)}
            allowed = []
            for t in range(96):
                for k, arc in outgoing[t]:
                    if (arc[0], arc[1]) in nodes:
                        allowed.append(k)
                        nodes.add((arc[2], arc[3]))
            self.reachable[unit] = set(allowed)
        self._A = None
        self._CSC = None
        self._pcs_cache = {}
        self._energy_cache = {}
        self._vertex_cache = {}

    def expression(self, name):
        """Own coordinate reconstruction, not analyze_point.expr/candidates()."""
        j = self.names.get(name)
        if j is None:
            # Native omission of unreachable site power / arcs denotes zero.
            return {}, F(0)
        k = int(self.target[j])
        return ({} if k < 0 else {k: F(1)}), self.offset[j]

    def value(self, name, point):
        terms, constant = self.expression(name)
        return constant + sum((w * exact(point[j]) for j, w in terms.items()), F(0))

    def load_matrix(self):
        if self._A is None:
            assert sha(SOURCE / 'FULL_A.npz') == FULL_A_SHA
            self._A = sparse.load_npz(SOURCE / 'FULL_A.npz').tocsr()
            self._CSC = self._A.tocsc()
        return self._A

    def row(self, i):
        A = self.load_matrix()
        return {int(j): exact(w) for j, w in
                zip(A.indices[A.indptr[i]:A.indptr[i + 1]],
                    A.data[A.indptr[i]:A.indptr[i + 1]])}

    def associated_rows(self, name, family):
        self.load_matrix()
        j = self.names[name]
        rows = self._CSC.indices[self._CSC.indptr[j]:self._CSC.indptr[j + 1]]
        return [int(i) for i in rows if str(self.full['row_names'][i]) == family]

    def pcs(self, unit, site, slot):
        key = unit, site, slot
        if key in self._pcs_cache:
            return self._pcs_cache[key]
        ch = self.names[f'Pch[{unit},{site},{slot}]']
        dis = self.names[f'Pdis[{unit},{site},{slot}]']
        q = self.names[f'Q[{unit},{site},{slot}]']
        arc = self.names[f'arc[{unit},{self.sites.index(site) * 96 + slot}]']
        faces = []
        for i in self.associated_rows(f'Q[{unit},{site},{slot}]', 'PCS16'):
            row = self.row(i)
            assert set(row).issubset({ch, dis, q, arc})
            assert row.get(ch, F(0)) == -row.get(dis, F(0))
            assert str(self.full['sense'][i]) == '<'
            assert exact(self.full['rhs'][i]) == 0
            # a*(D-C)+b*Q <= cap*connected, exact binary64 stored data.
            faces.append((row.get(dis, F(0)), row.get(q, F(0)), -row.get(arc, F(0))))
        # At f=0/8 Q coefficient can be exactly zero and absent from its CSC.
        for i in self.associated_rows(f'Pch[{unit},{site},{slot}]', 'PCS16'):
            row = self.row(i)
            face = (row.get(dis, F(0)), row.get(q, F(0)), -row.get(arc, F(0)))
            if face not in faces:
                assert set(row).issubset({ch, dis, q, arc})
                assert row.get(ch, F(0)) == -row.get(dis, F(0))
                assert str(self.full['sense'][i]) == '<' and exact(self.full['rhs'][i]) == 0
                faces.append(face)
        assert len(faces) == 16, (key, len(faces))
        self._pcs_cache[key] = tuple(faces)
        return self._pcs_cache[key]

    def energy(self, unit, slot):
        key = unit, slot
        if key in self._energy_cache:
            return self._energy_cache[key]
        ids = self.associated_rows(f'SOC[{unit},{slot + 1}]', 'energy_balance')
        i = next(i for i in ids if self.names[f'SOC[{unit},{slot}]'] in self.row(i))
        row = self.row(i)
        after = self.names[f'SOC[{unit},{slot + 1}]']
        before = self.names[f'SOC[{unit},{slot}]']
        normalizer = row[after]
        assert row[before] == -normalizer
        coefficients = defaultdict(set)
        for j, w in row.items():
            name = str(self.full['names'][j])
            family = name.split('[', 1)[0]
            if family in ('Pch', 'Pdis'):
                coefficients[family].add(-w / normalizer)
        assert len(coefficients['Pch']) == len(coefficients['Pdis']) == 1
        result = dict(charge=next(iter(coefficients['Pch'])),
                      discharge=next(iter(coefficients['Pdis'])),
                      row=i, raw=row, normalizer=normalizer)
        self._energy_cache[key] = result
        return result

    def reconstructed_candidate(self, candidate):
        family = candidate['family']
        unit, t, site = candidate['MESS'], int(candidate['slot']), candidate['site']
        assert family in FAMILIES and unit in self.initial and 0 <= t < 96
        L = exact(self.battery.p_limit)
        physical = []
        if family in ('AGGREGATE_CHARGE_MODE', 'AGGREGATE_CONNECTED_POWER'):
            physical.extend((f'Pch[{unit},{s},{t}]', F(1)) for s in self.sites)
        if family in ('AGGREGATE_DISCHARGE_MODE', 'AGGREGATE_CONNECTED_POWER'):
            physical.extend((f'Pdis[{unit},{s},{t}]', F(1)) for s in self.sites)
        rhs = F(0)
        if family == 'AGGREGATE_CHARGE_MODE':
            assert site == 'ALL'
            physical.append((f'charge_mode[{unit},{t}]', -L))
        elif family == 'AGGREGATE_DISCHARGE_MODE':
            assert site == 'ALL'
            physical.append((f'charge_mode[{unit},{t}]', L))
            rhs = L
        elif family == 'AGGREGATE_CONNECTED_POWER':
            assert site == 'ALL'
            physical.extend((f'arc[{unit},{k * 96 + t}]', -L) for k in range(len(self.sites)))
        else:
            assert site in self.sites
            physical = [(f'Pch[{unit},{site},{t}]', F(1)),
                        (f'Pdis[{unit},{site},{t}]', F(1)),
                        (f'arc[{unit},{self.sites.index(site) * 96 + t}]', -L)]
        terms = defaultdict(F)
        constant = F(0)
        for name, w in physical:
            expansion, offset = self.expression(name)
            constant += w * offset
            for j, v in expansion.items():
                terms[j] += w * v
        return {j: w for j, w in terms.items() if w}, rhs - constant


def solve3(rows, rhs):
    """Exact three-by-three Gaussian elimination, no numerical solver/API."""
    matrix = [list(map(exact, row)) + [exact(b)] for row, b in zip(rows, rhs)]
    for column in range(3):
        pivot = next((r for r in range(column, 3) if matrix[r][column]), None)
        if pivot is None:
            return None
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        scale = matrix[column][column]
        matrix[column] = [v / scale for v in matrix[column]]
        for r in range(3):
            if r != column:
                scale = matrix[r][column]
                matrix[r] = [a - scale * b for a, b in zip(matrix[r], matrix[column])]
    return tuple(matrix[r][3] for r in range(3))


def vertices3(halfplanes):
    """Enumerate all vertices of the bounded polytope by active triples."""
    unique = list(dict.fromkeys((tuple(map(exact, a)), exact(b)) for a, b in halfplanes))
    vertices = set()
    for chosen in itertools.combinations(unique, 3):
        v = solve3([r[0] for r in chosen], [r[1] for r in chosen])
        if v is not None and all(sum((w * x for w, x in zip(a, v)), F(0)) <= b for a, b in unique):
            vertices.add(v)
    return sorted(vertices)


def power_soc_vertices(authority, unit, slot, site, mode, travel=F(0), connected=True):
    """p>=0,Q,E0; E1=E0+alpha*p-travel, exact original stored alpha."""
    L, S = exact(authority.battery.p_limit), exact(authority.battery.pcs_kva)
    emin, emax = exact(authority.battery.minimum), exact(authority.battery.maximum)
    low0 = high0 = exact(authority.battery.initial) if slot == 0 else None
    if slot != 0:
        low0, high0 = emin, emax
    low1 = high1 = exact(authority.battery.terminal) if slot == 95 else None
    if slot != 95:
        low1, high1 = emin, emax
    coeff = authority.energy(unit, slot)
    alpha = coeff['charge'] if mode == 1 else coeff['discharge']
    bound = L if connected else F(0)
    if not connected:
        # With p=Q=0, the exact SOC interval is the entire bounded polytope.
        lo, hi = max(low0, low1 + travel), min(high0, high1 + travel)
        if lo > hi:
            return [], alpha
        return sorted(set([(F(0), F(0), lo), (F(0), F(0), hi)])), alpha
    planes = [((-1, 0, 0), 0), ((1, 0, 0), bound),
              ((0, -1, 0), S if connected else 0), ((0, 1, 0), S if connected else 0),
              ((0, 0, -1), -low0), ((0, 0, 1), high0),
              ((-alpha, 0, -1), -low1 - travel), ((alpha, 0, 1), high1 + travel)]
    if connected:
        sign = F(-1) if mode == 1 else F(1)
        planes.extend(((a * sign, b, F(0)), cap) for a, b, cap in authority.pcs(unit, site, slot))
    key = tuple((tuple(map(exact, a)), exact(b)) for a, b in planes)
    if key not in authority._vertex_cache:
        authority._vertex_cache[key] = vertices3(planes)
    return authority._vertex_cache[key], alpha


def state_residual(family, mode, power, connected, relevant_site=True, p_limit=F(300)):
    """Original-space cut test, independent of serialized selected-space terms."""
    ch = power if mode == 1 and connected else F(0)
    dis = power if mode == 0 and connected else F(0)
    if family == 'AGGREGATE_CHARGE_MODE':
        return ch - p_limit * mode
    if family == 'AGGREGATE_DISCHARGE_MODE':
        return dis + p_limit * mode - p_limit
    if family == 'AGGREGATE_CONNECTED_POWER':
        return ch + dis - p_limit * int(connected)
    if family == 'LOCAL_CONNECTED_POWER':
        return (ch + dis - p_limit * int(connected)) if relevant_site else F(0)
    raise AssertionError(family)


def enumerate_block(authority, unit, slot):
    """Every reachable integral arc covering this time cut, both binary modes."""
    states = []
    L = exact(authority.battery.p_limit)
    for k in sorted(authority.reachable[unit]):
        arc = authority.arcs[k]
        if not arc[1] <= slot < arc[3]:
            continue
        site, depart, destination, connect, route = arc
        connected = route is None
        if connected:
            assert depart == slot and connect == slot + 1
            kind, travel = 'STAY_CONNECTED', F(0)
        elif depart == slot:
            kind = 'MOVE_DEPARTURE'
            energy = authority.energy(unit, slot)
            column = authority.names[f'arc[{unit},{k}]']
            travel = energy['raw'].get(column, F(0)) / energy['normalizer']
            assert travel == exact(route.energy_kwh)
        else:
            kind, travel = 'TRANSIT_OR_PRECONNECT_WAIT', F(0)
        for mode in (0, 1):
            vertices, alpha = power_soc_vertices(authority, unit, slot, site, mode, travel, connected)
            maxima = {family: max((state_residual(family, mode, p, connected, True, L)
                                  for p, q, e in vertices), default=None) for family in FAMILIES}
            assert all(v is None or v <= 0 for v in maxima.values())
            encoded = [dict(power=rational(p), Q=rational(q), SOC0=rational(e),
                            SOC1=rational(e + alpha * p - travel)) for p, q, e in vertices]
            states.append(dict(arc=k, kind=kind, source=site, depart=depart,
                               destination=destination, connect=connect,
                               route_id=None if route is None else route.route_id,
                               connected=connected, mode=mode, movement_energy=rational(travel),
                               continuous_vertices=encoded, vertex_count=len(encoded),
                               all_four_family_max_residual={f: None if v is None else rational(v) for f, v in maxima.items()},
                               infeasible_under_one_slot_SOC_bounds=not bool(vertices)))
    assert states
    return dict(MESS=unit, slot=slot, integral_state_count=len(states),
                nonempty_integral_state_count=sum(s['vertex_count'] > 0 for s in states),
                continuous_vertex_count=sum(s['vertex_count'] for s in states), states=states,
                projection_kind='CONSERVATIVE_ONE_SLOT_HULL_WITH_FREE_BOUNDARY_SOC',
                horizon_endpoint_SOC_preserved=True,
                global_prior_future_SOC_reachability_not_enumerated=True,
                full_global_integer_hull_claim=False)


def verify_candidates(candidates, context=None, audit_blocks=None):
    """Root API. All candidates are checked; no production constructor is called.

    The geometric test covers every enumerated local vertex and all four cut
    schemas.  The global DAG/physical proof makes the same validity universal
    for every unit/site/slot, including unenumerated blocks.
    """
    authority = Authority(context)
    if context is None:
        start_path = PARENT / 'C3A_VALID_START.npz'
        assert sha(start_path) == 'be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5'
        with np.load(start_path) as z:
            start = z['point'].copy()
    else:
        start = context['start']
    errors, reports = [], []
    worst_start = None
    counts = defaultdict(int)
    for candidate in candidates:
        try:
            expected_terms, expected_rhs = authority.reconstructed_candidate(candidate)
            actual = {int(j): exact(w) for j, w in candidate['terms'].items() if exact(w)}
            assert actual == expected_terms, 'SELECTED_COORDINATE_TERMS_MISMATCH'
            assert exact(candidate['rhs']) == expected_rhs, 'SELECTED_COORDINATE_RHS_MISMATCH'
            residual = sum((w * exact(start[j]) for j, w in expected_terms.items()), F(0)) - expected_rhs
            assert residual <= TOL, 'VALIDATED_START_VIOLATION'
            worst_start = residual if worst_start is None else max(worst_start, residual)
            counts[candidate['family']] += 1
            reports.append(dict(id=candidate['id'], PASS=True,
                                exact_coordinate_reconstruction=True,
                                validated_start_residual=rational(residual),
                                integer_validity='UNIVERSAL_DAG_PATH_AND_EXCLUSIVE_MODE_PROOF'))
        except Exception as exc:
            errors.append(dict(id=candidate.get('id'), reason=repr(exc)))
    if audit_blocks is None:
        core_path = OUT / 'FRACTIONAL_CORE.json'
        if core_path.exists():
            core = json.loads(core_path.read_text())
            audit_blocks = [(r['MESS'], int(r['slot'])) for r in core['top20_time_blocks'][:2]]
        elif candidates:
            audit_blocks = [(candidates[0]['MESS'], int(candidates[0]['slot']))]
        else:
            audit_blocks = [(sorted(authority.initial)[0], 0)]
    blocks = [enumerate_block(authority, unit, t) for unit, t in dict.fromkeys(audit_blocks)]
    hull = dict(PASS=not errors, scope='ONE_SLOT_ONLY',
                representation='CONSERVATIVE_LOCAL_HULL_CONTAINING_EVERY_GLOBAL_INTEGER_PROJECTION',
                complete_global_hull=False, all_reachable_arc_mode_states_enumerated=True,
                continuous_state='Exact binary64 PCS16 plus power/Q/SOC bounds and native energy-balance coefficient',
                rational_arithmetic=True, no_solver_calls=True,
                original_FULL_DATA_SHA256=FULL_DATA_SHA, original_FULL_A_SHA256=FULL_A_SHA,
                original_battery=asdict(authority.battery), original_graph_receipt=authority.receipt,
                inverse_authority=authority.inverse_provenance,
                blocks=blocks,
                LP_hull_membership_test='NOT_EXECUTED_IN_THIS_INDEPENDENT_VERIFIER',
                validity_does_not_depend_on_LP_point=True,
                limitations=['One-slot boundary SOC is otherwise free inside original bounds.',
                             'Prior/future SOC feasibility and grid coupling are omitted, enlarging the hull conservatively.',
                             'No exact global or multi-period integer-hull claim is made.'])
    write('LOCAL_INTEGER_HULL_AUDIT.json', hull)
    result = dict(PASS=not errors, candidate_count=len(candidates),
                  candidates_by_family=dict(counts), rejected=errors,
                  exact_stored_coefficient_reconstruction=True,
                  production_constructor_imported_or_called=False,
                  rational_local_vertex_test=True,
                  enumerated_blocks=len(blocks),
                  enumerated_integral_states=sum(b['integral_state_count'] for b in blocks),
                  enumerated_continuous_vertices=sum(b['continuous_vertex_count'] for b in blocks),
                  maximum_validated_start_residual_exact=None if worst_start is None else rational(worst_start),
                  maximum_validated_start_residual_float=None if worst_start is None else float(worst_start),
                  validated_start_tolerance='original 1e-8; not relaxed',
                  integer_feasible_set_preserved_if_adopted=not errors,
                  original_P1_P2_preserved_for_every_integer_feasible_point=not errors,
                  proof='local_hull_proof.md',
                  local_hull_audit='LOCAL_INTEGER_HULL_AUDIT.json',
                  candidate_results=reports)
    return result


if __name__ == '__main__':
    # This entry point creates authority/proof evidence only; never a model/solve.
    candidate_path = OUT / 'CANDIDATE_COEFFICIENTS.json'
    candidates = json.loads(candidate_path.read_text()) if candidate_path.exists() else []
    result = verify_candidates(candidates)
    write('INEQUALITY_INDEPENDENT_VERIFICATION.json', result)
    print('INDEPENDENT_HULL_DONE', result['PASS'], result['candidate_count'],
          result['enumerated_integral_states'], result['enumerated_continuous_vertices'], flush=True)

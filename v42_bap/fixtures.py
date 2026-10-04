"""Five exhaustive synthetic fixtures; no scientific input files are read."""

from dataclasses import asdict
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
import gurobipy as gp
from scipy import sparse

from v42_dw_root.fixtures import original_fixture, enumerate_vertices
from v42_dw_root.models import Block, build
from v42_dw_resume.audit import corrected_rows, pure_binary_equalities
from v42_integrated.matrix import arrays, audit
from v42_native.mess import Battery, RouteArc, validate as physical_validate

from . import BASE_SHA
from .adapter import restrict_pricing, node_bound
from .state import BinaryProjection, BranchDecision, ColumnRegistry, Tree, digest
from .solver import ToyGuard, NodeCG, BoundedMaster
from .lexicographic import P1Acceptance, call_p2


class FixtureBlock(Block):
    """Reuse matrix transport, price, column SHA and coupling validator.
    Synthetic physical mapping is explicit; production Block is untouched.
    """

    def validate(self, x, physical=True):
        raw = corrected_rows(self.A, self.d, x, True, self.route_mask)
        if not raw['PASS'] or not physical:
            return raw
        names = dict(zip(map(str, self.d['names']), map(float, x)))
        # Native validator arc order: all stays A0,A1,B0,B1, then travel.
        values = {f'arc[MESS01,{j}]': v for j, v in enumerate((names['stay_A0'], names['stay_A1'], 0., names['stay_B1'], names['travel_A0_B1']))}
        values.update({f'SOC[MESS01,{t}]': names[f'SOC[{t}]'] for t in range(3)})
        for s, t in itertools.product(('A', 'B'), range(2)):
            for f in ('Pch', 'Pdis', 'Q'):
                values[f'{f}[MESS01,{s},{t}]'] = names.get(f'{f}[{s},{t}]', 0.)
            mode = names[f'mode[{t}]']
            if values[f'Pch[MESS01,{s},{t}]'] > .5 * mode + 1e-8 or values[f'Pdis[MESS01,{s},{t}]'] > .5 * (1 - mode) + 1e-8:
                return dict(PASS=False, mode_validation=False)
        battery = Battery(0., 2., 1., self.terminal, .5, 1., 1., 1.)
        route = RouteArc('toy', 'A', 'B', 0, 1, 1, .125, '0' * 64)
        plan = dict(values=values, initial_sites={'MESS01': 'A'}, chosen_arcs={'MESS01': [j for j in range(5) if values[f'arc[MESS01,{j}]'] > .5]}, mode='MILP')
        check = physical_validate(plan, ('A', 'B'), (route,), battery, 2, tolerance=1e-8)
        return dict(PASS=raw['PASS'] and check['PASS'], raw=raw, physical=check, exact_discrete=raw['integer_pattern_exact'])


class FixtureProblem:
    def __init__(self, name, units=1, terminal=1., branch_benefit=False, preferred_family='location', empty=False):
        if units not in (1, 2) or preferred_family not in ('location', 'movement'):
            raise ValueError('BOUNDED_FIXTURE_ONLY')
        self.name, self.blocks, self.vertices = name, [], []
        self.local_arrays = []
        # Existing tiny builder only constructs models. It never optimizes here.
        models = []
        try:
            for m in range(units):
                model, A, d, local = original_fixture(terminal)
                models.append(model)
                vertices, _, _ = enumerate_vertices(d, terminal)
                b = FixtureBlock.__new__(FixtureBlock)
                b.unit = f'MESS{m + 1:02d}'
                b.terminal = terminal
                b.A = A[:local, :-1].tocsr()
                b.d = dict(d, names=d['names'][:-1], rhs=d['rhs'][:local], sense=d['sense'][:local], lower=d['lower'][:-1],
                           upper=d['upper'][:-1], types=d['types'][:-1], objective=d['objective'][:-1], constant=np.array(0.), row_names=d['row_names'][:local])
                b.mask = b.d['types'] != 'C'
                b.route_mask = pure_binary_equalities(b.A, b.d)
                self.blocks.append(b)
                self.vertices.append(vertices)
                self.local_arrays.append((A, d, local))
            rows = 2 * units + (units + 1 if branch_benefit else 0) + int(empty)
            self.global_A = sparse.csr_matrix(np.full((rows, 1), -1.))
            rhs = []
            coupling = [sparse.lil_matrix((rows, len(b.d['names']))) for b in self.blocks]
            for m, (A, d, local) in enumerate(self.local_arrays):
                coupling[m][2*m:2*m+2, :] = A[local:, :-1]
                rhs.extend(d['rhs'][local:].tolist())
            if branch_benefit:
                for m in range(units):
                    j = list(map(str, self.blocks[m].d['names'])).index('travel_A0_B1')
                    coupling[m][2*units + m, j] = -1.
                    rhs.append(-.875)
                row = 3 * units
                # A separate, flow-identical binary carries capacity so each
                # original local coordinate has one +/-1 coupling entry.
                for m, b in enumerate(self.blocks):
                    j = list(map(str, b.d['names'])).index('stay_B1')
                    coupling[m][row, j] = 1.
                rhs.append(1. if units == 2 else .5)
                self.global_A = self.global_A.tolil()
                self.global_A[row, 0] = 0.
                self.global_A = self.global_A.tocsr()
            if empty:
                rhs.append(-1.)
                self.global_A = self.global_A.tolil()
                self.global_A[-1, 0] = 0.
                self.global_A = self.global_A.tocsr()
            self.global_d = dict(names=np.array(['rho']), rhs=np.array(rhs), sense=np.array(['<'] * rows),
                                 lower=np.array([0.]), upper=np.array([1.]), types=np.array(['C']), objective=np.array([1.]),
                                 constant=np.array(0.), row_names=np.array([f'toy_coupling[{i}]' for i in range(rows)]))
            projections = []
            for m, b in enumerate(self.blocks):
                b.B = coupling[m].tocsr()
                b.CSC = b.B.tocsc()
                b.model = build(b.A, b.d, 'BAP_SYNTHETIC_LOCAL')
                b.vars = b.model.getVars()
                names = list(map(str, b.d['names']))
                travel = names.index('travel_A0_B1')
                if preferred_family == 'location':
                    projections.append(BinaryProjection('location', m, 1, 'B', ((names.index('stay_B1'), 1.),)))
                projections.append(BinaryProjection('movement', m, 0, 'A0_B1', ((travel, 1.),)))
                for j in np.flatnonzero(b.d['types'] == 'B'):
                    projections.append(BinaryProjection('original_binary', m, 0 if '0' in names[j] else 1, names[j], ((int(j), 1.),)))
            self.projections = tuple(projections)
            self.scientific_sha = digest(dict(base=BASE_SHA, name=name, terminal=terminal, units=units, branch_benefit=branch_benefit,
                                              empty=empty, projections=[asdict(p) for p in projections]))
        finally:
            for model in models:
                model.dispose()

    def close(self):
        for b in self.blocks:
            b.model.dispose()

    def direct(self):
        local = sparse.block_diag([b.A for b in self.blocks], format='csr')
        local = sparse.hstack((local, sparse.csr_matrix((local.shape[0], 1))), format='csr')
        global_rows = sparse.hstack([b.B for b in self.blocks] + [self.global_A], format='csr')
        A = sparse.vstack((local, global_rows), format='csr')
        d = {}
        for k in ('names', 'lower', 'upper', 'types', 'objective'):
            d[k] = np.concatenate([b.d[k] for b in self.blocks] + [self.global_d[k]])
        for k in ('rhs', 'sense', 'row_names'):
            d[k] = np.concatenate([b.d[k] for b in self.blocks] + [self.global_d[k]])
        d['constant'] = np.array(0.)
        return build(A, d, 'BAP_DIRECT_ORIGINAL_TOY'), A, d

    def validate_projection(self, points, global_point, decisions=()):
        if len(points) != len(self.blocks):
            return dict(PASS=False)
        for m, (b, x) in enumerate(zip(self.blocks, points)):
            if not b.validate(np.asarray(x), True)['PASS'] or not all(d.compatible(m, x) for d in decisions):
                return dict(PASS=False)
        z = np.asarray(global_point)
        residual = self.global_A @ z - self.global_d['rhs']
        for b, x in zip(self.blocks, points):
            residual += b.B @ np.asarray(x)
        maximum = float(np.max(residual, initial=0.))
        objective = float(self.global_d['objective'] @ z)
        return dict(PASS=bool(np.isfinite(z).all() and len(z) == 1 and 0. <= z[0] <= 1. + 1e-8 and maximum <= 1e-8),
                    objective=objective, all_original_scientific_rows=True, independent_physical_validation=True, max_global_violation=maximum)

    def column_validator(self, m, x, a, c):
        if not 0 <= m < len(self.blocks) or not self.blocks[m].validate(np.asarray(x), True)['PASS']:
            return False
        expected, cost, _ = self.blocks[m].column(np.asarray(x))
        return np.array_equal(expected, a) and cost == c

    def pricing_min(self, m, decisions, cost, alpha):
        legal = [v for v in self.vertices[m] if all(d.compatible(m, v) for d in decisions)]
        return min(float(cost @ v - alpha) for v in legal)

    def bound_validator(self, lower_bound, certificate, decisions):
        if not certificate.get('PASS') or certificate.get('phase') is not False:
            return False
        expected_sha = digest(dict(pi=certificate['pi'], alpha=certificate['alpha'], node=certificate['node_id'], phase=False))
        if certificate['dual_sha'] != expected_sha:
            return False
        for m, b in enumerate(self.blocks):
            cost = b.d['objective'] - b.B.T @ np.asarray(certificate['pi'])
            if certificate['pricing_bounds'][m] > self.pricing_min(m, decisions, cost, certificate['alpha'][m]) + 1e-8:
                return False
        value, proof = node_bound(self.global_A, self.global_d, np.asarray(certificate['pi']), np.asarray(certificate['alpha']), certificate['pricing_bounds'])
        return value == lower_bound and proof['numerator'] == certificate['numerator'] and proof['denominator'] == certificate['denominator']


def seed(problem, complete=False):
    registry = ColumnRegistry()
    keys = []
    for m, (b, vertices) in enumerate(zip(problem.blocks, problem.vertices)):
        for x in vertices if complete else vertices[:1]:
            assert b.validate(x, True)['PASS']
            a, c, _ = b.column(x)
            keys.append(registry.add(m, x, a, c, 0))
    return registry, tuple(keys)


def complete_integer_master(problem, registry, keys):
    master = BoundedMaster(problem, False)
    for key in keys:
        c = registry.columns[key]
        master.add(c.mess, np.asarray(c.x), np.asarray(c.a), c.c, key)
    for m, b in enumerate(problem.blocks):
        for j in np.flatnonzero(b.d['types'] == 'B'):
            y = master.model.addVar(vtype='B', name=f'original_binary[{m},{j}]')
            master.model.addConstr(y == gp.quicksum(v * c['x'][j] for v, c in zip(master.lambdas, master.column_data) if c['unit'] == m))
    return master


def branch_proofs(problem, guard):
    results = []
    for p in problem.projections:
        # All original integer patterns and their polytope vertices. Since
        # branch projections contain binaries only, this also proves the full
        # continuous polytope partition, not merely sampled continuous points.
        m = p.mess
        parent = set(range(len(problem.vertices[m])))
        children = [{i for i, x in enumerate(problem.vertices[m]) if BranchDecision(p, bit).compatible(m, x)} for bit in (0, 1)]
        assert children[0] | children[1] == parent and not children[0] & children[1]
        for bit, expected in enumerate(children):
            decision = BranchDecision(p, bit)
            proxy = restrict_pricing(problem.blocks[m], m, (decision,), guard)
            try:
                A, d = arrays(proxy.model)
                original = problem.blocks[m]
                assert np.array_equal(A[:original.A.shape[0]].toarray(), original.A.toarray())
                for key in ('lower', 'upper', 'types', 'objective'):
                    assert np.array_equal(d[key], original.d[key])
                generated = {i for i, x in enumerate(problem.vertices[m]) if audit(A, d, x, integral=True, tolerance=1e-8)['PASS']}
                assert generated == expected
            finally:
                proxy.model.dispose()
        results.append(dict(variable=asdict(p), parent_vertices=len(parent), child_counts=list(map(len, children)),
                            union_parent_PASS=True, disjoint_PASS=True, pricing_domain_equal_PASS=True,
                            unchanged_original_rows_and_bounds_PASS=True))
    return results


def equivalence(problem, guard, code_sha):
    model, A, d = problem.direct()
    full_registry, full_keys = seed(problem, True)
    full = complete_integer_master(problem, full_registry, full_keys)
    registry, keys = seed(problem)
    solver = NodeCG(problem, guard)
    tree = Tree(registry, keys)
    try:
        guard.optimize(model, problem.name + '/direct_MILP')
        guard.optimize(full.model, problem.name + '/complete_trajectory_integer_master')
        assert model.Status == full.model.Status == gp.GRB.OPTIMAL
        status = tree.run(solver, problem.projections, problem.validate_projection)
        assert status == 'FINISHED' and tree.incumbent is not None
        optimum = tree.incumbent['objective']
        assert abs(model.ObjVal - optimum) <= 1e-8 and abs(full.model.ObjVal - optimum) <= 1e-8
        # Degenerate optimal modes need not be selected identically by solvers.
        # Verify ONE IDENTICAL optimal physical projection in all three models.
        points, z = tree.incumbent['points'], tree.incumbent['global_point']
        witness = np.concatenate([np.asarray(x) for x in points] + [np.asarray(z)])
        assert audit(A, d, witness, integral=True, tolerance=1e-8)['PASS']
        for variable, value in zip(model.getVars(), witness):
            variable.LB = variable.UB = float(value)
        guard.optimize(model, problem.name + '/identical_original_projection_witness')
        assert model.Status == gp.GRB.OPTIMAL and abs(model.ObjVal - optimum) <= 1e-8
        for m, x in enumerate(points):
            for j, value in enumerate(x):
                full.model.addConstr(gp.quicksum(v * c['x'][j] for v, c in zip(full.lambdas, full.column_data) if c['unit'] == m) == value)
        full.z[0].LB = full.z[0].UB = float(z[0])
        guard.optimize(full.model, problem.name + '/identical_master_projection_witness')
        assert full.model.Status == gp.GRB.OPTIMAL and abs(full.model.ObjVal - optimum) <= 1e-8
        proofs = branch_proofs(problem, guard)
        registry_size = len(registry.columns)
        internal = [n for n in tree.nodes.values() if any(c.parent_id == n.node_id for c in tree.nodes.values())]
        for parent in internal:
            for child in [n for n in tree.nodes.values() if n.parent_id == parent.node_id]:
                active, inactive = registry.partition(parent.column_ids, child.decisions)
                assert set(active) == set(child.inherited_column_ids) and set(inactive) == set(child.inactive_column_ids)
        assert len(registry.columns) == registry_size
        # Crash simulation at a real branching boundary. In-flight node work
        # is replayed from the last atomically published state, never a partial.
        cr, ck = seed(problem)
        crash = Tree(cr, ck)
        crash_solver = NodeCG(problem, guard)
        first = crash.step(crash_solver, problem.projections, problem.validate_projection)
        with tempfile.TemporaryDirectory(prefix='bap_') as directory:
            path = Path(directory) / 'tree.json'
            checkpoint_sha = crash.save(path, problem.scientific_sha, code_sha)
            path.with_suffix('.partial.tmp').write_text('simulated interrupted write', encoding='utf8')
            actual_crash_exit = None
            if problem.name == 'D_location_branch':
                # A pure-stdlib child reconstructs the published tree and dies
                # inside the SAME Tree.save after fsync, before atomic replace.
                # It imports no numerical library and starts no solver.
                child = '''import json, os, sys
from v42_bap.state import Tree, ColumnRegistry, TrajectoryColumn, Node, BranchDecision, BinaryProjection
p=json.load(open(sys.argv[1],encoding='utf8'))['payload']
r=ColumnRegistry()
r._columns={c['column_id']:TrajectoryColumn(c['column_id'],c['mess'],tuple(c['x']),tuple(c['a']),c['c'],c['sha']) for c in p['registry']}
r.provenance=p['provenance']
t=Tree(r,tolerance=p['tolerance'])
t.nodes={}
for raw in p['nodes']:
    raw['decisions']=tuple(BranchDecision(BinaryProjection(**d['variable']),d['value']) for d in raw['decisions'])
    t.nodes[raw['node_id']]=Node(**raw)
t.open_ids=p['queue']; t.completed_ids=p['completed']; t.next_id=p['next_id']; t.incumbent=p['incumbent']
t.nodes[0].rmp_objective=123.
os.replace=lambda *_:os._exit(23)
t.save(sys.argv[1],p['scientific_sha'],p['code_sha'])
'''
                completed = subprocess.run([sys.executable, '-c', child, str(path)], timeout=10, capture_output=True, text=True)
                actual_crash_exit = completed.returncode
                assert actual_crash_exit == 23, completed.stderr
                assert json.loads(path.read_text())['sha'] == checkpoint_sha
            resumed = Tree.load(path, problem.scientific_sha, code_sha, problem.column_validator, problem.projections, problem.validate_projection, problem.bound_validator)
            before = resumed.ordered_queue()
            resumed_status = resumed.run(NodeCG(problem, guard), problem.projections, problem.validate_projection)
            assert resumed_status == status and abs(resumed.incumbent['objective'] - optimum) <= 1e-8
            assert list(resumed.nodes) == list(tree.nodes)
            assert [(n.parent_id, n.decisions, n.fathom_reason) for n in resumed.nodes.values()] == [(n.parent_id, n.decisions, n.fathom_reason) for n in tree.nodes.values()]
            if resumed.incumbent:
                assert problem.validate_projection(resumed.incumbent['points'], resumed.incumbent['global_point'])['PASS']
        result = dict(name=problem.name, PASS=True, MESS=len(problem.blocks), slots=2, sites=2,
                      enumerated_vertices=list(map(len, problem.vertices)), direct_MILP=optimum, complete_trajectory_master=optimum,
                      branch_and_price=optimum, same_optimal_physical_projection_PASS=True, objective_equality_PASS=True,
                      node_count=len(tree.nodes), branch_count=len(internal), generated_columns=len(registry.columns) - len(keys),
                      incumbent_validation=tree.incumbent['validation'], gap=tree.gap,
                      fathom_reasons=[n.fathom_reason for n in tree.nodes.values() if n.fathom_reason],
                      continuous_domain='Every route/mode-pattern polytope vertex; continuous lambda mixtures within a common integral pattern remain legal.')
        return result, proofs, dict(name=problem.name, PASS=True, branched_nodes=len(internal), column_count_preserved=registry_size), dict(name=problem.name, PASS=True,
                           checkpoint_sha=checkpoint_sha, first_step=first, restored_queue=before, resumed_status=resumed_status,
                           objective=optimum, same_branch_tree_PASS=True, ignored_partial_write_PASS=True,
                           actual_writer_crash_exit=actual_crash_exit, crash_child_solver_calls=0), solver.pricing_audits
    finally:
        model.dispose()
        full.model.dispose()


def gap_fixture():
    tree = Tree(ColumnRegistry())
    tree.nodes[0].lower_bound = 99.
    variable = BinaryProjection('location', 0, 1, 'B', ((0, 1.),))
    left, right = tree.split(tree.nodes[0], variable)
    left.lower_bound, right.lower_bound = 99.6, 99.8
    tree.incumbent = dict(objective=100., node_id=0)
    assert tree.global_lb == 99.6 and abs(tree.gap - .004) < 1e-12 and tree.accepted(.005)
    right.lower_bound = 98.
    assert tree.global_lb == 98. and tree.gap == .02 and not tree.accepted(.005)
    right.lower_bound = None
    assert tree.global_lb is None and tree.gap is None and not tree.accepted(.005)
    return dict(PASS=True, UB=100., first_open_LBs=[99.6, 99.8], first_LB=99.6, first_gap=.004,
                second_open_LBs=[99.6, 98.], second_LB=98., second_gap=.02,
                threshold=.005, unknown_node_blocks_acceptance_PASS=True)


def p2_fixture():
    values = [(1., .2, 3), (1., .2, 2), (1., .4, 1), (1.1, .0, 0)]
    accepted = P1Acceptance(1., 1., True, True, 'tiny-p1-scope')
    calls = []
    def layer(name, p1_cap, energy_cap, sha):
        feasible = [v for v in values if v[0] <= p1_cap and (energy_cap is None or v[1] <= energy_cap)]
        j = 1 if name == 'movement_energy' else 2
        value = min(v[j] for v in feasible)
        calls.append(name)
        return dict(validated=True, globally_accepted=True, objective=value, scope_sha=sha)
    result = call_p2(accepted, layer)
    assert calls == ['movement_energy', 'movement_count']
    assert result['movement_energy']['objective'] == .2 and result['movement_count']['objective'] == 2
    return dict(PASS=True, calls=calls, result=result, production_P2_calls=0)

"""Lane-B-only semantic and bounded native tests. No scientific model loading."""

from dataclasses import asdict
import json
from types import SimpleNamespace

import numpy as np
import pytest

from v42_bap import BASE_SHA
from v42_bap.adapter import native_projections, node_bound, restrict_pricing
from v42_bap.fixtures import FixtureProblem, gap_fixture, p2_fixture, seed
from v42_bap.lexicographic import P1Acceptance, call_p2
from v42_bap.solver import ToyGuard, NodeCG
from v42_bap.state import BinaryProjection, BranchDecision, ColumnRegistry, NodeResult, Tree, digest, select_branch
from v42_bap.verify import source_sha, OUT
from v42_integrated.matrix import arrays, audit


def projection(family='location', mess=0, time=1, site='B', j=0):
    return BinaryProjection(family, mess, time, site, ((j, 1.),))


@pytest.fixture
def problem():
    p = FixtureProblem('unit_location', branch_benefit=True)
    yield p
    p.close()


def test_branch_immutable_and_binary_only():
    p = projection()
    decision = BranchDecision(p, 1)
    with pytest.raises(AttributeError):
        decision.value = 0
    for value in (2, -1, .5, True):
        with pytest.raises(ValueError):
            BranchDecision(p, value)
    assert decision.compatible(1, (0.,))  # unrelated MESS unaffected
    assert not decision.compatible(0, (0.,))


def test_fractionality_and_exact_deterministic_ties():
    family = projection('movement', j=0)
    loc = projection('location', j=1)
    assert select_branch((family, loc), ((.5, .25),)) == family
    assert select_branch((family, loc), ((.5, .5),)) == loc
    earlier = projection(time=0, j=2)
    assert select_branch((loc, earlier), ((0., .5, .5),)) == earlier
    assert select_branch((loc,), ((0., 1.),)) is None
    with pytest.raises(ValueError):
        select_branch((loc,), ((0., float('nan')),))


def test_native_location_departure_semantics_and_unreachable_constants():
    route = object()
    b = SimpleNamespace(unit='MESS01', sites=('A', 'B'), arcs=(('A', 0, 'A', 1, None), ('A', 0, 'B', 3, route), ('B', 3, 'B', 4, None)),
                        d=dict(names=np.array(['arc[MESS01,0]', 'arc[MESS01,1]', 'charge_mode[MESS01,2]']), types=np.array(['B', 'B', 'B'])))
    candidates = native_projections((b,))
    loc = next(p for p in candidates if p.family == 'location')
    assert loc.terms == ((0, 1.), (1, 1.))
    assert loc.value((0., 1., 0.)) == 1.
    assert not any(p.family == 'location' and p.site_or_arc == 'B' for p in candidates)
    assert {p.terms[0][0] for p in candidates if p.family == 'original_binary'} == {0, 1, 2}
    assert next(p for p in candidates if p.family == 'movement').time == 0


def test_column_identity_provenance_and_no_deletion(problem):
    registry, keys = seed(problem, True)
    count = len(registry.columns)
    c = registry.columns[keys[0]]
    duplicate = registry.add(c.mess, c.x, c.a, c.c, 8)
    assert duplicate == keys[0] and registry.provenance[duplicate] == [0, 8]
    other = registry.add(1, c.x, c.a, c.c, 8)
    assert other != duplicate
    with pytest.raises(TypeError):
        registry.columns[duplicate] = None
    decision = BranchDecision(problem.projections[0], 1)
    active, inactive = registry.partition(keys, (decision,))
    assert set(active) | set(inactive) == set(keys) and not set(active) & set(inactive)
    assert active and inactive and len(registry.columns) == count + 1


def test_child_inheritance_and_parent_bound(problem):
    registry, keys = seed(problem, True)
    tree = Tree(registry, keys)
    root = tree.nodes[0]
    root.lower_bound = .4
    children = tree.split(root, problem.projections[0])
    assert len(children) == 2
    assert all(c.lower_bound == .4 and c.parent_id == 0 and c.depth == 1 for c in children)
    assert set(children[0].column_ids) | set(children[1].column_ids) == set(keys)
    assert not set(children[0].column_ids) & set(children[1].column_ids)
    assert len(registry.columns) == len(keys)


@pytest.mark.parametrize('status', ['TIME_LIMIT', 'INTERRUPTED', 'RMP_INFEASIBLE_UNPROVEN', 'PRICING_INCONCLUSIVE'])
def test_inconclusive_keeps_node_open_and_never_uses_rmp_as_lb(status):
    tree = Tree(ColumnRegistry())
    result = NodeResult(status, rmp_objective=100.)
    assert tree.step(lambda *_: result, (), lambda *_: dict(PASS=False)) == 'INCONCLUSIVE'
    assert tree.open_ids == [0] and tree.nodes[0].lower_bound is None and tree.incumbent is None
    assert tree.nodes[0].rmp_objective == 100.


def test_integral_candidate_without_closed_pricing_only_updates_validated_ub():
    tree = Tree(ColumnRegistry())
    result = NodeResult('TIME_LIMIT', rmp_objective=1., points=((1.,),), global_point=(1.,))
    validator = lambda *_: dict(PASS=True, objective=1.)
    assert tree.step(lambda *_: result, (projection(),), validator) == 'INCONCLUSIVE'
    assert tree.incumbent['objective'] == 1. and tree.open_ids == [0] and tree.global_lb is None


def test_invalid_incumbent_and_bound_certificate_rejected():
    result = NodeResult('PRICING_CLOSED', rmp_objective=1., points=((1.,),), global_point=(1.,))
    tree = Tree(ColumnRegistry())
    with pytest.raises(ValueError, match='INDEPENDENT_VALIDATION'):
        tree.step(lambda *_: result, (projection(),), lambda *_: dict(PASS=False))
    result = NodeResult('TIME_LIMIT', certified_lower_bound=999.)
    with pytest.raises(ValueError, match='UNVERIFIED_LOWER_BOUND'):
        tree.step(lambda *_: result, (), lambda *_: dict(PASS=False))


def test_validated_integral_and_pricing_proof_fathoming():
    tree = Tree(ColumnRegistry())
    result = NodeResult('PRICING_CLOSED', rmp_objective=1., certified_lower_bound=1., pricing_closed=True,
                        points=((1.,),), global_point=(1.,), certificate=dict(PASS=True))
    assert tree.step(lambda *_: result, (projection(),), lambda *_: dict(PASS=True, objective=1.)) == 'FATHOMED'
    assert tree.nodes[0].fathom_reason == 'PROVEN_NO_IMPROVING_PRICING_AND_INTEGRAL'
    assert tree.global_lb == 1. and tree.gap == 0.


def test_separate_original_integer_optimality_reason():
    tree = Tree(ColumnRegistry())
    result = NodeResult('PRICING_CLOSED', rmp_objective=1., certified_lower_bound=1., pricing_closed=True,
                        points=((1.,),), global_point=(1.,), certificate=dict(PASS=True, integer_original_optimality_proven=True))
    assert tree.step(lambda *_: result, (projection(),), lambda *_: dict(PASS=True, objective=1.)) == 'FATHOMED'
    assert tree.nodes[0].fathom_reason == 'INTEGER_PROJECTED_SOLUTION'


def test_bound_fathoming_without_solver_and_queue_ties():
    tree = Tree(ColumnRegistry())
    root = tree.nodes[0]
    root.lower_bound = .1
    left, right = tree.split(root, projection())
    tree.incumbent = dict(objective=1., node_id=0)
    left.lower_bound = right.lower_bound = 1.
    assert tree.ordered_queue() == [1, 2]
    assert tree.step(lambda *_: pytest.fail('bound dominated node must not solve'), (), None) == 'FATHOMED'
    assert left.fathom_reason == 'BOUND_DOMINATED'
    right.lower_bound = None
    assert tree.global_lb is None and not tree.accepted()
    tree.finish(right, 'EXPLICIT_FIXTURE_TERMINATION')
    assert tree.global_lb is None  # explicit stop is not proof


def test_global_gap_threshold_formula_and_zero_ub():
    assert gap_fixture()['PASS']
    tree = Tree(ColumnRegistry())
    tree.nodes[0].lower_bound = -.000000000001
    tree.incumbent = dict(objective=0., node_id=0)
    assert tree.gap == 1.
    with pytest.raises(ValueError):
        tree.accepted(-1.)


def test_phase_I_recovers_empty_inherited_RMP(problem):
    registry = ColumnRegistry()
    tree = Tree(registry)
    solver = NodeCG(problem, ToyGuard())
    assert tree.run(solver, problem.projections, problem.validate_projection) == 'FINISHED'
    assert tree.incumbent['objective'] == .875 and len(registry.columns) > 0


def test_branch_rows_only_and_pricing_over_complete_local_domain(problem):
    b = problem.blocks[0]
    decision = BranchDecision(problem.projections[0], 1)
    proxy = restrict_pricing(b, 0, (decision,), ToyGuard())
    try:
        A, d = arrays(proxy.model)
        assert A.shape[0] == b.A.shape[0] + 1
        assert np.array_equal(A[:-1].toarray(), b.A.toarray())
        for x in problem.vertices[0]:
            assert audit(A, d, x, integral=True, tolerance=1e-8)['PASS'] == decision.compatible(0, x)
    finally:
        proxy.model.dispose()


def test_size_and_wall_limits_are_hard(problem):
    with pytest.raises(RuntimeError, match='OVERSIZE'):
        ToyGuard(max_vars=1).optimize(problem.blocks[0].model, 'must_not_solve')
    for kwargs in (dict(wall_seconds=31), dict(max_vars=10001), dict(max_rows=20001)):
        with pytest.raises(ValueError):
            ToyGuard(**kwargs)


def test_explicit_fixture_stop_blocks_global_acceptance_even_with_bounds():
    tree = Tree(ColumnRegistry())
    tree.nodes[0].lower_bound = 1.
    tree.incumbent = dict(objective=1., node_id=0)
    tree.finish(tree.nodes[0], 'EXPLICIT_FIXTURE_TERMINATION')
    assert tree.global_lb is None and not tree.accepted()


def test_corrected_bound_not_restricted_objective_and_unknown_bound(problem):
    lb, proof = node_bound(problem.global_A, problem.global_d, np.zeros(len(problem.global_d['rhs'])), np.array([0.]), [-.5])
    assert lb < -.5 and proof['PASS'] and not proof['rmp_objective_used_as_bound']
    with pytest.raises((ValueError, TypeError)):
        node_bound(problem.global_A, problem.global_d, np.zeros(len(problem.global_d['rhs'])), np.array([0.]), [None])


def test_atomic_checkpoint_revalidates_columns_incumbent_and_identity(problem, tmp_path):
    registry, keys = seed(problem)
    tree = Tree(registry, keys)
    solver = NodeCG(problem, ToyGuard())
    assert tree.step(solver, problem.projections, problem.validate_projection) == 'BRANCHED'
    path = tmp_path / 'tree.json'
    code_sha = source_sha()
    tree.save(path, problem.scientific_sha, code_sha)
    loaded = Tree.load(path, problem.scientific_sha, code_sha, problem.column_validator, problem.projections, problem.validate_projection, problem.bound_validator)
    assert loaded.ordered_queue() == tree.ordered_queue()
    with pytest.raises(ValueError, match='IDENTITY'):
        Tree.load(path, 'other-science', code_sha, problem.column_validator, problem.projections, problem.validate_projection, problem.bound_validator)
    with pytest.raises(ValueError, match='IDENTITY'):
        Tree.load(path, problem.scientific_sha, 'other-code', problem.column_validator, problem.projections, problem.validate_projection, problem.bound_validator)
    data = json.loads(path.read_text())
    data['payload']['queue'] = []
    data['sha'] = digest(data['payload'])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='QUEUE_PARTITION'):
        Tree.load(path, problem.scientific_sha, code_sha, problem.column_validator, problem.projections, problem.validate_projection, problem.bound_validator)
    assert tree.run(solver, problem.projections, problem.validate_projection) == 'FINISHED'
    tree.save(path, problem.scientific_sha, code_sha)
    data = json.loads(path.read_text())
    data['payload']['incumbent']['points'][0][0] = .3
    data['sha'] = digest(data['payload'])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='INCUMBENT_INVALID'):
        Tree.load(path, problem.scientific_sha, code_sha, problem.column_validator, problem.projections, problem.validate_projection, problem.bound_validator)


def test_p1_p2_contract_order_and_reject_unaccepted_p1():
    assert p2_fixture()['PASS']
    for acceptance in (P1Acceptance(0., 1., True, True, 'scope'), P1Acceptance(1., 1., False, True, 'scope'),
                       P1Acceptance(1., 1., True, False, 'scope'), P1Acceptance(2., 1., True, True, 'scope')):
        with pytest.raises(ValueError):
            call_p2(acceptance, lambda *_: pytest.fail('P2 must not run before P1 acceptance'))


def test_required_artifacts_and_fixture_evidence():
    verification = json.loads((OUT / 'VERIFICATION.json').read_text(encoding='utf8'))
    assert verification['PASS'] and verification['base_sha'] == BASE_SHA
    assert verification['code_sha'] == source_sha()
    assert verification['direct_MILP_equivalence_cases'] == 5
    resource = json.loads((OUT / 'BAP_RESOURCE_RECEIPT.json').read_text(encoding='utf8'))
    assert resource['full_scale_optimize_calls'] == resource['May_production_calls'] == 0
    assert resource['Gurobi_Threads'] == 1 and resource['max_solve_wall_seconds'] <= 30
    assert resource['max_vars'] <= 10000 and resource['max_rows'] <= 20000
    cases = verification['bounded_fixtures'][:5]
    assert all(c['same_optimal_physical_projection_PASS'] and c['objective_equality_PASS'] for c in cases)
    assert cases[1]['branch_count'] > 0 and cases[3]['branch_count'] > 0 and cases[4]['branch_count'] > 0

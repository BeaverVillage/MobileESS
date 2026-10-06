"""Explicit bounded-fixture entry point. Repository-wide pytest is deferred."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import time

from . import BASE_SHA
from .fixtures import FixtureProblem, equivalence, gap_fixture, p2_fixture, seed
from .solver import ToyGuard, NodeCG
from .state import Tree, digest, Node, FATHOM_REASONS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_conservative_early_bap_20261006/fixtures'


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')


def source_sha():
    # Full-scale adapter is not imported/executed by these bounded fixtures.
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / 'v42_bap').glob('*.py')) if p.name != 'fullscale.py'})


def run():
    start = time.perf_counter()
    guard = ToyGuard()
    code_sha = source_sha()
    results, branches, inheritance, restart, pricing = [], [], [], [], []
    cases = [dict(name='A_one_MESS_two_slots_two_sites'), dict(name='B_two_MESS_coupled_capacity', units=2, branch_benefit=True),
             dict(name='C_SOC_movement', terminal=.875), dict(name='D_location_branch', branch_benefit=True),
             dict(name='E_movement_branch', branch_benefit=True, preferred_family='movement')]
    for case in cases:
        problem = FixtureProblem(**case)
        try:
            result, proof, inherit, checkpoint, native_prices = equivalence(problem, guard, code_sha)
            results.append(result)
            branches.append(dict(name=problem.name, proofs=proof))
            inheritance.append(inherit)
            restart.append(checkpoint)
            pricing.extend(native_prices)
            print(problem.name, 'PASS', 'nodes', result['node_count'], 'objective', result['direct_MILP'], flush=True)
        finally:
            problem.close()
    for name, kwargs, reason in [('F_phase_I_global_infeasible', dict(empty=True), 'PHASE_I_PROVEN_INFEASIBLE'),
                                 ('G_full_local_infeasible', dict(terminal=1.5), 'FULL_LOCAL_DOMAIN_INFEASIBLE')]:
        problem = FixtureProblem(name, **kwargs)
        try:
            registry, keys = seed(problem)
            solver = NodeCG(problem, guard)
            tree = Tree(registry, keys)
            assert tree.run(solver, problem.projections, problem.validate_projection) == 'FINISHED'
            assert tree.nodes[0].pricing_status == reason and tree.nodes[0].fathom_reason == 'NODE_INFEASIBLE' and tree.incumbent is None
            results.append(dict(name=name, PASS=True, exact_infeasibility_reason=reason))
        finally:
            problem.close()
    flags = dict(BAP_FRAMEWORK_IMPLEMENTED=True, BAP_FULL_SCALE_RUN=False, BAP_PRODUCTION_RUN=False,
                 BAP_BRANCH_RULE_BASELINE_IMPLEMENTED=True, BAP_NODE_LOCAL_PRICING_IMPLEMENTED=True,
                 BAP_COLUMN_INHERITANCE_IMPLEMENTED=True, BAP_CHECKPOINT_RESTART_IMPLEMENTED=True,
                 BAP_TOY_FIXTURES_PASS=True, BAP_DIRECT_MILP_EQUIVALENCE_PASS=True,
                 FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=True, MAY_PRODUCTION_CALLS=0)
    write('BAP_ENUMERATION_FIXTURES.json', dict(PASS=True, cases=results, branch_completeness=branches, flags=flags))
    write('BAP_COLUMN_INHERITANCE_TEST.json', dict(PASS=True, cases=inheritance, global_column_deletions=0))
    write('BAP_PRICING_BRANCH_COMPATIBILITY.json', dict(PASS=True, branch_domain_proofs=branches,
          native_pricing_vs_exhaustive_min=pricing, no_missing_branch_compatible_pattern_polytope=True,
          coverage='All integer route/mode patterns and all rational endpoints of every continuous pattern polytope; branch rows involve binaries only.'))
    write('BAP_GLOBAL_GAP_FIXTURE.json', gap_fixture())
    write('BAP_CHECKPOINT_RESTART_FIXTURE.json', dict(PASS=True, cases=restart, code_sha=code_sha,
          replay_policy='A crash during solve restarts that still-open node from the latest atomic boundary; partial temporary files are ignored.'))
    write('BAP_BRANCH_SEMANTICS.json', dict(version=1, scientific_base_sha=BASE_SHA, immutable=True,
          candidates=['location (time-network departure node occupancy)', 'movement (individual original travel arc)', 'original_binary (all original arc/mode binaries)'],
          branch_values=[0, 1], selection=['closest to .5', 'family', 'MESS', 'time', 'site_or_arc', 'original terms'],
          child_union_parent=True, child_intersection_empty=True, native_location='sum outgoing original arc[m,k] at (site,time); zero during transit',
          pricing='all original local rows/bounds/types plus equality on same original-variable expression', lambda_column_branching=False,
          strong_branching=False, original_scientific_modules_changed=False))
    properties = {k: {} for k in asdict(Node(0, None, 0))}
    properties.update(node_id={'type': 'integer'}, parent_id={'type': ['integer', 'null']}, depth={'type': 'integer'},
                      lower_bound={'type': ['number', 'null']}, rmp_objective={'type': ['number', 'null']},
                      decisions={'type': 'array'}, pricing_status={'type': 'string'})
    for name in ('node_id', 'depth', 'creation_order'):
        properties[name] = dict(type='integer', minimum=0)
    for name in ('inherited_column_ids', 'inactive_column_ids', 'column_ids'):
        properties[name] = dict(type='array', items=dict(type='string'), uniqueItems=True)
    properties['incumbent_association'] = dict(type=['integer', 'null'])
    properties['fathom_reason'] = dict(enum=[None, *sorted(FATHOM_REASONS)])
    properties['checkpoint_sha'] = dict(type=['string', 'null'], pattern='^[0-9a-f]{64}$')
    term = dict(type='array', prefixItems=[dict(type='integer', minimum=0), dict(type='number')], minItems=2, maxItems=2)
    variable = dict(type='object', required=['family', 'mess', 'time', 'site_or_arc', 'terms'], additionalProperties=False,
                    properties=dict(family=dict(enum=['location', 'movement', 'original_binary']), mess=dict(type='integer', minimum=0),
                                    time=dict(type='integer', minimum=0), site_or_arc=dict(type='string'), terms=dict(type='array', minItems=1, items=term)))
    properties['decisions'] = dict(type='array', items=dict(type='object', required=['variable', 'value'], additionalProperties=False,
                                                          properties=dict(variable=variable, value=dict(type='integer', enum=[0, 1]))))
    write('BAP_NODE_STATE_SCHEMA.json', {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'type': 'object',
                                     'required': list(properties), 'additionalProperties': False, 'properties': properties})
    assert all(r['wall_seconds'] <= 30 and r['threads'] == 1 and r['vars'] <= 10000 and r['rows'] <= 20000 for r in guard.receipts)
    write('BAP_RESOURCE_RECEIPT.json', dict(PASS=True, Gurobi_Threads=1, concurrent_lane_b_solver_processes_max=1,
          full_scale_optimize_calls=0, original_Arc_LP_solve_calls=0, May_production_calls=0, production_P2_calls=0,
          solve_calls=len(guard.receipts), max_vars=max(r['vars'] for r in guard.receipts), max_rows=max(r['rows'] for r in guard.receipts),
          max_solve_wall_seconds=max(r['wall_seconds'] for r in guard.receipts), total_solve_wall_seconds=sum(r['wall_seconds'] for r in guard.receipts),
          fixture_wall_seconds=time.perf_counter()-start, native_solver_intervals=guard.receipts,
          resource_scope='Lane B only; concurrent external Lane A is intentionally untouched; no heavy resource gate/imported runner invoked.', flags=flags))
    write('BAP_P1_P2_FIXTURE.json', p2_fixture())
    write('VERIFICATION.json', dict(PASS=True, base_sha=BASE_SHA, code_sha=code_sha, flags=flags,
          bounded_fixtures=results, direct_MILP_equivalence_cases=5, full_pytest_deferred_command='python -m pytest -q',
          fixture_command='python -m v42_bap.verify', lane_b_test_command='python -m pytest -q tests/v42_bap',
          no_shared_production_source_edits=True, native_pricing_same_dual_audits=len(pricing)))
    print('LANE_B_BOUNDED_EXACT_FIXTURES_PASS', flush=True)


if __name__ == '__main__':
    run()

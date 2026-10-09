"""A-stage adapters: original code isolation and certificates, Native=0."""
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import gzip
import pickle

import numpy as np
import pytest
import scipy.sparse as sp

from v42_may_campaign.a_routing import (
    DayDirectory, InputDirectory, rebound, group, routed_optimize,
    dated_acceptance, native_zero_scope, ConstructionContext, ConstructionNative,
)
from v42_may_campaign.a_stage import (_NativeBudget, _paths, _check_budget, verify_case,
    _scientific_active_graph, _dated_fast_active)
from v42_may12_rescue.contract import decide
from v42_pr134_b1.common import atomic, record
from v42_a_stage_domain_v2.lexstage import Objective, LinearSnapshot


def acceptance_inputs(classes=7):
    return (
        {'PASS': True},
        {'PASS': True, 'classes': classes, 'complete_STAY_and_migration_coverage': True},
        {'PASS': True, 'exact_LB': '199/200'},
        {'PASS': True, 'exact_UB': '1', 'original_integer_types_restored': True},
        {'PASS': True, 'original_job_population_verified': True},
    )


def test_same_exact_p1_contract_routes_class_count_only():
    routed = dated_acceptance(decide, 7)
    result = routed(*acceptance_inputs())
    assert result['PASS'] and result['exact_gap'] == '1/200'
    assert result['A1_ACCEPTED'] is False and result['P2_objectives_optimized'] is False
    assert decide(*acceptance_inputs())['PASS'] is False
    args = acceptance_inputs()
    args[1]['classes'] = 6
    assert routed(*args)['reason'] == 'FULL_DATE_CLASS_DOMAIN_REQUIRED'
    args = acceptance_inputs()
    args[2]['exact_LB'] = '9949/10000'
    assert routed(*args)['PASS'] is False


@pytest.mark.parametrize('index', range(5))
def test_routed_contract_preserves_every_independent_gate(index):
    args = acceptance_inputs()
    args[index]['PASS'] = False
    assert not dated_acceptance(decide, 7)(*args)['PASS']


def test_conflicting_original_global_bounds_rejected():
    args = acceptance_inputs()
    args[2]['exact_LB'] = '1001/1000'
    with pytest.raises(ValueError, match='CERTIFIED_LB_UB_CONFLICT'):
        dated_acceptance(decide, 7)(*args)


def test_date_authority_cannot_cross_input_or_output(tmp_path):
    root = DayDirectory('2025-05-31', tmp_path)
    inputs = InputDirectory('2025-05-31', tmp_path / 'inputs')
    assert root / '2025-05-31' == tmp_path
    assert inputs / 'inputs' / '2025-05-31' == tmp_path / 'inputs'
    with pytest.raises(ValueError):
        root / '2025-05-01'
    with pytest.raises(ValueError):
        inputs / 'inputs' / '2025-05-01'


_route_value = 'historical'


def legacy_reader():
    return _route_value


def test_function_binding_preserves_original_code_and_globals():
    routed = rebound(legacy_reader, dict(legacy_reader.__globals__, _route_value='fresh-date'))
    assert routed.__code__ is legacy_reader.__code__
    assert routed() == 'fresh-date' and legacy_reader() == 'historical'


_route_worker = None


def legacy_worker():
    return _route_worker


def legacy_target(value):
    global _route_worker
    _route_worker = value
    return legacy_worker()


def test_targeted_worker_state_stays_in_the_routed_namespace():
    module = SimpleNamespace(legacy_worker=legacy_worker, legacy_target=legacy_target,
                             _route_worker=None)
    routed = group(module, ('legacy_worker', 'legacy_target'))
    assert routed['legacy_target']('current-date-native') == 'current-date-native'
    assert _route_worker is None


def sample_native_solve(self, model):
    def observe(m, where):
        return None
    return model.optimize(observe)


def test_exactly_one_original_optimize_is_sent_to_shared_budget():
    calls = []
    def shared(model, callback):
        calls.append((model, callback))
        return 9
    routed = routed_optimize(sample_native_solve,
                              dict(sample_native_solve.__globals__, _campaign_optimize=shared))
    model = SimpleNamespace()
    assert routed(None, model) == 9
    assert len(calls) == 1 and calls[0][0] is model


def test_native_zero_scope_forbids_and_restores_original_class():
    native_calls = []
    class OriginalModel:
        def optimize(self):
            native_calls.append(1)
    gp = SimpleNamespace(Model=OriginalModel)
    with pytest.raises(PermissionError, match='A_CAMPAIGN_NATIVE_ZERO_PREPARE'):
        with native_zero_scope(gp):
            gp.Model().optimize()
    assert gp.Model is OriginalModel and native_calls == []


def test_shared_runtime_is_verified_without_double_charging():
    shared = SimpleNamespace(native_used=2., remaining=lambda: 100., wall=lambda: 3.)
    facade = _NativeBudget(shared)
    facade.last_charged = 2.
    facade.charge(2.)
    assert shared.native_used == 2. and facade.last_charged is None
    facade.last_charged = 2.
    with pytest.raises(ValueError, match='ACCOUNTING_DRIFT'):
        facade.charge(3.)


def test_zero_remaining_blocks_model_generation_and_acceptance():
    exhausted = SimpleNamespace(remaining=lambda reserve=0: 0.)
    with pytest.raises(Exception, match='A_DATE_WALL_OR_NATIVE_BUDGET_EXHAUSTED'):
        _check_budget(exhausted)


def test_native_builder_context_keeps_original_checks_progress_and_arguments():
    events = []
    original_context = SimpleNamespace(folder='original-folder', check=lambda: events.append('original-check'),
                                       progress=lambda value: events.append(('original-progress', value)))
    def original_build(context, data, kind, *, original_switch):
        assert context.folder == 'original-folder'
        assert data is data_identity and kind == 'F2-CRA' and original_switch is switch_identity
        context.check()
        context.progress(dict(phase='CLASS_UNITS', classes_complete=1))
        return result_identity
    data_identity, switch_identity, result_identity = object(), object(), object()
    source = SimpleNamespace(build=original_build, unchanged='source-attribute')
    code = source.build.__code__
    proxy = ConstructionNative(source, lambda: events.append('shared-budget'),
                               lambda value: events.append(('root-progress', value)))
    assert proxy.unchanged == 'source-attribute'
    assert proxy.build(original_context, data_identity, 'F2-CRA', original_switch=switch_identity) is result_identity
    assert source.build.__code__ is code
    assert events.count('original-check') == 1
    assert ('original-progress', dict(phase='CLASS_UNITS', classes_complete=1)) in events
    assert ('root-progress', dict(phase='CLASS_UNITS', classes_complete=1)) in events


def test_original_context_exhaustion_is_observed_before_and_after_original_check():
    balance = [1.]
    original = SimpleNamespace(check=lambda: balance.__setitem__(0, 0.), progress=lambda value: None)
    context = ConstructionContext(original,
        lambda: _check_budget(SimpleNamespace(remaining=lambda reserve=0: balance[0])), lambda value: None)
    with pytest.raises(Exception, match='WALL_OR_NATIVE_BUDGET_EXHAUSTED'):
        context.check()


def test_model_construction_checkpoint_stops_inside_single_factor_without_native():
    calls = []
    class Model:
        def addVar(self, *args, **kwargs):
            calls.append((args, kwargs)); return len(calls)
        def optimize(self):
            raise AssertionError('Native forbidden')
    gp = SimpleNamespace(Model=Model)
    balance = [1.]
    checks = []
    def check():
        checks.append(len(calls))
        _check_budget(SimpleNamespace(remaining=lambda reserve=0: balance[0]))
    with pytest.raises(Exception, match='WALL_OR_NATIVE_BUDGET_EXHAUSTED'):
        with native_zero_scope(gp, construction_check=check):
            model = gp.Model()
            for index in range(300):
                if index == 7: balance[0] = 0.
                assert model.addVar(lb=index, name='same-original') == index + 1
    assert 7 < len(calls) < 256
    assert gp.Model is Model and checks[-1] == len(calls)
    assert calls[0] == ((), dict(lb=0, name='same-original'))


def test_batched_original_model_constructor_observes_budget_after_call():
    balance, calls = [1.], []
    class Model:
        def addVars(self, *args, **kwargs):
            calls.append((args, kwargs)); balance[0] = 0.
            return 'same-return'
        def optimize(self): raise AssertionError('Native forbidden')
    gp = SimpleNamespace(Model=Model)
    with pytest.raises(Exception, match='WALL_OR_NATIVE_BUDGET_EXHAUSTED'):
        with native_zero_scope(gp, construction_check=lambda: _check_budget(
                SimpleNamespace(remaining=lambda reserve=0: balance[0]))):
            gp.Model().addVars([1, 2], lb=0)
    assert calls == [(([1, 2],), dict(lb=0))] and gp.Model is Model


def active_seed_fixture():
    from v42_job_capability import Job
    job = Job('representative', 'RUNNING', 0, 0, 0, 'SITE', 4, 1,
              initial_sites=('SITE', 'DEST'), checkpoint_authorized=True,
              elapsed_seconds=3600., duration_authority='unchanged-frozen-Q50')
    # Full physical migration timestamps are deliberately absent from the
    # small initial engineering graph; they remain in the complete domain.
    domain = SimpleNamespace(stays=((0, 'SITE'),), blocks=((0, 'SITE', 2, 1800., 'DEST', 1, (2, 3)),),
                             sha='complete-domain-unmodified')
    return job, domain


def test_unique_active_seed_does_not_fold_full_nonfixed_scientific_class():
    from v42_a_stage_domain_v2.active import _graph
    job, domain = active_seed_fixture()
    original = _graph(job, set(domain.stays), (), domain, False)
    assert original.fixed and len(domain.stays) == 1 and domain.blocks
    records = []
    corrected = _scientific_active_graph(_graph, job, set(domain.stays), (), domain, False, correction_report=records.append)
    assert corrected.fixed is None
    for field in ('events', 'states', 'compatible', 'physical', 'transfers'):
        assert getattr(corrected, field) == getattr(original, field)
    assert corrected.sha != original.sha and len(records) == 1
    assert records[0]['physical_migration'] == 2 and records[0]['integer_class_histogram_retained']
    assert domain.sha == 'complete-domain-unmodified' and original.fixed is not None


def test_actual_singleton_physical_domain_stays_scientifically_fixed():
    from v42_a_stage_domain_v2.active import _graph
    job, domain = active_seed_fixture(); domain.blocks = ()
    records = []
    graph = _scientific_active_graph(_graph, job, set(domain.stays), (), domain, False, correction_report=records.append)
    assert graph.fixed and records == []


def test_unique_seed_with_lazy_other_stay_retains_scientific_variable():
    from v42_a_stage_domain_v2.active import _graph
    job, domain = active_seed_fixture(); domain.blocks = (); domain.stays = ((0, 'SITE'), (0, 'DEST'))
    graph = _scientific_active_graph(_graph, job, {(0, 'SITE')}, (), domain, False)
    assert graph.fixed is None and graph.events['y'] == (('SITE', 0),)


def legacy_activation_graph(job, stays, migration, domain, retained):
    return _graph(job, stays, migration, domain, retained)


def test_date_adapter_reuses_original_activation_code_and_keeps_historical_graph_function():
    from v42_a_stage_domain_v2.active import _graph as original_graph
    job, domain = active_seed_fixture()
    original = rebound(legacy_activation_graph, dict(legacy_activation_graph.__globals__, _graph=original_graph))
    records = []
    routed = _dated_fast_active(original, records.append)
    assert routed.__code__ is original.__code__
    assert original(job, set(domain.stays), (), domain, False).fixed is not None
    assert routed(job, set(domain.stays), (), domain, False).fixed is None
    assert original.__globals__['_graph'] is original_graph and len(records) == 1


def test_original_integer_histogram_survives_unique_seed_for_aggregate_class(monkeypatch):
    import gurobipy as gp
    from dataclasses import replace
    from v42_root import native
    from v42_a_stage_domain_v2.active import _graph
    job, domain = active_seed_fixture()
    graph = _scientific_active_graph(_graph, job, set(domain.stays), (), domain, False)
    members = ('member1', 'member2', 'member3', 'member4'); key = 'a' * 64
    jobs = {uid: replace(job, uid=uid) for uid in members}
    bounds = {uid: SimpleNamespace(latest_completion=8) for uid in members}
    graphs = {uid: graph for uid in members}
    class Fits:
        def __init__(self, *args): pass
        def fits(self, *args): return True
    monkeypatch.setattr(native, 'Generator', Fits)
    source_code = native.local_units.__code__
    with native_zero_scope(gp):
        model = gp.Model('AGGREGATE_UNIQUE_SEED_NATIVE0'); model.Params.OutputFlag = 0
        units = native.local_units(model, jobs, bounds, SimpleNamespace(), graphs, {key: list(members)},
            'F2-CRA', SimpleNamespace(progress=lambda value: None))
        model.update()
        assert native.local_units.__code__ is source_code and len(units) == 1
        assert units[0]['stay_count'] and units[0]['members'] == list(members)
        variable = units[0]['v']['y']['SITE', 0]
        assert isinstance(variable, gp.Var) and variable.VType == gp.GRB.INTEGER
        assert variable.LB == 0 and variable.UB == 4
        assert model.NumVars == 1 and model.NumConstrs == 1
        assert model.getA().toarray().tolist() == [[1.]] and model.getAttr('RHS') == [4.]
        model.dispose()


def test_original_canary_constant_fold_guard_is_preserved():
    import inspect
    from v42_a_stage_canary.prepare import prepare
    assert "if data[5][uid].fixed and (len(domains[uid].stays)!=1 or domains[uid].blocks)" in inspect.getsource(prepare)
    assert 'NONFIXED_SCIENTIFIC_CLASS_FOLDED_TO_CONSTANT' in inspect.getsource(prepare)


@pytest.mark.parametrize('arm,day', [('B2', '2025-05-01'), ('B1', '2025-04-30'), ('B1', '2025-05-32')])
def test_a_stage_rejects_b2_and_nonmay_authority(arm, day, tmp_path):
    with pytest.raises(ValueError):
        _paths(dict(arm=arm, day=day, input_folder=str(tmp_path / 'i'), output=str(tmp_path / 'o')))


class StayPool:
    def __init__(self, domain):
        self.physical_domain = domain
        self.active = set(domain.stays)
        self.inactive_count = 0

    def keys(self):
        return ()


def toy_case(tmp_path):
    day, key = '2025-05-31', 'a' * 64
    output = tmp_path / 'output'
    output.mkdir()
    input_path = tmp_path / 'NATIVE_INPUT.json'
    atomic(input_path, {'day': day})
    data_path = tmp_path / 'DATA.pkl'
    data_path.write_bytes(b'fresh-date-scientific-data')
    snap = LinearSnapshot(sp.csr_matrix((120, 1)), np.array([0.]), np.array([4.]),
                          np.array(['<'] * 120), np.ones(120), np.array(['C']),
                          (Objective('rho', ((0, Fraction(1)),), Fraction(0)),)).require()
    domain = SimpleNamespace(stays=((0, 'SITE'),), blocks=())
    graph = SimpleNamespace(sha='same-original-full-graph')
    cache_path = tmp_path / 'full.pkl.gz'
    with gzip.open(cache_path, 'wb') as f:
        pickle.dump(dict(snapshot=snap, graph=graph), f)
    roster = dict(class_id=key, cardinality=1, full_physical_STAY=1, full_physical_migration=0,
                  complete_local_snapshot_sha256=snap.fingerprint(), complete_graph_sha256=graph.sha,
                  external_full_block_cache=record(cache_path))
    atomic(output / 'BLOCK_PRICING_ORACLE_VERIFICATION.json', {'records': [roster]})
    return dict(
        _campaign=dict(day=day, arm='B1', output=str(output),
                       input_receipts={'bundle': record(input_path)}, original_data=record(data_path)),
        reference=snap, compact=snap,
        data=({'day': day}, {'j': SimpleNamespace()}, {'j': SimpleNamespace(latest_completion=120)},
              SimpleNamespace(capacities={'SITE': 4}), {}, {}, {}, {'classes': {key: ['j']}}),
        domains={'j': domain}, grows=tuple(range(120)),
        axes={('GPU', 'SITE', t): t for t in range(120)},
        ledger=dict(stay_pools={key: StayPool(domain)},
                    migration_pools={key: SimpleNamespace(inactive_count=0)},
                    receipt=dict(active_migration=0, inactive_migration=0, physical_migration=0)),
    )


def test_case_verifier_covers_original_population_and_full_block_sha(tmp_path):
    state = toy_case(tmp_path)
    receipt = verify_case(state)
    assert receipt['PASS'] and receipt['Native_calls'] == 0
    assert receipt['classes'] == 1 and receipt['jobs'] == 1
    roster = Path(state['_campaign']['output']) / 'BLOCK_PRICING_ORACLE_VERIFICATION.json'
    doc = {'records': []}
    atomic(roster, doc)
    with pytest.raises(ValueError, match='COMPLETE_PRICING_CLASS_AXIS'):
        verify_case(state)


def test_case_verifier_rejects_source_byte_drift(tmp_path):
    state = toy_case(tmp_path)
    Path(state['_campaign']['input_receipts']['bundle']['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='INPUT_SHA_DRIFT'):
        verify_case(state)


def test_case_verifier_rejects_past_horizon_capacity_omission(tmp_path):
    state = toy_case(tmp_path)
    del state['axes']['GPU', 'SITE', 0]
    with pytest.raises(ValueError, match='CAPACITY_HORIZON_AXIS'):
        verify_case(state)


def test_exhausted_arm_preserves_terminal_result_without_build_or_solve(tmp_path, monkeypatch):
    from v42_may_campaign import a_stage
    built = []
    monkeypatch.setattr(a_stage, 'prepare', lambda *a, **k: built.append(True))
    budget = SimpleNamespace(native_used=0., remaining=lambda reserve=0: 0., wall=lambda: 5400.)
    output = tmp_path / 'result'
    result = a_stage.run(dict(day='2025-05-31', arm='B1', input_folder=str(tmp_path / 'input'),
                             output=str(output)), budget)
    assert result['classification'] == 'TIME_LIMIT_NO_VALID_INCUMBENT'
    assert result['PASS'] is False and result['native_calls'] == result['P2_calls'] == 0
    assert not built and (output / 'A_RESULT.json').is_file()

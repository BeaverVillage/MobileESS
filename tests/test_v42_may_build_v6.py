"""Independent small-domain and invalid-point comparisons; Native=0."""
from dataclasses import replace
import pytest
from v42_job_capability import validate, Option
from v42_exact.gates import fixture
from v42_exact.support import ExactFactory
from v42_may_build_v6.efficient_validation import ConstructionChecks, routed_validate, construction_checks
from v42_may_build_v6.interval_projection import Intervals, interval_projection


def outcome(function, *args):
    try:
        return function(*args)
    except ValueError as error:
        return type(error), str(error)


@pytest.mark.parametrize('case', list('ABCDEFGHIJ'))
def test_all_original_projection_states_and_fixed_point(case):
    j, b, r, _ = fixture(case)
    old = ExactFactory(r, max(b.latest_completion, r.control_end)).graph(j, b)
    with interval_projection():
        new = ExactFactory(r, max(b.latest_completion, r.control_end)).graph(j, b)
    assert new == old


def test_union_preserves_holes_sites_empty_and_tail():
    source = [('A', 2, 6), ('A', 4, 9), ('A', 12, 16), ('B', 6, 14), ('A', 3, 3), ('A', 100, 104)]
    intervals = Intervals()
    for row in source:
        intervals.add(*row)
    assert intervals.materialize() == {(s, t) for s, a, b in source for t in range(a, b)}


@pytest.mark.parametrize('case', list('ABCDEFGHIJ'))
def test_every_complete_option_and_invalid_point_matches_original(case):
    from v42_job_capability import build_domain
    j, b, r, _ = fixture(case)
    checks = ConstructionChecks()
    fast = routed_validate(checks)
    options, _ = build_domain(j, b, r)
    for option in options:
        assert outcome(fast, j, option, b, r) == outcome(validate, j, option, b, r)
        for bad in [replace(option, start=-1), replace(option, checkpoint=0),
                    replace(option, segments=(('MISSING', 0, j.service_slots),)),
                    replace(option, wan=option.wan + option.wan) if option.wan else replace(option, wan=(('AB', 0, 9999),))]:
            assert outcome(fast, j, bad, b, r) == outcome(validate, j, bad, b, r)
    checks.verify_resources()


@pytest.mark.parametrize('used', [0, 3, 7.9999999995, 8.000000002])
def test_resource_tolerance_and_post_h_tail(used):
    from v42_job_capability import Job, ServiceBoundary, Resources
    j = Job('tail', 'PENDING', 0, 0, 100, 'A', 5, 2, initial_sites=('A',), duration_authority='TEST')
    b = ServiceBoundary('TEST', True, True, (100,), 105)
    r = Resources({'A': 10}, {'A': (10,)}, {}, {}, 96, 1, {('A', 104): used}, {}, {})
    o = Option(100, 'A', (('A', 100, 105),))
    assert outcome(routed_validate(ConstructionChecks()), j, o, b, r) == outcome(validate, j, o, b, r)


def test_frozen_boundary_require_and_resource_mutation_fail_closed():
    j, b, r, _ = fixture('A')
    c = ConstructionChecks()
    c.boundary(b); c.boundary(b)
    assert c.boundary_hits == 1
    c.limits(r); r.capacities['A'] += 1
    with pytest.raises(ValueError, match='RESOURCE_MUTATION'):
        c.verify_resources()


@pytest.mark.parametrize('case', list('ABCDEFGHIJ'))
def test_full_domain_hash_blocks_stays_unchanged(case):
    from v42_a_stage_domain_v2.domain import physical_domain
    j, b, r, _ = fixture(case)
    old = physical_domain(j, b, r)
    with construction_checks():
        new = physical_domain(j, b, r)
    assert (new.sha, new.stays, new.blocks) == (old.sha, old.stays, old.blocks)


def test_observer_covers_fresh_data_and_enters_once(tmp_path, monkeypatch):
    from v42_may_build_v6 import a_stage,build_reuse
    events=[]
    class Observer:
        def __init__(self,*args):pass
        def __enter__(self):events.append('enter');return self
        def __exit__(self,*args):events.append('exit')
    monkeypatch.setattr(build_reuse,'BuildObserver',Observer)
    monkeypatch.setattr(a_stage,'_prepare',lambda *args:events.append('fresh_data') or {'Native_calls':0})
    assert a_stage.prepare({'output':str(tmp_path/'output')})=={'Native_calls':0}
    assert events==['enter','fresh_data','exit']
    with pytest.raises(PermissionError,match='FRESH_PREPARE_DIRECTORY_REQUIRED'):
        a_stage.prepare({'output':str(tmp_path/'output')})

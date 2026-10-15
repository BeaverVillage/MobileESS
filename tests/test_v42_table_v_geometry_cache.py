"""Lossless cache sharing across distinct, valid native window receipts."""
from dataclasses import replace

import pytest

from v42_boundary.generator import Generator
from v42_integration import a_engine
from v42_integration import table_v_geometry_cache as cached
from v42_native.service import NativeServiceBoundary, CONTRACT
from test_v42_authorized_geometry import geometry


def inputs():
    job, bound, resources = geometry()
    native = NativeServiceBoundary(CONTRACT, True, False, bound.allowed_starts,
                                   bound.latest_completion, 'a' * 64, 'd' * 64)
    return job, native, resources


def test_distinct_window_lineage_shares_geometry_and_reseals_each_uid():
    job, bound, resources = inputs()
    generator = Generator(resources, bound.latest_completion)
    cache = {}
    first, graph, hit = cached.authorized_geometry(job, bound, resources, generator, False, cache)
    assert not hit
    other = replace(job, uid='other', qos_receipt_sha='b' * 64)
    other_bound = replace(bound, window_authority_sha256='b' * 64)
    second, shared, hit = cached.authorized_geometry(other, other_bound, resources, generator, False, cache)
    direct, direct_graph, _ = a_engine.authorized_geometry(other, other_bound, resources, generator, False, {})
    assert hit and len(cache) == 1 and graph is shared
    assert (second.stays, second.blocks, second.sha) == (direct.stays, direct.blocks, direct.sha)
    assert tuple(second) == tuple(direct)
    assert shared.sha == direct_graph.sha
    assert first.sha != second.sha


@pytest.mark.parametrize('field,value', [
    ('allowed_starts', (2, 3)),
    ('latest_completion', 15),
    ('duration_authority_sha256', 'e' * 64),
])
def test_numerical_window_and_duration_authority_are_not_shared(field, value):
    job, bound, resources = inputs()
    generator = Generator(resources, bound.latest_completion)
    cache = {}
    cached.authorized_geometry(job, bound, resources, generator, False, cache)
    changed = replace(bound, **{field: value})
    if field == 'allowed_starts':
        job = replace(job, qos_allowed_starts=value)
    _, _, hit = cached.authorized_geometry(job, changed, resources, generator, False, cache)
    assert not hit


def test_invalid_lineage_is_rejected_even_with_a_numerical_cache_hit():
    job, bound, resources = inputs()
    generator = Generator(resources, bound.latest_completion)
    cache = {}
    cached.authorized_geometry(job, bound, resources, generator, False, cache)
    with pytest.raises(Exception, match='SERVICE_INPUT_LINEAGE'):
        cached.authorized_geometry(job, replace(bound, window_authority_sha256=''),
                                   resources, generator, False, cache)


def test_original_functions_and_global_namespace_are_unchanged():
    assert a_engine.authorized_geometry.__globals__['asdict'] is not cached._geometry_asdict
    assert a_engine.authorized_data.__globals__['authorized_geometry'] is a_engine.authorized_geometry
    assert cached.authorized_geometry.__code__ is a_engine.authorized_geometry.__code__
    assert cached.authorized_data.__code__ is a_engine.authorized_data.__code__

import json
import pytest
from v44_actual_audit_encoding import ExactImmutableEncoding
from v44_recovery_r029.immutable import freeze
from v44_recovery_r029.current_ac_performance import ExactAuditEncoding


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def test_immutable_identity_hits_return_exact_bytes_and_keep_original_owner():
    value = freeze({'a': [{'전압': 1.000000000001, 'negative_zero': -0.0}]})
    cache = ExactImmutableEncoding()
    assert cache.encoded(value, canonical) == canonical(value)
    assert cache.encoded(value, canonical) == canonical(value)
    assert cache.identity_hits == 1
    with pytest.raises(TypeError):
        value['a'].append(0)


def test_mutable_fields_are_rehashed_and_modified_values_never_reuse_a_hit():
    value = {'v': [1]}
    cache = ExactImmutableEncoding()
    first = cache.encoded(value, canonical)
    value['v'][0] = 2
    assert cache.encoded(value, canonical) != first
    assert cache.identity_hits == 0


def test_same_object_with_different_encoder_is_not_reused():
    value = freeze({'x': 1})
    cache = ExactImmutableEncoding()
    one = lambda v: 'a'+canonical(v)
    two = lambda v: 'b'+canonical(v)
    assert cache.encoded(value, one).startswith('a')
    assert cache.encoded(value, two).startswith('b')


def test_eviction_and_oversized_values_stay_within_original_budget():
    cache = ExactImmutableEncoding(max_bytes=1000)
    for i in range(30):
        value = freeze({'i': i, 'items': list(range(50))})
        assert cache.encoded(value, canonical) == canonical(value)
        assert cache.bytes == sum(entry[1] for entry in cache.cache.values()) <= 1000
    huge = freeze({'x': 'x'*2000})
    assert cache.encoded(huge, canonical) == canonical(huge)
    assert cache.bytes <= 1000


def test_complete_raw_rows_and_changed_trajectory_sha_match_original_encoder():
    old, new = ExactAuditEncoding(), ExactImmutableEncoding()
    physical = freeze({'nodes': [{'v': 0.95}], 'currents': [], 'transformers': []})
    rows = [dict(slot=0, physical=physical, frozen_trajectory_SHA='a', events=[1, 2])]
    for token in ('a', 'a', 'b', 'c'):
        rows[0]['frozen_trajectory_SHA'] = token
        assert new.canonical_list(rows, canonical) == old.canonical_list(rows, canonical)
        assert new.canonical_list(rows, canonical) == canonical(rows)


def test_mutable_subclass_custom_reduction_keeps_original_behavior():
    class Custom(dict):
        def __reduce_ex__(self, protocol):
            raise RuntimeError('CUSTOM_REDUCTION')
    with pytest.raises(RuntimeError, match='CUSTOM_REDUCTION'):
        ExactImmutableEncoding().encoded(Custom(x=1), canonical)

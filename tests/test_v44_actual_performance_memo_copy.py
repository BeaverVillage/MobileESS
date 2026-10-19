from copy import deepcopy
import pytest
from v44_actual_performance.memo_copy import clone_physical


@pytest.mark.parametrize('value',[(1,2),set(),{1,2},frozenset({1,2}),bytearray(b'abc')])
def test_other_builtin_containers_preserve_deepcopy_semantics(value):
    source={'x':value,'y':value}
    result=clone_physical(source);reference=deepcopy(source)
    assert type(result['x']) is type(reference['x']) and result==reference
    assert result['x'] is result['y']
    if type(value) is tuple:
        assert result['x'] is value


def test_external_memo_and_tuple_cycle():
    source=[];bridge=(source,);source.append(bridge)
    memo={};result=clone_physical(source,memo)
    assert result[0][0] is result and clone_physical(source,memo) is result


def test_complex_leaf_preserved():
    assert clone_physical({'x':3+4j})=={'x':3+4j}


def test_global_copyreg_hooks_cannot_execute():
    import copyreg
    class Custom:pass
    def reduce(value):raise AssertionError('Unexpected custom serializer')
    copyreg.pickle(Custom,reduce)
    try:
        # deepcopy also consults copyreg, so use an explicit deepcopy protocol.
        Custom.__deepcopy__=lambda self,memo:'original-deepcopy'
        assert clone_physical({'x':Custom()})=={'x':'original-deepcopy'}
    finally:copyreg.dispatch_table.pop(Custom,None)


def test_nan_key_keeps_original_key_identity():
    key=float('nan');source={key:[1,2]}
    result=clone_physical(source)
    assert next(iter(result)) is key and result==source


def test_scope_is_B3_only_and_restores_after_exception():
    from types import SimpleNamespace
    import v44.svr11_ac as ac
    from v44_actual_performance.current_ac import scope
    from v44_recovery_r015.current_ac_performance import ExactAuditEncoding
    from v44_recovery_r015.physical_copy import clone_physical as b1_copy
    original=ac.deepcopy
    with pytest.raises(ValueError,match='SENTINEL'):
        with scope(ExactAuditEncoding(),SimpleNamespace(arm='B3')):
            assert ac.deepcopy is clone_physical
            raise ValueError('SENTINEL')
    assert ac.deepcopy is original
    with scope(ExactAuditEncoding(),SimpleNamespace(arm='B1')):
        assert ac.deepcopy is b1_copy
    assert ac.deepcopy is original
    with scope(ExactAuditEncoding(),SimpleNamespace(arm='B3',_independent_fresh=True)):
        assert ac.deepcopy is original

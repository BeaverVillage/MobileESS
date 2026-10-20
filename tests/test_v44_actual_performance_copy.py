import math
from copy import deepcopy

import numpy as np
from v44_actual_performance.memo_copy import clone_physical


def test_nested_physical_graph_is_independent_and_keeps_shared_children():
    child = {'tap': 1.00625, 'queue': [15, 2]}
    source = {'nodes': [child, child], 'live': child}
    result = clone_physical(source)
    assert result == deepcopy(source)
    assert result['nodes'][0] is result['nodes'][1] is result['live']
    result['live']['queue'].append(8)
    assert source['live']['queue'] == [15, 2]


def test_cycles_and_special_float_bits_are_preserved():
    source = {'negative_zero': -0.0, 'inf': math.inf, 'nan': math.nan}
    source['cycle'] = [source]
    result = clone_physical(source)
    assert result['cycle'][0] is result
    assert math.copysign(1, result['negative_zero']) == -1
    assert result['inf'] == math.inf and math.isnan(result['nan'])


def test_custom_protocols_and_arrays_use_deepcopy():
    class Custom:
        def __deepcopy__(self, memo):
            return 'deepcopy-result'

        def __reduce__(self):
            raise AssertionError('Custom pickle protocol must never run')

    array = np.array([1.0, 2.0])
    source = [Custom(), array, array]
    result = clone_physical(source)
    assert result[0] == 'deepcopy-result'
    assert result[1] is result[2] and result[1] is not array
    np.testing.assert_array_equal(result[1], array)


def test_container_subclasses_use_deepcopy():
    class CustomDict(dict):
        def __deepcopy__(self, memo):
            return {'custom': True}

    assert clone_physical({'x': CustomDict(a=1)}) == {'x': {'custom': True}}

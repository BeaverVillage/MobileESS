from copy import deepcopy
from dataclasses import dataclass
import numpy as np
from v44_recovery_r024.physical_copy import clone_physical


def test_nested_physical_graph_is_independent_and_aliases_survive():
    node=dict(v=1.03,phases=[1,2,3],label='한글',active=True,value=None)
    source=dict(nodes=[node,node],queue=[],inputs={'p':[-0.0,4.]})
    clone=clone_physical(source)
    assert clone==deepcopy(source)
    assert clone is not source and clone['nodes'][0] is not node
    assert clone['nodes'][0] is clone['nodes'][1]
    clone['nodes'][0]['phases'].append(4)
    assert node['phases']==[1,2,3]


def test_cycles_through_tuples_and_external_memo():
    source=[];bridge=(source,);source.append(bridge)
    memo={};clone=clone_physical(source,memo)
    assert clone[0][0] is clone
    assert memo[id(source)] is clone
    assert clone_physical(source,memo) is clone


def test_custom_protocol_and_subclasses_keep_original_deepcopy_contract():
    class Special:
        def __deepcopy__(self,memo):return {'original_protocol':True}
    class CustomList(list):pass
    source={'object':Special(),'list':CustomList([1,{'v':4}])}
    clone=clone_physical(source)
    assert clone['object']=={'original_protocol':True}
    assert type(clone['list']) is CustomList
    clone['list'][1]['v']=7
    assert source['list'][1]['v']==4


def test_numpy_dtype_flags_values_and_shared_buffer_object_match_deepcopy():
    a=np.array([1.,-0.,3.]);a.setflags(write=False)
    source=[a,a,np.float64(1.2)]
    got=clone_physical(source);expected=deepcopy(source)
    assert got[0] is got[1] and got[0] is not a
    assert got[0].dtype==expected[0].dtype
    assert got[0].flags.writeable==expected[0].flags.writeable
    assert got[0].tobytes()==expected[0].tobytes()
    assert type(got[2]) is type(expected[2])


def test_nonprimitive_keys_and_container_cross_aliases():
    class Key:pass
    key=Key();item={'x':[1,2]};source={key:item,'same':item,'tuple':(item,)}
    got=clone_physical(source)
    copied_key=next(k for k in got if type(k) is Key)
    assert copied_key is not key
    assert got[copied_key] is got['same'] is got['tuple'][0]


def test_new_copy_is_B1_original_and_B3_validated_C_copy():
    from types import SimpleNamespace
    import v44.svr11_ac as ac
    from v44_recovery_r024.current_ac_performance import live_read_scope
    original=ac.deepcopy
    from v44_recovery_r024.b3_copy import clone_physical as b3_copy
    with live_read_scope(oracle=SimpleNamespace(arm='B3')):
        assert ac.deepcopy is b3_copy
    with live_read_scope(oracle=SimpleNamespace(arm='B1')):
        assert ac.deepcopy is clone_physical
    assert ac.deepcopy is original

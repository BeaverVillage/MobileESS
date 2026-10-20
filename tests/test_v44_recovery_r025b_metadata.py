import gc,weakref
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import opendssdirect as d
from v44_recovery_r025b.property_metadata import PropertySchema,named_property,equipment_reader
from v44_recovery_r025b.current_ac_performance import live_properties


def circuit():
    engine=d.NewContext();engine.Text.Command('new circuit.metadata')
    engine.Text.Command('new load.x bus1=sourcebus kv=12.47 kw=30 kvar=10')
    engine.Text.Command('new transformer.tx phases=3 windings=2 buses=[sourcebus b.1.2.3] kvs=[12.47 .48] kvas=[500 500]')
    engine.Circuit.SetActiveElement('load.x');return engine


def test_every_value_remains_live_after_metadata_hit():
    engine=circuit();schema=PropertySchema()
    expected={k:str(engine.Properties.Value(k)) for k in engine.CktElement.AllPropertyNames()}
    assert live_properties(engine,schema)==expected
    engine.Loads.Name('x');engine.Loads.kW(71);engine.Loads.kvar(19)
    engine.Circuit.SetActiveElement('load.x')
    values=live_properties(engine,schema)
    assert values['kW']=='71' and values['kvar']=='19'
    assert schema.reads==1 and schema.hits==1
    engine.Basic.ClearAll()


def test_each_object_and_independent_context_reads_own_schema():
    left=circuit();right=circuit();schema=PropertySchema()
    for engine in (left,right):
        for name in ('load.x','transformer.tx'):
            engine.Circuit.SetActiveElement(name);live_properties(engine,schema);live_properties(engine,schema)
    assert schema.reads==4 and schema.hits==4 and len(schema.engines)==2
    left.Basic.ClearAll();right.Basic.ClearAll()


def test_live_class_count_drift_fails_closed():
    engine=circuit();schema=PropertySchema();live_properties(engine,schema)
    entries=schema.engines[engine];key=next(iter(entries));index,count,names=entries[key]
    entries[key]=(index,count+1,names)
    with pytest.raises(ValueError,match='SCHEMA_DRIFT'):live_properties(engine,schema)
    engine.Basic.ClearAll()


def test_schema_cache_does_not_hold_an_engine():
    class Fake:pass
    engine=Fake();schema=PropertySchema();schema.engines[engine]={1:(1,1,('p',))}
    ref=weakref.ref(engine);del engine;gc.collect()
    assert ref() is None and len(schema.engines)==0


def test_named_getter_same_value_selector_and_native_error():
    engine=circuit();engine.Circuit.SetActiveElement('transformer.tx')
    for name in ('NormAmps','EmergAmps','NormHkVA','EmergHkVA','Xhl','%noloadloss'):
        expected=engine.Properties.Value(name);selector=engine.Properties._lib.DSSProperty_Get_Name()
        assert named_property(engine,name)==expected
        assert engine.Properties._get_string(engine.Properties._lib.DSSProperty_Get_Name())==engine.Properties._get_string(selector)
    with pytest.raises(Exception) as expected_error:engine.Properties.Value('not_a_property_r025b')
    with pytest.raises(type(expected_error.value)) as actual_error:named_property(engine,'not_a_property_r025b')
    assert str(actual_error.value)==str(expected_error.value)
    engine.Basic.ClearAll()


def test_equipment_reader_preserves_all_values_and_detects_edits():
    from v44.svr12 import scope
    with scope():
        import v42_voltage_control.integration as integration
        engine=circuit();fast=equipment_reader(integration._equipment)
        assert fast(engine)==integration._equipment(engine)
        engine.Transformers.Name('tx');engine.Transformers.kVA(450)
        assert fast(engine)==integration._equipment(engine)
        engine.Basic.ClearAll()


def test_named_reader_shape_drift_rejected():
    def wrong(engine):return {}
    with pytest.raises(ValueError,match='BOUNDARY_DRIFT'):equipment_reader(wrong)


def test_backend_identity_drift_blocks_dispatch(monkeypatch,tmp_path):
    from v44_recovery_r025b import operations
    from v44.common import record,digest
    dependency=tmp_path/'native-schema.bin';dependency.write_bytes(b'original')
    pins=[record(dependency)]
    overlay=dict(sources=operations.sources(),schema_backend_sources=pins,handover_guard=pins[0],validation=pins[0])
    permit=dict(autonomous_recovery_overlay=overlay,autonomous_recovery_policy_sha=digest(overlay))
    monkeypatch.setattr(operations.q,'validate',lambda path:permit)
    monkeypatch.setattr(operations,'schema_backend_sources',lambda:pins)
    assert operations.validate() is permit
    dependency.write_bytes(b'changed')
    with pytest.raises(Exception):operations.validate()


def test_B3_uses_immutable_class_metadata_and_B1_keeps_object_metadata():
    from v44_recovery_r025b.current_ac_performance import live_read_scope
    from v44_recovery_r025b.class_metadata import ClassPropertySchema
    engine=circuit()
    with live_read_scope(oracle=SimpleNamespace(arm='B3')) as schema:
        assert isinstance(schema,ClassPropertySchema)
    with live_read_scope(oracle=SimpleNamespace(arm='B1')) as schema:
        assert isinstance(schema,PropertySchema)
    engine.Basic.ClearAll()

import gc,weakref
import pytest
from v44_recovery_r014.class_metadata import ClassPropertySchema
from v44_recovery_r014.current_ac_performance import live_properties
from test_v44_recovery_r014_metadata import circuit

def test_every_property_of_different_objects_matches_original_and_stays_live():
    engine=circuit();engine.Text.Command('new load.y bus1=sourcebus kv=12.47 kw=51 kvar=23')
    schema=ClassPropertySchema()
    for name in ['load.x','load.y','transformer.tx','load.y']:
        engine.Circuit.SetActiveElement(name)
        expected={key:str(engine.Properties.Value(key)) for key in engine.CktElement.AllPropertyNames()}
        assert live_properties(engine,schema)==expected
        assert engine.Properties._get_string(engine.Properties._lib.DSSProperty_Get_Name())==list(expected)[-1]
    assert schema.reads==2 and schema.hits==2
    engine.Loads.Name('y');engine.Loads.kW(87);engine.Loads.kvar(31);engine.Circuit.SetActiveElement('load.y')
    values=live_properties(engine,schema);assert values['kW']=='87' and values['kvar']=='31'
    engine.Basic.ClearAll()

def test_contexts_never_share_metadata():
    left=circuit();right=circuit();schema=ClassPropertySchema()
    for engine in [left,right]:live_properties(engine,schema)
    assert schema.reads==2 and schema.hits==0 and len(schema.engines)==2
    left.Basic.ClearAll();right.Basic.ClearAll()

def test_class_count_drift_fails_closed_on_every_read():
    engine=circuit();schema=ClassPropertySchema();live_properties(engine,schema)
    index=next(iter(schema.engines[engine]));count,names=schema.engines[engine][index]
    schema.engines[engine][index]=(count+1,names)
    with pytest.raises(ValueError,match='CLASS_SCHEMA_PROPERTY_COUNT_DRIFT'):live_properties(engine,schema)
    engine.Basic.ClearAll()

def test_weak_context_ownership():
    class Engine:pass
    engine=Engine();schema=ClassPropertySchema();schema.engines[engine]={1:(1,('p',))}
    ref=weakref.ref(engine);del engine;gc.collect()
    assert ref() is None and not schema.engines

def test_no_property_value_stored():
    engine=circuit();schema=ClassPropertySchema();live_properties(engine,schema)
    for count,names in schema.engines[engine].values():
        assert type(count) is int and all(type(name) is str for name in names)
    engine.Basic.ClearAll()

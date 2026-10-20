from types import SimpleNamespace
import pytest
from v44_actual_audit_light import Projection, BRANCH_DISCARDED, ADDED_TRANSFORMER_DISCARDED, REGULATOR_DISCARDED


def fixture(values):
    calls, disposed = [], []
    names = tuple(values)
    null = object()
    obj = object()
    def get(pointer, index):
        key = names[index-1]
        calls.append(key)
        return values[key]
    lib = SimpleNamespace(CktElement_Get_Pointer=lambda:obj, Obj_GetAsString=get,
                          DSS_Dispose_String=disposed.append, DSSProperty_Set_Index=lambda i:None)
    props = SimpleNamespace(_lib=lib, _api_util=SimpleNamespace(ffi=SimpleNamespace(NULL=null)),
                            _check_for_error=lambda:None, _get_string=lambda raw:raw)
    engine = SimpleNamespace(Properties=props, Circuit=SimpleNamespace(SetActiveElement=lambda name:1))
    projection = Projection(lambda e,n:dict(values))
    projection.schema = SimpleNamespace(names=lambda e,p:names)
    return engine, projection, calls, disposed


@pytest.mark.parametrize('added', [False, True])
def test_only_fields_explicitly_discarded_by_static_comparison_are_elided(added):
    values = dict(Bus='a', Buses='a b', Wdg='1', WdgCurrents='expensive', Tap='1.00625',
                  Taps='1 1.00625', NormHkVA='400', XHL='0.1', enabled='Yes')
    engine, p, calls, disposed = fixture(values)
    token = p.added.set(frozenset({'transformer.test'}) if added else frozenset())
    try:
        out = p.properties(engine, 'Transformer.test')
    finally:
        p.added.reset(token)
    skipped = ADDED_TRANSFORMER_DISCARDED if added else BRANCH_DISCARDED
    assert out == {k:v for k,v in values.items() if k not in skipped}
    assert set(calls) == set(out)
    assert len(disposed) == len(out)
    assert p.omitted == len(set(values)&skipped)


def test_original_regulator_static_projection_keeps_all_consumed_parameters_live():
    engine, p, calls, _ = fixture(dict(TapNum='1', Reset='No', Vreg='120', Delay='15', enabled='Yes'))
    token = p.added.set(frozenset())
    try:
        assert p.properties(engine, 'RegControl.creg1a', regulators=True) == dict(Vreg='120', Delay='15', enabled='Yes')
    finally:
        p.added.reset(token)
    assert not set(calls)&REGULATOR_DISCARDED


def test_consumed_parameter_changes_are_never_memoized():
    values = dict(NormHkVA='400', WdgCurrents='unused')
    engine, p, _, _ = fixture(values)
    token = p.added.set(frozenset())
    try:
        assert p.properties(engine, 'Transformer.x')['NormHkVA'] == '400'
        values['NormHkVA'] = '401'
        assert p.properties(engine, 'Transformer.x')['NormHkVA'] == '401'
    finally:
        p.added.reset(token)


def test_unscoped_and_unsupported_engines_keep_full_original_reader():
    engine, p, calls, _ = fixture(dict(WdgCurrents='full'))
    assert p.properties(engine, 'Transformer.x') == dict(WdgCurrents='full')
    assert not calls
    assert p.fallbacks == 1


def test_original_error_and_owned_string_disposal_are_retained():
    engine, p, _, disposed = fixture(dict(NormHkVA='400'))
    def fail():
        raise ValueError('original native error')
    engine.Properties._check_for_error = fail
    token = p.added.set(frozenset())
    try:
        with pytest.raises(ValueError, match='original native error'):
            p.properties(engine, 'Transformer.x')
    finally:
        p.added.reset(token)
    assert disposed == ['400']

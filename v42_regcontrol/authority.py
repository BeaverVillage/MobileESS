"""Exact PR127/source parameter integrity. No control-setting setter or tuning."""
import hashlib
import importlib.util
import json
import os
import sys
from functools import lru_cache
from .common import *


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@lru_cache(None)
def source():
    audit = read(AUDIT/'REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json')
    for row in audit['static_source_graph']['files']+audit['code_read']:
        resolve(row)
    expected = audit['actual_static_compile']
    if expected != audit['planning_static_compile']:
        raise ValueError('PR127_COMPILER_AUTHORITY_MISMATCH')
    spec = importlib.util.spec_from_file_location('pr127_control_inventory',AUDIT/'audit_sources.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.insert(0,str(CODE))
    from dayahead.v28r2.opendss_mapping import FeederAssets,compile_clean_engine,REGULATORS,CAPACITORS
    from dayahead.v40e.mapping import NativeAllocation
    from dayahead.v28r2.opendss_backend import _native_state,_voltage_vector,_branch_measurement
    from v42_thermal.measurement import branch_measurement
    from dayahead.full_ieee123_g11_v16_1 import _oriented_branches
    from dayahead import grid_background_v16_2 as bg
    old = read(OLD/'ELECTRICAL_SOURCE_AUTHORITY.json')
    static = [resolve(r) for r in old['static_sources'][:6]]
    assets = FeederAssets(*static)
    # Same exact ten normalization/static authorities as PR125; no May rows loaded.
    paths = bg.BackgroundSourcePaths(*[resolve(r) for r in old['static_sources'][6:]])
    return dict(audit=audit,expected=expected,inventory=module.inventory,assets=assets,
        compile=compile_clean_engine,REGULATORS=REGULATORS,CAPACITORS=CAPACITORS,
        NativeAllocation=NativeAllocation,native_state=_native_state,voltage_vector=_voltage_vector,
        branch_measurement=branch_measurement,legacy_branch_measurement=_branch_measurement,
        oriented_branches=_oriented_branches,bg=bg,paths=paths)


def regulator_parameters(inventory):
    return dict(engine_version=inventory['engine_version'],
        regulators=[{k:r[k] for k in ('name','transformer','winding','min_tap','max_tap','num_taps','tap_step')}
            | dict(properties={k:v for k,v in r['resolved_properties'].items() if k!='TapNum'})
            for r in inventory['regulators']],
        control_mode=inventory['control_mode'],solution_mode=inventory['solution_mode'],
        max_control_iterations=inventory['max_control_iterations'])


def assert_inventory(inventory, *, initial=False):
    expected = source()['expected']
    for key in ('regulator_transformers','RegControl_count','capacitor_banks','CapControl_count'):
        if inventory[key] != expected[key]:
            raise ValueError('SOURCE_CONTROL_INVENTORY_DRIFT:'+key)
    if not all(r['enabled'] for r in inventory['regulators']):
        raise ValueError('SOURCE_REGCONTROL_DISABLED')
    if regulator_parameters(inventory) != regulator_parameters(expected):
        raise ValueError('SOURCE_REGCONTROL_PARAMETER_OR_MODE_DRIFT')
    if inventory['capacitors'] != expected['capacitors']:
        raise ValueError('SOURCE_FIXED_CAPACITOR_STATE_OR_EQUIPMENT_DRIFT_NO_REPAIR')
    if initial and [r['initial_tap'] for r in inventory['regulators']] != [r['initial_tap'] for r in expected['regulators']]:
        raise ValueError('FRESH_DAY_SOURCE_INITIAL_TAP_DRIFT')
    return True


def common_contract(arm, *, regulator_sha=None, capacitor_sha=None):
    if arm not in ('B0','B1','B2','B3'):
        raise ValueError('COMPARISON_ARM_REQUIRED')
    expected=source()['expected']
    rs=digest(regulator_parameters(expected)); cs=digest(expected['capacitors'])
    if (regulator_sha is not None and regulator_sha!=rs) or (capacitor_sha is not None and capacitor_sha!=cs):
        raise ValueError('ARM_SPECIFIC_CONTROL_AUTHORITY_FORBIDDEN')
    return dict(REGCONTROL_AUTHORITY_SHA=rs,CAPACITOR_FIXED_STATE_AUTHORITY_SHA=cs,
        Planning_RegControl='AUTONOMOUS_SOURCE_BACKED',Actual_RegControl='AUTONOMOUS_SOURCE_BACKED',
        Planning_Capacitor='FIXED_ON_SOURCE_BACKED',Actual_Capacitor='FIXED_ON_SOURCE_BACKED',
        Planning_CapControl='ABSENT',Actual_CapControl='ABSENT',CapControl_count=0,
        control_mode='snapshot/static',maxcontroliter=100,
        state_semantics='fresh source initial each day; sequential within day',
        Planning_tap_cap_replay=False,tap_cap_optimization_variables=0,
        parameter_tuning=0,CapControl_creation=False)


def compile_verified():
    m=source(); previous=Path.cwd()
    try:
        odd,adapter=m['compile'](m['assets'])
        inventory=m['inventory'](odd)
        assert_inventory(inventory,initial=True)
        return odd,adapter,inventory
    finally:
        os.chdir(previous)

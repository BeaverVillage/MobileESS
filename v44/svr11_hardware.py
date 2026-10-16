"""V44-owned Epoch12 equipment revision and independent native contexts."""
from contextlib import contextmanager,ExitStack
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import os
import hashlib

from .common import ROOT,DOC,read,record,atomic,verify,digest,now
from .svr11_vendor import REVISION,FROZEN,install as load_vendor

HARDWARE=REVISION/'hardware'
IDS=('STA01','STA06','STA08','BUS83','BUS79','BUS108','BUS50','BUS82','BUS48','BUS86','BUS62')


def physics_sources():
    pin=read(REVISION/'EPOCH12_SOURCE_PIN.json')
    rows={r['relative']:record(FROZEN/r['relative']) for r in pin['sources']}
    for r in pin['sources']:
        if rows[r['relative']]['sha256']!=r['sha256']:raise PermissionError('SVR11_VENDOR_BYTES_DRIFT')
    for name in ('svr11_vendor.py','svr11_hardware.py','svr11_forecast.py'):
        p=ROOT/'v44'/name
        if p.exists():rows['v44/'+name]=record(p)
    for name in ('v43_arms/reference.py','v42_temporal/native.py'):
        rows[name]=record(ROOT/name)
    return rows


def source_identity():return digest({k:r['sha256'] for k,r in physics_sources().items()})


def _relocate_receipts(value,copied):
    if isinstance(value,dict):
        if all(k in value for k in ('path','sha256','bytes')):
            from .inputs import resolve_receipt
            try:row=resolve_receipt(value)
            except RuntimeError:
                text=Path(value['path']).as_posix();marker='docs/'
                if marker not in text:raise
                relative=text[text.index(marker):]
                candidates=[ROOT/relative,ROOT.parent/'v43_pr189_fast_planning_20261016'/relative,
                    Path('D:/ChatGPT/Mobile ESS 2/work/source18r-physical-global-lb-pilot')/relative]
                row=next((record(p) for p in candidates if p.is_file() and record(p)['sha256']==value['sha256']),None)
                if row is None:raise
            target=HARDWARE/'static'/(row['sha256']+'_'+Path(row['path']).name)
            target.parent.mkdir(parents=True,exist_ok=True)
            raw=Path(row['path']).read_bytes()
            if target.exists() and target.read_bytes()!=raw:raise ValueError('SVR11_IMMUTABLE_STATIC_DRIFT')
            if not target.exists():target.write_bytes(raw)
            copied[str(value['path'])]=dict(original=value,V44=record(target))
            return dict(value,**record(target))
        return {k:_relocate_receipts(v,copied) for k,v in value.items()}
    if isinstance(value,list):return [_relocate_receipts(v,copied) for v in value]
    return value


def equipment():
    load_vendor()
    from v42_voltage_control.integration import validate_scenario,scenario_identity
    original=read(REVISION/'epoch12/SCENARIO.json');copied={}
    translated=_relocate_receipts(original,copied)
    translated['scenario_SHA']=__import__('v42_b3_joint.contracts',fromlist=['digest']).digest(scenario_identity(translated))
    validate_scenario(translated)
    if tuple(u['id'] for u in translated['svr']['units'])!=IDS:raise ValueError('EXACT_EPOCH12_ELEVEN_BANKS_REQUIRED')
    b=next(u for u in translated['svr']['units'] if u['id']=='BUS82')
    if any(b[k]!=v for k,v in dict(cut_element='Line.l82',cut_terminal=1,original_bus_spec='81.1.2.3',
            upstream_new_bus='svr_bus82_line_input',sensed_bus='82').items()):raise ValueError('BUS82_EPOCH12_FINAL_LAYOUT_REQUIRED')
    HARDWARE.mkdir(parents=True,exist_ok=True);path=HARDWARE/'SCENARIO.json'
    if path.exists() and read(path)!=translated:raise ValueError('V44_SVR11_SCENARIO_IMMUTABLE')
    if not path.exists():atomic(path,translated)
    atomic(HARDWARE/'RECEIPT_RELOCATIONS.json',list(copied.values()))
    return translated


def compile_context(namespace,day,*,clock_class=None):
    load_vendor()
    from v42_regcontrol import authority
    from v42_voltage_control.timecontrol import CommonClock
    from v42_voltage_control.svr import install
    from v42_voltage_control.integration import assert_control_inventory,_equipment
    scenario=read(HARDWARE/'SCENARIO.json');engine,adapter,original=authority.compile_verified()
    before=_equipment(engine)
    clock=(clock_class or CommonClock)(namespace,day);clock.bind(engine)
    bank=install(engine,scenario['svr']);installed=authority.source()['inventory'](engine)
    assert_control_inventory(installed,scenario,initial=True)
    if installed['RegControl_count']!=40:raise ValueError('V44_EXACT_40_REGCONTROLS_REQUIRED')
    return engine,adapter,original,installed,clock,bank,before


def prepare():
    equipment()
    from v42_regcontrol import authority
    from v42_thermal.authority import compiled
    from v42_voltage_control.integration import _equipment
    from v42_voltage_control.timecontrol import queue,seconds
    from v42_svr11.context_lifecycle import retire_completed_probe,flush_completed_probes
    original=read(REVISION/'epoch12/HARDWARE.json');states=[];phys=[];thermal=None
    for namespace in ('DAYAHEAD','ACTUAL'):
        e,ad,initial,installed,clock,bank,before=compile_context(namespace,'2025-05-01')
        try:
            branches,topology=authority.source()['oriented_branches'](e);rows,lines=compiled(e,branches)
            assert len(rows)==153 and len({r['transformer'] for r in rows})==77
            identity=dict(schema='V42_TRANSFORMER_NORMALAMPS_CURRENT_V1',rows=rows,lines=lines,
                scenario_SHA=read(HARDWARE/'SCENARIO.json')['scenario_SHA'])
            t=dict(PASS=True,rows=rows,lines=lines,Planning=rows,Actual=rows,controls=installed,topology=topology,
                identity=identity,transformer_current_authority_sha256=__import__('v42_b3_joint.contracts',fromlist=['digest']).digest(identity))
            if thermal is None:thermal=t
            elif thermal!=t:raise ValueError('SVR11_PLANNING_ACTUAL_EQUIPMENT_AXIS_DRIFT')
            state=dict(namespace=namespace,source_initial_controls=initial,initial_controls=installed,
                initial_queue=queue(e),initial_seconds=seconds(e),svr_initial=bank.initial_state,
                installation=bank.installation_receipt,source_SHA=source_identity(),engine_object_id=id(e))
            atomic(HARDWARE/(namespace+'_INITIAL_STATE.json'),state);states.append(record(HARDWARE/(namespace+'_INITIAL_STATE.json')))
            phys.append(dict(original=before,installed=_equipment(e)))
        finally:retire_completed_probe(e)
        del e;flush_completed_probes()
    atomic(HARDWARE/'THERMAL.json',thermal)
    h=dict(schema='V44_SVR11_EQUIPMENT_REVISION_01',PASS=True,SVR_count=11,original_RegControl_count=7,
        additional_RegControl_count=33,RegControl_count=40,capacitors_fixed_ON=4,CapControl_count=0,DSTATCOM_count=0,
        tap_optimization_variables=0,epoch12_hardware=record(REVISION/'epoch12/HARDWARE.json'),
        epoch12_equipment_SHA=original['equipment_SHA'],equipment_SHA=digest(phys),
        scenario_SHA=read(HARDWARE/'SCENARIO.json')['scenario_SHA'],scenario=record(HARDWARE/'SCENARIO.json'),
        independent_initial_states=states,thermal=record(HARDWARE/'THERMAL.json'),
        source_SHA=source_identity(),sources=physics_sources(),physical_parameter_changes=0,
        source_receipt_paths_relocated=True,svr_voltage_effect='NOT_TESTED',UTC=now())
    atomic(HARDWARE/'HARDWARE.json',h);return h


@contextmanager
def scope():
    """V44 execution identity around exact Epoch12 equations and permission checks."""
    load_vendor()
    import v42_svr11.authority as epoch
    import v42_thermal.authority as thermal
    import v42_common_campaign.authority as common
    import v42_voltage_control.authority as physical
    import v42_svr11.stages as stages
    h=read(HARDWARE/'HARDWARE.json');verify([h['scenario'],h['thermal']]);verify(list(h['sources'].values()))
    manifest=dict(execution_SHA=h['source_SHA'],hardware=record(HARDWARE/'HARDWARE.json'),scenario=h['scenario'],
        thermal=h['thermal'],original_transformer_current_authority='COMPILED_NORMALAMPS_ONLY')
    sources={k:r['sha256'] for k,r in h['sources'].items()}
    token=epoch._active.set(manifest)
    # The physical infrastructure changed explicitly. Its compiled thermal
    # authority is scoped, while every original current/kVA formula is retained.
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(thermal,'current_authority',lambda:read(h['thermal']['path'])))
            for module in (common,physical):stack.enter_context(patch.object(module,'source_files',lambda:sources))
            import v42_integrated.contract as contract
            mod=ModuleType('v44_epoch12_grid');mod.__package__='v42_integrated'
            path=FROZEN/'v42_integrated/contract.py';exec(compile(path.read_bytes(),str(path),'exec'),mod.__dict__)
            for name in ('physical_authority','all_transformer_rows','grid_audit'):
                stack.enter_context(patch.object(contract,name,getattr(mod,name)))
            yield manifest
    finally:epoch._active.reset(token)

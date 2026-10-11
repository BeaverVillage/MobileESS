"""Source-bound permissions for independent physical control experiments.

These permissions do not admit any optimizer or change the original planning
authorization. A complete, byte-verified source archive precedes every replay.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from pathlib import Path
import shutil

from v42_pr134_b1.common import atomic, read, record
from v42_b3_joint.contracts import digest, require_sha
from v42_common_campaign.authority import ROOT, source_files

_permit = ContextVar('v42_voltage_control_physical_permit', default=None)


def checked(receipt):
    # Historical C: paths may be junctions to the preserved D: source.  The
    # literal path resolves to that same file; SHA and length remain exact.
    path=Path(receipt['path']).resolve()
    expected=dict(receipt,path=str(path))
    if record(path) != expected:
        raise PermissionError('VOLTAGE_CONTROL_AUTHORITY_RECEIPT_DRIFT')
    return path


def archive_source(output, *, source_SHA=None, external_receipts=()):
    """Archive all execution Python files and tests without altering originals.

    Source SHA is the existing common authority's entire v42 source map. Tests
    are also copied but have their own receipt, so execution identity is stable.
    Every copied byte and all originals are checked after copying. An existing
    archive is reverified, never overwritten.
    """
    output = Path(output).resolve()
    sources = source_files()
    expected = digest(sources)
    if source_SHA is not None and source_SHA != expected:
        raise PermissionError('VOLTAGE_CONTROL_ARCHIVE_SOURCE_SHA_DRIFT')
    receipt_path = output / 'SOURCE_SNAPSHOT_RECEIPT.json'
    if output.exists():
        if not receipt_path.is_file():
            raise PermissionError('VOLTAGE_CONTROL_PARTIAL_ARCHIVE_NEVER_REUSED')
        value = read(receipt_path)
        if value.get('source_SHA') != expected or value.get('execution_sources') != sources:
            raise PermissionError('VOLTAGE_CONTROL_EXISTING_ARCHIVE_SOURCE_DRIFT')
        for row in value['files'] + value['external_files']:
            checked(row['original']); checked(row['archived'])
        return record(receipt_path)
    output.mkdir(parents=True, exist_ok=False)
    names = sorted(set(sources) | {p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('*.py')})
    rows = []
    for name in names:
        original = record(ROOT/name)
        destination = output/'code'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original['path'], destination)
        archived = record(destination)
        if archived['sha256'] != original['sha256'] or archived['bytes'] != original['bytes']:
            raise PermissionError('VOLTAGE_CONTROL_ARCHIVE_BYTE_DRIFT:'+name)
        rows.append(dict(relative_path=name, original=original, archived=archived))
    external = []
    for i, receipt in enumerate(external_receipts):
        original = record(checked(receipt))
        destination = output/'original_sources'/str(i)/Path(original['path']).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original['path'], destination)
        archived = record(destination)
        if archived['sha256'] != original['sha256']:
            raise PermissionError('VOLTAGE_CONTROL_EXTERNAL_ARCHIVE_BYTE_DRIFT')
        external.append(dict(original=original, archived=archived))
    if source_files() != sources or any(record(row['original']['path']) != row['original'] for row in rows+external):
        raise PermissionError('VOLTAGE_CONTROL_SOURCE_MUTATED_DURING_ARCHIVE')
    atomic(receipt_path, dict(schema='V42_VOLTAGE_CONTROL_FULL_SOURCE_SNAPSHOT_V1', PASS=True,
        source_SHA=expected, execution_sources=sources, files=rows, external_files=external,
        byte_verified=True, original_files_modified=0, Native_optimizer_calls=0))
    return record(receipt_path)


@contextmanager
def physical_permit(arm, day, source_SHA, scenario, *, namespace='ACTUAL',
                    development=False, design_receipt=None):
    from .integration import validate_scenario
    if _permit.get() is not None or arm not in ('B0','B1','B2','B3') or namespace not in ('ACTUAL','DAYAHEAD'):
        raise PermissionError('VOLTAGE_CONTROL_EXPLICIT_SINGLE_PHYSICAL_PERMIT_REQUIRED')
    if date.fromisoformat(day).isoformat() != day:
        raise PermissionError('VOLTAGE_CONTROL_ISO_DAY_REQUIRED')
    require_sha(source_SHA)
    value, _, _ = validate_scenario(scenario)
    sources = source_files()
    if digest(sources) != source_SHA:
        raise PermissionError('VOLTAGE_CONTROL_EXECUTION_SOURCE_SHA_DRIFT')
    if development:
        if not (day.startswith('2025-04-') or day in ('2025-05-01','2025-05-28')) or design_receipt is not None:
            raise PermissionError('VOLTAGE_CONTROL_DISCLOSED_DEVELOPMENT_DATES_ONLY')
    else:
        design = verify_design(design_receipt, source_SHA)
        if design['scenario_SHA'] != value['scenario_SHA']:
            raise PermissionError('VOLTAGE_CONTROL_EVALUATION_FROZEN_INFRASTRUCTURE_DRIFT')
    identity = dict(arm=arm, day=day, source_SHA=source_SHA, scenario_SHA=value['scenario_SHA'],
                    namespace=namespace, development=development)
    token = _permit.set(identity)
    try:
        yield identity
    finally:
        _permit.reset(token)
        if source_files() != sources:
            raise PermissionError('VOLTAGE_CONTROL_EXECUTION_SOURCE_MUTATED')


def authorize_physical(arm, day, source_SHA, scenario_SHA, namespace):
    permit = _permit.get()
    if permit is None or any(permit[k] != v for k,v in
        (('arm',arm),('day',day),('source_SHA',source_SHA),('scenario_SHA',scenario_SHA),('namespace',namespace))):
        raise PermissionError('VOLTAGE_CONTROL_SOURCE_BOUND_NAMESPACE_PERMIT_REQUIRED')
    return dict(permit)


def authorize_actual(arm, day, source_SHA, scenario_SHA):
    return authorize_physical(arm,day,source_SHA,scenario_SHA,'ACTUAL')


def actual_permit(arm, day, source_SHA, scenario, **kwargs):
    return physical_permit(arm,day,source_SHA,scenario,namespace='ACTUAL',**kwargs)


def verify_frozen_infrastructure(receipt, source_SHA):
    """Hardware freeze authorizes replay, never new Planning/model qualification."""
    from .integration import validate_scenario, original_parameters
    value=read(checked(receipt))
    if (value.get('schema') not in ('V42_SVR4_HARDWARE_FREEZE_RECEIPT_V1','V42_SVR_HARDWARE_FREEZE_RECEIPT_V2')
        or value.get('status')!='FROZEN_HARDWARE_ONLY_NOT_E2E_QUALIFIED' or value.get('PASS') is not True
        or value.get('execution_SourceSHA_before')!=source_SHA or value.get('execution_SourceSHA_after')!=source_SHA
        or value.get('SourceCode_before_after_equal') is not True
        or value.get('original_RegControl_count')!=7 or value.get('CapControl_count')!=0
        or value.get('Cap4_fixed_ON_total_nameplate_kvar')!=750
        or value.get('existing_original_band_pu')!=[.95,1.05]
        or value.get('new_model_regenerated') is not False
        or value.get('optimized_Planning_Actual_E2E_qualified') is not False
        or value.get('all31May_qualified') is not False
        or any(value.get(k)!=0 for k in ('hardware_and_control_law_changes_from_selected_development_units',
            'original_equipment_rating_changes','original_RegControl_settings_changes','original_RegControl_tap_setters',
            'original_Capacitor_state_setters','Native_optimizer_calls','runtime_physical_solve_count','replay_logical_slots'))):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_HARDWARE_REPLAY_ONLY_IDENTITY_REQUIRED')
    scenario=read(checked(value['scenario']));validate_scenario(scenario)
    if (scenario['case']!='B' or scenario['time_mode']!='TIME' or scenario['capcontrol'] is not None
        or scenario['svr'] is None or scenario['svr']['status']!='FROZEN'
        or value['scenario_SHA']!=scenario['scenario_SHA']
        or read(checked(value['controller_contract']))!=scenario['svr']
        or digest(scenario['svr']['units'])!=value['selected_units_canonical_SHA_before']
        or value['selected_units_canonical_SHA_after']!=value['selected_units_canonical_SHA_before']):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_UNIT_LAYOUT_DRIFT')
    units=scenario['svr']['units']
    ids=[u['id'] for u in units]
    if len(ids)!=len(set(ids)):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_DUPLICATE_BANK_ID')
    original_ids={'STA01','STA06','STA08','BUS83'}
    if value['schema']=='V42_SVR4_HARDWARE_FREEZE_RECEIPT_V1':
        if set(ids)!=original_ids:
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_FOUR_UNIT_LAYOUT_DRIFT')
    else:
        _verify_variant_layout(value,scenario)
    phase_count=sum(len(u['phases']) for u in units)
    new_names={'svr_'+u['id'].lower()+'_p'+str(p) for u in units for p in u['phases']}
    if (value.get('additional_RegControl_count')!=phase_count
        or value.get('additional_single_phase_transformer_count')!=phase_count):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_DECLARED_PHASE_EQUIPMENT_COUNT_DRIFT')
    expected=read(ROOT/'docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json')['actual_static_compile']
    states=value['independent_namespaces']
    if len(states)!=2 or {r['namespace'] for r in states}!={'DAYAHEAD','ACTUAL'}:
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_INDEPENDENT_SOURCE_INITIAL_STATES_REQUIRED')
    identities=[]
    for row in states:
        doc=read(checked(row['initial_state_receipt']));state=doc['initial_state'];ident=digest(state);identities.append(ident)
        clock=state['native_clock'];inventory=state['installed_inventory']
        names={r['name'] for r in expected['regulators']}
        original=[r for r in inventory['regulators'] if r['name'] in names]
        if (ident!=row['initial_state_SHA'] or ident!=doc['initial_state_SHA'] or ident!=value['source_initial_state_SHA']
            or state['source_SHA']!=source_SHA or state['scenario_SHA']!=scenario['scenario_SHA']
            or state['original_initial_inventory']!=expected
            or original_parameters(dict(regulators=original))!=original_parameters(expected)
            or [r['initial_tap'] for r in original]!=[1.]*7
            or inventory['RegControl_count']!=7+phase_count or inventory['CapControl_count']!=0
            or len(inventory['regulators'])!=7+phase_count
            or {r['name'] for r in inventory['regulators']}!=names|new_names
            or not all(r['enabled'] for r in inventory['regulators'])
            or not all(r['initial_tap']==1. for r in inventory['regulators'])
            or inventory['capacitors']!=expected['capacitors']
            or clock!={'Hour':0,'Seconds':0.,'control_mode':2,'maxcontroliter':100,'maxiter':15,'queue':[],'queue_size':0,'solution_mode':0}
            or set(state['new_SVR_initial_winding_taps'])!=new_names
            or any(taps!=[1.,1.] for taps in state['new_SVR_initial_winding_taps'].values())
            or state['retired_inventory']['retired_objects_count']!=0):
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_LITERAL_INITIAL_STATE_DRIFT')
    if len(set(identities))!=1:
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_SOURCE_INITIAL_STATE_INDEPENDENCE_DRIFT')
    for row in value['external_original_source_receipts']: checked(row)
    archive=read(checked(value['source_archive_receipt']))
    if archive['source_SHA']!=source_SHA or archive['execution_sources']!=source_files():
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_FULL_SOURCE_ARCHIVE_DRIFT')
    return value,scenario


def _verify_variant_layout(value,scenario):
    """A new execution epoch keeps the exact four predecessor physical units."""
    variant=value.get('infrastructure_variant')
    if variant not in ('SVR4','SVR7'):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_EXPLICIT_SVR4_OR_SVR7_REQUIRED')
    predecessor=read(checked(value['original_SVR4_predecessor_receipt']))
    if (predecessor.get('schema')!='V42_SVR4_HARDWARE_FREEZE_RECEIPT_V1'
        or predecessor.get('status')!='FROZEN_HARDWARE_ONLY_NOT_E2E_QUALIFIED'
        or predecessor.get('PASS') is not True):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_ORIGINAL_SVR4_HARDWARE_RECEIPT_REQUIRED')
    old=read(checked(predecessor['scenario']))
    from .integration import validate_scenario
    validate_scenario(old)
    if (old['case']!='B' or old['time_mode']!='TIME' or old['capcontrol'] is not None
        or old['svr']['status']!='FROZEN' or {u['id'] for u in old['svr']['units']}!={'STA01','STA06','STA08','BUS83'}
        or digest(old['svr']['units'])!=predecessor['selected_units_canonical_SHA_before']
        or predecessor['selected_units_canonical_SHA_after']!=predecessor['selected_units_canonical_SHA_before']):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_PREDECESSOR_FOUR_UNIT_LAYOUT_DRIFT')
    selected={u['id']:u for u in scenario['svr']['units']}
    retained=[selected.get(u['id']) for u in old['svr']['units']]
    if (retained!=old['svr']['units']
        or value.get('preserved_SVR4_units_canonical_SHA')!=digest(old['svr']['units'])
        or scenario['connection_manifest']!=old['connection_manifest']):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_ORIGINAL_FOUR_PHYSICAL_UNIT_DRIFT')
    additional=[u for u in scenario['svr']['units'] if u['id'] not in {r['id'] for r in old['svr']['units']}]
    if variant=='SVR4':
        if additional or value.get('additional_unit_ids')!=[] or len(selected)!=4:
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_SVR4_VARIANT_HAS_ADDITIONAL_UNITS')
    else:
        new_ids={u['id'] for u in additional}
        if (len(selected)!=7 or len(additional)!=3 or new_ids not in
            ({'BUS79','BUS108','BUS48'},{'BUS79','BUS108','BUS50'})
            or value.get('additional_unit_ids')!=[u['id'] for u in additional]):
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_EXACT_THREE_NEW_BRANCH_SITES_REQUIRED')
        cuts={'BUS79':('line.l79','79'),'BUS108':('line.l105','108'),
              'BUS48':('line.l47','48'),'BUS50':('line.l49','50')}
        for unit in additional:
            element,bus=cuts[unit['id']]
            if (unit['cut_element'].lower()!=element or unit['cut_terminal']!=2
                or unit['downstream_bus'].lower()!=bus or unit['original_bus_spec'].lower().split('.')[0]!=bus):
                raise PermissionError('VOLTAGE_CONTROL_FROZEN_NEW_SITE_ORIGINAL_SERIAL_BRANCH_DRIFT')
    # Compare actual source files, including junction-normalized historical
    # aliases; no changed IEEE123 source or injection implementation is admitted.
    original=[record(checked(r)) for r in predecessor['external_original_source_receipts']]
    current=[record(checked(r)) for r in value['external_original_source_receipts']]
    if sorted(original,key=lambda r:r['path'])!=sorted(current,key=lambda r:r['path']):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_PREDECESSOR_ORIGINAL_PHYSICAL_SOURCE_DRIFT')


def preserved_plan_binding(arm,day,receipts,original_physical_sources,*,b3_terminal_proof=None):
    value=dict(schema='V42_VOLTAGE_CONTROL_PRESERVED_PLAN_BINDING_V1',arm=arm,day=day,
        receipts=receipts,original_physical_sources=original_physical_sources,b3_terminal_proof=b3_terminal_proof,
        new_Planning_optimization=False,Actual_reoptimization=False)
    return dict(value,binding_SHA=digest(value))


def verify_preserved_plan(binding,arm,day):
    value={k:v for k,v in binding.items() if k!='binding_SHA'}
    if (binding.get('schema')!='V42_VOLTAGE_CONTROL_PRESERVED_PLAN_BINDING_V1' or binding.get('arm')!=arm
        or binding.get('day')!=day or digest(value)!=binding.get('binding_SHA')
        or binding.get('new_Planning_optimization') is not False or binding.get('Actual_reoptimization') is not False):
        raise PermissionError('VOLTAGE_CONTROL_EXACT_EXISTING_FROZEN_PLAN_BINDING_REQUIRED')
    receipts=binding['receipts']
    if arm=='B0':
        names={'V_ACTUAL_AC.npz','ACTUAL_PHYSICAL.npz','RAW_CONTROL_LOG.json','RAW_PHYSICAL_INPUT_LOG.json','FRESH_ACTUAL_AC_RECEIPT.json','INPUT_FREEZE.json','Actual_exogenous'}
        if set(receipts)!=names:raise PermissionError('VOLTAGE_CONTROL_B0_EXACT_SIX_FROZEN_DAY_FILES_REQUIRED')
        folder=checked(receipts['INPUT_FREEZE.json']).parent
        from .b0_replay import load_historical_original
        payload=load_historical_original(day,folder)
        actual={Path(r['path']).name:r for r in payload['sources'][:6]};actual['Actual_exogenous']=payload['sources'][6]
        if actual!=receipts:raise PermissionError('VOLTAGE_CONTROL_B0_PRESERVED_SOURCE_BINDING_DRIFT')
    else:
        names={'REQUEST','PLANNING_FREEZE','ACTUAL_FIXED','ACTUAL_MESS','ORIGINAL_RAW_AC','PHYSICAL_INPUT_LOG','ORIGINAL_CONTROL_LOG','NATIVE_INPUT','OPERATIONS_INPUT','Actual_exogenous'}
        if set(receipts)!=names:raise PermissionError('VOLTAGE_CONTROL_COMPLETE_OPERATIONS_FROZEN_PLAN_RECEIPTS_REQUIRED')
        request=read(checked(receipts['REQUEST']));freeze=read(checked(receipts['PLANNING_FREEZE']))
        identity=freeze.get('identity',{})
        if request.get('arm')!=arm or request.get('day')!=day or identity.get('arm')!=arm or identity.get('day')!=day:
            raise PermissionError('VOLTAGE_CONTROL_ORIGINAL_REQUEST_FREEZE_ARM_DAY_DRIFT')
        inputs=read(checked(receipts['PHYSICAL_INPUT_LOG']))
        # Original physical logs contain only slots and exogenous receipt.
        # Their day is proved by the frozen request and the immutable 96-slot
        # exogenous timestamp axis, not a newly fabricated envelope field.
        logged_exogenous=inputs.get('Actual_exogenous')
        bound_exogenous=receipts['Actual_exogenous']
        if (('day' in inputs and inputs['day']!=day) or not isinstance(logged_exogenous,dict)
            or set(logged_exogenous)!=set(bound_exogenous)
            or checked(logged_exogenous)!=checked(bound_exogenous)):
            raise PermissionError('VOLTAGE_CONTROL_ORIGINAL_PHYSICAL_EXOGENOUS_BINDING_DRIFT')
        import numpy as np
        import pandas as pd
        rows=inputs.get('slots',[])
        if len(rows)!=96 or [r.get('slot') for r in rows]!=list(range(96)):
            raise PermissionError('VOLTAGE_CONTROL_ORIGINAL_LITERAL_96_PHYSICAL_INPUTS_REQUIRED')
        with np.load(checked(receipts['ACTUAL_FIXED']),allow_pickle=False) as fixed, \
                np.load(checked(receipts['ACTUAL_MESS']),allow_pickle=False) as mess:
            pairs=(('PCC_P_kw',fixed['PCC_P_kw'],(96,12)),('PCC_Q_kvar',fixed['PCC_Q_kvar'],(96,12)),
                   ('MESS_P_kw',mess['P_kw'],(96,4)),('MESS_Q_kvar',mess['Q_kvar'],(96,4)),
                   ('MESS_locations',mess['locations'],(96,4)))
            for key,array,shape in pairs:
                if array.shape!=shape or not np.array_equal(array,np.asarray([r[key] for r in rows])):
                    raise PermissionError('VOLTAGE_CONTROL_ORIGINAL_LITERAL_FROZEN_PQ_LOCATION_DRIFT:'+key)
        exogenous=pd.read_parquet(checked(receipts['Actual_exogenous']))
        target=pd.Timestamp(day,tz='Etc/GMT-10')
        stamps=[pd.Timestamp(t) for t in exogenous.ts_fixed_aest_end]
        if len(stamps)!=96 or any(t.tzinfo is None or t!=target+pd.Timedelta(minutes=15*(i+1)) for i,t in enumerate(stamps)):
            raise PermissionError('VOLTAGE_CONTROL_ORIGINAL_ACTUAL_EXOGENOUS_DAY_AXIS_DRIFT')
    for row in receipts.values():checked(row)
    if not binding['original_physical_sources']:
        raise PermissionError('VOLTAGE_CONTROL_ORIGINAL_PHYSICAL_SOURCE_RECEIPTS_REQUIRED')
    for row in binding['original_physical_sources']:checked(row)
    if arm=='B3':
        proof=read(checked(binding['b3_terminal_proof']))
        if (proof.get('schema')!='V42_B3_EXISTING_TERMINAL_CHAIN_PROOF_V1' or proof.get('arm')!=arm or proof.get('day')!=day
            or proof.get('PASS') is not True or proof.get('valid_A1_M1_A2_M2') is not True
            or set(proof.get('stage_receipts',{}))!={'A1','M1','A2','M2'}):
            raise PermissionError('VOLTAGE_CONTROL_B3_VALID_TERMINAL_A1_M1_A2_M2_REQUIRED')
        for row in proof['stage_receipts'].values():checked(row)
    return binding


@contextmanager
def frozen_plan_permit(arm,day,source_SHA,scenario,*,infrastructure_receipt,preserved_plan,namespace='ACTUAL'):
    """All-May existing-plan physical replay; no new Planning/optimizer rights."""
    from .integration import validate_scenario
    if (_permit.get() is not None or arm not in ('B0','B1','B2','B3') or namespace!='ACTUAL'
        or day not in tuple(f'2025-05-{i:02d}' for i in range(1,32))):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_REPLAY_ACTUAL_ONLY_MAY31_REQUIRED')
    sources=source_files()
    if digest(sources)!=source_SHA:raise PermissionError('VOLTAGE_CONTROL_FROZEN_REPLAY_EXECUTION_SOURCE_DRIFT')
    infrastructure,frozen=verify_frozen_infrastructure(infrastructure_receipt,source_SHA)
    value,_,_=validate_scenario(scenario)
    if value['case'] in ('REF','REFa'):
        if value['connection_manifest']!=frozen['connection_manifest']:
            raise PermissionError('VOLTAGE_CONTROL_FROZEN_REF_CONNECTION_SOURCE_DRIFT')
    elif value!=frozen:
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_SAME_FOUR_UNIT_SCENARIO_REQUIRED')
    verify_preserved_plan(preserved_plan,arm,day)
    identity=dict(arm=arm,day=day,source_SHA=source_SHA,scenario_SHA=value['scenario_SHA'],namespace='ACTUAL',
        scope='EXISTING_FROZEN_PLAN_NATIVE_ZERO_REPLAY',infrastructure_receipt=infrastructure_receipt,
        preserved_plan_binding_SHA=preserved_plan['binding_SHA'],new_Planning_E2E_qualified=False)
    from v42_may_campaign_native90.preflight import native_zero
    token=_permit.set(identity)
    try:
        with native_zero() as denied:
            yield identity
            if denied:raise PermissionError('VOLTAGE_CONTROL_FROZEN_REPLAY_NATIVE_OPTIMIZER_FORBIDDEN')
    finally:
        _permit.reset(token)
        if source_files()!=sources:raise PermissionError('VOLTAGE_CONTROL_FROZEN_REPLAY_SOURCE_MUTATED')
        checked(infrastructure_receipt)
        verify_preserved_plan(preserved_plan,arm,day)


def _evidence_identity(kind, item, source_SHA, scenario_SHA):
    if (item.get('PASS') is not True or item.get('evidence_kind') != kind
        or item.get('source_SHA') != source_SHA or item.get('scenario_SHA') != scenario_SHA):
        raise PermissionError('VOLTAGE_CONTROL_SOURCE_SCENARIO_MATCHED_DESIGN_EVIDENCE_REQUIRED:'+kind)
    if kind == 'physical_model_regeneration' and (item.get('model_regenerated') is not True
        or item.get('topology_measurement_proxy_only') is not False
        or item.get('original_model_reused') is not False):
        raise PermissionError('VOLTAGE_CONTROL_ACTUAL_MEASUREMENT_PROXY_IS_NOT_MODEL_REGENERATION')


def _gate_identity(label, gate, source_SHA, scenario_SHA):
    expected={'B2_May01_diagnostic':('B2',{'2025-05-01'}),
              'B1_May28_diagnostic':('B1',{'2025-05-28'}),
              'B0':('B0',{'2025-05-01'}),'B1':('B1',{'2025-05-28'}),
              'B2':('B2',{'2025-05-01'}),'B3':('B3',{'2025-05-01','2025-05-28'})}
    arm,days=expected[label]
    if (gate.get('PASS') is not True or gate.get('source_SHA')!=source_SHA
        or gate.get('scenario_SHA')!=scenario_SHA or gate.get('arm')!=arm or gate.get('day') not in days):
        raise PermissionError('VOLTAGE_CONTROL_EXACT_ARM_DAY_SOURCE_SCENARIO_GATE_REQUIRED:'+label)


def verify_design(receipt, source_SHA, *, qualified=False):
    from v42_svr11.authority import active, design
    if active() is not None:
        return design(receipt, source_SHA)
    if receipt is None:
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_DESIGN_RECEIPT_REQUIRED')
    design = read(checked(receipt))
    if (design.get('schema') != 'V42_VOLTAGE_CONTROL_FROZEN_DESIGN_V1'
        or design.get('source_SHA') != source_SHA or design.get('PASS') is not True
        or design.get('Planning_band_pu') != [.95,1.05] or design.get('Actual_band_pu') != [.95,1.05]
        or design.get('economic_analysis') is not False or design.get('MESS_PQ_repair') != 0
        or design.get('control_MILP_variables') != 0 or design.get('retired_objects_count') != 0
        or design.get('Planning_Actual_independent_Source_Initial_State') is not True):
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_DESIGN_CONTRACT_REQUIRED')
    from .integration import validate_scenario
    scenario = read(checked(design['scenario']))
    validate_scenario(scenario)
    for kind in ('capcontrol','svr'):
        if scenario[kind] is not None and scenario[kind].get('status')!='FROZEN':
            raise PermissionError('VOLTAGE_CONTROL_EVALUATION_COMPLETE_FROZEN_COMPONENT_REQUIRED:'+kind)
    if design.get('scenario_SHA') != scenario['scenario_SHA']:
        raise PermissionError('VOLTAGE_CONTROL_FROZEN_DESIGN_SCENARIO_SHA_DRIFT')
    stage=design.get('qualification_stage')
    if stage not in ('FROZEN_INFRASTRUCTURE_FOR_E2E','QUALIFIED_ALL_POLICY_CANARY'):
        raise PermissionError('VOLTAGE_CONTROL_EXPLICIT_QUALIFICATION_STAGE_REQUIRED')
    if qualified and stage != 'QUALIFIED_ALL_POLICY_CANARY':
        raise PermissionError('VOLTAGE_CONTROL_ALL_POLICY_CANARIES_PENDING')
    evidence=design.get('design_evidence',{})
    if set(evidence) != {'April_design','regression','physical_model_regeneration','Planning_Actual_isolation'}:
        raise PermissionError('VOLTAGE_CONTROL_PRE_CANARY_DESIGN_EVIDENCE_REQUIRED')
    for kind,row in evidence.items():
        item=read(checked(row))
        _evidence_identity(kind,item,source_SHA,scenario['scenario_SHA'])
    gates = design.get('physical_gates', {})
    required={'B0','B1','B2','B3'} if stage=='QUALIFIED_ALL_POLICY_CANARY' else {'B2_May01_diagnostic','B1_May28_diagnostic'}
    if set(gates) != required:
        raise PermissionError('VOLTAGE_CONTROL_STAGE_MATCHED_PHYSICAL_GATES_REQUIRED')
    if len({str(checked(r)) for r in gates.values()})!=len(gates):
        raise PermissionError('VOLTAGE_CONTROL_DISTINCT_ARM_PHYSICAL_GATE_RECEIPTS_REQUIRED')
    for arm, receipt in gates.items():
        gate = read(checked(receipt))
        _gate_identity(arm,gate,source_SHA,scenario['scenario_SHA'])
        verify_physical_gate(gate)
    return design


def verify_physical_gate(gate):
    """Recompute saved all-node and all-terminal measurements, not producer PASS."""
    from .replay import raw_metrics
    metrics=raw_metrics(checked(gate['raw_AC_receipt']))
    if metrics['converged_slots'] != 96 or any(metrics[k] for k in
        ('voltage_violation_cells','line_current_violation_cells',
         'original_service_and_grid_transformer_current_violation_cells',
         'original_service_and_grid_transformer_kva_violation_cells')):
        raise PermissionError('VOLTAGE_CONTROL_ORIGINAL_LITERAL_96_SLOT_PHYSICAL_GATE_FAILED')
    audit=read(checked(gate['physical_audit']))
    if (audit.get('logical_Fresh_slots')!=96 or audit.get('source_SHA')!=gate['source_SHA']
        or audit.get('scenario_SHA')!=gate['scenario_SHA']
        or audit.get('arm')!=gate.get('arm') or audit.get('day')!=gate.get('day') or audit.get('namespace')!='ACTUAL'
        or audit.get('Original_Source_SHA_before_after_equal') is not True
        or audit.get('Original_Fresh_and_96_slot_body_unchanged') is not True
        or audit.get('retired_objects_count') != 0 or audit.get('Actual_optimizer_calls')!=0
        or audit.get('Actual_plan_repair_calls')!=0 or audit.get('control_MILP_variables')!=0):
        raise PermissionError('VOLTAGE_CONTROL_PHYSICAL_AUDIT_IDENTITY_REQUIRED')
    from .integration import validate_scenario
    frozen,_,_=validate_scenario(audit['frozen_scenario'])
    if frozen['scenario_SHA']!=gate['scenario_SHA']:
        raise PermissionError('VOLTAGE_CONTROL_PHYSICAL_AUDIT_FROZEN_SCENARIO_DRIFT')
    rows=read(checked(audit['slots_receipt']))
    for receipt in audit['original_sources']:
        checked(receipt)
    if len(rows)!=96 or [r['slot'] for r in rows]!=list(range(96)):
        raise PermissionError('VOLTAGE_CONTROL_LITERAL_CHRONOLOGICAL_96_SLOTS_REQUIRED')
    from .integration import original_parameters
    expected=read(ROOT/'docs/v42_autonomous_grid_controls_april_b0/REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json')['actual_static_compile']
    original_parameters_expected=original_parameters(expected)
    if audit.get('source_initial_controls')!=expected:
        raise PermissionError('VOLTAGE_CONTROL_LITERAL_ORIGINAL_SOURCE_INITIAL_CONTROLS_REQUIRED')
    events=read(checked(audit['physical_solve_events_receipt']))
    if (len(events)!=audit['total_physical_SolveSnap_count'] or not all(e.get('completed') for e in events)
        or sum(e['kind']=='ORIGINAL_SLOT_INITIAL_SOLVE' for e in events)!=96):
        raise PermissionError('VOLTAGE_CONTROL_LITERAL_ALL_PHYSICAL_SOLVES_REQUIRED')
    for event in events:
        control=event.get('controls') or {}
        if (original_parameters(dict(regulators=control.get('original_regulators',[])))!=original_parameters_expected
            or control.get('all_seven_RegControls_enabled') is not True):
            raise PermissionError('VOLTAGE_CONTROL_LITERAL_ORIGINAL7_EVENT_SETTINGS_DRIFT')
    for row in rows:
        physical=row['physical'];controls=row['settled_original_controls']
        if row.get('arm')!=gate['arm'] or row.get('day')!=gate['day'] or row.get('namespace')!='ACTUAL':
            raise PermissionError('VOLTAGE_CONTROL_LITERAL_SLOT_ARM_DAY_NAMESPACE_DRIFT')
        if original_parameters(dict(regulators=controls['original_regulators']))!=original_parameters_expected:
            raise PermissionError('VOLTAGE_CONTROL_LITERAL_ORIGINAL7_SLOT_SETTINGS_DRIFT')
        original_nodes=[r['node_phase'] for r in physical['nodes'] if r.get('original') is True]
        if (len(original_nodes)!=386 or len(set(original_nodes))!=386
            or len(physical['nodes'])!=len({r['node_phase'] for r in physical['nodes']})
            or not physical['currents'] or not physical['transformers']):
            raise PermissionError('VOLTAGE_CONTROL_ALL_ORIGINAL_AND_ADDED_AXES_REQUIRED')
        if (not controls['solution_converged'] or not row['control_actions_done_as_of_current_time']
            or not controls['all_seven_RegControls_enabled'] or not row['original_input_setpoints_unchanged']
            or controls['configured_MaxControlIterations']!=100 or controls['configured_MaxIterations']!=15
            or any(not (.95<=r['voltage_pu']<=1.05) for r in physical['nodes'])
            or any(not (0<=r['loading_pu']<=1) for r in physical['currents']+physical['transformers'])
            or physical.get('all_original_and_added_axes_checked') is not True):
            raise PermissionError('VOLTAGE_CONTROL_LITERAL_ALL_AXES_CONTROL_GATE_FAILED')
        if row['capcontrol'] is not None and row['capcontrol'].get('PASS') is not True:
            raise PermissionError('VOLTAGE_CONTROL_ADDED_DEVICE_GATE_FAILED:capcontrol')
        if row['svr'] is not None and (row['svr'].get('hardware_PASS') is not True
                or row['svr'].get('added_nodes_voltage_PASS') is not True):
            raise PermissionError('VOLTAGE_CONTROL_ADDED_DEVICE_GATE_FAILED:svr')
    return audit

"""Explicit CapControl/SVR infrastructure around the original Fresh body.

The original optimizer, injection mapping, 96-slot backend and voltage limits
are unchanged. Source Initial State is compiled separately in each namespace.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone
from dataclasses import is_dataclass, replace
from pathlib import Path
from unittest.mock import patch
import csv
import dis
from functools import lru_cache
import hashlib
import inspect
import json
import math
import os
import sys

import numpy as np
from v42_b3_joint.contracts import canonical, digest, require, require_sha

SCHEMA = 'V42_VOLTAGE_CONTROL_SCENARIO_V1'
VERSION = 'V42_CAPCONTROL_SVR_INDEPENDENT_FRESH_V1'
_active = ContextVar('v42_voltage_control_scenario', default=None)


def record(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),sha256=sha,bytes=path.stat().st_size)


def scenario_identity(scenario):
    return {k:scenario[k] for k in ('schema','case','time_mode','capcontrol','svr','connection_manifest')}


def validate_scenario(scenario):
    value = json.loads(canonical(scenario))
    require(set(value) == set(('schema','case','time_mode','capcontrol','svr','connection_manifest','scenario_SHA')),
            'VOLTAGE_CONTROL_COMPLETE_EXPLICIT_SCENARIO_FIELDS_REQUIRED')
    require(value['schema'] == SCHEMA,'VOLTAGE_CONTROL_SCENARIO_SCHEMA_REQUIRED')
    require_sha(value['scenario_SHA'])
    require(digest(scenario_identity(value)) == value['scenario_SHA'],'VOLTAGE_CONTROL_SCENARIO_SHA_DRIFT')
    require(record(value['connection_manifest']['path']) == value['connection_manifest'],
            'VOLTAGE_CONTROL_CONNECTION_MANIFEST_RECEIPT_DRIFT')
    case = value['case']
    require(case in ('REF','REFa','A1','A2','B','C'),'VOLTAGE_CONTROL_EXPLICIT_CASE_REQUIRED')
    require(value['time_mode'] == ('STATIC' if case == 'REF' else 'TIME'),
            'VOLTAGE_CONTROL_REF_STATIC_OTHER_CASE_TIME_REQUIRED')
    require((value['capcontrol'] is not None) == (case in ('A1','A2','C')),
            'VOLTAGE_CONTROL_INDEPENDENT_CAP_CASE_CONTRACT_REQUIRED')
    require((value['svr'] is not None) == (case in ('B','C')),
            'VOLTAGE_CONTROL_INDEPENDENT_SVR_CASE_CONTRACT_REQUIRED')
    cap, svr = value['capcontrol'],value['svr']
    if cap is not None:
        from .capcontrol import validate_contract
        require(canonical(validate_contract(cap)) == canonical(cap),
                'VOLTAGE_CONTROL_CAP_FROZEN_COMPLETE_FIELDS_REQUIRED')
        names = {str(r['capacitor']).lower().removeprefix('capacitor.') for r in cap['devices']}
        expected = {'c83'} if case == 'A1' else {'c83','c88a','c90b','c92c'}
        require(names == expected,'VOLTAGE_CONTROL_CAP_VARIANT_EQUIPMENT_REQUIRED')
    if svr is not None:
        from .svr import validate_contract
        require(canonical(validate_contract(svr)) == canonical(svr),
                'VOLTAGE_CONTROL_SVR_FROZEN_COMPLETE_FIELDS_REQUIRED')
    return value,cap,svr


def original_parameters(inventory):
    """Element settings identity excludes changing tap and global control mode."""
    return [dict(name=r['name'],transformer=r['transformer'],winding=r['winding'],
        min_tap=r['min_tap'],max_tap=r['max_tap'],num_taps=r['num_taps'],tap_step=r['tap_step'],
        properties={k:v for k,v in r['resolved_properties'].items() if k != 'TapNum'})
        for r in inventory['regulators']]


def assert_control_inventory(inventory, scenario, *, initial=False, expected=None):
    from v42_regcontrol import authority
    expected = expected or authority.source()['expected']
    names = [r['name'] for r in expected['regulators']]
    original = [r for r in inventory['regulators'] if r['name'] in names]
    require([r['name'] for r in original] == names and all(r['enabled'] for r in original),
            'VOLTAGE_CONTROL_ORIGINAL_SEVEN_AUTO_REQUIRED')
    require(original_parameters(dict(regulators=original)) == original_parameters(expected),
            'VOLTAGE_CONTROL_ORIGINAL_REGCONTROL_PARAMETER_DRIFT')
    allowed_regs = set()
    if scenario['svr'] is not None:
        allowed_regs = {f"svr_{r['id']}_p{p}".lower() for r in scenario['svr']['units'] for p in r['phases']}
    require({r['name'].lower() for r in inventory['regulators']} == set(names)|allowed_regs,
            'VOLTAGE_CONTROL_UNDECLARED_OR_MISSING_REGCONTROL')
    require(all(r['enabled'] for r in inventory['regulators']), 'VOLTAGE_CONTROL_AUTOMATIC_CONTROL_DISABLED')
    require(inventory['engine_version'] == expected['engine_version'] and inventory['solution_mode'] == expected['solution_mode']
        and inventory['max_control_iterations'] == 100
        and inventory['control_mode'] == (0 if scenario['time_mode'] == 'STATIC' else 2),
        'VOLTAGE_CONTROL_DECLARED_NATIVE_MODE_OR_ITERATIONS_DRIFT')
    controlled = set()
    if scenario['capcontrol'] is not None:
        controlled = {str(r['capacitor']).lower().removeprefix('capacitor.') for r in scenario['capcontrol']['devices']}
    require(inventory['capacitor_banks'] == 4 and inventory['CapControl_count'] == len(controlled),
            'VOLTAGE_CONTROL_CAPCONTROL_COUNT_DRIFT')
    require([r['name'] for r in inventory['capacitors']] == [r['name'] for r in expected['capacitors']],
            'VOLTAGE_CONTROL_ORIGINAL_CAPACITOR_AXIS_DRIFT')
    for observed,reference in zip(inventory['capacitors'],expected['capacitors']):
        require({k:v for k,v in observed.items() if k != 'states'} == {k:v for k,v in reference.items() if k != 'states'},
                'VOLTAGE_CONTROL_ORIGINAL_CAP_PHYSICAL_RATING_OR_CONNECTION_DRIFT')
        require(observed['states'] in ([0],[1]),'VOLTAGE_CONTROL_SINGLE_PHYSICAL_STAGE_REQUIRED')
        if observed['name'].lower() not in controlled or initial:
            require(observed['states'] == [1],'VOLTAGE_CONTROL_UNCONTROLLED_CAP_FIXED_ON_REQUIRED')
    if initial:
        require([r['initial_tap'] for r in original] == [r['initial_tap'] for r in expected['regulators']],
                'VOLTAGE_CONTROL_SOURCE_INITIAL_ORIGINAL_TAPS_DRIFT')
    return True


@lru_cache(None)
def _global_loads(body):
    return tuple((i.offset,i.argval) for i in dis.get_instructions(body) if i.opname=='LOAD_GLOBAL')


def _physical_frame(body, namespace, *, direct_calls=None):
    frame = sys._getframe(1)
    try:
        while frame is not None:
            if frame.f_code is body:
                if direct_calls is not None:
                    # An auxiliary authority compile can occur underneath a
                    # branch getter inside this same body. Admit only the
                    # actual original backend hook call, never its ancestry.
                    loads=[name for offset,name in _global_loads(body) if offset<=frame.f_lasti]
                    if not loads or loads[-1] not in direct_calls:
                        return None
                trajectory = frame.f_locals.get('trajectory')
                if getattr(trajectory,'namespace',None) != namespace:
                    return None
                return dict(day=trajectory.day,arm=trajectory.case,slot=frame.f_locals.get('slot'),trajectory=trajectory)
            frame = frame.f_back
    finally:
        del frame
    return None


def _bindings():
    from .bindings import original_bindings
    authority, _, _, _, backend, mapping, _, _ = original_bindings()
    return authority,backend,mapping


def _physical_inputs(engine):
    result = {}
    for kind,collection in (('Load',engine.Loads),('Generator',engine.Generators)):
        for name in collection.AllNames():
            if str(name).lower() == 'none': continue
            collection.Name(name)
            result[kind+'.'+name] = [float(collection.kW()),float(collection.kvar())]
    return result


def _trajectory_sha(trajectory):
    return digest(dict(day=trajectory.day,arm=trajectory.case,namespace=trajectory.namespace,
        arrays={k:hashlib.sha256(np.asarray(getattr(trajectory,k)).tobytes()).hexdigest()
                for k in ('pcc_p_kw','pcc_q_kvar','mess_p_kw','mess_q_kvar','mess_locations_96x4')}))


def _equipment(engine):
    """All original physical ratings; connection edits are separately contracted."""
    result = {}
    for name in engine.Lines.AllNames():
        if name.lower() == 'none': continue
        engine.Lines.Name(name)
        engine.Circuit.SetActiveElement('line.'+name)
        result['line.'+name] = dict(NormAmps=float(engine.Lines.NormAmps()),EmergAmps=float(engine.Lines.EmergAmps()),
                                   buses=list(engine.CktElement.BusNames()))
    for name in engine.Transformers.AllNames():
        if name.lower() == 'none': continue
        engine.Transformers.Name(name); engine.Circuit.SetActiveElement('Transformer.'+name)
        properties = {k:engine.Properties.Value(k) for k in ('NormAmps','EmergAmps','NormHkVA','EmergHkVA','Xhl','%noloadloss')}
        windings = []
        for w in range(1,int(engine.Transformers.NumWindings())+1):
            engine.Transformers.Wdg(w)
            windings.append(dict(kV=float(engine.Transformers.kV()),kVA=float(engine.Transformers.kVA()),
                                 percentR=float(engine.Transformers.R()),delta=bool(engine.Transformers.IsDelta())))
        result['transformer.'+name] = dict(properties=properties,windings=windings,buses=list(engine.CktElement.BusNames()))
    return result


def _retired_inventory(engine):
    names = [str(n) for n in engine.Circuit.AllElementNames()]
    forbidden = [n for n in names if any(token in n.lower() for token in ('dstat','statcom'))]
    require(not forbidden,'VOLTAGE_CONTROL_RETIRED_PHYSICAL_OBJECT_FORBIDDEN')
    return dict(compiled_retired_objects=forbidden,retired_objects_count=0,
                retired_Q_injection_devices=0,compiled_element_count=len(names),
                compiled_element_names=names,compiled_element_names_SHA=digest(names))


def _controls(engine, scenario, authority=None):
    if authority is None:
        from v42_regcontrol import authority
    inventory = authority.source()['inventory'](engine)
    assert_control_inventory(inventory,scenario)
    original_names = {r['name'] for r in authority.source()['expected']['regulators']}
    original = [r for r in inventory['regulators'] if r['name'] in original_names]
    parameters = original_parameters(dict(regulators=original))
    require(int(engine.Solution.MaxIterations()) == 15,'VOLTAGE_CONTROL_ORIGINAL_MAXITERATIONS_DRIFT')
    return dict(regulator_settings_SHA=digest(parameters),
        original_static_source_regulator_authority_SHA=authority.digest(authority.regulator_parameters(authority.source()['expected'])),
        individual_regulator_settings_SHA={r['name']:digest(r) for r in parameters},
        original_regulators=original,all_seven_RegControls_enabled=all(r['enabled'] for r in original),
        taps=[r['initial_tap'] for r in original],capacitors=inventory['capacitors'],
        added_regulators=[r for r in inventory['regulators'] if r['name'] not in original_names],
        capcontrols=inventory['capcontrols'],control_mode=inventory['control_mode'],
        ControlActionsDone=bool(engine.Solution.ControlActionsDone()),solution_converged=bool(engine.Solution.Converged()),
        ControlIterations=int(engine.Solution.ControlIterations()),Solution_Iterations_total=int(engine.Solution.Iterations()),
        Solution_TotalIterations=int(engine.Solution.TotalIterations()),
        Solution_MostIterationsDone_per_control_pass=int(engine.Solution.MostIterationsDone()),
        configured_MaxControlIterations=int(engine.Solution.MaxControlIterations()),
        configured_MaxIterations=int(engine.Solution.MaxIterations()))


def measure_full_network(engine, original_nodes, original_equipment):
    """Read every phase voltage and every terminal current/kVA, including additions."""
    from v42_svr11.authority import active as svr11_active
    epoch=svr11_active()
    normalamps_original=bool(epoch and epoch.get('original_transformer_current_authority')=='COMPILED_NORMALAMPS_ONLY')
    all_names = list(map(str,engine.Circuit.AllNodeNames()))
    all_v = np.asarray(engine.Circuit.AllBusMagPu(),dtype=float)
    require(len(all_names) == len(all_v),'VOLTAGE_CONTROL_FULL_NODE_AXIS_DRIFT')
    nodes = [dict(node_phase=n.lower(),voltage_pu=float(v),original=n.lower() in original_nodes)
             for n,v in zip(all_names,all_v) if n.rsplit('.',1)[-1] in ('1','2','3')]
    require(nodes and all(math.isfinite(r['voltage_pu']) for r in nodes),'VOLTAGE_CONTROL_FINITE_ALL_NODES_REQUIRED')
    currents,transformers = [],[]
    for kind,collection in (('line',engine.Lines),('transformer',engine.Transformers)):
        for name in collection.AllNames():
            if name.lower() == 'none': continue
            element = kind+'.'+name
            engine.Circuit.SetActiveElement(element)
            ncond,nterm = int(engine.CktElement.NumConductors()),int(engine.CktElement.NumTerminals())
            order=list(map(int,engine.CktElement.NodeOrder()))
            amperes=list(map(float,engine.CktElement.CurrentsMagAng()))[0::2]
            powers=list(map(float,engine.CktElement.Powers()))
            if kind == 'line':
                collection.Name(name); norm=float(collection.NormAmps())
                kv1=None
            else:
                collection.Name(name); collection.Wdg(1)
                norm=float(engine.Properties.Value('NormAmps')); kv1=float(collection.kV())
            require(math.isfinite(norm) and norm>0,'VOLTAGE_CONTROL_COMPILED_NORMALAMPS_REQUIRED')
            for terminal in range(nterm):
                normal=norm; nameplate_current=None
                if kind == 'transformer':
                    collection.Wdg(terminal+1)
                    kv=float(collection.kV()); kva=float(collection.kVA())
                    require(math.isfinite(kv) and kv>0 and math.isfinite(kva) and kva>0,
                            'VOLTAGE_CONTROL_SOURCE_WINDING_NAMEPLATE_REQUIRED')
                    normal=norm*kv1/kv
                    # Exact original backend denominator: kVA/kV is amperes;
                    # kilo cancels. This conservative audit is separate from
                    # unchanged native NormalAmps and winding apparent power.
                    phases=int(engine.CktElement.NumPhases())
                    nameplate_current=kva/(math.sqrt(3.0)*kv) if phases>=2 else kva/kv
                    phase_positions=[terminal*ncond+j for j in range(ncond) if order[terminal*ncond+j] in (1,2,3)]
                    total=math.hypot(sum(powers[2*j] for j in phase_positions),sum(powers[2*j+1] for j in phase_positions))
                    transformers.append(dict(element=element,terminal=terminal+1,kVA=total,rating_kVA=kva,
                        loading_pu=total/kva,original=element in original_equipment))
                for j in range(ncond):
                    pos=terminal*ncond+j
                    if order[pos] in (1,2,3):
                        currents.append(dict(element=element,terminal=terminal+1,phase=order[pos],
                            current_A=amperes[pos],NormalAmps=normal,loading_pu=amperes[pos]/normal,
                            nameplate_current_A=nameplate_current,
                            nameplate_current_loading_pu=None if nameplate_current is None else amperes[pos]/nameplate_current,
                            original=element in original_equipment))
    require(all(math.isfinite(r['loading_pu']) for r in currents+transformers),'VOLTAGE_CONTROL_FINITE_ALL_THERMAL_REQUIRED')
    require(all(r['nameplate_current_loading_pu'] is None or math.isfinite(r['nameplate_current_loading_pu'])
                for r in currents),'VOLTAGE_CONTROL_FINITE_NAMEPLATE_CURRENT_REQUIRED')
    bad_nodes=[r for r in nodes if not .95<=r['voltage_pu']<=1.05]
    bad_current=[r for r in currents if r['loading_pu']>1]
    bad_kva=[r for r in transformers if r['loading_pu']>1]
    nameplate_exceedances=[r for r in currents if r['nameplate_current_loading_pu'] is not None and r['nameplate_current_loading_pu']>1]
    # Original source authority uses compiled NormalAmps, with winding kVA
    # checked separately. The inferred nominal phase current remains diagnostic.
    # Added single-phase SVRs retain their finite phase nameplate current guard.
    bad_nameplate=[r for r in nameplate_exceedances if not (normalamps_original and r['original'])]
    return dict(nodes=nodes,currents=currents,transformers=transformers,
        voltage_min_pu=min(r['voltage_pu'] for r in nodes),voltage_max_pu=max(r['voltage_pu'] for r in nodes),
        voltage_violation_cells=len(bad_nodes),line_current_violation_cells=sum(r['element'].startswith('line.') for r in bad_current),
        transformer_current_violation_cells=sum(r['element'].startswith('transformer.') for r in bad_current),
        transformer_nameplate_current_violation_cells=len(bad_nameplate),
        original_nominal_phase_current_diagnostic_exceedance_cells=sum(r['original'] for r in nameplate_exceedances),
        original_transformer_current_authority='COMPILED_NORMALAMPS_ONLY' if normalamps_original else 'LEGACY_NORMALAMPS_AND_NOMINAL_PHASE_GUARD',
        original_transformer_nameplate_current_violation_cells=sum(r['original'] for r in bad_nameplate),
        added_transformer_nameplate_current_violation_cells=sum(not r['original'] for r in bad_nameplate),
        transformer_kva_violation_cells=len(bad_kva),all_original_and_added_axes_checked=True,
        nameplate_current_denominator_source='Exact original backend winding kVA/(sqrt(3)*kV) for Phases>=2; winding kVA/kV otherwise, independently at every terminal',
        native_NormalAmps_and_winding_kVA_unchanged=True,
        PASS=not bad_nodes and not bad_current and not bad_kva and not bad_nameplate,losses_W_var=list(map(float,engine.Circuit.Losses())))


def assert_existing_controls(engine, *, initial=False):
    from v42_regcontrol import authority
    audit=_active.get()
    inventory=authority.source()['inventory'](engine)
    if audit is not None and id(engine) in audit.sessions:
        return assert_control_inventory(inventory,audit.scenario,initial=initial)
    # No scientific guard is weakened outside the explicit admitted engine.
    return authority.assert_inventory(inventory,initial=initial)


def current_declared_capcontrol_count():
    """Frozen scope count for honest original Fresh logging/validation."""
    audit=_active.get()
    return len(audit.cap_contract['devices']) if audit is not None and audit.cap_contract is not None else 0


class PhysicalScenario:
    def __init__(self,scenario,output,*,source_SHA,arm,day,namespace='ACTUAL'):
        require_sha(source_SHA)
        require(arm in ('B0','B1','B2','B3') and date.fromisoformat(day).isoformat()==day,'VOLTAGE_CONTROL_ARM_DAY_REQUIRED')
        require(namespace in ('DAYAHEAD','ACTUAL'),'VOLTAGE_CONTROL_EXPLICIT_NAMESPACE_REQUIRED')
        self.scenario,self.cap_contract,self.svr_contract=validate_scenario(scenario)
        self.output,self.source_SHA,self.arm,self.day=Path(output).resolve(),source_SHA,arm,day
        self.namespace=namespace; self.prefix='PLANNING' if namespace=='DAYAHEAD' else 'ACTUAL'
        require(not self.output.exists(),'VOLTAGE_CONTROL_PHYSICAL_OUTPUT_NEVER_OVERWRITTEN')
        self.sessions={}; self.rows=[]; self.sources=[]; self.events=[]
        self.topology_measurement_proxies=[]
        self.result=self.receipt=self.trajectory_SHA=self.source_initial_controls=self.initial_controls=None
        self.controllerinitialstate=None

    def _identity(self,identity):
        require(identity['day']==self.day and identity['arm']==self.arm
            and identity['trajectory'].namespace==self.namespace,'VOLTAGE_CONTROL_FRAME_SOURCE_IDENTITY_DRIFT')
        sha=_trajectory_sha(identity['trajectory'])
        if self.trajectory_SHA is None: self.trajectory_SHA=sha
        require(sha==self.trajectory_SHA,'VOLTAGE_CONTROL_FROZEN_TRAJECTORY_MUTATION')

    def install_actual(self,engine,identity,authority):
        from .authority import authorize_physical
        authorize_physical(self.arm,self.day,self.source_SHA,self.scenario['scenario_SHA'],self.namespace)
        self._identity(identity)
        require(not self.sessions,'VOLTAGE_CONTROL_ONE_INDEPENDENT_FRESH_ENGINE_REQUIRED')
        original=authority.source()['inventory'](engine)
        authority.assert_inventory(original,initial=True)
        self.original_compiled_inventory=_retired_inventory(engine)
        equipment=_equipment(engine); inputs=_physical_inputs(engine)
        nodes={n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in ('1','2','3')}
        self.source_initial_controls=original
        clock=bank=svrs=None
        if self.scenario['time_mode']=='TIME':
            from .timecontrol import CommonClock
            clock=CommonClock(self.namespace,self.day,slot_seconds=900); clock.bind(engine)
        if self.cap_contract is not None:
            from .capcontrol import install
            bank=install(engine,self.cap_contract,clock=clock)
        if self.svr_contract is not None:
            from .svr import install
            svrs=install(engine,self.svr_contract)
        self.sessions[id(engine)]=dict(engine=engine,clock=clock,bank=bank,svrs=svrs,
                                       original_equipment=equipment,original_nodes=nodes)
        self.engine_context_identity=dict(engine_object_id=id(engine),solution_object_id=id(engine.Solution))
        require(_physical_inputs(engine)==inputs,'VOLTAGE_CONTROL_INSTALL_ORIGINAL_INJECTION_MUTATION')
        self.installed_compiled_inventory=self._ratings(engine)
        assert_control_inventory(authority.source()['inventory'](engine),self.scenario,initial=True)
        # Identity excludes solution counters; it contains every original and
        # new native control element's actual Source Initial State.
        self.initial_controls=authority.source()['inventory'](engine)
        self.controllerinitialstate=dict(capcontrol=getattr(bank,'initial_state',None),svr=getattr(svrs,'initial_state',None),
            namespace=self.namespace,native_queue_started_independently=True,other_namespace_states_read=0)

    def _ratings(self,engine):
        session=self.sessions[id(engine)]
        current=_equipment(engine)
        cuts={} if self.svr_contract is None else {r['cut_element'].lower():r for r in self.svr_contract['units']}
        for key,original in session['original_equipment'].items():
            reference=json.loads(canonical(original))
            cut=cuts.get(key.lower())
            if cut is not None:
                terminal=cut['cut_terminal']-1
                require(reference['buses'][terminal].lower()==cut['original_bus_spec'].lower(),
                        'VOLTAGE_CONTROL_FROZEN_ORIGINAL_SERIES_CUT_DRIFT')
                reference['buses'][terminal]=cut['upstream_new_bus']+'.1.2.3'
            require(current.get(key)==reference,'VOLTAGE_CONTROL_ORIGINAL_PHYSICAL_RATING_OR_UNDECLARED_TOPOLOGY_DRIFT')
        return _retired_inventory(engine)

    def measure_original_branch(self,engine,branch,original_measurement):
        """Keep the original current authority; reflect only its declared cut.

        A series insertion changes the old physical element's terminal bus, not
        its phase/name/NormalAmps/kVA. The old axis remains useful for paired
        raw arrays; new elements are independently measured by the full audit.
        """
        if id(engine) not in self.sessions or self.svr_contract is None:
            return original_measurement(engine,branch)
        cut=next((r for r in self.svr_contract['units'] if r['cut_element'].lower()==branch.branch_id.lower()),None)
        if cut is None:
            return original_measurement(engine,branch)
        self._ratings(engine)
        original=self.sessions[id(engine)]['original_equipment'][branch.branch_id.lower()]
        old_bus=[b.split('.')[0].lower() for b in original['buses']]
        require(branch.parent_bus.lower() in old_bus,'VOLTAGE_CONTROL_ORIGINAL_BRANCH_PARENT_NOT_SOURCE_TERMINAL')
        parent_terminal=old_bus.index(branch.parent_bus.lower())
        engine.Circuit.SetActiveElement(branch.branch_id)
        buses=[b.split('.')[0].lower() for b in engine.CktElement.BusNames()]
        require(is_dataclass(branch),'VOLTAGE_CONTROL_ORIGINAL_BRANCH_DATACLASS_REQUIRED')
        proxy=replace(branch,parent_bus=buses[parent_terminal])
        self.topology_measurement_proxies.append(dict(branch_id=branch.branch_id,phase=branch.phase,
            original_parent_bus=branch.parent_bus,measured_parent_bus=proxy.parent_bus,
            original_parent_terminal_1based=parent_terminal+1,declared_cut_terminal_1based=cut['cut_terminal'],
            NormalAmps_and_kVA_authority_unchanged=True,only_metadata_parent_bus_replaced=True))
        return original_measurement(engine,proxy)

    def settle_actual(self,engine,identity,authority):
        from .authority import authorize_physical
        authorize_physical(self.arm,self.day,self.source_SHA,self.scenario['scenario_SHA'],self.namespace)
        self._identity(identity)
        require(id(engine) in self.sessions and self.sessions[id(engine)]['engine'] is engine,
                'VOLTAGE_CONTROL_ENGINE_NOT_ADMITTED')
        require(identity['slot']==len(self.rows) and len(self.rows)<96,'VOLTAGE_CONTROL_CHRONOLOGICAL_96_SLOT_REQUIRED')
        session=self.sessions[id(engine)]; slot=identity['slot']; inputs=_physical_inputs(engine)
        initial=_controls(engine,self.scenario,authority)
        self.events.append(dict(slot=slot,kind='ORIGINAL_SLOT_INITIAL_SOLVE',completed=True,controls=initial))
        clock_result=None
        if session['clock'] is not None:
            solution=engine.Solution; cls=type(solution); original=cls.SolveSnap
            def observed(instance,*args,**kwargs):
                if instance is not solution: return original(instance,*args,**kwargs)
                event=dict(slot=slot,kind='NATIVE_TIME_QUEUE_SOLVE',completed=False,controls=None)
                self.events.append(event)
                value=original(instance,*args,**kwargs)
                event['completed']=True; event['controls']=_controls(engine,self.scenario,authority)
                self._ratings(engine)
                require(_physical_inputs(engine)==inputs,'VOLTAGE_CONTROL_TIME_SOLVE_ORIGINAL_INJECTION_MUTATION')
                return value
            with patch.object(cls,'SolveSnap',observed):
                clock_result=session['clock'].settle_slot(engine,slot,bank=session['bank'],initial_solve_already_done=True)
        self._ratings(engine); controls=_controls(engine,self.scenario,authority); self._identity(identity)
        require(_physical_inputs(engine)==inputs,'VOLTAGE_CONTROL_ORIGINAL_FROZEN_PQ_MUTATION')
        physical=measure_full_network(engine,session['original_nodes'],session['original_equipment'])
        cap=None if session['bank'] is None else session['bank'].measure()
        svr=None if session['svrs'] is None else session['svrs'].measure()
        done=controls['ControlActionsDone'] if clock_result is None else clock_result['control_actions_done_as_of_current_time']
        passed=controls['solution_converged'] and done and physical['PASS']
        if cap is not None: passed=passed and cap.get('PASS') is True
        if svr is not None:
            passed=passed and svr.get('hardware_PASS') is True and svr.get('added_nodes_voltage_PASS') is True
        self.rows.append(dict(slot=slot,arm=self.arm,day=self.day,namespace=self.namespace,
            original_inputs_SHA=digest(inputs),frozen_trajectory_SHA=self.trajectory_SHA,
            original_initial_solve_controls=initial,settled_original_controls=controls,
            time_control=clock_result,capcontrol=cap,svr=svr,physical=physical,
            original_input_setpoints_unchanged=True,control_actions_done_as_of_current_time=bool(done),PASS=bool(passed)))
        self.write_progress()

    def write_progress(self,status='RUNNING',error=None):
        self.output.mkdir(parents=True,exist_ok=True)
        last=self.rows[-1] if self.rows else None
        value=dict(schema='V42_VOLTAGE_CONTROL_PROGRESS_V1',status=status,namespace=self.namespace,
            arm=self.arm,day=self.day,case=self.scenario['case'],time_mode=self.scenario['time_mode'],
            source_SHA=self.source_SHA,scenario_SHA=self.scenario['scenario_SHA'],PID=os.getpid(),
            updated_UTC=datetime.now(timezone.utc).isoformat(),logical_Fresh_slots_completed=len(self.rows),
            logical_Fresh_slots_target=96,total_physical_SolveSnap_count=len(self.events),
            completed_physical_SolveSnap_count=sum(e['completed'] for e in self.events),
            failed_slots_count=sum(not r['PASS'] for r in self.rows),
            last_completed_slot=None if last is None else last['slot'],
            last_slot_voltage_violation_cells=None if last is None else last['physical']['voltage_violation_cells'],
            Native_optimizer_calls=0,MESS_PQ_repair_calls=0,retired_objects_count=0,error=error)
        path=self.output/('VOLTAGE_CONTROL_'+self.prefix+'_PROGRESS.json'); temporary=path.with_suffix('.tmp')
        temporary.write_text(canonical(value)+'\n',encoding='utf8');os.replace(temporary,path)

    def persist(self,*,error=None,bodies_unchanged=True):
        self.output.mkdir(parents=True,exist_ok=True)
        path=self.output/('VOLTAGE_CONTROL_'+self.prefix+'_SLOTS.json')
        path.write_text(canonical(self.rows)+'\n',encoding='utf8')
        events=self.output/'VOLTAGE_CONTROL_PHYSICAL_SOLVE_EVENTS.json'
        events.write_text(canonical(self.events)+'\n',encoding='utf8')
        unchanged=all(record(r['path'])==r for r in self.sources)
        complete=len(self.rows)==96 and error is None and bodies_unchanged and unchanged
        passed=complete and all(r['PASS'] for r in self.rows)
        self.result=dict(schema=VERSION,PASS=bool(passed),hardware_and_controller_PASS=bool(passed),
            Full_AC_Physical_PASS=bool(passed),status='COMPLETE' if complete else 'NOT_RUN' if not self.rows and error is None else 'INCOMPLETE_OR_FAILED',
            source_SHA=self.source_SHA,execution_source_SHA=self.source_SHA,scenario_SHA=self.scenario['scenario_SHA'],
            day=self.day,arm=self.arm,namespace=self.namespace,case=self.scenario['case'],frozen_scenario=self.scenario,
            logical_Fresh_slots=len(self.rows),original_initial_physical_solve_count=sum(e['kind']=='ORIGINAL_SLOT_INITIAL_SOLVE' for e in self.events),
            total_physical_SolveSnap_count=len(self.events),completed_physical_SolveSnap_count=sum(e['completed'] for e in self.events),
            additional_time_queue_solve_count=sum(e['kind']=='NATIVE_TIME_QUEUE_SOLVE' for e in self.events),
            hardware_or_controller_failed_slots=[r['slot'] for r in self.rows if not r['PASS']],
            source_initial_controls=self.source_initial_controls,initial_controls=self.initial_controls,
            engine_context_identity=getattr(self,'engine_context_identity',None),
            DSTATCOM_object_count=0 if self.sessions else None,
            original_compiled_inventory=getattr(self,'original_compiled_inventory',None),
            installed_compiled_inventory=getattr(self,'installed_compiled_inventory',None),
            declared_topology_measurement_proxies=self.topology_measurement_proxies,
            original_thermal_authority_prewarm=getattr(self,'thermal_authority_prewarm',None),
            controllerinitialstate=self.controllerinitialstate,new_engine_from_original_Source_Initial_State=True,
            Planning_Tap_or_Cap_state_transfer_to_Actual=False,independent_state_per_namespace=True,
            Original_Fresh_and_96_slot_body_unchanged=bodies_unchanged,Original_Source_SHA_before_after_equal=unchanged,
            original_input_setpoints_unchanged=all(r['original_input_setpoints_unchanged'] for r in self.rows) if self.rows else None,
            transformer_nameplate_current_violation_cells=sum(r['physical']['transformer_nameplate_current_violation_cells'] for r in self.rows),
            original_transformer_nameplate_current_violation_cells=sum(r['physical']['original_transformer_nameplate_current_violation_cells'] for r in self.rows),
            original_nominal_phase_current_diagnostic_exceedance_cells=sum(r['physical']['original_nominal_phase_current_diagnostic_exceedance_cells'] for r in self.rows),
            original_transformer_current_authority=self.rows[0]['physical']['original_transformer_current_authority'] if self.rows else None,
            added_transformer_nameplate_current_violation_cells=sum(r['physical']['added_transformer_nameplate_current_violation_cells'] for r in self.rows),
            retired_objects_count=0 if self.sessions else None,retired_Q_injection_devices=0 if self.sessions else None,
            Actual_optimizer_calls=0,Native_optimizer_calls=0,
            Actual_plan_repair_calls=0,control_MILP_variables=0,Planning_band_pu=[.95,1.05],Actual_band_pu=[.95,1.05],
            Original_Reg_Delay_seconds=15,Original_Reg_TapDelay_seconds=2,original_physical_ratings_changed=False,
            original_sources=self.sources,slots_receipt=record(path),physical_solve_events_receipt=record(events),error=error,
            TIME_semantics='Native queue timestamps; future boundary events carry to next slot with that slot input. STATIC REF is a separate baseline.')
        result_path=self.output/('VOLTAGE_CONTROL_'+self.prefix+'_PHYSICAL_AUDIT.json')
        result_path.write_text(canonical(self.result)+'\n',encoding='utf8'); self.receipt=record(result_path)
        self.write_progress(self.result['status'],error)


@contextmanager
def scenario_scope(scenario,output,*,source_SHA,arm,day,namespace='ACTUAL'):
    from .authority import authorize_physical
    require(_active.get() is None,'VOLTAGE_CONTROL_NESTED_NAMESPACE_SCOPE_FORBIDDEN')
    audit=PhysicalScenario(scenario,output,source_SHA=source_SHA,arm=arm,day=day,namespace=namespace)
    authorize_physical(arm,day,source_SHA,audit.scenario['scenario_SHA'],namespace)
    authority,backend,mapping=_bindings()
    from v42_thermal.authority import current_authority
    cold=current_authority.cache_info().currsize==0
    thermal=current_authority()
    require(thermal.get('PASS') is True,'VOLTAGE_CONTROL_ORIGINAL_THERMAL_AUTHORITY_REQUIRED')
    audit.thermal_authority_prewarm=dict(completed_before_source_hooks=True,cache_was_cold=cold,
        transformer_current_authority_sha256=thermal['transformer_current_authority_sha256'],
        original_Planning_Actual_authority_equal=thermal['Planning']==thermal['Actual'],
        installed_scenario_objects_in_authority_compile=0)
    original_compile,original_voltage,original_assert=authority.compile_verified,backend._voltage_vector,authority.assert_inventory
    original_source=authority.source()
    original_measurements={name:original_source[name] for name in ('branch_measurement','legacy_branch_measurement')}
    body=backend.run_fresh_opendss.__code__
    audit.sources=[record(inspect.getfile(f)) for f in (original_compile,original_voltage,backend.run_fresh_opendss,
        mapping.apply_trajectory_slot,original_assert)] + [record(__file__)]
    from v42_regcontrol.common import resolve
    source_audit=authority.source()['audit']
    for receipt in source_audit['static_source_graph']['files']+source_audit['code_read']:
        current=record(resolve(receipt))
        if current not in audit.sources: audit.sources.append(current)
    def compiled():
        result=original_compile(); identity=_physical_frame(body,namespace,direct_calls=('compile_clean_engine',))
        if identity is not None: audit.install_actual(result[0],identity,authority)
        return result
    def voltage(engine,nodes):
        identity=_physical_frame(body,namespace,direct_calls=('_voltage_vector',))
        if identity is not None: audit.settle_actual(engine,identity,authority)
        return original_voltage(engine,nodes)
    def guarded(inventory,*,initial=False):
        identity=_physical_frame(body,namespace,direct_calls=('_voltage_vector','apply_trajectory_slot','apply_frozen_native_state'))
        if identity is not None and audit.sessions:
            return assert_control_inventory(inventory,audit.scenario,initial=initial)
        return original_assert(inventory,initial=initial)
    def measurement_hook(original_measurement):
        def measured_branch(engine,branch):
            if _physical_frame(body,namespace,direct_calls=('_branch_measurement',)) is not None and id(engine) in audit.sessions:
                return audit.measure_original_branch(engine,branch,original_measurement)
            return original_measurement(engine,branch)
        return measured_branch
    # Historical B0 RAW current_pu uses the exact original nameplate function;
    # successor RAW current_pu uses native NormAmps. Reflect the same declared
    # terminal metadata for either function, without changing either formula.
    measurement_hooks={name:measurement_hook(function) for name,function in original_measurements.items()}
    token=_active.set(audit);error=None
    try:
        with patch.object(authority,'compile_verified',compiled),patch.object(backend,'_voltage_vector',voltage),patch.object(authority,'assert_inventory',guarded),patch.dict(original_source,measurement_hooks):
            yield audit
    except BaseException as exc:
        error=type(exc).__name__+':'+str(exc);raise
    finally:
        _active.reset(token)
        audit.persist(error=error,bodies_unchanged=backend.run_fresh_opendss.__code__ is body)

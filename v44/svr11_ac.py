"""Original causal Actual probe with Epoch12 install/TIME/measurement calls."""
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from copy import deepcopy
from collections import OrderedDict
from unittest.mock import patch
import ast
import inspect
import textwrap
import numpy as np

from .common import read,record,digest
from .common import RUNTIME,atomic
from .svr11_hardware import HARDWARE,scope,compile_context
from .svr11_vendor import install as load_vendor


def prefix_clock_class():
    load_vendor()
    from v42_voltage_control.timecontrol import CommonClock
    tree=ast.parse(textwrap.dedent(inspect.getsource(CommonClock.settle_slot)));changes=0
    class Axis(ast.NodeTransformer):
        def visit_Compare(self,node):
            nonlocal changes
            if ast.unparse(node)=='0 <= slot < 96':
                node.comparators[-1]=ast.Constant(120);changes+=1
            return self.generic_visit(node)
    tree=Axis().visit(tree);ast.fix_missing_locations(tree)
    if changes!=1:raise ValueError('EPOCH12_TIME_PREFIX_AXIS_BOUNDARY_DRIFT')
    ns=dict(CommonClock.settle_slot.__globals__);exec(compile(tree,__file__,'exec'),ns)
    return type('V44IssuePrefixClock',(CommonClock,),dict(settle_slot=ns['settle_slot'],axis_adapter_only=True))


def probe_body():
    from v43_actual.current_ac import OriginalCurrentAC
    body=textwrap.dedent(inspect.getsource(OriginalCurrentAC._probe))
    def replace(old,new,count=1):
        nonlocal body
        if body.count(old)!=count:raise ValueError('V44_SVR11_PROBE_BOUNDARY_DRIFT:'+old)
        body=body.replace(old,new)
    replace('odd,adapter,initial=authority.compile_verified()',
        'odd,adapter,initial=self._compile_native()')
    replace("authority.assert_inventory(source['inventory'](odd))",
        "self._inventory(odd)",count=2)
    solve_line=next(line for line in body.splitlines() if 'odd.Solution.SolveSnap()' in line)
    indent=solve_line[:len(solve_line)-len(solve_line.lstrip())]
    replace(indent+'self._inventory(odd)\n'+solve_line,
        indent+'self._apply_frozen_mess(odd,row)\n'+indent+'self._inventory(odd)\n'+indent+'before_state=self._state(odd)\n'+indent+'time_receipt=self._settle(odd,slot)')
    replace(indent+'if not converged:\n',
        indent+'full=self._full_measurement(odd)\n'+
        indent+'steps[-1].update(time_control=time_receipt,native_state=self._state(odd),before_state=before_state,\n'+
        indent+'    full_physical=full,voltage_nodes=full["nodes"],\n'+
        indent+'    SVR_devices=self._bank.measure(),MESS_plan_sha=self.mess_sha)\n'+
        indent+'steps[-1]["PASS"]=steps[-1]["PASS"] and full["PASS"] and steps[-1]["SVR_devices"]["hardware_PASS"]\n'+
        indent+'if not converged:\n')
    replace('original_RegControl=7,added_SVR_count=0,CapControl_count=0,',
        'original_RegControl=7,added_SVR_count=11,RegControl_count=40,CapControl_count=0,')
    replace("control_mode='ORIGINAL_SNAPSHOT_STATIC'","control_mode='EPOCH12_AUTO_NATIVE_TIME_ISSUE_PREFIX120'")
    replace('odd.Basic.ClearAll()','self._retire(odd)')
    ns=dict(OriginalCurrentAC._probe.__globals__);exec(compile(body,__file__,'exec'),ns)
    return ns['_probe']


def evaluate_body():
    from v43_actual.current_ac import OriginalCurrentAC
    body=textwrap.dedent(inspect.getsource(OriginalCurrentAC.evaluate))
    old="'PR189_ORIGINAL7_AUTO_SNAPSHOT_STATIC_NO_ADDED_SVR'"
    if body.count(old)!=1:raise ValueError('SVR11_CACHE_IDENTITY_BOUNDARY_DRIFT')
    body=body.replace(old,"('V44_SVR11_NATIVE_TIME',self.hardware_record,self.scenario['scenario_SHA'],self.mess_sha)")
    ns=dict(OriginalCurrentAC.evaluate.__globals__);exec(compile(body,__file__,'exec'),ns)
    return ns['evaluate']


from v43_arms.current_ac import ArmCurrentAC


class SVR11CurrentAC(ArmCurrentAC):
    """Every candidate and Fresh engine starts independently from source state."""
    def __init__(self,*args,arm='B2',**kwargs):
        self.arm=arm
        super().__init__(*args,**kwargs);load_vendor()
        self.hardware=read(HARDWARE/'HARDWARE.json');self.scenario=read(self.hardware['scenario']['path'])
        self.hardware_record=record(HARDWARE/'HARDWARE.json')
        self.performance=dict(engine_compiles=0,slot_replays=0,verified_history_reuses=0,native_TIME=True)
        self._verified_history=OrderedDict();self._legacy_history=OrderedDict();self._independent_fresh=False
        self.performance['legacy_branch_measurement_reuses']=0
        self._native_probe=probe_body();self._candidate_evaluator=evaluate_body();self.certificates_log=[]

    def _compile_native(self):
        day=__import__('datetime').datetime.fromtimestamp(self.day_start,__import__('datetime').timezone(__import__('datetime').timedelta(hours=10))).date().isoformat()
        from v42_regcontrol import authority
        e,ad,old=authority.compile_verified()
        self._scenario_audit.install_actual(e,self._identity(0),authority)
        session=self._scenario_audit.sessions[id(e)]
        self._clock=session['clock'];self._bank=session['svrs']
        self._original_equipment=session['original_equipment'];self._original_nodes=session['original_nodes']
        self.performance['engine_compiles']+=1
        return e,ad,old

    def _inventory(self,e):
        from v42_regcontrol import authority
        from v42_voltage_control.integration import assert_control_inventory
        return assert_control_inventory(authority.source()['inventory'](e),self.scenario)

    def _full_measurement(self,e):
        self.performance['slot_replays']+=1
        return self._scenario_audit.rows[-1]['physical']

    def _identity(self,slot):
        return dict(day=self._day,arm=self.arm,slot=slot,trajectory=self._source_trajectory)

    def _settle(self,e,slot):
        from v42_regcontrol import authority
        e.Solution.SolveSnap()
        self._scenario_audit.settle_actual(e,self._identity(slot),authority)
        return self._scenario_audit.rows[-1]['time_control']

    def _state(self,e):
        from v42_regcontrol import authority
        from v42_voltage_control.timecontrol import queue,seconds
        inv=authority.source()['inventory'](e)
        return dict(taps=[r['initial_tap'] for r in inv['regulators']],caps=[r['states'] for r in inv['capacitors']],
            queue=queue(e),physical_seconds=seconds(e))

    def _retire(self,e):
        from v42_svr11.context_lifecycle import retire_completed_probe
        retire_completed_probe(e)
        self._clock=None;self._bank=None

    def _probe(self,rows):
        import uuid
        from datetime import datetime,timezone,timedelta
        from contextlib import ExitStack
        from functools import lru_cache
        if not 1<=len(rows)<=120:raise ValueError('SVR11_CAUSAL_ISSUE_PREFIX_1_TO_120_REQUIRED')
        if record(HARDWARE/'HARDWARE.json')!=self.hardware_record:raise ValueError('SVR11_CURRENT_AC_HARDWARE_DRIFT')
        self._day=datetime.fromtimestamp(self.day_start,timezone(timedelta(hours=10))).date().isoformat()
        mess_p=np.zeros((len(rows),4));mess_q=mess_p.copy()
        locations=np.full((len(rows),4),'PREFIX_SOURCE_INITIAL_ZERO_DISPATCH',dtype='<U48')
        if self._trajectory is not None:
            for i,row in enumerate(rows):
                slot=int((row['start_seconds']-self.day_start)//900)
                if 0<=slot<96:
                    mess_p[i]=self._trajectory.mess_p_kw[slot];mess_q[i]=self._trajectory.mess_q_kvar[slot]
                    locations[i]=self._trajectory.mess_locations_96x4[slot]
        self._source_trajectory=SimpleNamespace(day=self._day,case=self.arm,namespace='ACTUAL',
            pcc_p_kw=np.asarray([r['P'] for r in rows]),pcc_q_kvar=np.asarray([r['Q'] for r in rows]),
            mess_p_kw=mess_p,mess_q_kvar=mess_q,mess_locations_96x4=locations)
        output=RUNTIME/'svr11_revision01/AC_PROBES'/self._day/self.arm/uuid.uuid4().hex
        keys=[];previous=digest(dict(hardware=self.hardware_record,day=self._day,arm=self.arm,
            source=self.hardware['source_SHA'],mess_sha=self.mess_sha,sites=self.sites))
        for row in rows:
            previous=digest(dict(previous=previous,row=row));keys.append(previous)
        with scope():
            import v42_thermal.authority as thermal
            import v42_thermal.measurement as measurement
            import v42_voltage_control.integration as integration
            import v42_voltage_control.timecontrol as timecontrol
            from v42_voltage_control.authority import physical_permit
            from v42_svr11.initial_context import reference,independence
            from v42_svr11.context_lifecycle import retire_completed_probe
            cached=lru_cache(maxsize=1)(thermal.current_authority)
            original_class=integration.PhysicalScenario
            adapted=prefix_audit_class(original_class,len(rows))
            original_measure=integration.measure_full_network
            def measured(engine,original_nodes,original_equipment):
                slot=len(self._scenario_audit.rows)
                # Every native TIME solve, tap action and queue is replayed.
                # Only a historical measurement is reused, after exact source,
                # input-prefix, all complex bus voltages and control-state
                # equality. Independent Fresh always measures every terminal.
                self._legacy_slot_key=None;self._legacy_cache_hit=False
                if self._independent_fresh:return original_measure(engine,original_nodes,original_equipment)
                state=digest(dict(native=self._state(engine),complex_bus_voltages=list(engine.Circuit.AllBusVolts())))
                key=(keys[slot],state)
                if slot<len(rows)-1:self._legacy_slot_key=key
                if slot<len(rows)-1 and key in self._verified_history:
                    self._legacy_cache_hit=True
                    self.performance['verified_history_reuses']+=1
                    self._verified_history.move_to_end(key)
                    return deepcopy(self._verified_history[key])
                value=original_measure(engine,original_nodes,original_equipment)
                if slot<len(rows)-1:
                    self._verified_history[key]=deepcopy(value)
                    while len(self._verified_history)>120:self._verified_history.popitem(last=False)
                return value
            # The horizon adapter has its own copied function namespace. Bind
            # this measurement hook there as well as on the source module.
            adapted.settle_actual.__globals__['measure_full_network']=measured
            with ExitStack() as stack:
                stack.enter_context(patch.object(thermal,'current_authority',cached))
                stack.enter_context(patch.object(measurement,'current_authority',cached))
                ref=reference(output.with_name(output.name+'_REFERENCE'),self.scenario,self.hardware['source_SHA'],self.arm,self._day)
                try:
                    stack.enter_context(patch.object(integration,'PhysicalScenario',adapted))
                    stack.enter_context(patch.object(timecontrol,'CommonClock',prefix_clock_class()))
                    stack.enter_context(patch.object(integration,'measure_full_network',measured))
                    stack.enter_context(physical_permit(self.arm,self._day,self.hardware['source_SHA'],self.scenario,
                        namespace='ACTUAL',design_receipt=record(HARDWARE/'HARDWARE.json')))
                    with integration.scenario_scope(self.scenario,output,source_SHA=self.hardware['source_SHA'],
                            arm=self.arm,day=self._day) as audit:
                        self._scenario_audit=audit;self._legacy_slot_key=None;self._legacy_cache_hit=False
                        from v42_regcontrol import authority
                        source=authority.source();original_branch=source['branch_measurement'];original_vector=source['voltage_vector']
                        def legacy_entry():
                            key=self._legacy_slot_key
                            if self._independent_fresh or key is None:return None
                            if key not in self._legacy_history:self._legacy_history[key]=dict(branches={},voltages={})
                            self._legacy_history.move_to_end(key)
                            while len(self._legacy_history)>120:self._legacy_history.popitem(last=False)
                            return self._legacy_history[key]
                        def branch(engine,item):
                            entry=legacy_entry();key=(item.branch_id,item.parent_bus,item.phase)
                            if entry is not None and self._legacy_cache_hit and key in entry['branches']:
                                self.performance['legacy_branch_measurement_reuses']+=1
                                return entry['branches'][key].copy()
                            value=np.asarray(original_branch(engine,item)).copy()
                            if entry is not None:entry['branches'][key]=value.copy()
                            return value
                        def vector(engine,nodes):
                            entry=legacy_entry();key=tuple(nodes)
                            if entry is not None and self._legacy_cache_hit and key in entry['voltages']:
                                return entry['voltages'][key].copy()
                            value=np.asarray(original_vector(engine,nodes)).copy()
                            if entry is not None:entry['voltages'][key]=value.copy()
                            return value
                        with patch.dict(source,branch_measurement=branch,voltage_vector=vector):
                            result=self._native_probe(self,rows)
                    isolated=independence(ref,audit,self.hardware['source_SHA'],self.scenario,self.arm,self._day)
                    if not isolated['PASS']:raise ValueError('SVR11_ACTUAL_FORECAST_SOURCE_INITIAL_ISOLATION_FAILED')
                    atomic(output/'INDEPENDENCE.json',isolated)
                    result.update(physical_audit=audit.receipt,independence=record(output/'INDEPENDENCE.json'))
                finally:
                    retire_completed_probe(ref.engine)
                    if getattr(self,'_scenario_audit',None):self._scenario_audit.sessions.clear()
                del ref
        from v42_svr11.context_lifecycle import flush_completed_probes
        flush_completed_probes()
        result.update(hardware=record(HARDWARE/'HARDWARE.json'),scenario_SHA=self.scenario['scenario_SHA'],
            Source_Initial_State_independent=True,Planning_tap_queue_transfer=0,Actual_future_data_used_in_Planning=0,
            prefix_slots=24,evaluation_slots=max(0,len(rows)-24),Native_TIME_queue_processed=True)
        if len(rows)>=25:
            a=result['physical_steps'][23]['native_state']
            next_state=result['physical_steps'][24]['before_state'];b=result['physical_steps'][24]['time_control']
            result['midnight_continuity']=dict(PASS=a==next_state and a['physical_seconds']==b['start_seconds']==21600,
                reset_at_midnight=False,queue_carried=a['queue'],evaluation_slot0_time=b['start_seconds'])
        return result

    def full_fresh_probe(self,rows):
        previous=self._independent_fresh;self._independent_fresh=True
        try:return self._probe(rows)
        finally:self._independent_fresh=previous

    def evaluate(self,*args,**kwargs):
        # Per-instance cache contains measurements only; hardware identity is
        # explicit and a 7-RegControl certificate cannot instantiate this class.
        receipt=self._candidate_evaluator(self,*args,**kwargs)
        receipt.update(scope='V44_SVR11_CAUSAL_NATIVE_TIME_PREFIX',delayed_TIME_actuation_certificate='NATIVE_EVENT_TRACE',
            Hardware_SHA=self.hardware['equipment_SHA'],source_revision='V44_SVR11_REVISION01')
        return receipt

    def certificates(self):return dict(hardware=record(HARDWARE/'HARDWARE.json'),performance=self.performance,
        native_state_cache=False,Planning_state_transfer=False)


def prefix_audit_class(original,total):
    """Reuse the existing audit with only horizon/count metadata generalized."""
    methods={}
    for name in ('settle_actual','persist','write_progress'):
        function=getattr(original,name);tree=ast.parse(textwrap.dedent(inspect.getsource(function)))
        class Axis(ast.NodeTransformer):
            def visit_Constant(self,node):
                if type(node.value) is int and node.value==96:node.value=total
                return node
        tree=Axis().visit(tree);ast.fix_missing_locations(tree)
        ns=dict(function.__globals__);exec(compile(tree,function.__code__.co_filename,'exec'),ns)
        methods[name]=ns[name]
    return type('V44IssuePrefixPhysicalScenario',(original,),methods)

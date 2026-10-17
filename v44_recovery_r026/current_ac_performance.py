"""Live readers plus exact historical audit reuse; every native solve remains.

Historical controls may reuse exact certificates between full live slot guards.
The current candidate and independent Fresh keep all live measurements.
"""
import ast
import hashlib
import pickle
from collections import OrderedDict
from contextvars import ContextVar
from functools import wraps
from contextlib import contextmanager, ExitStack
import inspect
import linecache
import textwrap
from unittest.mock import patch


_actual_request=ContextVar("R026_ACTUAL_STAGE_REQUEST",default=None)

def ordinal_reader(function, expected):
    body=textwrap.dedent(inspect.getsource(function));tree=ast.parse(body);changed=0
    class Ordinal(ast.NodeTransformer):
        def visit_DictComp(self,node):
            nonlocal changed
            node=self.generic_visit(node)
            if len(node.generators)!=1:return node
            g=node.generators[0]
            if (not isinstance(g.target,ast.Name) or not isinstance(node.key,ast.Name)
                    or node.key.id!=g.target.id or g.ifs or g.is_async):return node
            if not (isinstance(g.iter,ast.Call) and isinstance(g.iter.func,ast.Attribute)
                    and g.iter.func.attr=='AllPropertyNames' and not g.iter.args):return node
            if not (isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name)
                    and node.value.func.id=='str' and len(node.value.args)==1):return node
            call=node.value.args[0]
            if not (isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute)
                    and call.func.attr=='Value' and isinstance(call.func.value,ast.Attribute)
                    and call.func.value.attr=='Properties' and len(call.args)==1
                    and isinstance(call.args[0],ast.Name) and call.args[0].id==g.target.id):return node
            # Same engine and same live AllPropertyNames sequence, 1-based API.
            if ast.dump(call.func.value.value)!=ast.dump(g.iter.func.value.value):
                raise ValueError('PROPERTY_ENGINE_AXIS_DRIFT')
            g.target=ast.Tuple(elts=[ast.Name(id='_r026_property_index',ctx=ast.Store()),g.target],ctx=ast.Store())
            g.iter=ast.Call(func=ast.Name(id='enumerate',ctx=ast.Load()),args=[g.iter,ast.Constant(1)],keywords=[])
            call.args=[ast.Name(id='_r026_property_index',ctx=ast.Load())];changed+=1
            return node
    tree=Ordinal().visit(tree);ast.fix_missing_locations(tree)
    if changed!=expected:raise ValueError('ORDINAL_PROPERTY_SOURCE_SHAPE_DRIFT:'+str(changed))
    source=ast.unparse(tree)+'\n';filename=str(__file__)+'.'+function.__name__+'.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__);exec(compile(source,filename,'exec'),ns)
    return ns[function.__name__]


def live_properties(engine,schema=None):
    """Read all strings live via the pinned C-API; free each owned result."""
    props=engine.Properties
    # Public ordinal fallback supports independent test doubles/older bindings.
    if not hasattr(props,'_lib') or not hasattr(props._lib,'Obj_GetAsString'):
        names=engine.CktElement.AllPropertyNames()
        return {name:str(props.Value(i)) for i,name in enumerate(names,1)}
    lib=props._lib;obj=lib.CktElement_Get_Pointer()
    if obj==props._api_util.ffi.NULL:raise ValueError('R026_ACTIVE_PROPERTY_OBJECT_REQUIRED')
    names=schema.names(engine,obj) if schema is not None else engine.CktElement.AllPropertyNames()
    values={}
    for i,name in enumerate(names,1):
        raw=lib.Obj_GetAsString(obj,i)
        try:
            props._check_for_error()
            values[name]=str(props._get_string(raw))
        finally:
            lib.DSS_Dispose_String(raw)
    # Match the original reader's final active property selector, too.
    if names:lib.DSSProperty_Set_Index(len(names)-1);props._check_for_error()
    return values


def direct_reader(function,expected,reader=None):
    indexed=ordinal_reader(function,expected)
    tree=ast.parse(inspect.getsource(indexed));changed=0
    class Direct(ast.NodeTransformer):
        def visit_DictComp(self,node):
            nonlocal changed
            if (len(node.generators)==1 and isinstance(node.generators[0].target,ast.Tuple)
                    and isinstance(node.generators[0].target.elts[0],ast.Name)
                    and node.generators[0].target.elts[0].id=='_r026_property_index'):
                engine=node.value.args[0].func.value.value;changed+=1
                return ast.Call(func=ast.Name(id='_r026_live_properties',ctx=ast.Load()),args=[engine],keywords=[])
            return self.generic_visit(node)
    tree=Direct().visit(tree);ast.fix_missing_locations(tree)
    if changed!=expected:raise ValueError('DIRECT_READ_BOUNDARY_DRIFT')
    source=ast.unparse(tree)+'\n';filename=str(__file__)+'.direct.'+function.__name__+'.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r026_live_properties=reader or live_properties)
    exec(compile(source,filename,'exec'),ns);return ns[function.__name__]


def expected_reference(original):
    # _ratings changes only the top-level buses list for the declared series cut.
    # Nested ratings/windings are still compared against every fresh live read.
    return dict(original,buses=original['buses'].copy())


def ratings_reader(function):
    source=textwrap.dedent(inspect.getsource(function))
    old='reference=json.loads(canonical(original))'
    if source.count(old)!=1:raise ValueError('EXPECTED_RATINGS_COPY_BOUNDARY_DRIFT')
    source=source.replace(old,'reference=_r026_expected_reference(original)')
    filename=str(__file__)+'.ratings.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r026_expected_reference=expected_reference)
    exec(compile(source,filename,'exec'),ns);return ns[function.__name__]


class ExactAuditEncoding:
    """Memoize only byte-identical JSON row encoding, never physics/verdicts."""
    def __init__(self,max_bytes=128*1024*1024):
        self.cache=OrderedDict();self.bytes=0;self.max_bytes=max_bytes;self.hits=0;self.misses=0
    def encoded(self,row,canonical):
        key=hashlib.sha256(pickle.dumps(row,protocol=5)).digest()
        if key in self.cache:
            value,size=self.cache[key];self.cache.move_to_end(key);self.hits+=1
        else:
            value=canonical(row);size=len(value.encode('utf-8'));self.misses+=1
            if size<=self.max_bytes:
                self.cache[key]=(value,size);self.bytes+=size
                while self.bytes>self.max_bytes:
                    _,(_,removed)=self.cache.popitem(last=False);self.bytes-=removed
        return value
    def canonical_list(self,rows,canonical):
        if not isinstance(rows,list):raise TypeError('R026_AUDIT_LIST_REQUIRED')
        encoded=[]
        for row in rows:
            if isinstance(row,dict) and 'frozen_trajectory_SHA' in row and all(isinstance(k,str) for k in row):
                # The global trajectory SHA changes for a new current candidate;
                # its unchanged historical physical fields can still encode exactly.
                encoded.append('{'+','.join(canonical(k)+':'+(self.encoded(v,canonical) if isinstance(v,(dict,list)) else canonical(v)) for k,v in sorted(row.items()))+'}')
            else:encoded.append(self.encoded(row,canonical))
        return '['+','.join(encoded)+']'


def audit_writer(function,encoding):
    source=textwrap.dedent(inspect.getsource(function))
    for old in ['canonical(self.rows)','canonical(self.events)']:
        if source.count(old)!=1:raise ValueError('EXACT_RAW_ENCODER_BOUNDARY_DRIFT')
        source=source.replace(old,'_r026_encode('+old[len('canonical('):-1]+')')
    filename=str(__file__)+'.persist.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r026_encode=lambda rows:encoding.canonical_list(rows,function.__globals__['canonical']))
    exec(compile(source,filename,'exec'),ns);return ns[function.__name__]


def state_inventory(engine):
    """Only the two live fields consumed by _state; not an inventory guard."""
    if any(n.lower()!='none' for n in engine.CapControls.AllNames()):
        from v42_regcontrol import authority
        return authority.source()['inventory'](engine)
    regs=[];caps=[]
    for name in engine.RegControls.AllNames():
        if name.lower()=='none':continue
        engine.RegControls.Name(name)
        transformer=str(engine.RegControls.Transformer());winding=int(engine.RegControls.Winding())
        engine.Circuit.SetActiveElement('RegControl.'+name)
        engine.Transformers.Name(transformer);engine.Transformers.Wdg(winding)
        regs.append(dict(initial_tap=float(engine.Transformers.Tap())))
    for name in engine.Capacitors.AllNames():
        if name.lower()=='none':continue
        engine.Capacitors.Name(name);engine.Circuit.SetActiveElement('Capacitor.'+name)
        caps.append(dict(states=list(map(int,engine.Capacitors.States()))))
    return dict(regulators=regs,capacitors=caps)


def state_reader(function):
    source=textwrap.dedent(inspect.getsource(function));old="inv=authority.source()['inventory'](e)"
    if source.count(old)!=1:raise ValueError('EXACT_STATE_FIELD_READ_BOUNDARY_DRIFT')
    source=source.replace(old,'inv=_r026_state_inventory(e)')
    filename=str(__file__)+'.state.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r026_state_inventory=state_inventory)
    exec(compile(source,filename,'exec'),ns);return ns[function.__name__]


def bank_reader(function,oracle):
    from copy import deepcopy
    if getattr(oracle,'arm',None)=='B1':
        from .physical_copy import clone_physical as deepcopy
    elif getattr(oracle,'arm',None)=='B3':
        from .b3_copy import clone_physical as deepcopy
    import numpy as np
    prior=None
    def measured(bank):
        nonlocal prior
        audit=getattr(oracle,'_scenario_audit',None)
        if bank is not getattr(oracle,'_bank',None) or audit is None:return function(bank)
        engine=bank.engine
        def stamp():
            from v42_voltage_control.integration import _physical_inputs
            return (oracle._state(engine),np.asarray(engine.Circuit.AllBusVolts()).tobytes(),deepcopy(_physical_inputs(engine)))
        before=stamp();slot=len(audit.rows)
        # Only the original immediate second read after settle_actual appended
        # this exact slot, with no solve, TIME/input/tap/queue/voltage change.
        if prior is not None and slot==prior[0]+1 and before==prior[1]:
            oracle._r026_duplicate_bank_reuses=getattr(oracle,'_r026_duplicate_bank_reuses',0)+1
            return deepcopy(prior[2])
        value=function(bank);prior=(slot,stamp(),deepcopy(value));return value
    return measured


@contextmanager
def live_read_scope(encoding=None,oracle=None):
    from v44.svr12 import scope
    from v44.svr11_ac import SVR11CurrentAC
    import v44.svr11_ac as ac
    from .physical_copy import clone_physical
    with scope():
        from v42_regcontrol import authority
        import v42_voltage_control.svr as svr
        import v42_voltage_control.integration as integration
        source=authority.source();inventory=source['inventory'];properties=svr._properties
        encoding=encoding or ExactAuditEncoding()
        from .property_metadata import PropertySchema,equipment_reader
        from .class_metadata import ClassPropertySchema
        schema=PropertySchema() if getattr(oracle,'arm',None)=='B1' else (ClassPropertySchema() if getattr(oracle,'arm',None)=='B3' else None)
        reader=lambda engine:live_properties(engine,schema)
        with ExitStack() as stack:
            stack.enter_context(patch.object(integration,'_equipment',equipment_reader(integration._equipment)))
            if oracle is not None and getattr(oracle,'arm',None)=='B1':
                stack.enter_context(patch.object(ac,'deepcopy',clone_physical))
            elif oracle is not None and getattr(oracle,'arm',None)=='B3':
                from .b3_copy import clone_physical as b3_clone
                stack.enter_context(patch.object(ac,'deepcopy',b3_clone))
            stack.enter_context(patch.dict(source,inventory=direct_reader(inventory,2,reader)))
            stack.enter_context(patch.object(svr,'_properties',direct_reader(properties,1,reader)))
            stack.enter_context(patch.object(SVR11CurrentAC,'_state',state_reader(SVR11CurrentAC._state)))
            stack.enter_context(patch.object(integration.PhysicalScenario,'_ratings',ratings_reader(integration.PhysicalScenario._ratings)))
            stack.enter_context(patch.object(integration.PhysicalScenario,'persist',audit_writer(integration.PhysicalScenario.persist,encoding)))
            if oracle is not None:
                stack.enter_context(patch.object(svr.SeriesSVRCollection,'measure',bank_reader(svr.SeriesSVRCollection.measure,oracle)))
            try:yield schema
            finally:
                if oracle is not None and schema is not None:
                    oracle._r026_schema_name_reads=getattr(oracle,'_r026_schema_name_reads',0)+schema.reads
                    oracle._r026_schema_metadata_hits=getattr(oracle,'_r026_schema_metadata_hits',0)+schema.hits


def require_policy(oracle):
    from v44.execution import assert_current
    from v44.common import read
    context=assert_current();case=context['request'];request=_actual_request.get()
    if (request is None or request.get('stage')!='ACTUAL'
            or any(request.get(k)!=case.get(k) for k in ('case_root','arm','day','source_sha'))):
        raise PermissionError('R026_EXACT_ACTUAL_STAGE_AND_CASE_REQUIRED')
    overlay=read(request['execution_permit']['path'])['autonomous_recovery_overlay']
    if (overlay.get('policy')!='V44_AUTONOMOUS_RECOVERY_R026'
            or overlay.get('Current_AC_performance')!='EXACT_PREFIX_HISTORY_AUDIT_REUSE_WITH_LIVE_BOUNDARIES_AND_IMMUTABLE_PHYSICS'
            or overlay.get('Historical_audit_guard')!='FIRST_AND_FINAL_FULL_LIVE_CONTROLS_RATINGS_AND_EXACT_NATIVE_STAMP'
            or request.get('stage')!='ACTUAL' or request['arm']!=oracle.arm):
        raise PermissionError('R026_LIVE_ACTUAL_PERFORMANCE_PERMIT_REQUIRED')
    if request['arm'] not in ('B0','B1','B3'):return False
    if (request['day']=='2025-05-01' and request['arm']=='B1'
            and __import__('pathlib').Path(request['case_root']).name=='attempt002'):
        raise PermissionError('USER_PROTECTED_MAY01_B1_MUST_KEEP_ORIGINAL_EXECUTION')
    return True


@contextmanager
def current_probe_scope(oracle,rows,encoding):
    if getattr(oracle,'_independent_fresh',False):
        raise PermissionError('R026_CURRENT_SCOPE_CANNOT_WRAP_FRESH')
    from .history import scope as history_scope
    with live_read_scope(encoding,oracle):
        with history_scope(oracle,rows) as stats:yield stats


@contextmanager
def install():
    from v44.svr12 import SVR12CurrentAC
    from v44.common import atomic,now,record
    from v44.execution import assert_current
    from pathlib import Path
    from v44 import worker
    original=SVR12CurrentAC._probe;original_actual=worker.actual;calls=0
    @wraps(original_actual)
    def actual(request,*args,**kwargs):
        token=_actual_request.set(request)
        try:return original_actual(request,*args,**kwargs)
        finally:_actual_request.reset(token)
    def probe(oracle,rows):
        nonlocal calls
        if not require_policy(oracle):return original(oracle,rows)
        if getattr(oracle,'_independent_fresh',False):
            from .fresh_performance import live_fresh_scope
            with live_fresh_scope(oracle):return original(oracle,rows)
        calls+=1
        if not hasattr(oracle,'_r026_encoding'):oracle._r026_encoding=ExactAuditEncoding()
        with current_probe_scope(oracle,rows,oracle._r026_encoding) as stats:answer=original(oracle,rows)
        totals=getattr(oracle,'_r026_history_totals',{})
        for key,value in stats.items():totals[key]=totals.get(key,0)+value
        oracle._r026_history_totals=totals
        proofs=oracle._prefix_history_proofs
        case=Path(_actual_request.get()['case_root'])
        atomic(case/'CURRENT_AC_R026_PERFORMANCE.json',dict(UTC=now(),adapter=record(__file__),
            complete_probe_calls=calls,arm=oracle.arm,
            live_property_getters='CURRENT_ALL_LIVE_HISTORY_FULL_SLOT_BOUNDARIES_WITH_EXACT_INTERMEDIATE_CERTIFICATES',
            history_last_probe=stats,history_oracle_totals=totals,
            history_certificate_cache=dict(slots=len(proofs.slots),bytes=proofs.bytes,hits=proofs.hits,
                misses=proofs.misses,evictions=proofs.evictions),
            native_state_snapshot_restored=False,skipped_current_or_history_solves=0,Raw_persistence_unchanged=True,
            exact_JSON_row_encoding_hits=oracle._r026_encoding.hits,exact_JSON_row_encoding_misses=oracle._r026_encoding.misses,
            encoding_cache_bytes=oracle._r026_encoding.bytes,
            same_state_second_SVR_measurement_reuses=getattr(oracle,'_r026_duplicate_bank_reuses',0),
            live_schema_name_reads=getattr(oracle,'_r026_schema_name_reads',0),
            immutable_object_schema_reuses=getattr(oracle,'_r026_schema_metadata_hits',0),
            Independent_Fresh_measurements_unchanged=True))
        return answer
    with patch.object(SVR12CurrentAC,'_probe',probe),patch.object(worker,'actual',actual):yield

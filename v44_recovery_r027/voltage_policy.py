"""A2-only voltage authority and explicit conditional recovery certificates."""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from types import FunctionType
from unittest.mock import patch
import inspect, textwrap, linecache, math
import numpy as np
from v44.common import read, record, verify, atomic, digest, now

ACTIVE = ContextVar('R027_A2_VOLTAGE_POLICY', default=None)
STRICT = (.95, 1.05)
RELAXED = (.945, 1.055)
SQUARED = (.893025, 1.113025)
POLICY = 'V44_R027_CONDITIONAL_SELECTIVE_A2_HALF_RELAXATION_RECOVER_M2_STRICT_V1'


def authority():
    return dict(policy=POLICY, stage='A2', lower_pu=.945, upper_pu=1.055,
        lower_squared=.893025, upper_squared=1.113025, maximum_relaxation_pu=.005,
        original_lower_pu=.95, original_upper_pu=1.05, initial_voltage_band=[.95,1.05],
        scope='ONLY_TRIGGER_VERIFIED_VIOLATED_NODE_PHASE_SLOT_DIRECTION',all_nodes_phases_slots=False,
        full_eligible_class_pricing_minimum=1,recent_actual_column_activations=2,
        each_full_Phi_relative_decrease_strictly_below=.05,minimum_voltage_artificial_fraction=.95,
        P1_objective_changed=False, non_voltage_constraints_changed=False,
        M2_lower_pu=.95, M2_upper_pu=1.05, Actual_Fresh_lower_pu=.95, Actual_Fresh_upper_pu=1.05,
        M2_voltage_recovery_failure_alone_is_case_failure=False,
        M2_nonvoltage_certified_operating_plan_may_enter_Actual_Fresh=True,
        final_PASS_requires_original_Actual_Fresh_physical_checks=True)


def audit(coefficients, controls, nodes, *, band=STRICT,controller=None):
    violations=[]; low=math.inf; high=-math.inf; max_excess=0.; relaxed_excess=0.; count=0
    if len(coefficients)!=len(controls) or len(coefficients)!=96:raise ValueError('R027_VOLTAGE_96_SLOTS_REQUIRED')
    for t,(c,x) in enumerate(zip(coefficients,controls)):
        squared=np.asarray(c.voltage_constant+c.voltage_matrix.T@np.asarray(x,float),float)
        if len(squared)!=len(nodes) or not np.isfinite(squared).all() or np.any(squared<0):raise ValueError('R027_FINITE_VOLTAGE_NODE_AXIS')
        pu=np.sqrt(squared);low=min(low,float(pu.min()));high=max(high,float(pu.max()));count+=len(pu)
        if controller is None:lower=np.full(len(pu),band[0]);upper=np.full(len(pu),band[1])
        else:
            lower_squared,upper_squared=controller.bounds(t,len(pu));lower=np.sqrt(lower_squared);upper=np.sqrt(upper_squared)
        relaxed_excess=max(relaxed_excess,float(np.max(lower-pu)),float(np.max(pu-upper)))
        for n in np.flatnonzero((pu<STRICT[0]-1e-10)|(pu>STRICT[1]+1e-10)):
            name=str(nodes[n]);excess=max(0.,STRICT[0]-float(pu[n]),float(pu[n])-STRICT[1]);max_excess=max(max_excess,excess)
            violations.append(dict(node=name,phase=name.rsplit('.',1)[-1],slot=t,issue_slot=t+24,
                voltage_pu=float(pu[n]),voltage_squared_pu=float(squared[n]),strict_deviation_pu=excess))
    return dict(PASS=relaxed_excess<=1e-10, voltage_kind='ORIGINAL_PLANNING_AFFINE_SQUARED_VOLTAGE_NOT_ACTUAL_AC',
        original_criteria=dict(lower_pu=.95,upper_pu=1.05,min_voltage_pu=low,max_voltage_pu=high,PASS=not violations),
        relaxed_criteria=dict(lower_pu_minimum=.945 if controller and controller.mask else band[0],
            upper_pu_maximum=1.055 if controller and controller.mask else band[1],
            only_approved_rows_relaxed=True,min_voltage_pu=low,max_voltage_pu=high,PASS=relaxed_excess<=1e-10),
        strict_PASS=not violations, min_voltage_pu=low,max_voltage_pu=high,
        maximum_strict_deviation_pu=max_excess,violation_node_phase_slot_count=len(violations),violations=violations,
        maximum_allowed_relaxation_pu=.005 if controller and controller.mask else 0., maximum_band_excess_pu=max(0.,relaxed_excess),
        evaluated_node_phase_slots=count,physical_slots=96,comparison_roundoff_pu=1e-10,
        voltage_relaxation_is_measured_not_added_to_P1_objective=True,
        conditional_policy_execution=controller.report() if controller else None)


def strict_authority_required():
    from v42_native.voltage import voltage_for,Stage
    if ACTIVE.get() is not None:raise PermissionError('R027_A2_SCOPE_LEAKED_INTO_M2_OR_ACTUAL')
    for stage in (Stage.A1,Stage.M1,Stage.M2,Stage.ACTUAL):
        v=voltage_for(stage)
        if (v.lower_pu,v.upper_pu)!=STRICT:raise PermissionError('R027_STRICT_DOWNSTREAM_VOLTAGE_REQUIRED')


@contextmanager
def a2_voltage_scope(request):
    from v42_native import voltage
    import v42_exact.validation as validation
    from v42_integrated import contract
    from .conditional_voltage import ConditionalVoltage
    if (request.get('arm'),request.get('stage'))!=('B3','A2'):raise PermissionError('R027_A2_ONLY_AUTHORITY')
    before=dict(voltage._MAPPING);controller=ConditionalVoltage(request)
    def routed(function,replacements):
        source=textwrap.dedent(inspect.getsource(function))
        for old,new in replacements:
            if source.count(old)!=1:raise ValueError('R027_SELECTIVE_VALIDATOR_SOURCE_DRIFT:'+old)
            source=source.replace(old,new)
        ns=dict(function.__globals__,_r027_bounds=controller.bounds)
        filename=__file__+'.'+function.__name__+'.generated'
        linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
        exec(compile(source,filename,'exec'),ns);return ns[function.__name__]
    grid_audit=routed(contract.grid_audit,[('for c,x in zip(coefficients,controls):','for _r027_slot,(c,x) in enumerate(zip(coefficients,controls)):'),
        ('0.95**2-v','_r027_bounds(_r027_slot,len(v))[0]-v'),('v-1.05**2','v-_r027_bounds(_r027_slot,len(v))[1]')])
    check=routed(validation.check,[('for c,x in zip(coeff,controls):','for _r027_slot,(c,x) in enumerate(zip(coeff,controls)):'),
        ('voltage.lower_squared-volt','_r027_bounds(_r027_slot,len(volt))[0]-volt'),
        ('volt-voltage.upper_squared','volt-_r027_bounds(_r027_slot,len(volt))[1]')])
    token=ACTIVE.set(controller)
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(validation,'check',check))
            stack.enter_context(patch.object(contract,'grid_audit',grid_audit))
            yield controller
    finally:
        ACTIVE.reset(token)
        if voltage._MAPPING!=before:raise PermissionError('R027_GLOBAL_VOLTAGE_MAPPING_CHANGED')


def finalize(result,request):
    if 'PHASE_I_NATIVE_1500_LIMIT_REACHED' in result.get('error',''):
        result.update(PASS=False,FULL_feasible=False,status='FAILED',classification='PHASE_I_NATIVE_1500_LIMIT_REACHED',
            Phase_I_native_limit=1500,fail_date_arm=True,continue_next_comparison=True)
        return result
    if request.get('stage')!='A2' or result.get('PASS') is not True:return result
    physical=read(result['incumbent']['physical']['path']);report=physical['A2_voltage_policy_report']
    if not physical['PASS'] or not report['PASS']:raise ValueError('R027_RELAXED_FULL_PHYSICAL_REQUIRED')
    output=Path(request['output'])
    refs={key:record(output/name) for key,name in dict(zero='PHASE_I_ZERO_CERTIFICATE.json',
        P1='P1_RESULT.json',pricing='COMPLETE_PRICING_CLOSURE.json',bound='P1_FULL_DOMAIN_BOUND_CERTIFICATE.json',
        types='ORIGINAL_INTEGER_TYPE_RESTORATION.json',acceptance='P1_ONLY_ACCEPTANCE_CONTRACT.json').items()}
    for key in ('zero','P1','pricing','bound','acceptance','types'):
        if read(refs[key]['path']).get('PASS') is not True:raise ValueError('R027_ALL_A2_CERTIFICATES_REQUIRED:'+key)
    if not physical.get('original_integer_types_restored') or not physical.get('original_job_population_verified'):
        raise ValueError('R027_ORIGINAL_INTEGER_PHYSICAL_REQUIRED')
    if not 0<=result['certified_gap']<=.005:raise ValueError('R027_ORIGINAL_HALF_PERCENT_GAP_REQUIRED')
    execution=report['conditional_policy_execution'];relaxed=bool(execution['approved_rows'])
    strict=bool(report['strict_PASS'] and not relaxed);status='A2_STRICT_PASS' if strict else 'A2_VOLTAGE_RECOVERY_PENDING'
    core_freeze=result['freeze'];frozen=read(core_freeze['path'])
    frozen.update(PASS=strict,accepted=strict,state=status,status=status,A2_STRICT_PASS=strict,
        A2_P1_ONLY_ACCEPTED=strict,relaxed_model_P1_accepted=True,voltage_policy=authority(),
        original_relaxed_model_core_freeze=core_freeze,M2_voltage_recovery_required=not strict)
    frozen_path=output/'A2_POLICY_FROZEN_WORKLOAD.json';atomic(frozen_path,frozen);result['freeze']=record(frozen_path)
    refs.update(physical=result['incumbent']['physical'],point=result['incumbent']['point'],freeze=result['freeze'],
        planning=result['planning'],model_policy=record(output/'A2_MODEL_VOLTAGE_POLICY.json'))
    certificate=dict(UTC=now(),PASS=True,day=request['day'],arm='B3',stage='A2',source_sha=request['source_sha'],
        status=status,policy=authority(),policy_sha=digest(authority()),relaxed_model_FULL_PASS=True,
        A2_STRICT_PASS=strict, M2_voltage_recovery_required=not strict,
        voltage_report=report,certified_gap=result['certified_gap'],certificates=refs,
        LB_scope='A2_SELECTIVE_CONDITIONALLY_RELAXED_COMPLETE_P1_DOMAIN' if relaxed else 'A2_STRICT_COMPLETE_P1_DOMAIN',
        strict_model_FULL_PASS=strict,artificial_free=True,P2_calls=0)
    path=output/'A2_VOLTAGE_POLICY_CERTIFICATE.json';atomic(path,certificate)
    result.update(PASS=strict,FULL_feasible=strict,classification=status,status=status,A2_STRICT_PASS=strict,
        relaxed_model_PASS=True,relaxed_FULL_feasible=True,voltage_policy_certificate=record(path),
        M2_voltage_recovery_required=not strict,independent_Global_LB_validated=True,
        A2_model_scope='A2_CONDITIONAL_SELECTED_ROWS_ONLY',voltage_policy=authority(),voltage_report=report)
    atomic(output/'A_RESULT.json',result)
    return result


def require_conditional(result,day):
    from v44.stages import require_parent
    require_parent(result,day=day,arm='B3',stage='A2')
    if (result.get('status')!='A2_VOLTAGE_RECOVERY_PENDING' or result.get('PASS') is not False
        or result.get('A2_STRICT_PASS') is not False or result.get('FULL_feasible') is not False
        or result.get('relaxed_model_PASS') is not True or result.get('relaxed_FULL_feasible') is not True
        or result.get('independent_Global_LB_validated') is not True or result.get('P2_calls')!=0):raise ValueError('R027_EXPLICIT_CONDITIONAL_A2_REQUIRED')
    receipt=result.get('voltage_policy_certificate');verify([receipt]);c=read(receipt['path'])
    if (not c.get('PASS') or c.get('policy')!=authority() or c.get('policy_sha')!=digest(authority())
        or c.get('source_sha')!=result.get('source_sha') or c.get('day')!=day
        or c.get('A2_STRICT_PASS') is not False or not c.get('relaxed_model_FULL_PASS')
        or not c.get('artificial_free') or c.get('P2_calls')!=0 or not 0<=c.get('certified_gap',1)<=.005
        or c['certified_gap']!=result.get('certified_gap')):
        raise ValueError('R027_CONDITIONAL_CERTIFICATE_BINDING')
    verify(list(c['certificates'].values()))
    for key in ('zero','P1','pricing','bound','acceptance','physical','types','model_policy'):
        if read(c['certificates'][key]['path']).get('PASS') is not True:raise ValueError('R027_CONDITIONAL_CERTIFICATE_FAILED:'+key)
    if not c['voltage_report']['PASS'] or c['voltage_report']['maximum_strict_deviation_pu']>.0050000001:
        raise ValueError('R027_VOLTAGE_RELAXATION_CAP')
    from .conditional_voltage import validate_execution
    validate_execution(c['voltage_report']['conditional_policy_execution'])
    binding=result.get('conditional_aidc_binding')
    if 'aidc_anchor' in result and not binding:raise ValueError('R027_FROZEN_AIDC_BINDING_REQUIRED')
    if binding:
        verify([binding]);b=read(binding['path']);verify([b['physical'],b['certificate'],b['parent_acceptance']])
        if (b['aidc_anchor']!=result['aidc_anchor'] or b['certificate']!=receipt or b['day']!=day
            or b['source_sha']!=result['source_sha']):raise ValueError('R027_FROZEN_AIDC_BINDING_DRIFT')
    return result


def require_handoff(result,day):
    if result.get('status')=='A2_VOLTAGE_RECOVERY_PENDING':return require_conditional(result,day)
    from v44.stages import require_a2
    return require_a2(result,day)


def can_export(result):
    if result.get('status')=='A2_VOLTAGE_RECOVERY_PENDING':
        require_conditional(result,result['day']);return True
    return result.get('PASS') is True


def export_function(original):
    source=textwrap.dedent(inspect.getsource(original))
    old="    if result.get('PASS') is not True or not 0<=result.get('certified_gap',1)<=.005:raise ValueError('INDEPENDENT_A_ACCEPTANCE_REQUIRED')"
    if source.count(old)!=1:raise ValueError('R027_EXPORT_GATE_SOURCE_DRIFT')
    source=source.replace(old,"    _r027_export_gate(result,request,stage)")
    old="    atomic(folder/'AIDC_REFERENCE.json',dict(identity=identity,**aidc));return folder"
    assert source.count(old)==1
    source=source.replace(old,"    identity=_r027_identity(identity,result,folder)\n"+old)
    def gate(result,request,stage):
        if stage=='A2':require_handoff(result,request['day'])
        elif result.get('PASS') is not True or not 0<=result.get('certified_gap',1)<=.005:raise ValueError('INDEPENDENT_A_ACCEPTANCE_REQUIRED')
    def identity(i,r,folder):
        if i['stage']!='A2' or not r.get('voltage_policy_certificate'):return i
        fields=('PASS','FULL_feasible','status','A2_STRICT_PASS','relaxed_model_PASS','relaxed_FULL_feasible',
                'voltage_policy_certificate','M2_voltage_recovery_required','A2_model_scope')
        i.update({k:r[k] for k in fields})
        path=Path(folder)/'A2_CONDITIONAL_AIDC_BINDING.json'
        atomic(path,dict(PASS=True,day=i['day'],source_sha=i['source_sha'],aidc_anchor=i['aidc_anchor'],
            physical=i['physical'],certificate=r['voltage_policy_certificate'],parent_acceptance=i['parent_acceptance']))
        i['conditional_aidc_binding']=record(path);return i
    ns=dict(original.__globals__,_r027_export_gate=gate,_r027_identity=identity)
    exec(compile(source,__file__+'.export.generated','exec'),ns)
    return ns[original.__name__]


@contextmanager
def install():
    from v44 import worker,a2,runtime
    from v44 import daily
    from v44.checkpoints import seal_stage
    original_scope=a2.scope;original_a=inspect.unwrap(worker.a_stage);original_runtime=runtime.build
    @contextmanager
    def scope(request,m1):
        with a2_voltage_scope(request) as controller,original_scope(request,m1) as run:
            ns=dict(run.__globals__);physical=ns['_physical']
            def wrap_physical(*args,**kwargs):
                Physical,power=physical(*args,**kwargs);old=Physical.verify
                def check(self,x):
                    result=old(self,x)
                    result['A2_voltage_policy_report']=audit(self.coeff,result['controls'],self.state['atlas']['node_names'],controller=controller)
                    result['PASS']=result['PASS'] and result['A2_voltage_policy_report']['PASS']
                    return result
                Physical.verify=check;return Physical,power
            ns['_physical']=wrap_physical
            prepare=ns['prepare']
            def fresh(current,progress=None):
                state=prepare(current,progress)
                controller.bind(state)
                from .model_difference import verify_state_policy
                verify_state_policy(state,Path(current['output']),controller=controller)
                return state
            ns['prepare']=fresh
            adapted=FunctionType(run.__code__,ns,run.__name__,run.__defaults__,run.__closure__)
            adapted.__kwdefaults__=run.__kwdefaults__
            yield adapted
    # Retain the complete original worker, replacing only the explicit A2 acceptance/export gate.
    source=textwrap.dedent(inspect.getsource(original_a))
    source=source.replace('@stage_scope\n','')
    old="        atomic(root/'RESULT.json',result)\n        if result.get('PASS'):"
    if source.count(old)!=1:raise ValueError('R027_WORKER_RESULT_BOUNDARY_DRIFT')
    source=source.replace(old,"        result=_r027_finalize(result,request)\n        atomic(root/'RESULT.json',result)\n        if _r027_can_export(result):")
    ns=dict(original_a.__globals__,_r027_finalize=finalize,_r027_can_export=can_export,export_a=export_function(daily.export_a))
    exec(compile(source,__file__+'.worker.generated','exec'),ns)
    # Original outer wrappers (thread placement / rebuild / costs) call this new worker body.
    from v44.planning import stage_scope
    new_a=stage_scope(ns['a_stage'])
    runtime_source=textwrap.dedent(inspect.getsource(original_runtime))
    old="        require_a2(i,request['day'])"
    assert runtime_source.count(old)==1
    runtime_source=runtime_source.replace(old,"        _r027_handoff(i,request['day'])\n        _r027_strict()")
    runtime_ns=dict(original_runtime.__globals__,_r027_handoff=require_handoff,_r027_strict=strict_authority_required)
    exec(compile(runtime_source,__file__+'.runtime.generated','exec'),runtime_ns)
    with patch.object(a2,'scope',scope),patch.object(worker,'a_stage',new_a),patch.object(runtime,'build',runtime_ns['build']):
        yield

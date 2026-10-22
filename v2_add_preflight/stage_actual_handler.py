"""Same-date production Actual IO; original r043 controller and policy.

Import/prepare constructs no event run and grants no campaign approval.
Production numerical security and Job outcomes are evaluated only after the
real accepted A/M stages; a finite preparation fixture is never their result.
"""
from contextlib import contextmanager
import ast,copy,inspect,textwrap,types
from unittest.mock import patch
import numpy as np
from .stage_common import *
from v42_native.contracts import digest
from .stage_a_canary import Coefficients
from .stage_policy_grid import GridPacket
from .stage_actual import CurrentAC,controller_type


def zero_mess():
    services=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)]
    plan=dict(P_by_site={s:[0.]*96 for s in services},Q_by_site={s:[0.]*96 for s in services},
        units=8,initial_sites=INITIAL,authority='B0_B1_FIXED_ZERO_MESS',
        time_axis=list(range(96)),P_sign='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch')
    plan['plan_sha']=digest(plan);return plan


def binding(arm,folder,mess=None,*,fixture=False):
    from v44 import daily
    from v43_actual.vendor.policy import digest as source_digest
    if arm not in ('B0','B1','B2','B3'):raise ValueError('ORIGINAL_ARM_REQUIRED')
    if arm in ('B0','B1') and mess is not None:raise ValueError('ZERO_MESS_ARM')
    if arm in ('B2','B3') and mess is None:raise ValueError('CURRENT_FULL_MESS_REQUIRED')
    day=day_inputs();payload,doc=daily.load_aidc(folder,day['day']);identity=doc['identity']
    if any(identity[k]['sha256']!=day['files'][key]['sha256'] for k,key in (('input','native'),('windows','windows'))):
        raise ValueError('ACTUAL_SOURCE_INPUT_OR_WINDOWS_DRIFT')
    if not fixture and arm in ('B1','B3'):
        if (identity.get('FULL_feasible') is not True or identity.get('independent_Global_LB_validated') is not True
                or not 0<=identity.get('certified_gap',1)<=.005):raise ValueError('ACCEPTED_FULL_AIDC_REQUIRED')
    if digest({k:v for k,v in doc.items() if k not in ('identity','aidc_anchor')})!=identity['aidc_anchor']:
        raise ValueError('ACTUAL_AIDC_ANCHOR_DRIFT')
    if mess is not None:
        if (set(mess.get('P_kW',{}))!=set(INITIAL) or set(mess.get('Q_kvar',{}))!=set(INITIAL)
                or source_digest({k:v for k,v in mess.items() if k!='plan_sha'})!=mess['plan_sha']
                or mess['initial_sites']!=INITIAL or mess['time_axis']!=list(range(96))
                or mess['P_sign']!='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch'):
            raise ValueError('MESS8_PLAN_IDENTITY_DRIFT')
    base=object.__new__(daily.ActualBinding)
    base.day=day['day'];base.row=day;base.arm=arm;base.mess=mess;base.folder=Path(folder)
    base.arrays=payload['planning'];base.aidc=doc;base.anchor=identity['aidc_anchor']
    base.aidc['aidc_anchor']=base.anchor;base.freeze=record(base.folder/'AIDC_REFERENCE.json');base.bundle=Path(day['actual_bundle'])
    if arm in ('B1','B3'):
        fn=types.FunctionType(daily.corrective_binding.__code__,dict(daily.corrective_binding.__globals__,
            ActualBinding=lambda *a,**kw:base),argdefs=daily.corrective_binding.__defaults__)
        answer=fn(arm,folder,mess,day['day'])
    else:answer=base
    answer.build=types.MethodType(build,base)
    return answer


def build(self,args,case,output):
    """Reuse original CC4/TrackingReference materialization; replace grid IO."""
    from v43_arms.actual import ArmBinding
    from v44.daily import accepted
    from v42_pr134_b1 import native
    from v42_native import voltage
    source_bind=native.bind;coeff=Coefficients()
    def bind(*a,**kw):
        fn=types.FunctionType(source_bind.__code__,dict(source_bind.__globals__,original_coefficients_for_day=lambda *a:coeff),argdefs=source_bind.__defaults__)
        return fn(*a,**kw)
    @contextmanager
    def physical():
        saved=dict(voltage._MAPPING)
        for s in (voltage.Stage.A1,voltage.Stage.A2):voltage._MAPPING[s]=voltage.Voltage('SOURCE_YY',.95,1.05,.95**2,1.05**2)
        try:yield
        finally:voltage._MAPPING.clear();voltage._MAPPING.update(saved)
    def packet(c,power,swing,caps,aidc,mess,authority,bindings,**kw):
        bindings['physical_sha']=read(OUT/'SOURCE_YY_HARDWARE_FREEZE.json')['hardware_sha']
        return GridPacket(arrays=self.arrays,power=power,swing=swing,capacities=caps,aidc_plan=aidc,mess=mess,
            bindings=bindings,begin_seconds=kw['begin_seconds'],rack_compatibility=kw['rack_compatibility'])
    # Source imports its physical context and packet inside the function.
    tree=ast.parse(textwrap.dedent(inspect.getsource(ArmBinding.build)))
    class IO(ast.NodeTransformer):
        def visit_ImportFrom(self,node):
            if node.module=='v42_integrated.contract':return ast.Pass()
            return node
        def visit_keyword(self,node):
            # The source also uses receipt index4: preserve it literally.
            if node.arg=='units' and isinstance(node.value,ast.Constant) and node.value.value==4:
                node.value=ast.copy_location(ast.Constant(8),node.value)
            return self.generic_visit(node)
        def visit_Subscript(self,node):
            if ast.unparse(node)=="native['initial_MESS_sites']":return ast.copy_location(ast.Name('_initial8',ast.Load()),node)
            return self.generic_visit(node)
    tree=IO().visit(tree);ast.fix_missing_locations(tree)
    ns=dict(ArmBinding.build.__globals__,accepted=lambda:accepted(self.folder,self.day),BUNDLE=self.bundle,
        OriginalGridPacket=packet,physical_authority=physical,_initial8=INITIAL)
    exec(compile(tree,ArmBinding.build.__code__.co_filename,'exec'),ns)
    with patch.object(native,'bind',bind):return ns['build'](self,args,case,output)


def run(*,arm,folder,mess,output,fixture=False,control_slots=120,with_fresh=True):
    """Real original event/CurrentAC/Fresh path; no optimizer is called here."""
    if fixture:raise PermissionError('DIAGNOSTIC_FIXTURE_CANNOT_ENTER_PRODUCTION_ACTUAL')
    if control_slots!=120:raise ValueError('PRODUCTION_FULL_PREFIX24_PLUS96_REQUIRED')
    from v44.config import KNOWN_POLICY
    from .full_weather import observations
    from .stage_work import validate
    from v43_actual.vendor.actual import run_actual
    from v43_corrective.policy import CorrectivePolicy
    target=Path(output);target.mkdir(parents=True,exist_ok=False)
    adapter=binding(arm,folder,mess);args,case=adapter.prepare(target/'CASE')
    native=read(day_inputs()['files']['native']['path']);population={r['job_uid']:r for r in native['known_population']}
    qos=args['qos_window_provider'];external=[]
    for request,site,start in args['running']:
        if request.uid not in qos.windows and not population[request.uid]['planning_eligible']:
            assert not request.metadata['Can_Checkpoint_Migrate'] and request.uid not in args['known_schedule']
            external.append(request.uid)
    if set(external)-set(qos.external_running):
        parent=qos.provider_sha;qos.external_running=frozenset(set(qos.external_running)|set(external))
        qos.provider_sha=digest(dict(parent_provider=parent,positive_service_external_Running=sorted(external),
            contract='EXTERNAL_OBSERVED_RUNNING_CONTINUATION_ONLY_ZERO_FLEXIBILITY'))
        qos.case_sha=digest(dict(parent_case=qos.case_sha,provider_sha=qos.provider_sha))
        case=dict(case,parent_case_sha=case['case_sha'],case_sha=qos.case_sha,
            positive_service_external_Running=sorted(external),external_running_flexibility=0)
        (target/'CURRENT_CASE_BINDINGS.json').write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
    obs=observations(day_inputs(),args['begin'],args['end'])
    args['weather']=[obs.at(t,observed_now=t)['weather']['values'] for t in np.arange(args['begin'],args['end'],900)]
    racks=read(day_inputs()['files']['planning_input']['path'])['rack_compatibility']
    known=KNOWN_POLICY if arm in ('B1','B3') else None
    cls=controller_type(arm,known_policy=known,initial_running=args['running'],rack_limits=racks)
    policy=None;bindings=None
    if arm in ('B1','B3'):
        reference,packet,bindings,proof=adapter.build(args,case,target/'REFERENCE')
        oracle=CurrentAC(issue_seconds=args['begin'],sites=reference.sites,power_model=args['power_model'],observations=obs,mess_plan=mess)
        policy=CorrectivePolicy(reference,packet,variant='C1',oracle=oracle,bindings=bindings,
            expected_bindings=bindings,evidence_scope='REAL_V2_ADD_SOURCE_YY')
        policy.spec.pop('original_7_RegControl_hardware_required',None)
        policy.spec.update(hardware=packet.authority['hardware'],original_RegControl=12,additional_serial_SVR_banks=3)
        policy.sha=digest(policy.spec)
        policy.bind_observed_c1(args['power_model'],current_weather_provider=lambda when:obs.at(when,observed_now=oracle.now)['weather']['values'])
    actual=run_actual(**dict(args,arm=arm),frozen_policy=policy,controller_class=cls,expected_bindings=bindings)
    if policy is not None:policy.require_bindings(bindings)
    conservation,rows=validate(actual,args,allow_known_research=known is not None)
    if not conservation['PASS']:raise ValueError('ORIGINAL_FULL_ACTUAL_WORK_GPU_WAN_REPLAY_REJECTED')
    p=actual['physical']['PCC_P_kw'];q=actual['physical']['PCC_Q_kvar']
    from .stage_actual import fresh_handler
    physical=fresh_handler(day_inputs(),dict(P=p,Q=q),mess,target/'ELECTRICAL') if with_fresh else None
    return dict(PASS=bool(conservation['PASS'] and (physical is None or physical['PASS'])),actual=actual,work=conservation,independent_physical=physical,
        original_Known_Unknown_policy=known,Source_QoS_PASS=conservation['Source_QoS_PASS'],
        full120_security_PASS=None if physical is None else physical['PASS'],independent_new_engine=physical is not None,
        original_FULL_Job_PASS=conservation['PASS'])

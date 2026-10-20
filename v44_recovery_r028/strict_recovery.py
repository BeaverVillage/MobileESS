"""Strict M2 search; voltage-only nonrecovery may enter strict Actual/Fresh."""
from contextlib import contextmanager
from pathlib import Path
from functools import wraps
from unittest.mock import patch
import inspect,textwrap,linecache
import numpy as np
from v44.common import read,record,verify,atomic,now,digest
from .voltage_policy import strict_authority_required,audit,STRICT


def voltage_report(case,payload,plan):
    controls=[];sites=list(map(str,payload['planning']['sites']))
    for t,c in enumerate(case.coefficients):
        row=[]
        for name in c.control_names:
            site=name.split('[',1)[1][:-1]
            if name.startswith('aidc_load_kw'):value=payload['planning']['PCC_P_kw'][t,sites.index(site)]
            elif name.startswith('mess_p_kw'):value=plan['site_P_kW'][site][t]
            elif name.startswith('mess_q_kvar'):value=plan['site_Q_kvar'][site][t]
            else:raise ValueError('R028_M2_CONTROL_AXIS:'+name)
            row.append(value)
        controls.append(row)
    return audit(case.coefficients,controls,case._v43_coefficient_metadata['node_names'],band=STRICT)


def nonvoltage_replay(case,point):
    """Exclude only named voltage rows; retain every bound and integer check."""
    from v42_m1_research.check_ub import matrix_replay,physical_replay
    d=case.original_d;names=np.asarray(d['row_names']).astype(str)
    families=np.array([n.split('[',1)[0] for n in names])
    voltage=np.isin(families,('voltage_lower','voltage_upper'));keep=~voltage
    if not voltage.any():raise ValueError('R028_M2_VOLTAGE_AXIS_REQUIRED')
    selected=dict(d,rhs=d['rhs'][keep],sense=d['sense'][keep],row_names=names[keep])
    tight=np.isin(families[keep],('flow','terminal_location','NormalAmps','line_thermal_face','transformer_kVA'))
    matrix=matrix_replay(case.original_A[keep],selected,point,tolerance=1e-6,row_tolerances=np.where(tight,1e-8,1e-6))
    physical=physical_replay(case,point)
    return dict(PASS=bool(matrix['PASS'] and physical['PASS']),matrix=matrix,physical=physical,
        excluded_voltage_rows=int(voltage.sum()),all_other_original_rows_bounds_integrality_retained=True,
        original_tolerances_unchanged=True,certifies_FULL_feasibility=False)


def parent_operating_point(request,case):
    """Use the exact operating plan A2 froze, with a new nonvoltage replay."""
    from .parent_admission import original_point
    from v44.stages import require_m1
    from .voltage_policy import require_handoff
    root=Path(request['case_root']);stage=root/'M1'
    restored=root/'RESTORED_COMPLETED_STAGES.json'
    if not (stage/'RESULT.json').exists() and restored.exists():stage=Path(read(restored)['M1']['root'])
    if not (stage/'RESULT.json').exists() and request.get('fresh_a2_parent'):stage=Path(request['fresh_a2_parent'])/'M1'
    m1=read(stage/'RESULT.json');plan=require_m1(m1,request['day'])
    a2=read(root/'A2/RESULT.json');require_handoff(a2,request['day'])
    if a2.get('fixed_M1_plan_sha')!=plan['plan_sha']:raise ValueError('R028_FALLBACK_NOT_A2_FIXED_M1_PLAN')
    names,point=original_point(stage);lookup=dict(zip(map(str,names),map(float,point)))
    target=list(map(str,case.original_d['names']))
    if set(target)!=set(lookup):raise ValueError('R028_M1_M2_ORIGINAL_VARIABLE_AXIS_DIFFERENCE')
    x=np.array([lookup[n] for n in target]);epigraph=[]
    for j,name in enumerate(target):
        if name.split('[',1)[0]=='rho_max':
            x[j]=case.original_d['upper'][j];epigraph.append(name)
    proof=nonvoltage_replay(case,x)
    proof.update(M1_result=record(stage/'RESULT.json'),accepted_A2=record(root/'A2/RESULT.json'),
        source_M1_plan_sha=plan['plan_sha'],dispatch_route_SOC_unchanged=True,
        diagnostic_thermal_epigraph_set_to_original_upper_bound=epigraph,
        UB_or_objective_certificate_claimed=False)
    if not proof['PASS']:raise ValueError('R028_M1_PLAN_FAILS_CURRENT_A2_NONVOLTAGE_CONSTRAINTS')
    return plan,proof


def require_actual(result,arm):
    """Authenticated alternative to FULL_M2, never a forged FULL flag."""
    if result.get('arm')!=arm:raise ValueError('FROZEN_ARM_FULL_MESS_REQUIRED')
    receipt=result.get('actual_voltage_diagnostic_handoff')
    if not receipt:
        if result.get('FULL_feasible') is True:return
        raise ValueError('R028_FULL_OR_AUTHORIZED_VOLTAGE_DIAGNOSTIC_REQUIRED')
    verify([receipt]);p=read(receipt['path']);verify(p['evidence']+[p['nonvoltage_receipt']])
    if (p.get('PASS') is not True or p.get('day')!=result.get('day') or p.get('arm')!=arm
        or p.get('source_sha')!=result.get('source_sha') or p.get('MESS_plan_sha')!=result.get('MESS_plan',{}).get('plan_sha')
        or p.get('nonvoltage_PASS') is not True or p.get('Actual_Fresh_original_strict_voltage_required') is not True
        or result.get('FULL_feasible') is True or result.get('global_gap_certified') is True):
        raise PermissionError('R028_VOLTAGE_DIAGNOSTIC_HANDOFF_INVALID')
    if not read(p['nonvoltage_receipt']['path'])['PASS']:raise PermissionError('R028_DIAGNOSTIC_NONVOLTAGE_REPLAY_REQUIRED')
    if digest({k:v for k,v in result['MESS_plan'].items() if k!='plan_sha'})!=p['MESS_plan_sha']:
        raise PermissionError('R028_DIAGNOSTIC_PLAN_SHA_DRIFT')


def diagnostic_driver(function):
    source=textwrap.dedent(inspect.getsource(function))
    gate="if result.get('FULL_feasible') is not True or result['arm']!=arm:raise ValueError('FROZEN_ARM_FULL_MESS_REQUIRED')"
    if source.count(gate)!=1:raise ValueError('R028_ACTUAL_MESS_ADMISSION_BOUNDARY_DRIFT')
    source=source.replace(gate,'_r028_require_actual(result,arm)')
    filename=__file__+'.actual.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r028_require_actual=require_actual)
    exec(compile(source,filename,'exec'),ns);return ns[function.__name__]


@contextmanager
def install():
    from v44 import worker,runtime,svr12_policy
    from v44.checkpoints import seal_stage
    from v42_m1_research.check_ub import validate_candidate
    original_build=runtime.build;old_m=worker.m_stage;old_actual=worker.actual;old_driver=svr12_policy.corrective_driver;built={}
    def build(payload,request,progress=None):
        if request['stage']=='M2':strict_authority_required()
        case=original_build(payload,request,progress)
        if request['stage']=='M2':
            built[str(Path(request['root']))]=(case,payload)
            atomic(Path(request['root'])/'M2_STRICT_AUTHORITY.json',dict(UTC=now(),PASS=True,
                lower_pu=.95,upper_pu=1.05,lower_squared=.9025,upper_squared=1.1025,
                Q250=True,PCS400=True,source_sha=request['source_sha'],case_sha=case.case_sha,
                A2_relaxation_inherited=False,Native_budgets=dict(K48=300,Joint=900,Joint_call=300),Threads=4,Method=2))
        return case
    @wraps(old_m)
    def m_stage(request,aidc):
        result=old_m(request,aidc)
        if request['stage']!='M2':return result
        strict_authority_required();entry=built.get(str(Path(request['root'])))
        proof=dict(UTC=now(),PASS=False,day=request['day'],arm='B3',stage='M2',voltage_band=[.95,1.05],
            A2_relaxation_inherited=False,source_sha=request['source_sha'])
        if entry is None:raise ValueError('R028_M2_CURRENT_CASE_REQUIRED')
        case,payload=entry;root=Path(request['root']);original_status=result['status'];nonvoltage=None
        if result.get('allow_downstream'):
            with np.load(root/'ACCEPTED_M_POINT.npz',allow_pickle=False) as z:point=z['point']
            full=validate_candidate(case,point);plan=result['MESS_plan']
            report=voltage_report(case,payload,plan);nonvoltage=nonvoltage_replay(case,case.lift(point))
            proof.update(PASS=bool(full['PASS'] and report['strict_PASS']),original_FULL_replay=full,
                voltage_report=report,accepted_point=record(root/'ACCEPTED_M_POINT.npz'),MESS_plan_sha=plan['plan_sha'])
        if not proof['PASS']:
            if not result.get('M_stage_execution_PASS') or result.get('implementation_errors') or result.get('error'):
                raise ValueError('R028_M2_IMPLEMENTATION_FAILURE_CANNOT_BE_VOLTAGE_DIAGNOSTIC')
            if not nonvoltage or not nonvoltage['PASS']:
                plan,nonvoltage=parent_operating_point(request,case);result['MESS_plan']=plan
            report=voltage_report(case,payload,result['MESS_plan'])
            proof.update(voltage_report=report,MESS_plan_sha=result['MESS_plan']['plan_sha'],
                status='M2_VOLTAGE_RECOVERY_UNPROVEN_ACTUAL_FRESH_REQUIRED',failure_for_voltage_alone=False)
        path=root/'M2_STRICT_VOLTAGE_RECOVERY.json';atomic(path,proof);result['strict_voltage_recovery']=record(path)
        if not proof['PASS']:
            nonpath=root/'M2_ACTUAL_PLAN_NONVOLTAGE_REPLAY.json';atomic(nonpath,nonvoltage)
            handoff=dict(UTC=now(),PASS=True,day=request['day'],arm=request['arm'],source_sha=request['source_sha'],
                MESS_plan_sha=result['MESS_plan']['plan_sha'],nonvoltage_PASS=True,nonvoltage_receipt=record(nonpath),
                evidence=[record(path),record(nonpath)],Actual_Fresh_original_strict_voltage_required=True,
                M2_FULL_or_Global_Gap_claimed=False,voltage_recovery_failure_alone_is_case_failure=False)
            hpath=root/'M2_ACTUAL_VOLTAGE_DIAGNOSTIC_HANDOFF.json';atomic(hpath,handoff)
            result.update(PASS=False,FULL_feasible=False,global_gap_certified=False,allow_downstream=True,
                status='M2_VOLTAGE_RECOVERY_PENDING_ACTUAL_FRESH',original_M2_status=original_status,
                actual_voltage_diagnostic_handoff=record(hpath),M2_voltage_recovery_failure_is_case_failure=False)
        atomic(root/'RESULT.json',result);seal_stage(root,request,result);return result
    @wraps(old_actual)
    def actual(request,*args,**kwargs):
        strict_authority_required()
        if request['arm']=='B3':require_actual(read(request['MESS_result']),'B3')
        result=old_actual(request,*args,**kwargs)
        if request['arm']=='B3':
            m=read(request['MESS_result']);result.update(M2_strict_voltage_recovery=m.get('strict_voltage_recovery'),
                M2_voltage_diagnostic_handoff=m.get('actual_voltage_diagnostic_handoff'),
                final_PASS_authority='UNCHANGED_INDEPENDENT_ACTUAL_FRESH_STRICT_PHYSICAL_VALIDATION')
            status=Path(request['output'])/'CORRECTIVE_CERTIFICATION_STATUS.json'
            if m.get('actual_voltage_diagnostic_handoff') and status.exists():
                c=read(status);c.update(PLANNING_FULL_PASS='M2_VOLTAGE_DIAGNOSTIC_NO_FULL_CERTIFICATE',
                    PLANNING_GLOBAL_GAP_PASS='M2_DIAGNOSTIC_GAP_NOT_CERTIFIED',
                    M2_voltage_diagnostic_handoff=m['actual_voltage_diagnostic_handoff'])
                atomic(status,c)
            atomic(Path(request['output'])/'RESULT.json',result);seal_stage(request['root'],request,result)
        return result
    def driver(function,*args,**kwargs):return old_driver(diagnostic_driver(function),*args,**kwargs)
    with patch.object(runtime,'build',build),patch.object(worker,'m_stage',m_stage),patch.object(worker,'actual',actual),patch.object(svr12_policy,'corrective_driver',driver):yield

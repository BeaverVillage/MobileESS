"""Monthly B2 adapter to the existing M anytime primal/dual hybrid.

Only case/date/output/seed/budget routing is new. Role-exchange restrictions,
signed pricing, restricted master and exact certificates are called from their
existing implementations. All Native calls belong to the campaign budget.
"""
from contextlib import ExitStack
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from hashlib import sha256
import json
import re
import time

import numpy as np

from v42_pr134_b1.common import atomic, record, sha
from v42_m1_research.check_lb import check_rational_dual_certificate
from v42_m1_research.check_ub import validate_candidate, vector_sha, physical_replay
from v42_m1_hybrid.final_verify import _strict_ub
from .m_model import CampaignMCase, build_case, verify_case


TARGET=F(3,100)


def prepare(request, progress=None):
    from .inputs import generate_b2
    if request['arm']!='B2': raise ValueError('M_STAGE_B2_ONLY')
    payload=generate_b2(request)
    case=build_case(payload,request,progress)
    point,receipt=stationary_candidate(case)
    atomic(case.output/'SAME_DAY_STATIONARY_CANDIDATE.json',receipt)
    case.point=point
    return case


def stationary_candidate(case):
    """A new current-day no-movement candidate, never a historical warm start."""
    from v42_integrated.start import reconstruct, PRIMARY
    if case.graph[3].initial!=case.graph[3].terminal:
        return None,dict(PASS=False,reason='STATIONARY_INITIAL_TERMINAL_SOC_DIFFER',historical_point_reads=0)
    sites,initial,arcs,battery,_=case.graph
    stay={(a[0],a[1]):k for k,a in enumerate(arcs) if a[-1] is None}
    values={}
    for name in map(str,case.original_d['names']):
        family=name.split('[',1)[0]
        if family not in PRIMARY: continue
        if family=='arc':
            unit,k=name[4:-1].split(',');k=int(k);a=arcs[k]
            value=float(a[-1] is None and a[0]==initial[unit])
        elif family=='SOC': value=float(battery.initial)
        elif family=='rho_max': value=1.
        else: value=0.
        values[name]=value
    try:
        raw,_=reconstruct(case.original_A,case.original_d,list(values),list(values.values()))
        rho=int(np.flatnonzero(case.original_d['names']=='rho_max')[0])
        coefficient=case.original_A[:,rho].toarray().ravel()
        ids=np.flatnonzero((coefficient<0)&(case.original_d['sense']=='<'))
        required=raw[rho]+(case.original_A@raw-case.original_d['rhs'])[ids]/(-coefficient[ids])
        if len(ids):
            value=max(0.,float(np.max(required)))
            values['rho_max']=float(np.nextafter(value,np.inf))
            raw,_=reconstruct(case.original_A,case.original_d,list(values),list(values.values()))
        point=case.presolve.forward(case.compact.forward(raw))
        replay=validate_candidate(case,point)
        if replay['PASS']:
            from v42_m1_research.check_joint import check_exact_integer_replay
            check_exact_integer_replay(replay)
            packet=case.output/'SAME_DAY_STATIONARY_RAW_POINT.npz'
            np.savez_compressed(packet,point=point)
            strict=_strict_ub(case,packet,{})
            return point,dict(PASS=True,source='CURRENT_DAY_STATIONARY_ROUTE_NO_DISPATCH',
                case_sha=case.case_sha,strict_UB=strict,original_triangular_helper_reconstruction=True,
                historical_point_reads=0,Native_optimize_calls=0,AIDC_optimization_calls=0)
        return None,dict(PASS=False,reason='SAME_DAY_STATIONARY_POINT_NOT_ORIGINAL_FEASIBLE',
            case_sha=case.case_sha,replay=replay,historical_point_reads=0,Native_optimize_calls=0)
    except ValueError as exc:
        return None,dict(PASS=False,reason=str(exc),case_sha=case.case_sha,
            historical_point_reads=0,Native_optimize_calls=0)


def _model(case, continuous=False):
    from v42_m1_research.lb import build_model
    relaxation=SimpleNamespace(A=case.A,d=case.d)
    model,receipt=build_model(relaxation,continuous=continuous)
    return model,receipt


def _seed_integer(case,budget,progress):
    model,identity=_model(case)
    try:
        atomic(case.output/'SAME_DAY_SEED_MODEL_IDENTITY.json',identity)
        if progress: progress(dict(phase='M_SAME_DAY_P1_INTEGER_SEED',day=case.bundle['day'],arm='B2'))
        budget.native_optimize(model,component='P1',track='M_SEED',label='CURRENT_DAY_UNRESTRICTED_P1_SEED',
                               requested_seconds=min(900.,budget.remaining(reserve=budget.final_reserve)/3))
        if not model.SolCount:
            return None,dict(status='INCONCLUSIVE' if model.Status==3 else 'TIME_LIMIT_NO_VALID_INCUMBENT',
                reason='NO_SAME_DAY_ORIGINAL_VALID_INTEGER_SEED',Native_status=int(model.Status))
        raw=np.asarray(model.getAttr('X'),dtype=np.float64)
        packet=case.output/'SAME_DAY_NATIVE_SEED_RAW_POINT.npz';np.savez_compressed(packet,point=raw)
        try:
            with budget.cost('integer_physical_validation','M_seed_physical_replay'):
                receipt=_strict_ub(case,packet,{})
            atomic(case.output/'SAME_DAY_NATIVE_SEED_STRICT_REPLAY.json',dict(receipt,case_sha=case.case_sha))
            return raw,receipt
        except ValueError as exc:
            return None,dict(status='PHYSICAL_FAILURE',reason=str(exc),replay=validate_candidate(case,raw))
    finally:model.dispose()


def _fresh_lp_dual(case,budget,progress):
    from v42_m1_research.lb import repair_affine_equality_duals
    if progress:progress(dict(phase='M_SAME_DAY_FULL_LP_EXACT_LB',day=case.bundle['day'],arm='B2'))
    model,identity=_model(case,continuous=True)
    dual={};repair=None
    try:
        atomic(case.output/'SAME_DAY_LP_MODEL_IDENTITY.json',identity)
        model.Params.Method=1
        budget.native_optimize(model,component='P1',track='M_LB',label='CURRENT_DAY_FULL_LP_EXACT_DUAL',
                               requested_seconds=min(300.,budget.remaining(reserve=budget.final_reserve)))
        try:
            pi=np.asarray(model.getAttr('Pi'),dtype=float)
            if pi.shape==(case.A.shape[0],) and np.isfinite(pi).all():
                dual,repair=repair_affine_equality_duals(case.A,case.d,pi)
        except Exception as exc:
            atomic(case.output/'LP_DUAL_UNAVAILABLE.json',dict(error=str(exc),zero_signed_dual_retained=True))
    finally:model.dispose()
    # Zero multipliers are also a rigorous same-day box lower bound, although
    # they may be weak. No previous-day/native BestBd is used as a certificate.
    with budget.cost('integer_physical_validation','M_initial_independent_exact_LB'):
        cert=check_rational_dual_certificate(case.A,case.d,dual,case_sha=case.case_sha)
    cert['exact_Global_LB']=cert['exact_bound']
    atomic(case.output/'INITIAL_EXACT_ORIGINAL_DUAL.json',dual)
    atomic(case.output/'INITIAL_EXACT_LB_CERTIFICATE.json',dict(cert,affine_repair=repair))
    return dual,cert


def _plan(case,point):
    original=case.lift(point);values=dict(zip(map(str,case.original_d['names']),map(float,original)))
    sites,initial,arcs,battery,_=case.graph
    chosen={}
    for unit in initial:
        for k in range(len(arcs)):values.setdefault(f'arc[{unit},{k}]',0.)
        for site in sites:
            for t in range(96):
                for family in ('Pch','Pdis','Q'):values.setdefault(f'{family}[{unit},{site},{t}]',0.)
        chosen[unit]=[k for k in range(len(arcs)) if values[f'arc[{unit},{k}]']==1.]
    units=tuple(sorted(initial));p=np.zeros((96,4));q=np.zeros_like(p);soc=np.zeros((97,4));locations=[]
    route_records=[]
    for t in range(96):
        row=[]
        for j,unit in enumerate(units):
            a=next(a for k in chosen[unit] if (a:=arcs[k])[1]<=t<a[3])
            connected=a[-1] is None;site=a[0]
            row.append(site if connected else f'TRANSIT_{a[0]}_{a[2]}')
            if connected:
                p[t,j]=values[f'Pdis[{unit},{site},{t}]']-values[f'Pch[{unit},{site},{t}]']
                q[t,j]=values[f'Q[{unit},{site},{t}]']
            soc[t,j]=values[f'SOC[{unit},{t}]']
        locations.append(row)
    for j,unit in enumerate(units):
        soc[96,j]=values[f'SOC[{unit},96]']
        for k in chosen[unit]:
            a=arcs[k]
            if a[-1] is not None:
                r=a[-1];route_records.append(dict(unit=unit,route_id=r.route_id,source=r.source,destination=r.destination,
                    depart=r.depart,arrive=r.arrive,connect=r.connect,energy_kwh=r.energy_kwh))
    plan=dict(values=values,initial_sites=initial,chosen_arcs=chosen,mode='MILP',
        unit_ids=list(units),locations=locations,P_kw=p.tolist(),Q_kvar=q.tolist(),SOC_kwh=soc.tolist(),
        routes=route_records,units=list(units),power_units='kW_kvar_kVA_kWh_hours',case_sha=case.case_sha,day=case.bundle['day'],arm='B2')
    np.savez_compressed(case.output/'MESS_PHYSICAL.npz',P_kw=p,Q_kvar=q,SOC_kwh=soc,
        locations=np.asarray([[s or '' for s in row] for row in locations]),unit_ids=np.asarray(units))
    atomic(case.output/'OPTIMIZED_MESS_PLAN.json',plan)
    return plan


def _lb_catalog_sha(decomp,point,context):
    """Hash admitted mathematical columns, never packet names or timestamps."""
    columns={}
    for unit,block in decomp.units.items():
        values={vector_sha(point[block.original_columns])}
        for path in context['seed_columns'][unit]:
            with np.load(path,allow_pickle=False) as packet:
                values.add(vector_sha(packet['point']))
        columns[unit]=sorted(values)
    return sha256(json.dumps(columns,sort_keys=True).encode('ascii')).hexdigest()


def run(request,budget,progress,*,lb_rescue=None):
    from v42_m1_anytime import algorithms as alg,core
    from v42_m1_hybrid.blocks import build_blocks
    from v42_m1_hybrid.verify import verify_decomposition,verify_rmp_pricing_lower_bounds
    request=dict(request,_budget=budget)
    with budget.cost('model_preparation','M_original_model_build'):
        case=prepare(request,progress)
    budget.check() if hasattr(budget,'check') else None
    proof=case.identity['transport'];point=case.point
    if point is None:
        point,seed=_seed_integer(case,budget,progress)
        if point is None:
            result=dict(day=request['day'],arm='B2',case_sha=case.case_sha,accepted=False,PASS=False,
                status=seed.get('status','TIME_LIMIT_NO_VALID_INCUMBENT'),seed=seed,
                UB=None,global_LB=None,gap=None,P2_calls=0,AIDC_optimization_calls=0,
                Native_Runtime=budget.used(),wall_seconds=budget.wall(),output=str(case.output))
            result.update(classification=result['status'],LB=None,certified_gap=None,
                native_seconds=budget.used(),native_calls=len(budget.calls))
            atomic(case.output/'M_STAGE_RESULT.json',result);return result
    case.point=point.copy();decomp=build_blocks(case);verify_decomposition(case,decomp)
    search=None if lb_rescue is None else lb_rescue(case,request)
    packet=case.output/'INITIAL_STRICT_UB_POINT.npz';np.savez_compressed(packet,point=point)
    with budget.cost('integer_physical_validation','M_initial_strict_UB'):
        strict=_strict_ub(case,packet,{});strict.update(case_sha=case.case_sha)
    ubpath=case.output/'INITIAL_STRICT_UB_CERTIFICATE.json';atomic(ubpath,strict)
    dual,lbcert=_fresh_lp_dual(case,budget,progress)
    lbpath=case.output/'INITIAL_EXACT_LB_CERTIFICATE.json'
    context=dict(fixed_rows=(),seed_columns={u:[] for u in decomp.units})
    history=[];choices=[];counts={k:0 for k in ('U1','U2','U3','U4','L1','L2','L3','L4')}
    grid_cache={};rmpdual=None;latest_rmp=None;error=None;termination='NATIVE_BUDGET_WINDOW_CLOSED'
    with ExitStack() as scope:
        # Existing Frontier's sole fixed case constant is routed for this
        # single worker. Its packet/SHA/rational admission logic is unchanged.
        scope.enter_context(patch.object(core,'CASE',case.case_sha))
        frontier=core.Frontier(case.output/'frontier',budget,lbcert['exact_bound'],strict['exact_Global_UB'],
            lbpath,ubpath,clock=lambda:budget.started+budget.wall())
        try:
            for iteration in range(4096):
                if frontier.gap()<=TARGET:
                    termination='INDEPENDENT_GLOBAL_GAP_3_PERCENT_CERTIFIED';break
                if budget.remaining(reserve=budget.final_reserve)<=0:break
                method,reason=core.schedule_choice(history,iteration,budget.wall())
                if search is not None and budget.remaining(reserve=budget.final_reserve)>=600:
                    rescue=search.take_rescue(history,budget.remaining(reserve=budget.final_reserve),frontier.gap())
                    if rescue is not None:method=rescue['method'];reason=rescue
                if method.startswith('L') and budget.remaining(reserve=budget.final_reserve)<600:
                    method='U3';reason['reason']='FINAL_CERTIFICATE_RESERVE_REQUIRES_SHORTER_UB_TASK'
                if method=='L4' and budget.remaining(reserve=budget.final_reserve)<1000:
                    method='U4';reason['reason']='FULL_MILP_PRICE_PASS_RESERVE_REQUIRES_SHORTER_UB_TASK'
                counts[method]+=1;ordinal=counts[method]-1;label=f'{iteration:03d}_{method}_{ordinal:02d}'
                target=case.output/label;frontier.algorithm=label;begin=time.perf_counter()
                choices.append(dict(method=method,ordinal=ordinal,reason=reason,wall_seconds=budget.wall(),case_sha=case.case_sha))
                if progress:progress(dict(phase='M_ADAPTIVE_'+method,day=request['day'],arm='B2',
                    UB=float(frontier.ub),global_LB=float(frontier.lb),gap=float(frontier.gap()),goal_gap=.03))
                if method.startswith('U'):
                    key=vector_sha(point)
                    if key not in grid_cache:
                        with budget.cost('active_source_grid_projection',label):
                            grid_cache[key]=alg.dynamic_grid(case,point,case.output/(label+'_GRID_PROJECTION.json'),context=context)
                    if iteration<4:limit={'U1':120,'U2':90,'U3':120,'U4':90}[method]
                    else:limit=300 if any(r['method']==method and r['certified_gain']>0 for r in history) else (180,240)[ordinal%2]
                    row,point=alg.ub_trial(case,point,method,ordinal,budget,frontier,target,limit,grid_cache[key],context=context)
                    case.point=point.copy()
                else:
                    price=dual;alpha=None;selection=None
                    if method in ('L2','L3'):
                        if method=='L2' or rmpdual is None:
                            if search is not None:search.record_rmp(_lb_catalog_sha(decomp,point,context))
                            latest_rmp=alg.feedback_master(case,decomp,point,budget,case.output/(label+'_MASTER'),context=context)
                            rmpdual=latest_rmp.get('full_original_dual')
                        if rmpdual is None:
                            history.append(dict(method=method,certified_gain=0,wall_seconds=time.perf_counter()-begin,
                                status='NOT_RUN_NO_FINITE_RMP_PI'));continue
                        if search is not None:
                            with budget.cost('exact_dual_candidate_selection',label):
                                selection=search.select(case,dual,rmpdual,frontier.lb,
                                    certify=lambda y:check_rational_dual_certificate(case.A,case.d,y,case_sha=case.case_sha))
                            price=selection['dual'];alpha=selection.get('alpha')
                            atomic(case.output/(label+'_DUAL_SEARCH.json'),selection)
                        elif method=='L2':price=rmpdual
                        else:
                            alpha=('1/8','1/4','1/2')[ordinal%3];price=alg.mix_duals(dual,rmpdual,alpha)
                    kind='MILP_AND_LP' if method=='L4' else 'LP_ONLY'
                    if search is not None and not search.consume_pricing(decomp,price,kind):
                        history.append(dict(method=method,certified_gain=0,wall_seconds=time.perf_counter()-begin,
                            status='NOT_RUN_IDENTICAL_STAGE_PRICE_INPUT'))
                        atomic(case.output/'ADAPTIVE_SCHEDULER_AUDIT.json',dict(case_sha=case.case_sha,
                            choices=choices,history=history,goal_gap=.03,development_only=True))
                        continue
                    start_lb=frontier.lb
                    row,adopted,pricing=alg.lp_round(case,decomp,price,budget,frontier,target,method,
                        kind,context=context)
                    if adopted is not None:dual=adopted
                    for unit,columns in pricing['columns'].items():
                        for column in columns:
                            if column.get('admission',{}).get('PASS') and column['path'] not in context['seed_columns'][unit]:
                                context['seed_columns'][unit].append(column['path'])
                    row['dual_stabilization_weight']=alpha
                    if search is not None:
                        certificate=json.loads(Path(row['certificate']).read_text(encoding='utf-8'))
                        # lp_round independently checks the complete four-unit
                        # certificate, including trials the Frontier did not adopt.
                        certificate['exact_bound']=certificate['exact_Global_LB']
                        search.record_pricing(price,certificate,frontier.lb-start_lb,
                            new_catalog_sha=_lb_catalog_sha(decomp,point,context))
                        row['development_dual_search_status']=None if selection is None else selection['status']
                    if method=='L2' and latest_rmp.get('convexity_duals') is not None and selection is None:
                        selected=json.loads((target/'SELECTED_UNIT_DUALS_EXACT.json').read_text(encoding='utf-8'))
                        closure=verify_rmp_pricing_lower_bounds(case,decomp,rmpdual,selected,latest_rmp['convexity_duals'])
                        atomic(target/'INDEPENDENT_MISSING_COLUMN_CERTIFICATE.json',closure)
                row['wall_seconds']=time.perf_counter()-begin;row['completed_wall_seconds']=budget.wall();history.append(row)
                atomic(case.output/'ADAPTIVE_SCHEDULER_AUDIT.json',dict(case_sha=case.case_sha,
                    choices=choices,history=history,goal_gap=.03,existing_scheduler='v42_m1_anytime.core.schedule_choice',
                    development_dual_search=search is not None))
        except TimeoutError:
            termination='NATIVE_BUDGET_WINDOW_CLOSED_AT_SOLVER_BOUNDARY'
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc);termination='INPUT_OR_CERTIFICATION_FAILURE'
            atomic(case.output/'M_ADAPTIVE_ERROR.json',dict(error=error,wall_seconds=budget.wall()))
        # Each Native call ends naturally or through its remaining TimeLimit.
        # Final independent replay is measured outside the Native budget.
        packet=case.output/'BEST_STRICT_UB_POINT.npz';np.savez_compressed(packet,point=point)
        with budget.cost('integer_physical_validation','M_final_integer_physical_exact_replay'):
            strict=_strict_ub(case,packet,{});strict.update(case_sha=case.case_sha)
            exact=check_rational_dual_certificate(case.A,case.d,dual,case_sha=case.case_sha)
        if F(strict['exact_Global_UB'])!=frontier.ub or F(exact['exact_bound'])!=frontier.lb:
            raise ValueError('CURRENT_M_FINAL_FRONTIER_INDEPENDENT_CERTIFICATE_DRIFT')
        atomic(case.output/'BEST_STRICT_UB_CERTIFICATE.json',strict)
        atomic(case.output/'BEST_EXACT_ORIGINAL_DUAL.json',dual)
        atomic(case.output/'BEST_EXACT_LB_CERTIFICATE.json',exact)
        ub=F(strict['exact_Global_UB']);lb=F(exact['exact_bound'])
        if ub<lb or ub<=0:raise ValueError('CURRENT_M_FINAL_EXACT_BRACKET_INVALID')
        gap=(ub-lb)/abs(ub);plan=_plan(case,point)
        deadline_ok=budget.used()<=5400
        accepted=error is None and gap<=TARGET and deadline_ok
        result=dict(day=request['day'],arm='B2',case_sha=case.case_sha,accepted=accepted,PASS=accepted,
            status='PASS' if accepted else 'INPUT_OR_CERTIFICATION_FAILURE' if error else
                'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED' if budget.remaining()<=0 else 'INCONCLUSIVE',
            UB=float(ub),global_LB=float(lb),gap=float(gap),exact_Global_UB=str(ub),exact_Global_LB=str(lb),exact_gap=str(gap),
            target_gap=.03,termination=termination,error=error,planning=case.planning,mess=plan,
            certificate=dict(strict_UB=record(case.output/'BEST_STRICT_UB_CERTIFICATE.json'),
                exact_LB=record(case.output/'BEST_EXACT_LB_CERTIFICATE.json'),original_domain_equivalence=proof),
            Native_Runtime=budget.used(),wall_seconds=budget.wall(),deadline_PASS=deadline_ok,
            AIDC_optimization_calls=0,P2_calls=0,historical_bounds_points_columns_read=0,
            existing_algorithms=['v42_m1_anytime.core.schedule_choice','v42_m1_anytime.algorithms.ub_trial',
                'v42_m1_anytime.algorithms.lp_round','v42_m1_anytime.algorithms.feedback_master'],
            output=str(case.output))
        result.update(classification=result['status'],LB=float(lb),certified_gap=float(gap),
            native_seconds=budget.used(),native_calls=len(budget.calls),mess_plan=record(case.output/'OPTIMIZED_MESS_PLAN.json'))
        frontier.checkpoint('FINAL')
    atomic(case.output/'M_STAGE_RESULT.json',result)
    return result

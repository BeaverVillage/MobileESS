"""One retained original FULL branch-and-bound search with certified gap stop."""
from copy import deepcopy
import json,math,time
from pathlib import Path
import numpy as np
from .a_engine import digest
from .m_engine import _write,file_record,vector_sha
from .table_v_global_control import GlobalGapControl

def solve_original(model,budget,case,context,binding,objective_sha,dw,output):
    import gurobipy as gp
    output=Path(output)
    scope=dict(source_sha=context['manifest']['source_sha'],case_sha=case.case_sha,
        day=case.table_v_day,arm=case.arm,stage=case.stage,matrix_sha=binding['matrix_sha'],
        domain_sha=binding['domain_sha'],objective_sha=objective_sha)
    control=GlobalGapControl(scope,.005,output/'GLOBAL_CONTROL')
    errors=[];warnings=[];gap_stop=[False];candidate=[None];last=[None];last_report=[-10.];initial_remaining=budget.remaining()
    if (dw.get('LB_certified') is True and dw.get('full_domain_pricing_complete') is True
        and dw.get('case_sha')==case.case_sha and dw.get('native_binding')==binding):
        control.offer_lower(dw['Global_LB'],'DW_FULL_PRICING',dict(PASS=True,binding=scope,
            full_domain_pricing_complete=True,phase_I_zero_certified=True,certificate=dw['certificate']))
    A=model.getA();rhs=np.asarray(model.getAttr('RHS'));sense=np.asarray(model.getAttr('Sense'))
    lower=np.asarray(model.getAttr('LB'));upper=np.asarray(model.getAttr('UB'));integer=np.asarray(model.getAttr('VType'))!='C'
    objective=np.asarray(model.getAttr('Obj'));constant=float(model.ObjCon);variables=model.getVars()
    def preserve_incumbent(point,value,residual):
        sha=vector_sha(point);path=output/('FULL_INCUMBENT_'+sha+'.npz')
        if not path.exists():
            with path.open('xb') as stream:np.savez_compressed(stream,point=point)
        _write(output/'RECOVERABLE_FULL_INCUMBENT.json',dict(PASS=True,binding=scope,
            point=file_record(path),point_sha=sha,objective=value,FULL_max_residual=residual,
            raw_float_values_preserved=True,solver_accepted=True,Global_LB_claimed=False))
    def replay(point):
        point=np.asarray(point);activity=A@point
        rows=np.maximum(0.,np.where(sense=='<',activity-rhs,np.where(sense=='>',rhs-activity,abs(activity-rhs))))
        residual=max(float(rows.max(initial=0)),float((lower-point).max(initial=0)),float((point-upper).max(initial=0)),
            float(abs(point[integer]-np.rint(point[integer])).max(initial=0)))
        return np.isfinite(point).all() and residual<=1e-5,residual
    def callback(m,where):
        try:
            if where==gp.GRB.Callback.MESSAGE:
                message=m.cbGet(gp.GRB.Callback.MSG_STRING)
                if any(word in message for word in ('Numerical trouble','Numeric error','Out of memory')):
                    # A MESSAGE is diagnostic text, not a terminal native
                    # status. In particular barrier may recover via crossover.
                    warnings.append(message.strip())
            elif where==gp.GRB.Callback.MIPSOL:
                point=np.asarray(m.cbGetSolution(variables));valid,residual=replay(point)
                if valid:
                    value=float(objective@point+constant)
                    if candidate[0] is None or value<candidate[0][0]:candidate[0]=(value,point,residual)
            elif where==gp.GRB.Callback.MIP and candidate[0] is not None:
                accepted=float(m.cbGet(gp.GRB.Callback.MIP_OBJBST));bound=float(m.cbGet(gp.GRB.Callback.MIP_OBJBND))
                value,point,residual=candidate[0]
                # MIPSOL candidates are admitted only after the solver accepts them.
                if math.isfinite(accepted) and abs(accepted-value)<=1e-8*max(1.,abs(value)):
                    if control.upper is None or value<control.upper['value']:
                        preserve_incumbent(point,value,residual)
                    control.offer_upper(value,dict(PASS=True,binding=scope,original_FULL_replayed=True,integer_point=True,
                        point_sha=vector_sha(point),FULL_max_residual=residual),Native_Runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME)))
                    certified=control.bounds()['Global_LB'];lb=max(v for v in (bound,certified) if v is not None)
                    state=(accepted,bound)
                    if state!=last[0] and time.monotonic()-last_report[0]>=2.:
                        control.record('ORIGINAL_BB_PROGRESS',provisional_native_global_bound=bound,
                            Native_Runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME)),Native_remaining_before_call=initial_remaining,
                            provisional_bound_certified_after_native_return_only=True)
                        last[0]=state
                        last_report[0]=time.monotonic()
                    if not errors and math.isfinite(lb) and lb<=value and (value-lb)/max(abs(value),1e-10)<=.005:
                        gap_stop[0]=True;m.terminate()
        except Exception as error:
            errors.append(repr(error));m.terminate()
    call=None;certificate=None
    try:
        model.Params.OutputFlag=1;model.Params.LogToConsole=0;model.Params.MIPGap=.005;model.Params.MIPGapAbs=0.
        control.begin_operation('ORIGINAL_FULL_BRANCH_AND_BOUND',digest(binding))
        if budget.remaining()>0:
            call=budget.solve(model,label='RELEASE_P1:'+case.stage+':ORIGINAL_P1',cap=budget.remaining(),callback=callback)
            status=int(model.Status)
            if status==gp.GRB.NUMERIC:errors.append('NATIVE_NUMERIC_STATUS_12')
            if status==gp.GRB.INTERRUPTED and not gap_stop[0] and not errors:
                errors.append('NATIVE_INTERRUPTED_WITHOUT_VERIFIED_GAP_STOP')
            bound=float(model.ObjBound)
            valid=(status in (2,9,11) and math.isfinite(bound) and abs(bound)<gp.GRB.INFINITY and not errors
                and call.get('native_numeric_attributes',{}).get('ObjBound')==bound
                and call.get('native_numeric_attributes',{}).get('IsMIP')==1.)
            packet=dict(PASS=valid,binding=scope,original_FULL_integer_model=True,native_bound_valid=valid,
                exact_rational_BB_certificate=False,Global_LB=bound if valid else None,
                native_binding=binding,objective_sha=objective_sha,native_call=call,numerical_errors=errors,
                numerical_warnings=warnings,callback_gap_stop=gap_stop[0],
                ledger=str(budget.path),status=status,model_scope='ORIGINAL_UNCOMPRESSED_FULL_INTEGER')
            _write(output/'ORIGINAL_INTEGER_BOUND_ATTRIBUTES.json',packet)
            if valid:
                certificate=dict(packet,attributes=file_record(output/'ORIGINAL_INTEGER_BOUND_ATTRIBUTES.json'))
                control.offer_lower(bound,'ORIGINAL_INTEGER_MILP',certificate,Native_Runtime=call['Native_Runtime'])
            if model.SolCount:
                point=np.asarray(model.getAttr('X'));valid_point,residual=replay(point)
                if valid_point:
                    value=float(objective@point+constant);preserve_incumbent(point,value,residual)
                    control.offer_upper(value,dict(PASS=True,binding=scope,
                        original_FULL_replayed=True,integer_point=True,point_sha=vector_sha(point),FULL_max_residual=residual))
        reason=('IMPLEMENTATION_OR_NUMERICAL_FAILURE' if errors else 'NO_FULL_FEASIBLE_SOLUTION' if control.upper is None else
            'NATIVE_BUDGET_EXHAUSTED' if budget.remaining()<=1. else 'NO_FURTHER_CERTIFIED_IMPROVEMENT')
        summary=control.finish(reason,Native_remaining=budget.remaining(),numerical_errors=errors,numerical_warnings=warnings,
            same_original_BB_search_retained=True,unchanged_model_restarts=0)
        return call,certificate,summary
    except BaseException as error:
        control.finish('IMPLEMENTATION_OR_NUMERICAL_FAILURE',error=repr(error))
        raise
    finally:control.close()

def verified_integer_lower(result):
    certificate=result.get('Original_Integer_Bound_Certificate')
    if certificate is None:return None
    record=certificate['attributes']
    if file_record(record['path'])!=record:raise ValueError('ORIGINAL_INTEGER_BOUND_RAW_DRIFT')
    packet=json.loads(Path(record['path']).read_text(encoding='utf8'))
    if packet!={k:v for k,v in certificate.items() if k!='attributes'}:raise ValueError('ORIGINAL_INTEGER_BOUND_HEADER_DRIFT')
    native=packet['native_call'];ledger=json.loads(Path(packet['ledger']).read_text(encoding='utf8'))
    scope=packet['binding'];native_context=native.get('stage_context',{});attributes=native.get('native_numeric_attributes',{})
    if (packet.get('PASS') is not True or packet.get('native_bound_valid') is not True
        or packet['native_binding']!=result['native_binding'] or packet['objective_sha']!=result['objective_sha']
        or any(scope[k]!=result[k] for k in ('case_sha','arm','stage'))
        or scope['source_sha']!=result['D0_source_sha']
        or native not in ledger['calls'] or native.get('native_execution_entered') is not True
        or native.get('native_binding')!=packet['native_binding']
        or any(native_context.get(k)!=scope[k] for k in ('day','arm','stage','source_sha'))
        or native_context.get('stage_case_sha')!=scope['case_sha']
        or attributes.get('IsMIP')!=1. or attributes.get('ObjBound')!=packet['Global_LB']
        or native.get('status')==11 and packet.get('callback_gap_stop') is not True
        or native.get('status') not in (2,9,11) or packet.get('numerical_errors')):
        raise ValueError('SAME_ORIGINAL_FULL_INTEGER_NATIVE_BOUND_EVIDENCE_REQUIRED')
    return packet['Global_LB']

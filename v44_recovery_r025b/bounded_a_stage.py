"""User-authorized Native60 / Phase1000, with independently verified UB freezes."""
from contextlib import contextmanager,ExitStack
from contextvars import ContextVar
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import math,traceback
import numpy as np

TOTAL_NATIVE=3600.
PHASE_NATIVE=1000.
_current=ContextVar('r025b_bounded_a_stage',default=None)


class PhaseDeadline(TimeoutError):
    pass


def measured_timeout(error,budget):
    # The inherited Native.solve persists Raw then wraps a DateBudget stop
    # into RuntimeError. Normalize only that exact measured budget boundary.
    text=str(error)
    return (type(error).__name__=='BudgetStop' or
        (isinstance(error,RuntimeError) and 'BudgetStop:' in text
         and 'NATIVE_RUNTIME_CEILING_EXCEEDED' in text and budget.used()>=TOTAL_NATIVE))


def current():
    return _current.get()


def phase_used(budget):
    return getattr(budget,'phase_native_used',budget.used())


def phase_cost(calls):
    phase=True;total=0.
    for call in calls:
        component=call.get('component')
        if component=='PHASE_I':phase=True
        elif component in ('ORIGINAL_P1','INTEGER_CONTROL'):phase=False
        if call.get('r025b_phase_I',phase):total+=call.get('Native_Runtime') or 0.
    return total


class Controller:
    def __init__(self,budget,output):
        self.budget=budget;self.output=Path(output);self.phase=True;self.state=None
        budget.r025b_controller=self

    def checkpoint(self,state,day=None):
        self.state=state
        if self.phase and phase_used(self.budget)>=PHASE_NATIVE:
            raise PhaseDeadline('R025B_PHASE_I_NATIVE1000_REACHED')

    def start_p1(self,state,day=None):
        self.state=state;self.phase=False


def budget_type(original,request):
    class BoundedBudget(original):
        def __init__(self,path,**kwargs):
            kwargs['native_limit']=TOTAL_NATIVE
            self.phase_native_used=0.
            super().__init__(path,**kwargs)
            parent=request.get('r025b_native_parent')
            if parent:
                from v44.common import read,verify
                proof=read(parent);verify([proof['ledger']]);old=read(proof['ledger']['path'])
                if old.get('inflight') or (proof['measured']>TOTAL_NATIVE and not request.get('r025b_incumbent_parent')):
                    raise PermissionError('R025B_INVALID_CURRENT_NATIVE_CONTINUATION')
                self.native_used=proof['measured'];self.calls=deepcopy(old['calls']);self.costs=deepcopy(old['costs'])
                self.phase_native_used=phase_cost(self.calls)
                self.started=self.clock()-old['wall_seconds'];self.persist()

        def remaining(self,reserve=None):
            value=super().remaining(reserve)
            control=getattr(self,'r025b_controller',None)
            if control is not None and control.phase:
                value=min(value,max(0.,PHASE_NATIVE-self.phase_native_used))
            return value

        def charge(self,runtime):
            control=getattr(self,'r025b_controller',None)
            if control is not None and control.phase:self.phase_native_used+=float(runtime)
            return super().charge(runtime)

        def native_optimize(self,*args,**kwargs):
            first=len(self.calls);control=getattr(self,'r025b_controller',None)
            is_phase=bool(control is not None and control.phase)
            try:return super().native_optimize(*args,**kwargs)
            finally:
                for call in self.calls[first:]:call['r025b_phase_I']=is_phase
                self.persist()

        def persist(self):
            super().persist()
            from v44.common import read,atomic
            value=read(self.path)
            value.update(policy_version='R025B_NATIVE60_PHASE1000_UB',Phase_I_Native_ceiling_seconds=PHASE_NATIVE,
                measured_Phase_I_Native_Runtime=self.phase_native_used,
                Native_clock_reset=not bool(request.get('r025b_native_parent')),
                parent_native_account=request.get('r025b_native_parent'))
            atomic(self.path,value)
    return BoundedBudget


class BoundedNative:
    def __init__(self,native,controller):
        object.__setattr__(self,'native',native);object.__setattr__(self,'controller',controller)
    def __getattr__(self,key):return getattr(self.native,key)
    def __setattr__(self,key,value):setattr(self.native,key,value)
    def remaining(self):
        if self.controller.phase and phase_used(self.controller.budget)>=PHASE_NATIVE:
            raise PhaseDeadline('R025B_PHASE_I_NATIVE1000_REACHED')
        return self.native.remaining()
    def solve(self,snapshot,folder,component):
        self.remaining()
        result,raw=self.native.solve(snapshot,folder,component)
        if (self.controller.phase and result.get('status')!=2
                and phase_used(self.controller.budget)>=PHASE_NATIVE):
            raise PhaseDeadline('R025B_PHASE_I_NATIVE1000_REACHED_DURING_NATIVE')
        return result,raw


def run(request,budget,progress,ns):
    """Retain original equations, original integer restoration and physical audit."""
    from v44.common import read,record,atomic,now
    from v42_a_stage_canary import phase,pricing,targeted
    from v42_a_stage_practical.integer_model import restore_types
    from v42_a_stage_phase1.core import primal_replay
    from v42_a_stage_lexfull.runner import objective_value
    from v42_a_stage_acceptance.schedule_audit import original_schedule_metrics
    from v42_may12_rescue.contract import decide
    day,inputs,output=ns['_paths'](request)
    controller=Controller(budget,output);token=_current.set(controller)
    native=None;state=None;candidates=[];invalid=[];exact_lb=None;closure=None;zero=None;bound=None
    result=dict(PASS=False,accepted=False,day=day,arm=request['arm'],stage=request['stage'],
        classification='INCONCLUSIVE',P2_calls=0,MESS_optimization_calls=0,
        independent_Global_LB_validated=False,global_gap_certified=False,FULL_feasible=False,
        Phase_I_skipped=False,P1_skipped=False,scientific_infeasibility_proven=False)
    try:
        with budget.cost('model_preparation','A_complete_model_build'):
            if request.get('r025b_state_checkpoint'):
                from .a2_checkpoint import load
                from v44.common import verify
                verify([request['r025b_state_checkpoint']]);state=load(request['r025b_state_checkpoint']['path'])['state']
                authority=state['_campaign'];verify(list(authority['input_receipts'].values()))
                authority.update(output=str(output),input_folder=str(inputs))
                output.mkdir(parents=True,exist_ok=True)
                # Preserve the byte-pinned physical cache and every prior Raw
                # in the original attempt, rather than relabelling it as fresh.
                atomic(output/'R025B_CURRENT_STATE_RESTORED.json',dict(PASS=True,
                    checkpoint=request['r025b_state_checkpoint'],Native_clock_reset=False,
                    inherited_Native_seconds=budget.used(),new_preparation_Native_calls=0))
            else:state=ns['prepare'](dict(request,_budget=budget),progress)
        authority=state['_campaign'];controller.checkpoint(state) if phase_used(budget)<PHASE_NATIVE else None
        controller.state=state
        native=BoundedNative(ns['_native'](request,state,budget,progress),controller)
        if hasattr(native,'budget') and hasattr(native.budget,'record'):
            native.budget.record.update(limit_seconds=TOTAL_NATIVE,Phase_I_limit_seconds=PHASE_NATIVE,
                policy_version='R025B_NATIVE60_PHASE1000_UB')
        atomic(output/'CONTINUATION_BUDGET.json',dict(PASS=True,native_limit=TOTAL_NATIVE,
            phase_I_native_limit=PHASE_NATIVE,wall_limit=None,accounting='MEASURED_NATIVE_RUNTIME_ONLY',
            policy_version='R025B_NATIVE60_PHASE1000_UB',Native_clock_reset=not bool(request.get('r025b_native_parent'))))
        full_pricing=ns['rebound'](pricing.full_pricing,dict(pricing.full_pricing.__globals__,HISTORY=output))
        target_group=ns['group'](targeted,('worker','targeted'),HISTORY=output)
        phase_group=ns['group'](phase,('activate','run'),OUT=ns['DayDirectory'](day,output),
            full_pricing=full_pricing,targeted=target_group['targeted'])
        try:
            controller.checkpoint(state)
            state,_,expanded,priced=phase_group['run'](native,state,day)
            state['_campaign']=authority
            exact_lb=Fraction(priced['full_domain_phase1_lower_bound'])
            closure=dict(PASS=True,classes=len(state['data'][7]['classes']),
                complete_STAY_and_migration_coverage=priced['complete_STAY_and_migration_coverage'],
                no_negative_omitted_block_certified=priced['no_negative_omitted_block_certified'],
                full_pricing=record(read(output/'P1_RESULT.json')['full_pricing']['path']))
            if not closure['no_negative_omitted_block_certified']:raise ValueError('R025B_INCOMPLETE_P1_CLOSURE')
            bound=dict(PASS=True,exact_LB=str(exact_lb),LB=float(exact_lb),
                scope='FULL_ORIGINAL_DATE_P1_LP_RELAXATION',restricted_native_ObjBound_not_used=True,closure=closure)
            zero=read(output/'PHASE_I_ZERO_CERTIFICATE.json')
            atomic(output/'P1_FULL_DOMAIN_BOUND_CERTIFICATE.json',bound)
            atomic(output/'COMPLETE_PRICING_CLOSURE.json',closure)
            ns['_dump_state'](output/'STATIC/P1_CLOSED_STATE.pkl.gz',state)
        except PhaseDeadline as error:
            state=controller.state;state['_campaign']=authority
            controller.phase=False
            result.update(Phase_I_skipped=True,P1_skipped=True,phase_stop_reason=str(error))
            atomic(output/'R025B_PHASE_I_P1_SKIPPED.json',dict(UTC=now(),PASS=True,
                reason=str(error),Native_seconds=budget.used(),Phase_I_limit=PHASE_NATIVE,
                Phase_I_Native_seconds=phase_used(budget),
                next='ORIGINAL_INTEGER_CONTROL_NO_ARTIFICIALS',Phase_I_zero_certified=False,
                P1_closure_certified=False,global_LB=None,global_gap=None,original_constraints_relaxed=False))
        controller.phase=False
        typed,typeproof=restore_types(state,state['global_types'])
        atomic(output/'ORIGINAL_INTEGER_TYPE_RESTORATION.json',typeproof)
        Physical,power=ns['_physical'](state,inputs,output);physical=Physical(state,typed)
        contract=ns['dated_acceptance'](decide,len(state['data'][7]['classes']))

        def validate(point,objective):
            rows=primal_replay(typed,point);iv=typed.vtypes!='C'
            integral=float(np.max(abs(point[iv]-np.rint(point[iv])),initial=0))
            if not rows['PASS'] or integral>1e-5:
                invalid.append(dict(PASS=False,original_rows=rows,integral_max_residual=integral));return
            verification=physical.verify(point)
            if not verification['PASS']:invalid.append(verification);return
            upper=objective_value(typed,point,'rho')
            if not math.isfinite(float(upper)) or abs(float(upper)-objective)>1e-6:
                raise ValueError('R025B_ORIGINAL_OBJECTIVE_IDENTITY_FAIL')
            if exact_lb is not None and upper<exact_lb:raise ValueError('R025B_CERTIFIED_LB_UB_CONFLICT')
            if candidates and upper>=Fraction(candidates[-1]['exact_UB']):return
            values={o.name:str(objective_value(typed,point,o.name)) for o in typed.objectives}
            metrics,residuals=original_schedule_metrics(state['data'][1],verification['selected_jobs'],values)
            verification.update(original_job_population_verified=True,original_jobs=len(state['data'][1]),
                original_integer_types_restored=True,integral_max_residual=integral,scientific_primal_replay=rows,
                objective_values=values,schedule_metrics=metrics,schedule_objective_residuals=residuals,
                original_P1_objective_consistency=True,no_future_information=True)
            path=output/'I'/('V'+str(len(candidates)+1));path.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(str(path)+'.npz',X=point);atomic(str(path)+'.json',verification)
            candidate=dict(PASS=True,exact_UB=str(upper),UB=float(upper),
                exact_LB=str(exact_lb) if exact_lb is not None else None,LB=float(exact_lb) if exact_lb is not None else None,
                original_integer_types_restored=True,physical=record(str(path)+'.json'),point=record(str(path)+'.npz'),
                exact_objective_values=values,evaluated_P2_metrics_only=metrics,gap=None)
            if exact_lb is not None:
                acceptance=contract(zero,closure,bound,candidate,verification)
                candidate.update(gap=acceptance['gap'],acceptance=acceptance)
            candidates.append(candidate)
            atomic(output/'VALIDATED_INTEGER_INCUMBENTS.json',dict(trajectory=candidates))
            atomic(output/'ORIGINAL_PHYSICAL_REPLAY.json',verification)
            ns['_notify'](progress,phase='INTEGER_CONTROL',day=day,UB=float(upper),
                Certified_Global_LB=candidate['LB'],Certified_Gap=candidate['gap'])
            if candidate.get('acceptance',{}).get('PASS') and native.live_model is not None:
                native.live_model.terminate()

        native.incumbent_callback=validate
        try:
            if request.get('r025b_incumbent_parent'):
                # No optimize: restore only this same-model physically verified
                # incumbent after the old worker's wrapped budget exception.
                from v44.common import verify
                parent=Path(request['r025b_incumbent_parent'])
                old=read(parent/'OUTPUT/VALIDATED_INTEGER_INCUMBENTS.json')['trajectory'][-1]
                verify([old['point'],old['physical']])
                identity=read(parent/'OUTPUT/P1/INTEGER_CONTROL/MODEL_IDENTITY.json')
                if typed.fingerprint()!=identity['original_snapshot_sha256']:
                    raise ValueError('R025B_UB_RECOVERY_TYPED_MODEL_IDENTITY_DRIFT')
                with np.load(old['point']['path'],allow_pickle=False) as saved:point=saved['X'].copy()
                validate(point,old['UB']);result['native_status']=9
                atomic(output/'R025B_VERIFIED_UB_RECOVERED.json',dict(UTC=now(),PASS=bool(candidates),
                    parent_point=old['point'],parent_physical=old['physical'],Native_clock_reset=False,
                    new_Native_calls=0,inherited_Native_seconds=budget.used(),original_typed_model_identity=True))
            else:
                rec,raw=native.solve(typed,output/'P1/INTEGER_CONTROL','INTEGER_CONTROL')
                result['native_status']=rec['status']
                if 'X' in raw:validate(raw['X'],rec['objective'])
        except Exception as error:
            # Only a measured budget exhaustion may preserve a healthy incumbent.
            if not measured_timeout(error,budget):raise
            result.update(native_status=9,native_budget_stop=repr(error))
        if candidates:
            best=candidates[-1];verification=read(best['physical']['path'])
            planning=ns['_planning'](state,verification,power,output)
            certified=bool(best.get('acceptance',{}).get('PASS'))
            freeze=dict(PASS=True,accepted=True,state=request['stage']+'_VERIFIED_UB_FROZEN',
                A1_P1_ONLY_ACCEPTED=certified if request['stage']=='A1' else False,
                A2_P1_ONLY_ACCEPTED=certified if request['stage']=='A2' else False,
                A1_ACCEPTED=False,A2_full_hierarchy_accepted=False,P1_only=True,
                UB_feasible_only=not certified,global_gap_certified=certified,
                arm=request['arm'],day=day,stage=request['stage'],selected_jobs=verification['selected_jobs'],
                controls=verification['controls'],globals=verification['globals'],
                validated_original_integer_point=best['point'],physical=best['physical'],planning=planning,
                source=record(native.freeze_path),scientific_input=authority['input_receipts'],
                exact_objective_values=best['exact_objective_values'],P2_calls=0,MESS_optimization_calls=0,
                UB=best['UB'],LB=best['LB'],certified_gap=best['gap'],
                independent_Global_LB_validated=exact_lb is not None,policy='R025B_NATIVE60_PHASE1000_UB')
            if request.get('M1_result'):
                freeze['fixed_M1_plan_sha']=read(request['M1_result']['path'])['MESS_plan']['plan_sha']
            name='B1_UB_FREEZE.json' if request['stage']=='A1' else 'B3_A2_UB_FREEZE.json'
            atomic(output/name,freeze)
            result.update(PASS=True,accepted=True,classification='GLOBAL_GAP_PASS' if certified else 'VERIFIED_UB_FROZEN_GAP_NOT_CERTIFIED',
                freeze=record(output/name),planning=planning,incumbent=best,UB=best['UB'],LB=best['LB'],
                exact_UB=best['exact_UB'],exact_LB=best['exact_LB'],certified_gap=best['gap'],
                global_gap_certified=certified,independent_Global_LB_validated=exact_lb is not None,
                FULL_feasible=True,allow_downstream=True,UB_feasible_only=not certified,
                planning_rho_max=verification['physical']['P1_rho'],policy='R025B_NATIVE60_PHASE1000_UB')
        else:
            result.update(classification='TIME_LIMIT_NO_VALID_INCUMBENT' if result.get('native_status') in (9,11)
                else 'NO_VALID_INCUMBENT',allow_downstream=False)
    except Exception as error:
        result.update(classification='TIME_LIMIT_NO_VALID_INCUMBENT' if type(error).__name__=='BudgetStop'
            else 'IMPLEMENTATION_FAILURE',error=repr(error),traceback=traceback.format_exc(),allow_downstream=False)
    finally:
        result.update(native_seconds=budget.used(),wall_seconds=budget.wall(),
            native_calls=len(native.calls) if native is not None else 0,invalid_original_physical_replay_count=len(invalid),
            total_Native_limit=TOTAL_NATIVE,Phase_I_Native_limit=PHASE_NATIVE,policy='R025B_NATIVE60_PHASE1000_UB')
        output.mkdir(parents=True,exist_ok=True);atomic(output/'A_RESULT.json',result);_current.reset(token)
    return result


@contextmanager
def install():
    from v44 import worker,daily,stages
    from v44.frozen.v43_a2 import adapter
    from v42_may_campaign_native90 import a_stage,budget
    from .ub_downstream import export_a,require_a2,worker_function
    original_worker=worker.a_stage;original_route=adapter.routed_function
    bounded_worker=worker_function(original_worker)
    def routed(module,name,namespace,mess):
        function,changes=original_route(module,name,namespace,mess)
        if name=='run':
            def bounded(request,budget,progress=None):return run(request,budget,progress,namespace)
            namespace['run']=bounded;function=bounded
        return function,changes
    def a_run(request,budget,progress=None):return run(request,budget,progress,a_stage.__dict__)
    def worker_run(request,*args,**kwargs):
        if request.get('arm') not in ('B1','B3') or request.get('stage') not in ('A1','A2'):
            return original_worker(request,*args,**kwargs)
        request=dict(request,native_budget_seconds=TOTAL_NATIVE,phase_I_native_budget_seconds=PHASE_NATIVE,
            a_execution_policy='R025B_NATIVE60_PHASE1000_UB')
        with patch.object(budget,'DateBudget',budget_type(budget.DateBudget,request)):
            return bounded_worker(request,*args,**kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch.object(a_stage,'run',a_run))
        stack.enter_context(patch.object(adapter,'routed_function',routed))
        stack.enter_context(patch.object(worker,'a_stage',worker_run))
        stack.enter_context(patch.object(daily,'export_a',export_a(daily.export_a)))
        stack.enter_context(patch.object(worker,'export_a',export_a(worker.export_a)))
        stack.enter_context(patch.object(stages,'require_a2',require_a2(stages.require_a2)))
        yield

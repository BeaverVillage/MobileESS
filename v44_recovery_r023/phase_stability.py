"""Original matrices and tolerances, robust simplex, and live witness dominance."""
from contextvars import ContextVar
from pathlib import Path
from fractions import Fraction
import inspect,linecache,textwrap
import numpy as np
from v44.common import atomic,record,now

_solve=ContextVar('R023_STABLE_LP_CALL',default=None)
PRIMARY=dict(Method=1,NumericFocus=3,ScaleFlag=2,Aggregate=0,Presolve=1,LPWarmStart=2)
REPAIR=dict(PRIMARY,Method=0,Quad=1,MarkowitzTol=.5)


def policy(original):
    def apply(model,approved,gp):
        effective=original(model,approved,gp);context=_solve.get()
        if context is None:return effective
        if model.NumIntVars:raise PermissionError('R023_CONTINUOUS_STABILITY_ONLY')
        preserved={name:getattr(model.Params,name) for name in ('FeasibilityTol','OptimalityTol','IntFeasTol','MIPGap','Seed','Threads')}
        settings=REPAIR if context['repair'] else PRIMARY
        for name,value in settings.items():model.setParam(name,value)
        seed=context.get('seed')
        if seed is not None:
            if len(seed['X'])!=model.NumVars:raise ValueError('R023_PRIOR_POINT_COLUMN_AXIS')
            model.setAttr('PStart',model.getVars(),seed['X'].tolist())
        assert all(getattr(model.Params,k)==v for k,v in preserved.items())
        effective.update(settings,R023_numerical_stability=True,scientific_tolerances_unchanged=True,
            same_stage_prior_primal_start=seed is not None)
        atomic(context['folder']/'R023_NUMERICAL_POLICY.json',dict(UTC=now(),component=context['component'],
            repair=context['repair'],settings=settings,preserved=preserved,
            model_matrix_and_objective_unchanged=True,prior_point_seeded=seed is not None))
        return effective
    return apply


def observe(function):
    def optimize(model,*args,**kwargs):
        result=function(model,*args,**kwargs);context=_solve.get()
        if context is not None:
            quality={}
            for attr in ('Status','ConstrVio','BoundVio','DualVio','ComplVio','Kappa'):
                try:
                    value=float(model.getAttr(attr))
                    quality[attr]=value if np.isfinite(value) else str(value)
                except Exception:quality[attr]=None
            context['quality']=quality
        return result
    return optimize


def annotated_atomic(original):
    def write(path,value):
        context=_solve.get()
        if context is not None and Path(path).name=='MODEL_IDENTITY.json':
            value=dict(value,solver_policy_unchanged=False,scientific_matrix_and_objective_unchanged=True,
                numerical_policy_overlay='R023_ROBUST_SIMPLEX_UNCHANGED_TOLERANCES')
        return original(path,value)
    return write


class StableNative:
    def __init__(self,native):self.native=native;self.seed=None
    def __getattr__(self,name):return getattr(self.native,name)

    def admit_prior(self,snapshot,point):
        from v42_a_stage_phase1.core import primal_replay
        replay=primal_replay(snapshot,point)
        if not replay['PASS']:raise ValueError('R023_PRIOR_POINT_NOT_ORIGINAL_FEASIBLE')
        objective=snapshot.objectives[0]
        phi=Fraction(objective.constant)+sum((c*Fraction(float(point[j])) for j,c in objective.coefficients().items()),Fraction(0))
        self.seed=dict(snapshot_sha=snapshot.fingerprint(),X=np.asarray(point).copy(),Phi=phi,replay=replay)

    def assess(self,snapshot,record_,raw,seed):
        from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
        if record_.get('status')!=2 or not all(k in raw for k in ('X','Pi','RC')):
            return dict(PASS=False,reason='NONOPTIMAL_OR_INCOMPLETE_RAW')
        replay=primal_replay(snapshot,raw['X']);sign=verify_sign_convention(snapshot,raw['Pi'],raw['RC'])
        objective=snapshot.objectives[0]
        value=Fraction(objective.constant)+sum((c*Fraction(float(raw['X'][j])) for j,c in objective.coefficients().items()),Fraction(0))
        dominance=seed is None or value<=seed['Phi']+Fraction(1,100000000)
        return dict(PASS=replay['PASS'] and sign['PASS'] and dominance,original_primal=replay,original_dual_sign=sign,
            exact_objective=str(value),prior_accepted_feasible_Phi=str(seed['Phi']) if seed else None,
            dominance_PASS=dominance,dominance_allowance='1/100000000',
            reason=None if replay['PASS'] and sign['PASS'] and dominance else 'RAW_REPLAY_OR_PRIOR_FEASIBLE_DOMINANCE_FAILED')

    def solve(self,snapshot,folder,component):
        folder=Path(folder)
        if component not in ('PHASE_I','LOCAL_PRICING','ORIGINAL_P1'):
            return self.native.solve(snapshot,folder,component)
        seed=self.seed if component=='PHASE_I' else None
        if seed is not None and seed['snapshot_sha']!=snapshot.fingerprint():
            raise ValueError('R023_RETAINED_PRIOR_SNAPSHOT_IDENTITY_DRIFT')
        attempts=[]
        for repair in (False,True):
            target=folder/'NUMERICAL_REPAIR' if repair else folder
            context=dict(folder=target,component=component,repair=repair,seed=seed)
            token=_solve.set(context)
            try:rec,raw=self.native.solve(snapshot,target,component)
            finally:_solve.reset(token)
            check=self.assess(snapshot,rec,raw,seed)
            attempts.append(dict(folder=str(target),Native_seconds=rec['native_seconds'],quality=context.get('quality'),
                numerical_check=check,native_result=record(target/'NATIVE_RESULT.json') if (target/'NATIVE_RESULT.json').exists() else None))
            if check['PASS']:
                total=sum(a['Native_seconds'] for a in attempts)
                atomic(folder/'R023_NUMERICAL_ACCEPTANCE.json',dict(UTC=now(),PASS=True,attempts=attempts,
                    chosen_attempt=len(attempts)-1,total_Native_seconds=total,all_calls_charged_to_original_shared_budget=True,
                    prior_accepted_feasible_point_retained=seed is not None,raw_points_not_replaced_or_clipped=True))
                return dict(rec,native_seconds=total,numerical_stability_PASS=True,numerical_attempts=len(attempts)),raw
            if rec.get('status') in (9,11):break
            self.native.remaining()
        atomic(folder/'R023_NUMERICAL_ACCEPTANCE.json',dict(UTC=now(),PASS=False,attempts=attempts,
            all_calls_charged_to_original_shared_budget=True,raw_points_not_replaced_or_clipped=True))
        raise ValueError('R023_NUMERICAL_OPTIMALITY_OR_PRIOR_POINT_DOMINANCE_NOT_VERIFIED')


def stabilized_phase(function,namespace):
    source=textwrap.dedent(inspect.getsource(function))
    anchor="        new.update(scientific_descriptor=state['scientific_descriptor'],global_types=state['global_types'],atlas=state['atlas'])"
    assert source.count(anchor)==1,'R023_PHASE_PRIOR_ADMISSION_SOURCE_DRIFT'
    source=source.replace(anchor,"        native.admit_prior(fullnew.snapshot,included_point)\n"+anchor)
    filename=__file__+'.phase.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    exec(compile(source,filename,'exec'),namespace)
    return namespace['run']

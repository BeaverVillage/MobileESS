"""Continuous-A precision and same-snapshot polish; acceptance stays strict."""
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from .io import atomic,now

ZERO=Fraction(1,100000000)
SOLVER_TOLERANCE=1e-9


def objective(snapshot,raw):
 obj=snapshot.objectives[0]
 return Fraction(obj.constant)+sum((v*Fraction(float(raw['X'][j])) for j,v in obj.coefficients().items()),Fraction(0))


def policy_wrapper(factory,stable):
 def policy(original):
  apply_original=factory(original)
  def apply(model,approved,gp):
   effective=apply_original(model,approved,gp);context=stable._solve.get()
   if context is None or context['component'] not in ('PHASE_I','ORIGINAL_P1','LOCAL_PRICING'):return effective
   settings=dict(FeasibilityTol=SOLVER_TOLERANCE,OptimalityTol=SOLVER_TOLERANCE)
   if context['component'] in ('ORIGINAL_P1','LOCAL_PRICING'):
    from .p1_interval import LEVEL
    level=LEVEL.get()
    settings.update(Method=1,NumericFocus=3,ScaleFlag=2,Aggregate=0,Presolve=1,Quad=1,MarkowitzTol=.5,LPWarmStart=2,PerturbValue=.0002)
    # The inherited second attempt is a DIFFERENT algorithm. Never overwrite
    # its repair flag with the normal dual-simplex policy again.
    if context.get('repair') or level:
     settings.update(Method=1 if level==2 else 0,Presolve=0 if level==2 else 1)
   if context.get('iteration2_polish'):
    settings.update(Method=0,Quad=1,Presolve=0,Aggregate=0,ScaleFlag=0,LPWarmStart=1,PerturbValue=0)
   for name,value in settings.items():model.setParam(name,value)
   effective.update(settings,iteration2_continuous_A_precision=True,iteration2_phase_I_precision=context['component']=='PHASE_I',scientific_acceptance_unchanged=True)
   filename='ITERATION2_PHASE_I_NUMERICAL_POLICY.json' if context['component']=='PHASE_I' else 'ITERATION2_P1_PRICING_NUMERICAL_POLICY.json'
   atomic(Path(context['folder'])/filename,dict(UTC=now(),component=context['component'],settings=settings,
    same_snapshot_polish=bool(context.get('iteration2_polish')),certified_zero_tolerance=str(ZERO),
    original_exact_price_epsilon=str(ZERO),
    original_physical_replay_tolerance=1e-6,acceptance_relaxed=False,Native_budget_reset=False))
   return effective
  return apply
 return policy


def precision_native(previous,stable):
 class PrecisionNative(previous):
  def solve(self,snapshot,folder,component):
   rec,raw=super().solve(snapshot,folder,component)
   if component!='PHASE_I':return rec,raw
   phi=objective(snapshot,raw)
   if not ZERO<phi<=Fraction(1,100000):return rec,raw
   # A small residual gets one numerical repair of the SAME matrix before
   # the inherited row/column generator decides whether expansion is needed.
   from v42_a_stage_phase1.core import primal_replay
   target=Path(folder)/'ITERATION2_NUMERICAL_POLISH';self.native.remaining()
   seed=dict(snapshot_sha=snapshot.fingerprint(),X=raw['X'].copy(),Phi=phi,replay=primal_replay(snapshot,raw['X']))
   context=dict(folder=target,component=component,repair=True,seed=seed,basis=None,iteration2_polish=True)
   token=stable._solve.set(context)
   try:polished,point=self.native.solve(snapshot,target,component)
   finally:stable._solve.reset(token)
   check=self.assess(snapshot,polished,point,seed)
   improved=bool(check['PASS'] and objective(snapshot,point)<phi)
   chosen,answer=(polished,point) if improved else (rec,raw)
   atomic(Path(folder)/'ITERATION2_PHASE_I_POLISH.json',dict(UTC=now(),PASS=check['PASS'],selected_polished_point=improved,
    before_Phi=str(phi),after_Phi=str(objective(snapshot,point)) if check['PASS'] else None,
    original_snapshot_sha=snapshot.fingerprint(),original_zero_tolerance=str(ZERO),
    all_calls_charged_to_original_shared_budget=True,raw_points_not_clipped=True,
    matrix_bounds_objective_unchanged=True,numerical_check=check))
   return dict(chosen,native_seconds=rec['native_seconds']+polished['native_seconds']),answer
 return PrecisionNative


@contextmanager
def scope():
 from v44_recovery_r029 import phase_stability as stable
 previous=stable.StableNative;factory=stable.policy
 with patch.object(stable,'StableNative',precision_native(previous,stable)),patch.object(stable,'policy',policy_wrapper(factory,stable)):
  yield

"""Bounded adaptive Phase-I arithmetic; original scientific replay is unchanged.

Every retry changes an explicit numeric policy, not rows, domains or tolerances
of the independent verifier. All calls use the same cumulative A-stage ledger.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import time
import numpy as np

VERSION='TABLE_V_VERIFIED_ADAPTIVE_PHASE_I_V1'
REPLAY_TOLERANCE=1e-6
INTEGER_RETURN_RESERVE=1800.
PHASE_I_STAGE_ALLOWANCE=900.

@dataclass(frozen=True)
class Policy:
    name:str
    presolve:int
    tolerance:float
    focus:int
    seconds:float
    scale:int=2

    def parameters(self):
        return dict(Presolve=self.presolve,FeasibilityTol=self.tolerance,
            OptimalityTol=self.tolerance,NumericFocus=self.focus,ScaleFlag=self.scale,
            Method=2,Threads=1,OutputFlag=1,LogToConsole=0)

POLICIES=(Policy('FAST_A',-1,1e-6,0,30.),Policy('FAST_B',-1,1e-8,1,180.),
          Policy('ACCURATE_C',-1,1e-9,3,300.),Policy('CURRENT',0,1e-9,3,300.))

def allowance(remaining,phase_used):
    """Reserve the original integer search and bound all Phase-I diagnostics."""
    if not all(math.isfinite(float(v)) and v>=0 for v in (remaining,phase_used)):
        raise ValueError('FINITE_NONNEGATIVE_PHASE_I_BUDGET_REQUIRED')
    return max(0.,min(PHASE_I_STAGE_ALLOWANCE-phase_used,remaining-INTEGER_RETURN_RESERVE))

def validate_raw(snapshot,raw):
    from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
    if not all(key in raw for key in ('X','Pi','RC')):
        return dict(PASS=False,reason='OPTIMAL_PRIMAL_DUAL_ATTRIBUTES_REQUIRED')
    primal=primal_replay(snapshot,raw['X'],REPLAY_TOLERANCE)
    dual=verify_sign_convention(snapshot,raw['Pi'],raw['RC'])
    # Independent dual sign/complementarity, separate from RC reconstruction.
    pi=np.asarray(raw['Pi']);rc=np.asarray(raw['RC']);x=np.asarray(raw['X'])
    activity=snapshot.matrix@x;slack=activity-snapshot.rhs
    sign=np.maximum(0.,np.where(snapshot.senses=='<',pi,np.where(snapshot.senses=='>',-pi,0.)))
    bound=np.maximum(np.where(x>snapshot.lower+REPLAY_TOLERANCE,np.maximum(rc,0.),0.),
                     np.where(x<snapshot.upper-REPLAY_TOLERANCE,np.maximum(-rc,0.),0.))
    complementary=np.abs(pi*slack)
    kkt=dict(max_dual_sign_violation=float(sign.max(initial=0)),
        max_reduced_cost_bound_violation=float(bound.max(initial=0)),
        max_complementarity=float(complementary.max(initial=0)))
    kkt['PASS']=max(kkt.values())<=REPLAY_TOLERANCE
    return dict(PASS=primal['PASS'] and dual['PASS'] and kkt['PASS'],
        original_primal=primal,native_dual_reconstruction=dual,dual_KKT=kkt,
        independent_replay_tolerance_unchanged=True,raw_point_modified=False,
        Phi_zero_or_global_LB_claimed=False)

def require_exact_zero(original_verify):
    def verify(master,point,**kwargs):
        result=original_verify(master,point,**kwargs)
        result['PASS']=result['PASS'] and result['exact_arithmetic_zero'] is True
        result['exact_zero_required_by_current_release']=True
        return result
    return verify

def progress_callback(folder,component):
    """Solver diagnostics are never used as feasibility or bound certificates."""
    import gurobipy as gp
    from .table_v_progress import write_progress
    start=time.monotonic();last=[-10.]
    def callback(model,where):
        now=time.monotonic()
        if now-last[0]<2.:return
        fields={}
        if where==gp.GRB.Callback.BARRIER:
            for label,name in (('barrier_iteration','BARRIER_ITRCNT'),('diagnostic_Phi','BARRIER_PRIMOBJ'),
                ('dual_objective','BARRIER_DUALOBJ'),('primal_residual','BARRIER_PRIMINF'),
                ('dual_residual','BARRIER_DUALINF'),('complementarity','BARRIER_COMPL')):
                fields[label]=float(model.cbGet(getattr(gp.GRB.Callback,name)))
        elif where==gp.GRB.Callback.SIMPLEX:
            for label,name in (('simplex_iteration','SPX_ITRCNT'),('diagnostic_Phi','SPX_OBJVAL'),
                ('primal_residual','SPX_PRIMINF'),('dual_residual','SPX_DUALINF')):
                fields[label]=float(model.cbGet(getattr(gp.GRB.Callback,name)))
        else:return
        last[0]=now
        fields={k:v for k,v in fields.items() if math.isfinite(v)}
        write_progress(folder/'SOLVER_PROGRESS.json',dict(component=component,phase_iteration=folder.parent.name,
            observed_wall_seconds=now-start,certified=False,**fields))
    return callback

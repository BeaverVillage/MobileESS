"""Fast elastic LP admission with separate unchanged original certification.

The elastic numerical check uses 1e-5; original P1/FULL, exact zero and rational
Global LB certificates retain their independent requirements and tolerances.
All calls use the same cumulative A-stage ledger.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import time
import numpy as np

VERSION='TABLE_V_SOURCE18R_PHASE_I_V3'
REPLAY_TOLERANCE=1e-5
CERTIFICATION_TOLERANCE=1e-6
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
            Method=2,Threads=1,OutputFlag=1,LogToConsole=0,
            Crossover=-1,BarHomogeneous=-1)

# Restore the recorded Source18r settings, including automatic scaling.
# Later S iterations receive only the remaining shared allowance; a slow solve
# is never interrupted at an arbitrary short per-profile warmup cap.
SOURCE18R_FAST=Policy('SOURCE18R_FAST',-1,1e-6,0,PHASE_I_STAGE_ALLOWANCE,scale=-1)
FAST_B=Policy('FAST_B',-1,1e-8,1,PHASE_I_STAGE_ALLOWANCE)
# A second policy is eligible only for a terminal NUMERIC or independently
# rejected optimal point. TimeLimit never triggers a fresh arithmetic attempt.
POLICIES=(SOURCE18R_FAST,FAST_B)

def allowance(remaining,phase_used):
    """Reserve the original integer search and bound all Phase-I diagnostics."""
    if not all(math.isfinite(float(v)) and v>=0 for v in (remaining,phase_used)):
        raise ValueError('FINITE_NONNEGATIVE_PHASE_I_BUDGET_REQUIRED')
    return max(0.,min(PHASE_I_STAGE_ALLOWANCE-phase_used,remaining-INTEGER_RETURN_RESERVE))

def validate_raw(snapshot,raw,*,tolerance=REPLAY_TOLERANCE):
    from v42_a_stage_phase1.core import primal_replay,verify_sign_convention
    if not all(key in raw for key in ('X','Pi','RC')):
        return dict(PASS=False,reason='OPTIMAL_PRIMAL_DUAL_ATTRIBUTES_REQUIRED')
    primal=primal_replay(snapshot,raw['X'],tolerance)
    dual=verify_sign_convention(snapshot,raw['Pi'],raw['RC'],absolute=tolerance)
    # Independent dual sign/complementarity, separate from RC reconstruction.
    pi=np.asarray(raw['Pi']);rc=np.asarray(raw['RC']);x=np.asarray(raw['X'])
    activity=snapshot.matrix@x;slack=activity-snapshot.rhs
    sign=np.maximum(0.,np.where(snapshot.senses=='<',pi,np.where(snapshot.senses=='>',-pi,0.)))
    bound=np.maximum(np.where(x>snapshot.lower+tolerance,np.maximum(rc,0.),0.),
                     np.where(x<snapshot.upper-tolerance,np.maximum(-rc,0.),0.))
    complementary=np.abs(pi*slack)
    kkt=dict(max_dual_sign_violation=float(sign.max(initial=0)),
        max_reduced_cost_bound_violation=float(bound.max(initial=0)),
        max_complementarity=float(complementary.max(initial=0)))
    kkt['PASS']=max(kkt.values())<=tolerance
    return dict(PASS=primal['PASS'] and dual['PASS'] and kkt['PASS'],
        original_primal=primal,native_dual_reconstruction=dual,dual_KKT=kkt,
        numerical_admission_only=True,replay_tolerance=tolerance,raw_point_modified=False,
        Phi_zero_or_global_LB_claimed=False)

def phase_primal_replay(original):
    """Only elastic Phi LP admission changes; original P1/FULL stays strict."""
    def replay(snapshot,point,tolerance=CERTIFICATION_TOLERANCE):
        if tuple(o.name for o in snapshot.objectives)==('Phi',):
            tolerance=REPLAY_TOLERANCE
        return original(snapshot,point,tolerance)
    return replay

def phase_dual_replay(original):
    def replay(snapshot,pi,rc,**kwargs):
        if tuple(o.name for o in snapshot.objectives)==('Phi',):
            kwargs.setdefault('absolute',REPLAY_TOLERANCE)
        return original(snapshot,pi,rc,**kwargs)
    return replay

def compare_raw(snapshot,raw):
    """Keep the old 1e-6/1e-7 contract independently visible in receipts."""
    from v42_a_stage_phase1.core import verify_sign_convention
    strict=validate_raw(snapshot,raw,tolerance=CERTIFICATION_TOLERANCE)
    if all(k in raw for k in ('X','Pi','RC')):
        strict['native_dual_reconstruction']=verify_sign_convention(snapshot,raw['Pi'],raw['RC'])
        strict['PASS']=all(strict[k]['PASS'] for k in ('original_primal','native_dual_reconstruction','dual_KKT'))
    return dict(numerical_1e5=validate_raw(snapshot,raw),legacy_1e6=strict,
                certified_Global_LB=None,physical_constraints_modified=False)

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

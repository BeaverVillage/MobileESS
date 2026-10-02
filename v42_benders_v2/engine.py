"""Sequential exact loop. Native certificates first, Phase-I only on rejection."""
from time import perf_counter
from pathlib import Path
import numpy as np
import gurobipy as gp
from v42_benders.engine import configure, relative_gap
from v42_benders.certificates import Uncertifiable
from .recourse import Recourse
from .certificates import create
from .independent import verify

def certified(n,raw,kind,known=()):
    cut=create(n,raw,kind);cut['independent_validation']=verify(n,cut,known);return cut

def add_validated_cut(master,x,theta,n,cut,known=()):
    # Replay again at the sole insertion boundary; payload flags alone cannot authorize a cut.
    verify(n,cut,known)
    expr=cut['record']['intercept']+cut['coefficients']@x
    if cut['record']['type']=='optimality':
        if theta is None:raise Uncertifiable('OPTIMALITY_WITHOUT_P1')
        master.addConstr(theta>=expr)
    else:master.addConstr(expr>=0)

def solve(n,*,env,directory,seconds=60,threads=1,feasibility=False,known=(),validate=None,
          warm_start=None,initial_lower=0.,initial_upper=None,target_gap=.005):
    start=perf_counter();directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    master=gp.Model('V2_COMPLETE_ROUTE_MODE_MASTER',env=env);configure(master,threads,seconds,directory/'master.log')
    x=master.addMVar(len(n.xi),lb=n.xlower,ub=n.xupper,vtype='B')
    dr=np.flatnonzero(np.diff(n.A.indptr)==0)
    master.addMConstr(n.B[dr],x,n.sense[dr],n.b[dr])
    theta=None if feasibility else master.addVar(lb=initial_lower,name='theta_rho')
    master.setObjective(0. if feasibility else theta)
    best=None;upper=None;lower=None if feasibility else initial_lower
    if initial_upper is not None:
        if validate is None or warm_start is None:raise ValueError('UB_REQUIRES_INDEPENDENT_COMPLETE_WITNESS')
        z=np.asarray(warm_start);check=validate(z)
        if len(z)!=len(n.names) or not check.get('PASS') or n.residual(z[n.xi],z[n.yi])>1e-7 or np.max(abs(z[n.xi]-np.rint(z[n.xi])),initial=0)>1e-7:
            raise ValueError('INVALID_WARM_UB')
        if abs(float(n.c@z[n.yi]+n.objective_constant)-initial_upper)>1e-7:raise ValueError('UB_OBJECTIVE')
        upper=initial_upper;best=z.copy();x.Start=z[n.xi];theta.Start=upper
    native=Recourse(n,env,directory/'native',threads,objective=not feasibility);phase=None
    cuts=[];seen=set();progress=[];iteration=0;status='TIME_LIMIT';fallbacks=0
    try:
        while perf_counter()-start<seconds:
            iteration+=1;master.Params.TimeLimit=max(.001,seconds-(perf_counter()-start));master.optimize()
            row=dict(iteration=iteration,master_status=master.Status,master_seconds=master.Runtime,recourse_status=None,cut_hash=None)
            progress.append(row)
            if master.Status==3:
                if upper is not None:raise Uncertifiable('BOUND_CONTRADICTION')
                status='MASTER_INFEASIBLE';break
            if master.Status in [4,11,12]:raise Uncertifiable('UNSAFE_MASTER_STATUS')
            if not feasibility:
                if np.isfinite(master.ObjBound) and abs(master.ObjBound)<1e90:lower=max(lower,float(master.ObjBound))
                if upper is not None and relative_gap(upper,lower)<=target_gap:status='ACCEPTED_P1';break
            if not master.SolCount:break
            xv=np.asarray(x.X)
            if np.max(abs(xv-np.rint(xv)),initial=0)>1e-7:raise Uncertifiable('NONINTEGER_MASTER')
            xv=np.rint(xv);raw=native.solve(xv,seconds-(perf_counter()-start));row['recourse_status']=raw['status']
            if raw['status']==2:
                if not native.primal_valid(raw):raise Uncertifiable('NATIVE_PRIMAL')
                z=n.assemble(xv,np.asarray(raw['primal']));check=validate(z) if validate else dict(PASS=n.residual(xv,z[n.yi])<=1e-7)
                if not check.get('PASS'):raise Uncertifiable('INDEPENDENT_PHYSICS_WITNESS')
                if feasibility:best=z;status='FEASIBLE_WITNESS';break
                value=raw['objective']
                if upper is None or value<upper:upper=value;best=z
                cut=certified(n,raw,'optimality',known)
            elif raw['status']==3:
                try:cut=certified(n,raw,'native_farkas',known)
                except (Uncertifiable,TypeError,KeyError) as e:
                    row['native_rejection']=str(e);fallbacks+=1
                    if perf_counter()-start>=seconds:status='NATIVE_REJECTED_NO_FALLBACK_BUDGET';break
                    if phase is None:phase=Recourse(n,env,directory/'phase1',threads,phase=True)
                    aux=phase.solve(xv,seconds-(perf_counter()-start))
                    if not phase.primal_valid(aux):raise Uncertifiable('PHASE1_NONTERMINAL_OR_PRIMAL')
                    cut=certified(n,aux,'phase1',known)
            else:status='RECOURSE_NONTERMINAL_NO_CUT';break
            if cut['record']['cut_hash'] in seen:raise Uncertifiable('DUPLICATE_CUT_WITHOUT_PROGRESS')
            add_validated_cut(master,x,theta,n,cut,known)
            cuts.append(cut);seen.add(cut['record']['cut_hash']);row['cut_hash']=cut['record']['cut_hash']
            row.update(lower=lower,upper=upper)
        return dict(status=status,iterations=iteration,seconds=perf_counter()-start,lower=lower,upper=upper,
            gap=None if feasibility else relative_gap(upper,lower),valid_cuts=len(cuts),
            feasibility_cuts=sum(c['record']['type']=='feasibility' for c in cuts),
            optimality_cuts=sum(c['record']['type']=='optimality' for c in cuts),
            phase1_cuts=sum(c['record']['kind']=='phase1' for c in cuts),fallback_calls=fallbacks,
            progress=progress,uncertified_cuts_used=0),best,cuts
    except Uncertifiable as e:
        return dict(status='STOP_UNCERTIFIABLE',reason=str(e),iterations=iteration,lower=None,upper=upper,
            gap=None,progress=progress,valid_cuts=len(cuts),uncertified_cuts_used=0),best,cuts
    finally:
        native.close()
        if phase is not None:phase.close()
        master.dispose()

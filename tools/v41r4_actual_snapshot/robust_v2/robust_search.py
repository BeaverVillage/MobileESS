"""Frozen deterministic full-domain Q search. No DA or active-power variables."""
from common import *
import inspect,time,itertools
import numpy as np
from scipy.optimize import minimize
from scipy.stats import qmc
import qsafe as kernel
from qsafe import q_bounds,feasible,constraints

METHOD=read(OUT/'METHOD_FREEZE.json');RULES=METHOD['search']
assert METHOD['version']=='V41R4_ACTUAL_ETA95_QSAFE_ROBUST_V2'
PAPER_WORDING=METHOD['paper_facing_wording']

def correct_slot(evaluate,q_original,lower,upper,q_da=None):
    q0=np.asarray(q_original).copy();reference=np.asarray(q_da if q_da is not None else q0).copy()
    idx=np.flatnonzero(upper>lower+1e-10);cache={};solvers=[];phase='FROZEN_Q_FIRST';cap=RULES['stopping']['unique_exact_Q_trial_cap']
    started=time.perf_counter();budget_reached=False;phase_counts={};optimizer_calls=0
    class BudgetReached(Exception):pass
    def objective(q):return float(np.sum((q-reference)**2))
    def penalty(r):
        g=constraints(r);negative=np.maximum(-g,0)
        return float(negative@negative)
    def ev(q):
        q=np.asarray(q,dtype=float).copy()
        assert q.shape==q0.shape and np.all(np.isfinite(q))
        assert np.all(q>=lower-1e-9) and np.all(q<=upper+1e-9)
        key=q.tobytes()
        if key not in cache:
            if len(cache)>=cap:raise BudgetReached()
            r=evaluate(q);cache[key]=(q,r,penalty(r),objective(q))
            phase_counts[phase]=phase_counts.get(phase,0)+1
        return cache[key][1]
    baseline=ev(q0)
    if feasible(baseline):
        return q0,baseline,dict(status='UNCHANGED',optimizer_calls=0,evaluations=1,robust_search_triggered=False,search_runtime_seconds=time.perf_counter()-started)
    if not len(idx):
        return q0,baseline,dict(status='ROBUST_Q_ONLY_UNRESOLVED',optimizer_calls=0,evaluations=1,robust_search_triggered=True,reason='NO_CONNECTED_Q_VARIABLE',search_runtime_seconds=time.perf_counter()-started)
    def full(u):
        q=lower.copy();q[idx]=lower[idx]+np.asarray(u)*(upper[idx]-lower[idx]);return np.minimum(np.maximum(q,lower),upper)
    def unit(q):return (np.asarray(q)[idx]-lower[idx])/(upper[idx]-lower[idx])
    def rank(item):return (item[2],item[3],tuple(item[0]))
    def ranked():return sorted(cache.values(),key=rank)
    def separated(points,limit,distance):
        result=[]
        for item in points:
            u=unit(item[0])
            if all(np.linalg.norm(u-unit(prior[0]))>distance for prior in result):result.append(item)
            if len(result)==limit:break
        return result
    try:
        phase='EXTREME_AND_ZERO_SCREENING'
        ev(lower);ev(upper);ev(np.clip(np.zeros_like(q0),lower,upper))
        phase='FULL_DOMAIN_COARSE_GRID'
        for u in itertools.product(RULES['coarse_grid']['unit_coordinates'],repeat=len(idx)):ev(full(u))
        phase='FULL_DOMAIN_SOBOL'
        sampler=qmc.Sobol(d=len(idx),scramble=RULES['Sobol']['scramble'],seed=RULES['Sobol']['seed'])
        for u in sampler.random_base2(8):ev(full(u))
        starts=[]
        for q in (q0,lower,np.clip(np.zeros_like(q0),lower,upper)):
            if not any(np.array_equal(q,s) for s in starts):starts.append(q.copy())
        signatures=set()
        for q,r,p,o in ranked():
            sig=tuple(r['taps'])
            if sig not in signatures and not any(np.array_equal(q,s) for s in starts):starts.append(q.copy());signatures.add(sig)
            if len(starts)>=RULES['multistart']['max_starts']:break
        for i,seed in enumerate(starts):
            phase=f'MULTISTART_POWELL_{i}';n=len(cache);rule=RULES['multistart']
            optimizer_calls+=1
            res=minimize(lambda u:penalty(ev(full(u))),unit(seed),method='Powell',bounds=[(0,1)]*len(idx),options={k:rule[k] for k in ('maxiter','maxfev','xtol','ftol')})
            final=ev(full(res.x));solvers.append(dict(stage=phase,success=bool(res.success),message=str(res.message),iterations=int(res.nit),evaluations=len(cache)-n,feasible=feasible(final)))
        for radius in RULES['progressive_refinement']['unit_radii']:
            phase=f'PROGRESSIVE_REFINEMENT_{radius}'
            centers=separated(ranked(),RULES['progressive_refinement']['max_centers'],.15)
            for q,r,p,o in centers:
                u=unit(q)
                for j in range(len(idx)):
                    for sign in (-1,1):
                        trial=u.copy();trial[j]=np.clip(trial[j]+sign*radius,0,1);ev(full(trial))
                for delta in itertools.product((-radius,radius),repeat=len(idx)):ev(full(np.clip(u+delta,0,1)))
        feasible_candidates=[item for item in cache.values() if feasible(item[1])]
        order=sorted(feasible_candidates,key=lambda x:(x[3],tuple(x[0]))) if feasible_candidates else ranked()
        local_starts=separated(order,RULES['local_refinement']['max_starts'],.025)
        bounds=list(zip(lower[idx]/400,upper[idx]/400));reference_x=reference[idx]/400
        def q_from_x(x):
            q=lower.copy();q[idx]=np.asarray(x)*400;return np.minimum(np.maximum(q,lower),upper)
        def fun(x):return .5*objective(q_from_x(x))/400**2
        def jac(x):return np.asarray(x)-reference_x
        def con(x):return constraints(ev(q_from_x(x)))
        def cj(x):
            g=con(x);derivative=np.zeros((len(g),len(idx)));h=RULES['local_refinement']['finite_difference_step_kvar']/400
            for j,(lo,hi) in enumerate(bounds):
                xp=x.copy();xm=x.copy();xp[j]=min(hi,x[j]+h);xm[j]=max(lo,x[j]-h)
                derivative[:,j]=(con(xp)-con(xm))/(xp[j]-xm[j])
            return derivative
        for i,(q,r,p,o) in enumerate(local_starts):
            phase=f'LOCAL_DEVIATION_SLSQP_{i}';n=len(cache);rule=RULES['local_refinement']
            optimizer_calls+=1
            res=minimize(fun,q[idx]/400,jac=jac,bounds=bounds,constraints=[dict(type='ineq',fun=con,jac=cj)],method='SLSQP',options=dict(maxiter=rule['maxiter'],ftol=rule['ftol'],disp=False))
            final=ev(q_from_x(res.x));solvers.append(dict(stage=phase,success=bool(res.success),message=str(res.message),iterations=int(res.nit),evaluations=len(cache)-n,feasible=feasible(final),objective_Q_deviation=objective(q_from_x(res.x))))
    except BudgetReached:budget_reached=True
    candidates=[item for item in cache.values() if feasible(item[1])]
    proof=dict(robust_search_triggered=True,optimizer_calls=optimizer_calls,evaluations=len(cache),unique_Q_trials=len(cache),phase_trial_counts=phase_counts,solvers=solvers,budget_reached=budget_reached,stopping_phase=phase,feasible_candidates_found=len(candidates),search_runtime_seconds=time.perf_counter()-started,optimality=PAPER_WORDING,global_minimum_proven=False,Q_DA_reference=reference.tolist())
    if candidates:
        q,r,p,o=min(candidates,key=lambda x:(x[3],tuple(x[0])))
        # This uncached exact AC solve also restores the identical approved start state.
        final=evaluate(q.copy());assert feasible(final)
        assert np.array_equal(final['v'],r['v']) and np.array_equal(final['ipu'],r['ipu']) and final['taps']==r['taps'],'SELECTED_Q_EXACT_REVALIDATION_MISMATCH'
        proof.update(status='Q_CORRECTED',evaluations=len(cache)+1,sum_squared_delta_Q=o,final_exact_validation=True,search_runtime_seconds=time.perf_counter()-started)
        return q.copy(),final,proof
    proof.update(status='ROBUST_Q_ONLY_UNRESOLVED',reason='PRESCRIBED_ROBUST_SEARCH_FOUND_NO_AC_FEASIBLE_Q; not a proof of physical infeasibility; original physical Q and fixed P retained',final_exact_validation=False)
    return q0,baseline,proof

# Keep the independently verified engine, prefix restoration and audit machinery.
source=inspect.getsource(kernel.run_qsafe)
source=source.replace('def run_qsafe(context,voltage,trajectory,connected,authority,folder):','def run_qsafe(context,voltage,trajectory,connected,authority,folder,q_da=None):')
source=source.replace("initialq=trajectory.mess_q_kvar.copy();fixedp=trajectory.mess_p_kw.copy();fixedaidc=trajectory.pcc_p_kw.copy()","initialq=trajectory.mess_q_kvar.copy();fixedp=trajectory.mess_p_kw.copy();fixedaidc=trajectory.pcc_p_kw.copy();reference=initialq.copy() if q_da is None else np.asarray(q_da).copy()")
source=source.replace('correct_slot(lambda q:e.evaluate(t,q),initialq[t],lo,hi)','correct_slot(lambda q:e.evaluate(t,q),initialq[t],lo,hi,q_da=reference[t])')
source=source.replace('Q_ONLY_INFEASIBLE','ROBUST_Q_ONLY_UNRESOLVED')
namespace={**vars(kernel),'correct_slot':correct_slot}
exec(compile(source,__file__+'::sequential_runner','exec'),namespace)
run_qsafe=namespace['run_qsafe']

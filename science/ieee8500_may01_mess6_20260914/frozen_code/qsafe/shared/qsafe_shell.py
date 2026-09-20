"""Fleet-independent deviation-shell search over an injected exact evaluator."""
import itertools,time
import numpy as np
from scipy.optimize import minimize

VERSION='QSAFE_V2_LEGACY_EXACT_DEVIATION_SHELL_V1'

def coarse_shells(lower,upper,reference,coordinates):
    lower=np.asarray(lower);upper=np.asarray(upper);reference=np.asarray(reference)
    idx=np.flatnonzero(upper>lower+1e-10)
    points=[]
    for u in itertools.product(coordinates,repeat=len(idx)):
        q=lower.copy();q[idx]=lower[idx]+np.asarray(u)*(upper[idx]-lower[idx])
        points.append((float(np.sum((q-reference)**2)),tuple(q),q))
    points.sort(key=lambda p:(p[0],p[1]))
    # Equality is the existing floating-point objective value, with no new
    # tolerance or rounding that could merge different-deviation shells.
    for deviation,group in itertools.groupby(points,key=lambda p:p[0]):
        yield deviation,[p[2] for p in group]

def correct_slot(evaluate,q_original,lower,upper,*,q_da=None,rules,feasible,constraints,evaluate_many=None,progress=None,refine=True):
    started=time.perf_counter();q0=np.asarray(q_original).copy();reference=np.asarray(q_da if q_da is not None else q0).copy()
    lower=np.asarray(lower);upper=np.asarray(upper);idx=np.flatnonzero(upper>lower+1e-10)
    assert q0.shape==lower.shape==upper.shape==reference.shape
    cache={};evaluations=0;shells=[];q1_feasible=[];local_evals=0;phase='FROZEN_Q_FIRST'
    def emit(**kw):
        if progress:progress(dict(phase=phase,evaluations=evaluations,refinement_evaluations=local_evals,elapsed_s=time.perf_counter()-started,**kw))
    def objective(q):return float(np.sum((q-reference)**2))
    def ev_many(qs):
        nonlocal evaluations,local_evals
        pending=[];seen=set()
        for q in qs:
            q=np.asarray(q,dtype=float)
            assert np.isfinite(q).all() and np.all(q>=lower-1e-9) and np.all(q<=upper+1e-9)
            key=q.tobytes()
            if key not in cache and key not in seen:pending.append(q.copy());seen.add(key)
        results=(evaluate_many(pending) if evaluate_many else [evaluate(q) for q in pending]) if pending else []
        assert len(results)==len(pending)
        for q,r in zip(pending,results):
            cache[q.tobytes()]=(q,r,objective(q));evaluations+=1
            if phase=='Q2_LOCAL_REFINEMENT':local_evals+=1
        emit()
        return [cache[np.asarray(q,dtype=float).tobytes()][1] for q in qs]
    def ev(q):return ev_many([q])[0]
    baseline=ev(q0)
    if feasible(baseline):
        return q0,baseline,dict(status='UNCHANGED',version=VERSION,evaluations=evaluations,optimizer_calls=0,shells=[],refinement_evaluations=0,robust_search_triggered=False,search_runtime_seconds=time.perf_counter()-started)
    if not len(idx):
        return q0,baseline,dict(status='ROBUST_Q_ONLY_UNRESOLVED',version=VERSION,evaluations=evaluations,optimizer_calls=0,reason='NO_CONNECTED_Q_VARIABLE',shells=[],refinement_evaluations=0,robust_search_triggered=True)
    phase='Q1_MINIMUM_DEVIATION_SHELL';first=None;tested=0
    for shell_index,(deviation,qs) in enumerate(coarse_shells(lower,upper,reference,rules['coarse_grid']['unit_coordinates'])):
        # The entire shell is evaluated before any feasible result can terminate Q1.
        results=ev_many(qs);good=[q for q,r in zip(qs,results) if feasible(r)];tested+=len(qs)
        entry=dict(shell_index=shell_index,deviation=deviation,candidates=len(qs),feasible_candidates=len(good))
        shells.append(entry);emit(shell=entry,shells_visited=len(shells),coarse_candidates=tested)
        if good:
            first=shell_index;q1_feasible=good;break
    q1_evaluations=evaluations
    # Existing SLSQP refinement: objective, feasible domain, bound-aware central
    # differences, step, maxiter/ftol and deterministic separated-start rule.
    # It has its own stage and is never suppressed by a coarse evaluation cap.
    phase='Q2_LOCAL_REFINEMENT';rule=rules['local_refinement'];solvers=[]
    ranked=sorted(cache.values(),key=lambda x:(x[2],tuple(x[0])))
    feasible_points=[x for x in ranked if feasible(x[1])]
    if feasible_points:order=feasible_points
    else:order=sorted(ranked,key=lambda x:(float(np.maximum(-constraints(x[1]),0)@np.maximum(-constraints(x[1]),0)),x[2],tuple(x[0])))
    starts=[]
    for q,r,o in order:
        u=(q[idx]-lower[idx])/(upper[idx]-lower[idx])
        if all(np.linalg.norm(u-(s[idx]-lower[idx])/(upper[idx]-lower[idx]))>.025 for s in starts):starts.append(q)
        if len(starts)>=rule['max_starts']:break
    bounds=list(zip(lower[idx]/400,upper[idx]/400));refx=reference[idx]/400
    def full(x):
        q=lower.copy();q[idx]=np.asarray(x)*400;return np.minimum(np.maximum(q,lower),upper)
    def fun(x):return .5*objective(full(x))/400**2
    def jac(x):return np.asarray(x)-refx
    def con(x):return constraints(ev(full(x)))
    def cj(x):
        g=con(x);h=rule['finite_difference_step_kvar']/400;points=[];spans=[]
        for j,(lo,hi) in enumerate(bounds):
            xp=x.copy();xm=x.copy();xp[j]=min(hi,x[j]+h);xm[j]=max(lo,x[j]-h)
            points.extend((full(xp),full(xm)));spans.append(xp[j]-xm[j])
        rs=ev_many(points)
        return np.column_stack([(constraints(rs[2*j])-constraints(rs[2*j+1]))/span for j,span in enumerate(spans)])
    if refine:
        for i,q in enumerate(starts):
            before=evaluations
            res=minimize(fun,q[idx]/400,jac=jac,bounds=bounds,constraints=[dict(type='ineq',fun=con,jac=cj)],method='SLSQP',options=dict(maxiter=rule['maxiter'],ftol=rule['ftol'],disp=False))
            final=ev(full(res.x));solvers.append(dict(start=i,success=bool(res.success),message=str(res.message),iterations=int(res.nit),evaluations=evaluations-before,feasible=feasible(final)))
            emit(refinement_solver=solvers[-1])
    good=[x for x in cache.values() if feasible(x[1])]
    proof=dict(version=VERSION,robust_search_triggered=True,evaluations=evaluations,unique_Q_trials=len(cache),connected_dimension=len(idx),complete_coarse_domain=len(rules['coarse_grid']['unit_coordinates'])**len(idx),global_candidate_cap=None,wall_time_stop=False,shells=shells,shells_visited=len(shells),coarse_candidates=tested,first_feasible_shell=first,feasible_candidates_in_selected_shell=len(q1_feasible),coarse_evaluations=q1_evaluations,refinement_evaluations=local_evals,refinement_starts=len(starts) if refine else 0,optimizer_calls=len(solvers),solvers=solvers,Q_DA_reference=reference,search_runtime_seconds=time.perf_counter()-started)
    if good:
        q,r,o=min(good,key=lambda x:(x[2],tuple(x[0])))
        phase='FINAL_FULL_CHRONOLOGICAL_VALIDATION';fresh=evaluate(q.copy());evaluations+=1
        assert feasible(fresh),'FINAL_EXACT_NOT_FEASIBLE'
        assert np.array_equal(fresh['v'],r['v']) and np.array_equal(fresh['ipu'],r['ipu']) and fresh['taps']==r['taps'],'SELECTED_Q_EXACT_REVALIDATION_MISMATCH'
        proof.update(status='Q_CORRECTED',evaluations=evaluations,final_exact_validation=True,selected_Q=q,sum_squared_delta_Q=o,search_runtime_seconds=time.perf_counter()-started)
        return q.copy(),fresh,proof
    proof.update(status='ROBUST_Q_ONLY_UNRESOLVED',reason='SEARCH_FOUND_NO_EXACT_FEASIBLE_Q',final_exact_validation=False)
    return q0,baseline,proof

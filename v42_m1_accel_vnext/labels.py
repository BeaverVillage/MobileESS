"""Exact LP-valued binary labels; no SOC lattice and no heuristic dominance.

This is a coverage prototype, not a claim of a polynomial shortest-path solver.
Every binary prefix retains the full original continuous polyhedron. Splitting
an unfixed binary at 0/1 covers every original integer continuation exactly.
Only an exact residual-corrected LP dual lower bound can prune by cost. Full-scale
incomplete search bounds/candidates are diagnostics, never a D-W certificate.
"""
from fractions import Fraction as F
import heapq
import time
import numpy as np
import gurobipy as gp
from v42_dw_root.models import build
from v42_dw_bound.certificate import global_dual

def solve(A,d,seconds=60.,validator=None,seed=None,guard=None,log=None):
    start=time.perf_counter();integers=np.flatnonzero(d['types']!='C')
    assert np.all(d['types'][integers]=='B')
    assert np.isfinite(d['lower']).all() and np.isfinite(d['upper']).all()
    assert np.max(abs(d['upper']))<1e90 and np.max(abs(d['lower']))<1e90
    relaxed=dict(d,types=np.full(len(d['types']),'C',dtype='<U1'))
    m=build(A,relaxed,'EXACT_LP_VALUED_LABELS');variables=m.getVars()
    for p,v in dict(Threads=1,Method=2,Crossover=1,BarConvTol=1e-11,
                    FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,InfUnbdInfo=1).items():m.setParam(p,v)
    if log:m.Params.LogFile=str(log)
    best=None;best_x=None
    if seed is not None and (validator is None or validator(seed)):
        best=sum((F(float(c))*F(float(x)) for c,x in zip(d['objective'],seed)),F(float(d['constant'])))
        best_x=seed.copy()
    frontier=[(-float('inf'),0,{},None)];counter=1;completed=0;LP_calls=0;native=0.;pruned=0;unresolved=[]
    root_bound=None;errors=[]
    try:
        while frontier and time.perf_counter()-start<seconds and not (guard and guard.cancel.is_set()):
            _,_,fixed,inherited=heapq.heappop(frontier)
            if best is not None and inherited is not None and inherited>=best:pruned+=1;continue
            lo=d['lower'].copy();hi=d['upper'].copy()
            for j,v in fixed.items():lo[j]=hi[j]=v
            m.setAttr('LB',variables,lo.tolist());m.setAttr('UB',variables,hi.tolist())
            m.Params.TimeLimit=max(.001,min(20.,seconds-(time.perf_counter()-start)))
            if guard:guard.active=m
            tick=time.perf_counter();m.optimize();native+=time.perf_counter()-tick;LP_calls+=1
            if guard:guard.active=None
            if m.Status==3:
                # An independently verified Farkas contradiction is needed.
                y=np.asarray(m.getAttr('FarkasDual'));a=np.asarray(A.T@y).ravel()
                # Exact arithmetic; >= rows have negative multipliers here.
                sign=np.all(y[d['sense']=='<']>=0) and np.all(y[d['sense']=='>']<=0)
                coeff={};rhs=F(0)
                for i in np.flatnonzero(y):
                    q=F(float(y[i]));rhs+=q*F(float(d['rhs'][i]))
                    for j,w in zip(A.indices[A.indptr[i]:A.indptr[i+1]],A.data[A.indptr[i]:A.indptr[i+1]]):coeff[int(j)]=coeff.get(int(j),F(0))+q*F(float(w))
                minimum=sum((q*F(float(lo[j] if q>=0 else hi[j])) for j,q in coeff.items()),F(0))
                if sign and minimum>rhs:pruned+=1;continue
                unresolved.append((fixed,inherited));errors.append('FARKAS_NOT_CERTIFIED');continue
            if m.Status!=2:
                unresolved.append((fixed,inherited));errors.append('NONOPTIMAL_LABEL_LP');break
            bound,proof=global_dual(A,d,np.asarray(m.getAttr('Pi')),lo,hi)
            if not fixed:root_bound=float(bound)
            if best is not None and bound>=best:pruned+=1;continue
            x=np.asarray(m.getAttr('X'));rounded=x.copy();rounded[integers]=np.rint(x[integers])
            if (validator is None and np.array_equal(x[integers],rounded[integers])) or (validator is not None and validator(rounded)):
                value=sum((F(float(c))*F(float(v)) for c,v in zip(d['objective'],rounded)),F(float(d['constant'])))
                if best is None or value<best:best=value;best_x=rounded.copy()
            unfixed=[int(j) for j in integers if j not in fixed]
            fractional=[j for j in unfixed if x[j]!=round(x[j])]
            if not fractional:
                if best is not None and bound>=best-F(1e-8):completed+=1;continue
                if not unfixed:unresolved.append((fixed,bound));errors.append('LEAF_DUAL_GAP');continue
                j=unfixed[0]
            else:j=max(fractional,key=lambda k:min(x[k],1-x[k]))
            for value in (0.,1.):
                f=dict(fixed);f[j]=value
                heapq.heappush(frontier,(float(bound),counter,f,bound));counter+=1
        unresolved_bounds=[p[3] for p in frontier]+[b for _,b in unresolved]
        complete=not frontier and not unresolved and not errors
        return dict(status='COMPLETE_WITH_NUMERICAL_CONTRACT' if complete else 'INCOMPLETE_EXACT_DOMAIN_SEARCH',
            exact_domain_cover=True,SOC_discretization=False,LP_calls=LP_calls,labels_generated=counter,
            labels_remaining=len(frontier)+len(unresolved),pruned_with_certificate=pruned,completed=completed,
            optimum=float(best) if complete and best is not None else None,incumbent=float(best) if best is not None else None,
            root_residual_corrected_LP_bound=root_bound,global_frontier_bound=None if any(b is None for b in unresolved_bounds) else float(min(unresolved_bounds+[best] if best is not None else unresolved_bounds)) if unresolved_bounds else float(best) if best is not None else None,
            native_seconds=native,wall_seconds=time.perf_counter()-start,errors=errors,
            scientific_DW_certificate_eligible=False),best_x
    finally:
        if guard:guard.active=None
        m.dispose()

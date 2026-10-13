"""Bounded final-admission LP with joint P/Q/SOC redispatch, heuristic only.

Beam labels and their width/depth remain unchanged. This small relaxation uses
all selected critical rows (all96 slots), original PCS envelope, efficiency,
travel energy and terminal SOC. It is never an original FULL UB or global LB.
"""
import time
import warnings
import numpy as np
from scipy import sparse
from scipy.optimize import linprog,OptimizeWarning
from scipy.spatial import ConvexHull
from v42_pr134_b1.common import atomic,read
from tools.minimax_beam1800.grid import Minimax
from tools.global_local_multistart1800.dag import Graph
from tools.global_local_multistart1800.joint import path_signature,pool_signature


class DispatchScore:
    def __init__(self,case,point,context):
        if {r['slot'] for r in context['rows']}!=set(range(96)):
            raise ValueError('REDISPATCH_ALL96_CRITICAL_COVERAGE_REQUIRED')
        self.base=Minimax(case,point,context);self.case=case;self.cache={};self.seconds=0.
        self.rows=context['rows'];self.graph=Graph(case)
        self.planes=ConvexHull(self.base.vertices).equations

    def score(self,paths):
        key=tuple((u,path_signature(paths[u])) for u in sorted(paths))
        if key in self.cache:return self.cache[key]
        begin=time.perf_counter();b=self.case.graph[3];units=sorted(paths)
        # Four96-slot Pch/Pdis/Q schedules and97-slot SOC, plus minimax rho.
        stride=96*3+97;n=4*stride+1;rho=n-1
        lo=np.full(n,-np.inf);hi=np.full(n,np.inf);eqr=[];eqc=[];eqv=[];rhs=[]
        def equality(terms,value):
            row=len(rhs)
            for col,v in terms: eqr.append(row);eqc.append(col);eqv.append(v)
            rhs.append(value)
        rows=[];cols=[];vals=[];ub=[]
        def inequality(terms,value):
            row=len(ub)
            for col,v in terms:
                if v:rows.append(row);cols.append(col);vals.append(v)
            ub.append(value)
        connections={}
        for ui,u in enumerate(units):
            self.graph.validate(u,paths[u]);connected=np.full(96,-1,dtype=int);energy=np.zeros(96)
            for k in paths[u]:
                a=self.case.graph[2][k]
                if a[-1] is None:connected[a[1]]=self.base.site_id[a[0]]
                else:energy[a[1]]+=float(a[-1].energy_kwh)
            connections[u]=connected;offset=ui*stride
            for t in range(96):
                pch,pdis,q=offset+3*t,offset+3*t+1,offset+3*t+2
                lo[pch:pdis+1]=0.;hi[pch:pdis+1]=b.p_limit if connected[t]>=0 else 0.
                if connected[t]<0:lo[q]=hi[q]=0.
                else:
                    inequality([(pch,1.),(pdis,1.)],b.p_limit)
                    for a,c,d in self.planes:
                        inequality([(pch,-a),(pdis,a),(q,c)],-d)
                s=offset+288+t
                equality([(s+1,1.),(s,-1.),(pch,-b.dt_hours*b.eta_charge),
                    (pdis,b.dt_hours/b.eta_discharge)],-energy[t])
            lo[offset+288:offset+385]=b.minimum;hi[offset+288:offset+385]=b.maximum
            equality([(offset+288,1.)],b.initial)
            lo[offset+384]=max(b.minimum,b.terminal)
        for ri,row in enumerate(self.rows):
            terms=[(rho,-1.)];t=row['slot']
            for ui,u in enumerate(units):
                si=connections[u][t]
                if si>=0:terms.extend((ui*stride+3*t+fi,float(self.base.coeff[ui,si,ri,fi])) for fi in range(3))
            inequality(terms,-float(self.base.base[ri]))
        objective=np.zeros(n);objective[rho]=1.
        with warnings.catch_warnings():
            # scipy forwards native HiGHS options after this expected warning.
            warnings.filterwarnings('ignore',category=OptimizeWarning,message='Unrecognized options detected.*')
            result=linprog(objective,A_ub=sparse.csr_matrix((vals,(rows,cols)),shape=(len(ub),n)),b_ub=ub,
                A_eq=sparse.csr_matrix((eqv,(eqr,eqc)),shape=(len(rhs),n)),b_eq=rhs,
                bounds=list(zip(lo,hi)),method='highs',options={'time_limit':2.,'threads':1})
        elapsed=time.perf_counter()-begin;self.seconds+=elapsed
        value=float(result.fun) if result.success else None
        self.cache[key]=dict(score=value,LP_status=int(result.status),LP_wall_seconds=elapsed,
            heuristic_only=True,continuous_Mode_relaxation=True,full_grid_not_checked=True,
            all_four_PQ_SOC_redispatched=True,Original_FULL_UB=False,Global_LB=False)
        return self.cache[key]


def refine(case,point,context,pools,docs,epoch):
    """Rescore a bounded shortlist; pin STAY/current/authority, keep MOVE classes."""
    scorer=DispatchScore(case,point,context);graph=scorer.graph
    from tools.minimax_beam1800.adapter import current_paths
    from tools.adaptive_compact_joint import beam
    base=current_paths(case,point)
    authority=current_paths(case,beam.v.load_point(beam.ROOT/beam.RAW_REL))
    moving_raw=docs/'BEST_MOVING_INCUMBENT.npz'
    moving_authority=current_paths(case,beam.v.load_point(moving_raw)) if moving_raw.exists() else None
    result={};diagnostics=[]
    # Original Beam already supplies diverse eight-route choices. Add the first
    # four heuristic reservoir finalists, rather than solving thousands of LPs.
    reservoir=docs/'BEAM_RESERVOIR.json'
    extra=read(reservoir)['units'] if reservoir.exists() else {}
    for u in sorted(pools):
        options=list(pools[u]);existing={path_signature(p) for p in options}
        if u in extra:
            ranked=sorted((scorer.base.peak(dict(base,**{u:p}))[0],sig,p) for sig,p in extra[u].items() if sig not in existing)
            options.extend(p for _,_,p in ranked[:4])
        chosen=[];seen=set()
        def add(p):
            sig=path_signature(p)
            if sig not in seen:chosen.append(p);seen.add(sig)
        add(authority[u]);add(base[u]);add(graph.complete(u,[]))
        if moving_authority is not None:
            add(moving_authority[u])
            if moving_authority[u] not in options:options.append(moving_authority[u])
        ranked=[]
        for p in options:
            q=scorer.score(dict(base,**{u:p}));sig=path_signature(p)
            diagnostics.append(dict(unit=u,signature=sig,**q))
            # LP failure is inconclusive, never exact exclusion or feasibility.
            fallback=scorer.base.peak(dict(base,**{u:p}))[0]
            ranked.append((q['score'] if q['score'] is not None else fallback,sig,p))
        ranked.sort(key=lambda x:x[:2])
        for predicate in (lambda p:len(graph.move_indices(p))==1,lambda p:len(graph.move_indices(p))>=2):
            candidates=[p for _,sig,p in ranked if sig not in seen and predicate(p)]
            if candidates:add(candidates[0])
        for _,sig,p in ranked:
            if len(chosen)>=8:break
            add(p)
        assert len(chosen)==8 and all(p in chosen for p in (authority[u],base[u],graph.complete(u,[])))
        result[u]=chosen
    atomic(docs/f'REDISPATCH_ADMISSION_{epoch:03d}.json',dict(PASS=True,pools=result,
        pool_signature=pool_signature(result),old_pool_signature=pool_signature(pools),candidates=diagnostics,
        candidate_LP_calls=len(scorer.cache),LP_wall_seconds=scorer.seconds,Native_optimize_calls=0,
        no_MOVE_forcing=True,all_four_route_decisions_free=True,score_is_not_UB_or_Global_LB=True))
    return result,pool_signature(result)

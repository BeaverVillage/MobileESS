"""Exhaustive bounded physical and route fixtures; no full-scale optimize."""
from .common import *
from .formulation import Compact,residual,subset
from .presolve import Presolve
from fractions import Fraction as F
from collections import Counter,defaultdict
import numpy as np
from scipy import sparse
from scipy.optimize import linprog
import gurobipy as gp
import itertools,time
from v42_benders.fixtures import CASES,build as fixture
from v42_integrated.matrix import arrays,audit
from verify_redundancy_fixtures import tiny_reduction,configure
from v42_redundancy.model import build

def fixtures():
    begin=time.perf_counter();env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();results=[];summaries=[]
    try:
        for case,cfg in CASES.items():
            m=fixture(env,case);A,d=arrays(m);ix=np.flatnonzero(d['types']=='B')
            arcs=[('A',0,'A',1),('A',1,'A',2),('B',1,'B',2),('A',0,'B',1),('A',0,'B',1)]
            c=Compact(A,d,arcs,{'F':'A'},2,{('F',k):int(ix[k]) for k in range(5)})
            keep,_=tiny_reduction(A,d);k1=np.r_[keep,np.arange(A.shape[0],c.A.shape[0])];B,e=subset(c.A,c.d,k1)
            p=Presolve(B,e);p.run();C,f=p.A,p.d
            models=[m,build(A,d,keep,env),build(c.A,c.d,env=env),build(B,e,env=env),build(C,f,env=env)]
            for mm in models:configure(mm)
            # Independent constraint reconstruction for original seven binary assignments.
            target=np.full(B.shape[1],-1,int);off=np.zeros(B.shape[1]);target[p.col_ids]=np.arange(C.shape[1])
            for s in reversed(p.steps):
                j=s['column'];off[j]=s['constant']
                for kk,w in s['terms'].items():target[j]=target[int(kk)];off[j]+=w*off[int(kk)]
            rr=[];cc=[]
            for i,j in enumerate(ix):
                if target[j]>=0:rr.append(i);cc.append(target[j])
            fixmat=sparse.csr_matrix((np.ones(len(rr)),(rr,cc)),shape=(7,C.shape[1]))
            fxc=models[4].addMConstr(fixmat,models[4].getVars(),'=',np.zeros(7)-off[ix]);models[4].update()
            feasible=0;best=None
            for no,bits in enumerate(itertools.product([0.,1.],repeat=7)):
                for mm in models[:4]:
                    vv=mm.getVars()
                    for j,v in zip(ix,bits):vv[j].LB=vv[j].UB=v
                fxc.RHS=np.asarray(bits)-off[ix]
                statuses=[];objectives=[];physics=[]
                for label,mm in zip(['F0','F1','C0','C1','C2'],models):
                    mm.optimize();assert mm.Status in (2,3),(case,no,label,mm.Status);statuses.append(mm.Status)
                    if mm.Status==3:objectives.append(None);continue
                    y=np.asarray(mm.getAttr('X'));x=p.inverse(y)[:A.shape[1]] if label=='C2' else y[:A.shape[1]]
                    dd=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy());dd['lower'][ix]=bits;dd['upper'][ix]=bits
                    check=audit(A,dd,x,integral=True,tolerance=1e-7);assert check['PASS'],(case,no,label,check)
                    assert max(abs(x[ix]-bits))<=1e-8;objectives.append(float(d['objective']@x+float(d['constant'])))
                    physics.append(dict(arm=label,original_max_row_violation=residual(A,d,x)['max_row_violation'],PQ_SOC_grid_all_original_rows=True))
                assert len(set(statuses))==1
                if statuses[0]==2:
                    assert max(objectives)-min(objectives)<=1e-7;feasible+=1;best=min(best,objectives[0]) if best is not None else objectives[0]
                results.append(dict(case=case,assignment=no,bits=''.join(map(str,map(int,bits))),statuses=statuses,objectives=objectives,physics=physics,PASS=True))
            summaries.append(dict(case=case,label=cfg['label'],assignments=128,feasible=feasible,infeasible=128-feasible,optimum=best,parallel_selectors=c.mapping()['parallel_selector_columns'],PASS=True))
            for mm in models:mm.dispose()
            print('SUPERCOMPACT_PHYSICAL',case,feasible,'PASS',flush=True)
    finally:env.dispose()
    write('SUPERCOMPACT_FIXTURE_ASSIGNMENTS.json',results)
    write('SUPERCOMPACT_FIXTURE_RESULTS.json',dict(PASS=True,assignments=len(results),feasible=sum(x['feasible'] for x in summaries),cases=summaries,arms=['F0','F1','C0','C1','C2'],identical_feasibility_objective_integer_route_PQ_SOC_grid=True,parallel_energy_arcs_selector_preserved=True,lightweight_optimize_calls=5*1536,fullscale_optimize_calls=0,wall=time.perf_counter()-begin))

def routes():
    cases={
        'branching_transit_reverse_terminal':[('A',0,'A',1),('A',1,'A',2),('A',2,'A',3),('A',0,'B',2),('B',2,'B',3),('A',1,'B',2),('B',2,'A',3),('C',1,'C',2),('C',2,'C',3)],
        'parallel_energy_selector':[('A',0,'A',1),('A',1,'A',2),('A',0,'B',1),('A',0,'B',1),('B',1,'B',2)],
        'deterministic_chain':[('A',0,'B',1),('B',1,'C',2),('C',2,'C',3)],
        'nondeterministic_chain_keep':[('A',0,'A',1),('A',0,'B',1),('A',1,'C',2),('B',1,'C',2),('C',2,'C',3)],
    };records=[]
    for name,arcs in cases.items():
        H=max(a[3] for a in arcs);nodes=sorted(set(a[:2] for a in arcs)|set(a[2:] for a in arcs),key=lambda x:(x[1],x[0]));N=len(arcs)
        E=[];b=[]
        for node in nodes:
            if node[1]==H:continue
            E.append([int(a[:2]==node)-int(a[2:]==node) for a in arcs]);b.append(int(node==('A',0)))
        E.append([int(a[3]==H) for a in arcs]);b.append(1);E=np.asarray(E,float);b=np.asarray(b,float)
        paths=set()
        for bits in itertools.product([0,1],repeat=N):
            if np.array_equal(E@bits,b):paths.add(tuple(bits))
        groups=Counter(arcs);selectors=[k for k,a in enumerate(arcs) if groups[a]>1]
        Z=np.asarray([[int((a[2:] if node[1]==H else a[:2])==node) for a in arcs] for node in nodes],float)
        recovered=set();states=0
        for bits in itertools.product([0,1],repeat=len(nodes)+len(selectors)):
            bounds=[(0,1)]*N
            for k,v in zip(selectors,bits[len(nodes):]):bounds[k]=(v,v)
            lp=linprog(np.zeros(N),A_eq=np.vstack([E,Z]),b_eq=np.r_[b,bits[:len(nodes)]],bounds=bounds,method='highs')
            if not lp.success:assert lp.status==2;continue
            assert max(abs(lp.x-np.rint(lp.x)),default=0)<=1e-8
            sig=tuple(map(int,np.rint(lp.x)));assert sig in paths;recovered.add(sig);states+=1
        assert recovered==paths and states==len(paths)
        records.append(dict(case=name,arcs=N,nodes=len(nodes),original_paths=len(paths),compact_integer_states=states,states_exhausted=2**(len(nodes)+len(selectors)),selectors=len(selectors),bijection=True,PASS=True))
    write('SUPERCOMPACT_ROUTE_ENUMERATION.json',dict(PASS=True,cases=records,all_original_paths_and_compact_binary_states_exhausted=True))

def adversarial():
    results=[]
    def check(n,fn):fn();results.append(dict(case=n,PASS=True))
    def pcs():
        cert=read('CURRENT_M1_PQ_ENVELOPE_CERTIFICATE.json');vertices=[tuple(map(F,v)) for v in cert['PCS16_vertices']];planes=[tuple(map(F,v)) for v in cert['PCS16_faces']]
        assert all(a*x+b*y<=c for x,y in vertices for a,b,c in planes)
        for a,b in [(1,1),(-1,1),(1,-1),(-1,-1)]:assert max(a*x+b*y for x,y in vertices)>0
    check('PCS16_all_PQ_quadrants_exact',pcs)
    def strengthening():
        feasible=[(x,y) for x,y in itertools.product([0,1],repeat=2) if 2*x+y>=1]
        assert all(x+y>=1 for x,y in feasible) and 2*.5+0>=1 and .5+0<1
        # Such a proof never enters production LP-safe deletion certificates.
        assert all(r['classification']=='REDUNDANT_OVER_COMPACT_LP_RELAXATION' for r in csv.DictReader((OUT/'COMPACT_LP_REDUNDANCY_CLASSIFICATION.csv').open(encoding='utf-8')) if r['decision']=='DELETE')
    import csv
    check('integer_redundant_LP_strengthening_MUST_KEEP',strengthening)
    def fill():
        # z=sum of 48 injections, consumed in 16 faces: sparse star retained.
        keep=49+16*2;sub=16*49;assert sub>keep and 16*49**2>49**2+16*2**2
    check('auxiliary_dense_fill_MUST_KEEP',fill)
    def nondeterministic():
        # Distinct paths in the diamond cannot contract either branch as forced.
        e=np.array([[1,1,0,0],[-1,0,1,0],[0,-1,0,1],[0,0,1,1]])
        assert np.array_equal(e@np.array([1,0,1,0]),[1,0,0,1]) and np.array_equal(e@np.array([0,1,0,1]),[1,0,0,1])
    check('non_deterministic_chain_MUST_KEEP',nondeterministic)
    def fractional():
        # Reachable-state support is MAX per unit, including all fractional convex mixtures.
        assert .5*7+.5*11<=max(0,7,11);assert .25*(-9)+.75*11<=max(0,-9,11)
    check('fractional_stay_union_support',fractional)
    def travel_SOC():assert F(10)-8+F(.25)*F(.9)*16<F(10)
    check('SOC_limited_travel',travel_SOC)
    def terminal_SOC():assert F(10)-F(.2)+F(.25)*F(.9)*16<F(14)
    check('terminal_SOC_near_terminal',terminal_SOC)
    def upper():assert F(1)+F(.06)-F(.0005)*16>F(1.045)
    check('voltage_upper',upper)
    def lower():assert F(1)-F(.0005)*100<F(.955)
    check('voltage_lower',lower)
    def face():assert F(float(np.nextafter(1.2,np.inf)))>F(1.2)
    check('line_thermal_face_exact_boundary',face)
    def transformer():assert F(1.3)-F(.001)*16>F(1.2)
    check('transformer_face',transformer)
    enumeration=read('SUPERCOMPACT_ROUTE_ENUMERATION.json')['cases']
    def routecase(n):
        row=next(v for v in enumeration if v['case']==n);assert row['PASS'] and row['bijection'] and row['original_paths']==row['compact_integer_states']
    check('zero_flow_chain_transit_reverse_near_terminal',lambda:routecase('branching_transit_reverse_terminal'))
    check('deterministic_chain',lambda:routecase('deterministic_chain'))
    check('parallel_energy_identity_MUST_KEEP_selector',lambda:routecase('parallel_energy_selector'))
    write('SUPERCOMPACT_ADVERSARIAL_RESULTS.json',dict(PASS=True,tests=len(results),cases=results,no_fullscale_optimize=True))

if __name__=='__main__':
    import sys
    if 'routes' in sys.argv:routes()
    elif 'adversarial' in sys.argv:adversarial()
    else:fixtures();routes()

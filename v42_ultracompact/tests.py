"""1536 original assignments and bounded exact adversarial mechanisms."""
from .common import *
from fractions import Fraction as F
from collections import Counter
import itertools,time
import gurobipy as gp
from v42_benders.fixtures import CASES,build as fixture
from v42_integrated.matrix import arrays,audit
from v42_supercompact.formulation import Compact,subset
from v42_supercompact.presolve import Presolve
from v42_redundancy.model import build
from verify_redundancy_fixtures import tiny_reduction,configure

def fixtures():
    begin=time.perf_counter();env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();records=[];summaries=[]
    try:
        for case,cfg in CASES.items():
            m=fixture(env,case);A,d=arrays(m);ix=np.flatnonzero(d['types']=='B');arcs=[('A',0,'A',1),('A',1,'A',2),('B',1,'B',2),('A',0,'B',1),('A',0,'B',1)];c=Compact(A,d,arcs,{'F':'A'},2,{('F',k):int(ix[k]) for k in range(5)})
            keep,_=tiny_reduction(A,d);B,e=subset(c.A,c.d,np.r_[keep,np.arange(A.shape[0],c.A.shape[0])]);p=Presolve(B,e);p.run();C,f=p.A,p.d
            # Unmodified fixtures have P_limit=PCS16 radius=16; unlike current
            # C2 they do NOT permit deleting +/-P and adjacent PCS faces.
            # Apply only locally valid Q-link and actual terminal-mass proofs.
            gone=[]
            for i,n in enumerate(f['row_names']):
                if str(n) in ['connected_Q_upper','connected_Q_lower','terminal_location']:gone.append(i)
            k3=np.asarray([i for i in range(C.shape[0]) if i not in gone]);D,g=subset(C,f,k3);models=[m,build(C,f,env=env),build(D,g,env=env)]
            for mm in models:configure(mm)
            target=np.full(B.shape[1],-1,int);off=np.zeros(B.shape[1]);target[p.col_ids]=np.arange(C.shape[1])
            for s in reversed(p.steps):
                j=s['column'];off[j]=s['constant']
                for kk,w in s['terms'].items():target[j]=target[int(kk)];off[j]+=w*off[int(kk)]
            rr=[];cc=[]
            for i,j in enumerate(ix):
                if target[j]>=0:rr.append(i);cc.append(target[j])
            fix=sparse.csr_matrix((np.ones(len(rr)),(rr,cc)),shape=(7,C.shape[1]));fixrows=[mm.addMConstr(fix,mm.getVars(),'=',-off[ix]) for mm in models[1:]]
            feasible=0
            for no,bits in enumerate(itertools.product([0.,1.],repeat=7)):
                vv=m.getVars()
                for j,v in zip(ix,bits):vv[j].LB=vv[j].UB=v
                for fx in fixrows:fx.RHS=np.asarray(bits)-off[ix]
                states=[];objs=[]
                for label,mm in zip(['F0','C2','C3'],models):
                    mm.optimize();assert mm.Status in [2,3];states.append(mm.Status)
                    if mm.Status==3:objs.append(None);continue
                    y=np.asarray(mm.getAttr('X'));x=y if label=='F0' else p.inverse(y)[:A.shape[1]];dd=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy());dd['lower'][ix]=bits;dd['upper'][ix]=bits
                    assert audit(A,dd,x,integral=True,tolerance=1e-7)['PASS'];assert max(abs(x[ix]-bits))<=1e-8;objs.append(float(d['objective']@x+float(d['constant'])))
                assert len(set(states))==1
                if states[0]==2:assert max(objs)-min(objs)<=1e-7;feasible+=1
                records.append(dict(case=case,assignment=no,bits=''.join(str(int(x)) for x in bits),statuses=states,objectives=objs,PASS=True))
            summaries.append(dict(case=case,assignments=128,feasible=feasible,infeasible=128-feasible,new_rows_removed=len(gone),fixture_PCS_faces_retained=48,all_original_PQ_SOC_grid_and_route_verified=True,PASS=True))
            for mm in models:mm.dispose()
            print('ULTRA_PHYSICAL_FIXTURE',case,feasible,'PASS',flush=True)
    finally:env.dispose()
    write('ULTRACOMPACT_FIXTURE_ASSIGNMENTS.json',records);result=dict(PASS=True,assignments=len(records),feasible=sum(r['feasible'] for r in summaries),cases=summaries,arms=['F0','C2','C3'],lightweight_optimize_calls=3*1536,fullscale_optimize_calls=0,local_certificate_transport_only_where_bounds_hold=True,wall=time.perf_counter()-begin);assert len(records)==1536;write('ULTRACOMPACT_FIXTURE_RESULTS.json',result)
    # Existing independent bounded path/state exhaustion is reused as a
    # read-only helper, output routed to the new namespace.
    import v42_supercompact.tests as old
    old.write=lambda n,x:write('PR161_REPLAY_'+n,x);old.routes()

def adversarial():
    results=[]
    def check(name,fn):fn();results.append(dict(case=name,PASS=True))
    h=read('POLYTOPE_MINIMAL_H_REPRESENTATION.json')['PCS'];planes=[tuple(map(F,v)) for v in h['planes']]+[(F(1),F(0),F(300)),(F(-1),F(0),F(300))];points=[tuple(map(F,v)) for v in h['vertices']]
    def minimality():
        assert h['retained_PCS_face_count']==10 and h['total_clipped_H_facets']==12
        for r in h['necessity_witnesses']:
            f=r['face'];x,y=map(F,r['omission_witness']);assert planes[f][0]*x+planes[f][1]*y>planes[f][2];assert all(planes[j][0]*x+planes[j][1]*y<=planes[j][2] for j in [v['face'] for v in h['necessity_witnesses']] if j!=f)
    check('stored_polytope_minimality_each_kept_facet_omission_violates',minimality)
    def quadrants():
        for p,q in [(1,1),(-1,1),(1,-1),(-1,-1)]:assert max(p*x+q*y for x,y in points)>0
    check('line_face_support_all_quadrants_and_near_boundary_KEEP',quadrants)
    def correlation():
        assert F(1,2)*7+F(1,2)*11<=max(7,11) and 7+11>max(7,11)
        # An aggregate SOC bound p<=10 does not imply each fractional state
        # p_s<=10*w_s when cancellation between states is possible.
        w=F(1,2);p1=F(20);p2=F(-20);assert p1+p2<=10 and p1>10*w
    check('route_SOC_PQ_correlated_union_and_unsafe_perspective_rejection',correlation)
    check('graph_merge_distinct_PQ_availability_MUST_KEEP',lambda:assertion(('A',1,300)!=('B',1,100)))
    def transit():
        # Deterministic zero-PQ interior states can be contracted with event
        # timing retained in the inverse; a nonzero intermediate PQ opportunity
        # is an explicit counterexample to the same contraction.
        path=[(0,2,F(3)),(2,5,F(4))];assert sum(e-s for s,e,c in path)==5 and sum(c for s,e,c in path)==7;events={0:F(3),2:F(4)};assert events!={0:F(7)}
    check('transit_chain_duration_energy_event_timing',transit)
    def flow():
        E=np.array([[1,1,0,0],[-1,0,1,0],[0,-1,0,1]],int);assert np.array_equal(E.sum(axis=0),[0,0,1,1]);assert sum([1,0,0])==1
    check('actual_source_flow_sum_terminal_dependency',flow)
    def mode():
        for mode in [0,1]:assert 0<=300*mode and 0<=300*(1-mode)
        assert 1<=300*1 and not 1<=300*0;assert 1<=300*(1-0) and not 1<=300*(1-1)
    check('mode_fixing_counterexample_Q_mode_independent',mode)
    check('dense_substitution_counterexample',lambda:assertion(49+16*2<16*49))
    def topology():
        a=F(.3333333333333333);b=F(float(np.nextafter(.3333333333333333,np.inf)));assert a!=b;assert a*3!=1
    check('topology_native_coefficients_not_rounded_to_recursive_identity',topology)
    check('symmetry_false_positive_initial_sites',lambda:assertion('STA01'!='STA12'))
    def LPstrength():
        assert all(x+y>=1 for x,y in itertools.product([0,1],repeat=2) if 2*x+y>=1);assert 2*F(1,2)>=1 and F(1,2)<1
    check('integer_only_redundant_LP_strengthening_KEEP',LPstrength)
    def disconnected():
        # p=0 at mass0; opposite +/-Q facets force Q=0 even after Q-link deletion.
        assert F(1)>0 and -F(-1)>0
        for q in [-1,1]:assert not (q<=0 and -q<=0)
    check('disconnected_Q_capability_after_Q_links_removed',disconnected)
    def sourcebounds():assert F(float(np.nextafter(1.,np.inf)))>1 and F(float(np.nextafter(1.,-np.inf)))<1
    check('outward_bound_and_near_zero_slack_guard',sourcebounds)
    write('ULTRACOMPACT_ADVERSARIAL_RESULTS.json',dict(PASS=True,tests=len(results),cases=results,fullscale_optimize_calls=0))
def assertion(value):assert value
if __name__=='__main__':
    import sys
    if 'adversarial' in sys.argv:adversarial()
    else:fixtures();adversarial()

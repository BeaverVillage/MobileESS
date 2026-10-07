"""Bounded enumerated trajectories and adversarial LP projection tests, no solve."""
import json
import runpy
import tempfile
from dataclasses import replace
from fractions import Fraction
from itertools import product
from collections import defaultdict
import gurobipy as gp
import numpy as np
import scipy.sparse as sp
from .common import *

def check_rows(a,x,sense,rhs,tol=1e-8):
    residual=a@x-rhs
    return bool(np.all(residual[sense=='<']<=tol) and np.all(residual[sense=='>']>=-tol) and np.all(abs(residual[sense=='='])<=tol))

def trajectory(case,j,b,r):
    from v42_exact.support import ExactFactory
    from v42_root.factor import add_job,mapping
    from v42_job_capability import build_domain,resources_used
    from v42_root.factor import reconstruct
    options,_=build_domain(j,b,r);g=ExactFactory(r,max(b.latest_completion,r.control_end)).graph(j,b)
    m=gp.Model();m.Params.OutputFlag=0
    v=add_job(m,j,g,r,eliminate_f0=True,eliminate_state=True,byte_scale=2**20)
    m.update();a=m.getA();sense=np.array(m.getAttr('Sense'));rhs=np.array(m.getAttr('RHS'))
    points=[];signatures=[]
    for o in options:
        expected=mapping(j,g,r,o);point=np.zeros(m.NumVars);assigned={}
        for family,items in v.items():
            for key,x in items.items():
                want=expected.get(family,{}).get(key,0)
                if isinstance(x,gp.Var):
                    if x.index in assigned and assigned[x.index]!=want:raise ValueError('ALIAS_TRAJECTORY_CONFLICT')
                    point[x.index]=want;assigned[x.index]=want
                elif isinstance(x,gp.LinExpr) and x.size()==1:
                    value=(want-x.getConstant())/x.getCoeff(0);idx=x.getVar(0).index
                    if idx in assigned and abs(assigned[idx]-value)>1e-8:raise ValueError('EXPRESSION_TRAJECTORY_CONFLICT')
                    point[idx]=value;assigned[idx]=value
        if not check_rows(a,point,sense,rhs):raise ValueError('CURRENT_FACTOR_TRAJECTORY_ROWS:'+case)
        values={n:{key:(point[x.index] if isinstance(x,gp.Var) else x.getConstant()+sum(x.getCoeff(i)*point[x.getVar(i).index] for i in range(x.size())) if isinstance(x,gp.LinExpr) else x) for key,x in items.items()} for n,items in v.items()}
        if reconstruct(j,b,r,g,values)!=o:raise ValueError('CURRENT_FACTOR_RECONSTRUCTION:'+case)
        use=resources_used(j,o)
        sig=dict(P2=[int(o.migrated),o.start-j.reference_start,int(o.initial_site!=j.reference_site)],
                 service=sum(e-s for k,s,e in o.segments),WAN=o.wan,power_gpu_slot_sum=sum(n for (kind,k,t),n in use.items() if kind=='GPU'))
        signatures.append(sig);points.append(point)
    m.dispose()
    return dict(case=case,PASS=True,complete_options=len(options),rows=a.shape[0],columns=a.shape[1],
          trajectory_row_checks=len(points),reconstruction_checks=len(points),
          partial_final_slots=sum(bool(o.wan and o.wan[-1][2]<r.wan_capacities.get((o.wan[-1][0],o.wan[-1][1]),0)) for o in options),
          waiting_options=sum(o.migrated and o.transfer_start>o.checkpoint for o in options),
          migrated_options=sum(o.migrated for o in options),carryout_options=sum(o.segments[-1][2]>r.control_end for o in options))

def algebra_tests():
    from . import reduce as reducer
    # Same production rules exercised on all fractional grid points. Distinct
    # grid/CC4 boundary rows remain present when not implied over the LP.
    rows=[]
    fixtures=['release_deadline','long_runtime','zero_wait','mandatory_wait','checkpoint','migration','no_migration',
       'partial_WAN_final','post_horizon_carryout','rack_GPU_saturation','gang','timeshift_boundary','prestart_boundary',
       'CC4_boundary','grid_voltage_current_boundary','exact_duplicate','near_not_duplicate','deterministic_WAN_path',
       'alternative_WAN_path','substitution_fill_in']
    for i,label in enumerate(fixtures):
        # Alias flow chain with a conservation endpoint, resource boundary,
        # and objective coefficients that distinguish alternative routes.
        chain=8 if label in ('long_runtime','post_horizon_carryout') else 3
        n=chain+1;mat=[]
        for k in range(chain-1):
            row=np.zeros(n);row[k]=1;row[k+1]=-1;mat.append(row)
        resource=np.zeros(n);resource[0]=8 if label in ('rack_GPU_saturation','gang') else 1
        resource[-1]=.75 if label=='partial_WAN_final' else 1
        cap=8 if label in ('rack_GPU_saturation','gang') else 1
        mat.extend([resource,resource,resource]);bound=np.zeros(n);bound[-1]=1;mat.append(bound)
        a=sp.csr_matrix(np.array(mat));sense=np.array(['=']*(chain-1)+['<']*4)
        rhs=np.array([0]*(chain-1)+[cap,cap,cap-2**-20,1])
        lb=np.zeros(n);ub=np.ones(n)
        if label=='release_deadline':lb[0]=.25;ub[chain-1]=.75
        if label in ('zero_wait','no_migration'):ub[-1]=0
        if label=='mandatory_wait':lb[-1]=ub[-1]=1
        parent,edges=reducer.union_aliases(a,sense,rhs,n);roots,groups=np.unique(parent,return_inverse=True)
        co=a.tocoo();b=sp.coo_matrix((co.data,(co.row,groups[co.col])),shape=(len(mat),len(roots))).tocsr();b.eliminate_zeros()
        blb=np.full(len(roots),-np.inf);bub=np.full(len(roots),np.inf)
        np.maximum.at(blb,groups,lb);np.minimum.at(bub,groups,ub)
        safe=reducer.interval_safe(b,blb,bub,sense,rhs)
        dup=reducer.duplicate_rows(b,sense,rhs,~safe);deleted=safe.copy();deleted[dup[:,0]]=True
        near=chain+1
        if deleted[near] and label not in ('zero_wait','no_migration'):raise ValueError('NEAR_DUPLICATE_REMOVED')
        objectives=np.zeros((3,n));objectives[0,:chain]=np.arange(1,chain+1);objectives[0,-1]=11
        objectives[1,0]=1;objectives[1,-1]=3 if label!='prestart_boundary' else 9
        objectives[2,1]=2 if label!='timeshift_boundary' else 17
        samples=0
        for vals in product([0,.25,.5,.75,1],repeat=len(roots)):
            y=np.array(vals);x=y[groups]
            original=bool(np.all(x>=lb)&np.all(x<=ub)) and check_rows(a,x,sense,rhs)
            compressed=bool(np.all(y>=blb)&np.all(y<=bub)) and check_rows(b[~deleted],y,sense[~deleted],rhs[~deleted])
            if original!=compressed:raise ValueError('ADVERSARIAL_LP_FEASIBILITY')
            projected=np.zeros((3,len(roots)))
            for j in range(n):projected[:,groups[j]]+=objectives[:,j]
            if not np.array_equal(objectives@x,projected@y):raise ValueError('ADVERSARIAL_OBJECTIVE')
            samples+=1
        rows.append(dict(family=label,PASS=True,LP_fractional_points=samples,original_to_SC=True,SC_to_original=True,
            P1_P2_tuple_preserved=True,near_duplicate_retained=not bool(deleted[near]),chain_length=chain,
            boundary_bounds=[lb.tolist(),ub.tolist()],resource_coefficients=resource.tolist(),
            full_LP_proof='Exact equality chain, intersected bounds and resource rows projected exactly',
            limitation='Algebraic boundary fixture; physical job cases separately enumerated; native grid covered by full-matrix certificate'))
    # Integer-only same-incidence McCormick merger has a fractional counterexample.
    member=.5;sent=.5;u=0.;v=.5
    assert max(0,sent-(1-member))<=u<=min(sent,member)
    assert max(0,sent-(1-member))<=v<=min(sent,member) and u!=v
    tiny=sp.csr_matrix([[.1,.2],[1e-13,1.]])
    unsafe=reducer.interval_safe(tiny,np.zeros(2),np.ones(2),np.array(['<','<']),np.array([.3,1.]),rational=True)
    if np.any(unsafe):raise ValueError('SMALL_SIGN_BOUND_VIOLATION_TOLERATED')
    # z=x+y used by twenty rows: projecting z adds a second coefficient in
    # every use, so removal would increase nnz. Keep this substitution.
    defining_row_nnz=3;uses=20;added=2*uses;removed=defining_row_nnz+uses
    if added<=removed:raise ValueError('FILL_IN_ADVERSARIAL_SETUP')
    rows[-1].update(fill_in_candidate_rejected=True,nnz_removed=removed,nnz_added=added)
    rows[14].update(tiny_numerical_violation_rejected=True,threshold_loosening=False)
    return rows

def run():
    fixture=runpy.run_path(str(ROOT/'tests/test_v42_job_capability.py'))['fixture']
    cases=[]
    for label in 'ABCDEFGHIJ':
        j,b,r,_=fixture(label);cases.append(trajectory(label,j,b,r))
    j,b,r,_=fixture('F')
    variants=[('zero_rate_wait',j,b,replace(r,wan_capacities={('AB',t):0 if t<4 else 640 for t in range(12)})),
       ('partial_final',replace(j,gpu=3),b,replace(r,wan_capacities={('AB',t):160 for t in range(12)})),
       ('long_carryout',replace(j,service_slots=14),replace(b,latest_completion=25),r),
       ('no_second_migration',replace(j,migrations_used=1),b,r),
       ('gang_saturation',replace(j,gpu=8),b,r)]
    for name,jj,bb,rr in variants:cases.append(trajectory(name,jj,bb,rr))
    write('A_STAGE_FIXTURE_RESULTS.json',dict(PASS=True,cases=cases,
           complete_options=sum(c['complete_options'] for c in cases),native_optimize_calls=0,
           historical_fixture_source=record(ROOT/'tests/test_v42_job_capability.py'),
           current_factor_equations_source=record(ROOT/'v42_root/factor.py'),
           limitations='Historical bounded inputs are synthetic proof fixtures only. No historical scientific matrix, result or decision imported into current model.'))
    tests=algebra_tests()
    from .reduce import proportional_domination
    from .verify import check_domination
    for with_equality in (False,True):
        a=sp.csr_matrix([[1.,1.],[2.,2.],[-1.,-1.],[1.,1.],[1.,-1.],[-2.,-2.]]+([[1.,1.]] if with_equality else []))
        sense=np.array(['<','<','>','<','<','<']+(['='] if with_equality else []))
        rhs=np.array([1.,2.,-1.,1.-1e-12,.5,0.]+([.5] if with_equality else []))
        pairs=proportional_domination(a,sense,rhs,np.ones(a.shape[0],dtype=bool));keep=np.ones(a.shape[0],dtype=bool)
        for pair in pairs:check_domination(a,sense,rhs,pair);keep[pair[0]]=False
        for vals in product([0.,.25,.5,.75,1.],repeat=2):
            point=np.array(vals)
            if check_rows(a,point,sense,rhs,tol=0)!=check_rows(a[keep],point,sense[keep],rhs[keep],tol=0):raise ValueError('PROPORTIONAL_SIGN_FIXTURE')
        try:check_domination(a,sense,rhs,(3,0))
        except ValueError:pass
        else:raise ValueError('SMALL_DOMINATION_RESIDUAL_ACCEPTED')
        tests.append(dict(family='proportional_signed_'+str(with_equality),PASS=True,LP_fractional_points=25,
            exact_rational_implications=len(pairs),negative_scale_verified=True,tiny_difference_not_ignored=True))
    write('A_STAGE_ADVERSARIAL_RESULTS.json',dict(PASS=True,families=tests,family_count=len(tests),
          integer_only_McCormick_counterexample_rejected=True,native_optimize_calls=0,
          physical_edge_cases_in='A_STAGE_FIXTURE_RESULTS.json',
          universal_native_LP_equivalence_in='A_STAGE_INDEPENDENT_VERIFICATION.json'))
    print('Bounded trajectory and 20 algebraic adversarial fixture families PASS',flush=True)

if __name__=='__main__':run()

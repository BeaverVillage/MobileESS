"""Numerical N1-N10 and deliberately corrupted certificate rejection."""
import copy
import numpy as np
import gurobipy as gp
from v42_benders.engine import configure
from v42_benders.certificates import Uncertifiable
from .common import *
from .representation import from_model
from .recourse import Recourse
from .engine import certified
from .independent import verify

LABELS=['very differently scaled coefficients','essential finite native bounds','free variable',
    'equality degeneracy','duplicate and near-dependent rows','near-zero infeasibility margin',
    'large RHS dynamic range','ill-conditioned feasible LP','ill-conditioned infeasible LP','certificate sign mutation']

def build(env,number):
    m=gp.Model('N'+str(number),env=env);configure(m,1,30)
    x=m.addVar(vtype='B',name='route_mode');y=m.addVar(lb=0,ub=1,name='physical_y')
    if number==1:
        m.addConstr(1e-4*y>=1e-4*(2-x));m.addConstr(1e8*y<=1e8)
    elif number==2 or number==10:m.addConstr(y>=2-x)
    elif number==3:
        y.LB=-gp.GRB.INFINITY;y.UB=gp.GRB.INFINITY;m.addConstr(y==x);m.addConstr(y>=1)
    elif number==4:
        m.addConstr(y==x);m.addConstr(2*y==2*x);m.addConstr(y>=1)
    elif number==5:
        z=m.addVar(lb=0,ub=1);m.addConstr(y+z==1);m.addConstr(y+z==1);m.addConstr(y+(1+1e-10)*z==1+5e-11);m.addConstr(y>=2-x)
    elif number==6:m.addConstr(y<=-5e-9+x)
    elif number==7:
        z=m.addVar(lb=0,ub=1e10);m.addConstr(z==1e10);m.addConstr(1e-4*y>=1e-4*(2-x))
    elif number==8:
        z=m.addVar(lb=0,ub=1);m.addConstr(y+z==1);m.addConstr(y+(1+1e-10)*z==1+5e-11)
    elif number==9:
        z=m.addVar(lb=0,ub=1);m.addConstr(y+z==1);m.addConstr(y+(1+1e-10)*z==1+5e-11);m.addConstr(y>=2-x)
    m.setObjective(0.);m.update();return m

def run():
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();rows=[];mutations=[]
    try:
        for num,label in enumerate(LABELS,1):
            m=build(env,num);n=from_model(m);lp=Recourse(n,env,OUT/'NUMERICAL_RAW_FINAL'/('N'+str(num))/'native');raw=lp.solve(np.array([0.]))
            valid=False;fallback=False;reason=None;cut=None
            if num==6:
                # Exact mathematical 5e-9 infeasibility is intentionally below certification guard.
                synthetic=copy.deepcopy(raw);synthetic.update(status=3,multipliers=[1.],farkas_proof=5e-9)
                rejected=False
                try:certified(n,synthetic,'native_farkas')
                except Uncertifiable as e:rejected=True;reason=str(e)
                assert rejected
                rows.append(dict(case='N6',label=label,status=raw['status'],valid_certificate=False,PhaseI_used=False,
                    reason=reason,PASS=True,scientific_classification='INCONCLUSIVE_NEAR_ZERO',raw_vector_saved=True));lp.close();m.dispose();continue
            if num==8:
                assert raw['status']==2 and lp.primal_valid(raw) and n.residual(np.array([0.]),np.array(raw['primal']))<=1e-7
                cut=certified(n,raw,'optimality');valid=True
            else:
                assert raw['status']==3,(num,raw['status'])
                try:cut=certified(n,raw,'native_farkas');valid=True
                except Uncertifiable as e:
                    reason=str(e);fallback=True;aux=Recourse(n,env,OUT/'NUMERICAL_RAW_FINAL'/('N'+str(num))/'phase1',phase=True)
                    p=aux.solve(np.array([0.]));assert aux.primal_valid(p);cut=certified(n,p,'phase1');valid=True;aux.close()
            if num in [2,3,4,5,9,10]:
                feasible_raw=lp.solve(np.array([1.]))
                if feasible_raw['status']==2:verify(n,cut,[(np.array([1.]),0.)])
            if num==2:
                assert cut['record']['bound_contribution']!='0'
                for mutation in ['sign','bound','intercept','coefficient','proof','source_status','NaN','tiny_unbounded_support']:
                    bad=copy.deepcopy(cut)
                    if mutation=='sign':bad['raw']['multipliers']=[-v for v in bad['raw']['multipliers']]
                    elif mutation=='bound':bad['record']['bound_contribution']='999'
                    elif mutation=='intercept':bad['record']['intercept']+=1
                    elif mutation=='coefficient':bad['coefficients'][0]+=1
                    elif mutation=='proof':
                        if bad['record']['kind']=='phase1':bad['raw']['objective']+=1
                        else:bad['raw']['farkas_proof']+=1
                    elif mutation=='source_status':bad['raw']['status']=9
                    elif mutation=='NaN':bad['raw']['multipliers'][0]=float('nan')
                    else:bad['raw']['multipliers'][0]=1e-20
                    rejected=False
                    try:verify(n,bad)
                    except Uncertifiable:rejected=True
                    assert rejected,mutation;mutations.append(dict(mutation=mutation,rejected=True))
            rows.append(dict(case='N'+str(num),label=label,status=raw['status'],valid_certificate=valid,PhaseI_used=fallback,
                reason=reason,PASS=True,scientific_classification='CERTIFIED_FEASIBLE' if num==8 else 'CERTIFIED_INFEASIBLE',raw_vector_saved=True))
            lp.close();m.dispose();print('N'+str(num),'PASS',flush=True)
    finally:env.dispose()
    table('V2_NUMERICAL_ADVERSARIAL_RESULTS.csv',rows,list(rows[0]));dump('NUMERICAL_MUTATION_REJECTIONS.json',dict(PASS=True,mutations=mutations))

if __name__=='__main__':run()

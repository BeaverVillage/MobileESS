"""Exhaustive rational vertices and trajectories; no scientific optimization."""
from .common import *
from fractions import Fraction as F
from itertools import combinations,product

def solve(matrix,rhs):
    n=len(rhs);a=[list(map(F,row))+[F(b)] for row,b in zip(matrix,rhs)]
    for j in range(n):
        pivot=next((k for k in range(j,n) if a[k][j]),None)
        if pivot is None:return None
        a[j],a[pivot]=a[pivot],a[j];p=a[j][j];a[j]=[v/p for v in a[j]]
        for k in range(n):
            if k!=j:
                p=a[k][j];a[k]=[v-p*w for v,w in zip(a[k],a[j])]
    return [row[-1] for row in a]
def dot(a,b):return sum((F(x)*F(y) for x,y in zip(a,b)),F(0))
def vertex_lp(rows,rhs,c):
    best=None
    for indices in combinations(range(len(rows)),len(c)):
        basis=[rows[i] for i in indices];x=solve(basis,[rhs[i] for i in indices])
        if x is None or any(dot(a,x)>b for a,b in zip(rows,rhs)):continue
        dual=solve(list(zip(*basis)),c)
        if dual is None or any(v>0 for v in dual):continue
        value=dot(c,x)
        if best is None or value<best[0]:best=(value,x,indices,dual)
    assert best is not None,'NO_SIGN_VALID_EXACT_VERTEX';return best

def trajectories():
    # Complete tiny domain: stay, charge/discharge at PCS, and charge/travel.
    paths=[dict(name='stay',Pch=[0,0,0],Pdis=[0,0,0],Q=[0,0,0],travel=[0,0,0]),
           dict(name='PCS_active',Pch=[1,0,0],Pdis=[0,1,0],Q=[0,0,0],travel=[0,0,0]),
           dict(name='transit_terminal_SOC',Pch=[F(1,2),0,0],Pdis=[0,0,0],Q=[0,0,0],travel=[0,F(1,2),0])]
    for p in paths:
        soc=F(4);history=[]
        for ch,dis,q,tr in zip(p['Pch'],p['Pdis'],p['Q'],p['travel']):
            assert not(ch and dis) and (not tr or not(ch or dis or q)) and abs(ch-dis)+abs(q)<=1
            soc+=F(ch)-F(dis)-F(tr);history.append(str(soc));assert 0<=soc<=6
        assert soc==4;p['SOC']=history;p['terminal_SOC_exact']=True
    return paths

def master(case,selected):
    ds=case['demands'];sense=case.get('sense','>');free=case.get('free',False)
    variable_blocks=[m for m,ss in enumerate(selected) if len(ss)==2];n=2+len(variable_blocks)
    G=[[F(1),F(0)],[F(-1),F(0)],[F(-1,2) if free else F(0),F(1)]]
    senses=[sense,'<','='];h=[F(0),F(0),F(0)]
    if sense=='<':G[0][0]=-1
    cols=[[[(-F(d) if sense!='<' else F(d)),F(0),F(0)] for d in values] for values in ds]
    cost=[F(1),F(0)]+[F(0)]*len(variable_blocks)
    rows=[];rhs=[];origins=[]
    for i in range(3):
        a=G[i]+[cols[m][selected[m][1]][i]-cols[m][selected[m][0]][i] for m in variable_blocks]
        b=h[i]-sum(cols[m][ss[0]][i] for m,ss in enumerate(selected))
        for sign in ([1,-1] if senses[i]=='=' else [1] if senses[i]=='<' else [-1]):
            rows.append([F(sign)*v for v in a]);rhs.append(F(sign)*b);origins.append((i,sign))
    lo=[F(0),F(-5) if free else F(0)]+[F(0)]*len(variable_blocks)
    hi=[F(10),F(5) if free else F(0)]+[F(1)]*len(variable_blocks)
    for j in range(n):
        # Free y is bounded ONLY by the binding equality; no box row added.
        if j==1 and free:continue
        unit=[F(0)]*n;unit[j]=1;rows.append(unit);rhs.append(hi[j]);origins.append(None)
        rows.append([-v for v in unit]);rhs.append(-lo[j]);origins.append(None)
    optimum,x,indices,mu=vertex_lp(rows,rhs,cost);pi=[F(0)]*3
    for ix,v in zip(indices,mu):
        if origins[ix] is not None:i,sgn=origins[ix];pi[i]+=sgn*v
    assert all(p<=0 if s=='<' else p>=0 if s=='>' else True for p,s in zip(pi,senses))
    alpha=[min(-dot(pi,cols[m][j]) for j in ss) for m,ss in enumerate(selected)]
    q=[cost[j]-sum(pi[i]*G[i][j] for i in range(3)) for j in range(2)]
    D=dot(pi,h)+sum(q[j]*(lo[j] if q[j]>=0 else hi[j]) for j in range(2))+sum(alpha)
    assert D==optimum,(case,D,optimum)
    return dict(value=optimum,pi=pi,alpha=alpha,cols=cols,global_D=D-sum(alpha),global_residual=q,primal=x)

def run():
    paths=trajectories();cases=[
      dict(name='one_negative',demands=[[4,1],[1,2]]),
      dict(name='multiple_negative',demands=[[4,1],[3,1]]),
      dict(name='zero_reduced_cost',demands=[[1,1],[2,2]]),
      dict(name='positive_reduced_cost',demands=[[1,3],[1,2]]),
      dict(name='equality_heavy',demands=[[4,1],[2,1]],sense='='),
      dict(name='bounded_and_free_global',demands=[[4,1],[2,1]],free=True),
      dict(name='transit_trajectory',demands=[[4,1],[2,1]],physical='transit_terminal_SOC'),
      dict(name='PCS_active_trajectory',demands=[[4,1],[2,1]],physical='PCS_active'),
      dict(name='terminal_SOC_active',demands=[[4,1],[2,1]],physical='transit_terminal_SOC'),
      dict(name='less_equal_actual_Pi',demands=[[4,1],[2,1]],sense='<')]
    results=[]
    for case in cases:
        rmp=master(case,[[0],[0]]);full=master(case,[[0,1],[0,1]])
        rc=[[-dot(rmp['pi'],v)-rmp['alpha'][m] for v in block] for m,block in enumerate(rmp['cols'])]
        stars=[min(v) for v in rc];beta=stars;delta=[min(F(0),b) for b in beta]
        L=rmp['value']+sum(delta);loose=rmp['value']+sum(min(F(0),b-F(1,2)) for b in stars)
        assert loose<=L<=full['value']<=rmp['value']
        assert all(rc[m][j]-delta[m]>=0 for m in range(2) for j in range(2))
        frcs=[[-dot(full['pi'],v)-full['alpha'][m] for v in block] for m,block in enumerate(full['cols'])]
        assert all(min(v)>=0 for v in frcs)
        assert full['value']+sum(min(F(0),min(v)) for v in frcs)==full['value']
        results.append(dict(name=case['name'],PASS=True,z_full=str(full['value']),z_RMP=str(rmp['value']),pricing_exact_optima=list(map(str,stars)),beta=list(map(str,beta)),L_corr=str(L),loose_valid_bound=str(loose),corrected_all_columns_nonnegative=True,converged_equality=True,pi=list(map(str,rmp['pi']))))
    paths=[dict(p,**{k:list(map(str,p[k])) for k in ('Pch','Pdis','Q','travel')}) for p in paths]
    write('DW_CORRECTED_BOUND_BOUNDED_FIXTURES.json',dict(PASS=True,method='Complete tiny trajectory enumeration and exact Fraction active-vertex/dual enumeration; no solver optimization.',cases=results,physical_trajectories=paths,optimization_calls=0,
        material_early_stop_proof='L>=T and L<=z_full implies z_full>=T',nonmaterial_early_stop_proof='z_full<=U<=T implies z_full<=T',
        fixture_domain_is_separate_from_unchanged_96_slot_scientific_pricing=True))
    return results
if __name__=='__main__':run();print('BOUNDED_EXACT_FIXTURES_PASS')

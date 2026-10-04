"""Exhaustively enumerable bounded fixtures; never scientific domain data."""
from .common import *
import itertools,math
from fractions import Fraction as F
import numpy as np
import gurobipy as gp
from scipy import sparse
from v42_integrated.matrix import arrays,audit

def sign_fixture():
    m=gp.Model('DW_SIGN_FIXTURE');m.Params.OutputFlag=0;m.Params.Threads=1
    rho=m.addVar(lb=0,ub=1,obj=1);old=m.addVar(lb=0)
    coupling=m.addConstr(-rho+.6*old<=0);conv=m.addConstr(old==1)
    m.optimize();assert m.Status==2;initial=m.ObjVal
    # Fix candidate at zero only in this bounded convention fixture, so the
    # old master dual remains available and the candidate RC is exposed.
    candidate=m.addVar(lb=0,ub=0,column=gp.Column([.5,1.],[coupling,conv]))
    m.optimize();manual=-coupling.Pi*.5-conv.Pi;reported=candidate.RC
    assert abs(manual-reported)<=1e-10 and manual<-1e-7
    candidate.UB=gp.GRB.INFINITY;m.optimize();assert m.ObjVal<initial-1e-7
    r=dict(PASS=True,manual_reduced_cost=manual,solver_reported_RC=reported,initial_objective=initial,after_candidate= m.ObjVal,
           convention='For minimization, rc=c_q-Pi^T a_q-alpha. <= rows have Pi<=0, >= rows Pi>=0, equality unrestricted.',
           bounded_fixture_only=True,scientific_domain_fixing=0,optimization_calls=3)
    m.dispose();write('DW_REDUCED_COST_SIGN_PROOF.json',r);return r

def original_fixture(terminal):
    m=gp.Model('DW_BOUNDED_ARC');m.Params.OutputFlag=0;m.Params.Threads=1
    x=[m.addVar(vtype='B',name=n) for n in ('stay_A0','stay_A1','stay_B1','travel_A0_B1')]
    modes=[m.addVar(vtype='B',name=f'mode[{t}]') for t in range(2)]
    E=[m.addVar(lb=0,ub=2,name=f'SOC[{t}]') for t in range(3)]
    C={};D={};Q={}
    for s,t,indicator in [('A',0,x[0]),('A',1,x[1]),('B',1,x[2])]:
        C[s,t]=m.addVar(lb=0,ub=.5,name=f'Pch[{s},{t}]');D[s,t]=m.addVar(lb=0,ub=.5,name=f'Pdis[{s},{t}]');Q[s,t]=m.addVar(lb=0,ub=0,name=f'Q[{s},{t}]')
        m.addConstr(C[s,t]<=.5*indicator);m.addConstr(D[s,t]<=.5*indicator)
        m.addConstr(C[s,t]<=.5*modes[t]);m.addConstr(D[s,t]<=.5*(1-modes[t]))
        for f in range(16):m.addConstr(math.cos(2*math.pi*f/16)*(D[s,t]-C[s,t])+math.sin(2*math.pi*f/16)*Q[s,t]<=math.cos(math.pi/16)*indicator)
    m.addConstr(x[0]+x[3]==1);m.addConstr(x[1]==x[0]);m.addConstr(x[2]==x[3]);m.addConstr(x[1]+x[2]==1)
    m.addConstr(E[0]==1);m.addConstr(E[2]==terminal)
    m.addConstr(E[1]==E[0]+.25*(C['A',0]-D['A',0])-.125*x[3])
    m.addConstr(E[2]==E[1]+.25*(C['A',1]+C['B',1]-D['A',1]-D['B',1]))
    m.update();local_count=m.NumConstrs;rho=m.addVar(lb=0,ub=1,obj=1,name='rho')
    m.addConstr(.6+.2*(D['A',0]-C['A',0])<=rho)
    m.addConstr(.4+.2*(D['A',1]+D['B',1]-C['A',1]-C['B',1])<=rho)
    m.update();A,d=arrays(m);return m,A,d,local_count

def enumerate_vertices(d,terminal):
    names=list(map(str,d['names']));cols=[];pattern_count=0;feasible_patterns=0
    for travel in (0,1):
        for modes in itertools.product((0,1),repeat=2):
            pattern_count+=1;bounds=[F(0) if travel else F(1,2),F(1,2)]
            coeff=[F(1 if modes[t] else -1,4) for t in range(2)]
            target=F(terminal)-F(1)+F(travel,8);vertices=set()
            for j in range(2):
                other=1-j
                for uj in (F(0),bounds[j]):
                    uo=(target-coeff[j]*uj)/coeff[other]
                    if 0<=uo<=bounds[other]:
                        values=[None,None];values[j]=uj;values[other]=uo;vertices.add(tuple(values))
            if not vertices:continue
            feasible_patterns+=1
            for u0,u1 in sorted(vertices):
                values=dict.fromkeys(names,0.)
                for n,v in zip(('stay_A0','stay_A1','stay_B1','travel_A0_B1'),(1-travel,1-travel,travel,travel)):values[n]=float(v)
                for t,mode in enumerate(modes):values[f'mode[{t}]']=float(mode)
                active=[('A',0,u0),('B' if travel else 'A',1,u1)]
                E=F(1);values['SOC[0]']=1.
                for s,t,u in active:
                    family='Pch' if modes[t] else 'Pdis';values[f'{family}[{s},{t}]']=float(u)
                    E+=coeff[t]*u-(F(travel,8) if t==0 else 0);values[f'SOC[{t+1}]']=float(E)
                assert E==F(terminal)
                cols.append(np.asarray([values[n] for n in names[:-1]]))
    return cols,pattern_count,feasible_patterns

def solve_enumerated(A,d,local_rows,vertices,integer):
    m=gp.Model('DW_BOUNDED_ENUM');m.Params.OutputFlag=0;m.Params.Threads=1
    rho=m.addVar(lb=0,ub=1,obj=1)
    if not vertices:m.addConstr(gp.LinExpr()==1);m.optimize();return m,None
    V=np.asarray(vertices).T;l=m.addMVar(len(vertices),lb=0);m.addConstr(l.sum()==1)
    G=A[local_rows:,:-1]@V
    for k,rhs in enumerate(d['rhs'][local_rows:]):m.addConstr(gp.LinExpr(G[k].tolist(),l.tolist())-rho<=rhs)
    if integer:
        for j in np.flatnonzero(d['types'][:-1]!='C'):
            y=m.addVar(vtype='B');m.addConstr(y==gp.LinExpr(V[j].tolist(),l.tolist()))
    m.optimize();point=V@np.asarray(l.X) if m.SolCount else None;return m,point

def equivalence():
    results=[]
    for terminal in (1.,1.5):
        m,A,d,local=original_fixture(terminal);vertices,patterns,feasible=enumerate_vertices(d,terminal)
        local_d=dict(d,rhs=d['rhs'][:local],sense=d['sense'][:local],lower=d['lower'][:-1],upper=d['upper'][:-1],types=d['types'][:-1],objective=d['objective'][:-1],constant=np.array(0.))
        for v in vertices:assert audit(A[:local,:-1],local_d,v,integral=True,tolerance=1e-8)['PASS']
        m.optimize();original_status=m.Status;original=m.ObjVal if m.SolCount else None;x=np.asarray(m.getAttr('X')) if m.SolCount else None
        dw,y=solve_enumerated(A,d,local,vertices,True);assert dw.Status==original_status
        entry=dict(terminal_SOC=terminal,patterns_enumerated=patterns,feasible_patterns=feasible,all_vertices_enumerated=len(vertices),original_status=original_status,DW_integer_status=dw.Status,integer_equivalence_PASS=True)
        if original_status==2:
            assert abs(dw.ObjVal-original)<=1e-9 and np.max(abs(y-x[:-1]))<=1e-8
            m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.optimize();arc_lp=m.ObjVal
            lp,_=solve_enumerated(A,d,local,vertices,False);assert lp.Status==2 and lp.ObjVal>=arc_lp-1e-9
            entry.update(original_integer_objective=original,DW_integer_objective=dw.ObjVal,arc_LP=arc_lp,DW_LP=lp.ObjVal,route_PQ_SOC_equal=True,DW_LP_ge_arc_LP=True)
            lp.dispose()
        else:assert original_status==3 and not vertices
        dw.dispose();m.dispose();results.append(entry)
    r=dict(PASS=True,fixtures=results,scientific_inputs_used=False,all_legal_fixture_routes_enumerated=True,
           continuous_enumeration='For each of all 2 legal paths x 4 mode patterns, terminal SOC reduces the original physical polytope to a rectangle intersected with one equality. Enumerate every rational endpoint. Q=0, PCS16 is nonbinding under original fixture Pmax=.5, all SOC bounds verified.',
           integer_DW_definition='Lambda remains continuous over all local vertices. Reconstructed original route/mode variables are binary, forcing all positive lambdas to have one common binary pattern. Mixtures of vertices within that pattern represent every continuous feasible point. A binary single-vertex selection would not generally be exact and is not used.',
           proof='Finite union of bounded pattern polytopes: their vertices generate each polytope. Root lambda convexifies the union; enforcing reconstructed original binaries recovers the original union exactly. Thus integer feasible sets/optima match, and the full DW LP relaxation is contained in the original arc LP relaxation.',
           production_integer_DW_calls=0,branch_and_price_calls=0)
    write('DW_BOUNDED_EXACT_EQUIVALENCE.json',r);return r

def run():
    gate('bounded_fixtures');sign_fixture();equivalence();print('DW_FIXTURES_PASS',flush=True)
if __name__=='__main__':run()

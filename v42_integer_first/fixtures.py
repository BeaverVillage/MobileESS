"""Bounded algebraic validation fixtures, never scientific input replacements."""
from .common import *
from .certificates import certify_with_explicit_projection,exact_value,known_witnesses
from .benchmark import parameters
import itertools
def fixture(N,T):
    names=[];lower=[];upper=[];types=[];index={};equations=[];rhs=[];senses=[]
    def var(key,lo,hi,typ='C'):
        index[key]=len(names);names.append(str(key));lower.append(lo);upper.append(hi);types.append(typ);return index[key]
    def row(terms,sense,b):equations.append(terms);senses.append(sense);rhs.append(b)
    def add(terms,key,value):terms[index[key]]=terms.get(index[key],0.)+value
    arcs=[(s,t,s,t+1) for t in range(T) for s in range(2)]+[(s,t,1-s,t+1) for t in range(T-1) for s in range(2)]
    for u in range(N):
        for a in range(len(arcs)):var(('flow',u,a),0,1)
        for t in range(T):
            for s in range(2):
                var(('node',u,s,t),0,1,'B')
                for k in ('Pch','Pdis'):var((k,u,s,t),0,300)
                var(('Q',u,s,t),-400,400)
            var(('mode',u,t),0,1,'B')
        for t in range(T+1):var(('SOC',u,t),760 if t in (0,T) else 440,760 if t in (0,T) else 1080)
    rho=var(('rho',),0,4)
    for u in range(N):
        for t in range(T+1):
            for s in range(2):
                terms={}
                for a,(ss,tt,dd,aa) in enumerate(arcs):
                    if (ss,tt)==(s,t):add(terms,('flow',u,a),1)
                    if (dd,aa)==(s,t):add(terms,('flow',u,a),-1)
                row(terms,'=',1. if (s,t)==(0,0) else -1. if (s,t)==(1,T) else 0.)
                if t==T:continue
                terms={index['node',u,s,t]:1.}
                for a,(ss,tt,dd,aa) in enumerate(arcs):
                    if (ss,tt)==(s,t):add(terms,('flow',u,a),-1.)
                row(terms,'=',0.)
                stay=next(a for a,v in enumerate(arcs) if v==(s,t,s,t+1))
                row({index['Pch',u,s,t]:1,index['flow',u,stay]:-300},'<',0)
                row({index['Pdis',u,s,t]:1,index['flow',u,stay]:-300},'<',0)
                row({index['Pch',u,s,t]:1,index['mode',u,t]:-300},'<',0)
                row({index['Pdis',u,s,t]:1,index['mode',u,t]:300},'<',300)
                for k in range(16):
                    a=2*np.pi*k/16
                    row({index['Pdis',u,s,t]:float(np.cos(a)),index['Pch',u,s,t]:float(-np.cos(a)),index['Q',u,s,t]:float(np.sin(a)),index['flow',u,stay]:-float(400*np.cos(np.pi/16))},'<',0.)
        for t in range(T):
            terms={index['SOC',u,t+1]:1,index['SOC',u,t]:-1}
            for s in range(2):add(terms,('Pch',u,s,t),-.25*.95);add(terms,('Pdis',u,s,t),.25/.95)
            for a,(ss,tt,dd,aa) in enumerate(arcs):
                if tt==t and ss!=dd:add(terms,('flow',u,a),5.)
            row(terms,'=',0.)
    for t in range(T):
        terms={rho:-1000.}
        for u in range(N):
            for s in range(2):add(terms,('Pch',u,s,t),1.);add(terms,('Pdis',u,s,t),-1.)
        row(terms,'<',-float([600,300,700,200][t]))
        q={index['Q',u,s,t]:1. for u in range(N) for s in range(2)}
        row(q,'<',100.);row({j:-v for j,v in q.items()},'<',100.)
        mix=dict(terms);mix.pop(rho);mix.update({j:.125*v for j,v in q.items()});row(mix,'<',300.)
    ii=[];jj=[];vv=[]
    for i,r in enumerate(equations):
        for j,v in r.items():
            if v:ii.append(i);jj.append(j);vv.append(v)
    A=sparse.csr_matrix((vv,(ii,jj)),shape=(len(rhs),len(names)));c=np.zeros(len(names));c[rho]=1
    d=dict(names=np.array(names),row_names=np.array([f'fixture_{i}' for i in range(len(rhs))]),lower=np.array(lower,float),upper=np.array(upper,float),types=np.array(types),sense=np.array(senses),rhs=np.array(rhs),objective=c,constant=np.array(0.))
    pure=np.array([key[0] in ('flow','node','mode') for key in index]);return A,d,pure,index
def gpbuild(A,d,label):
    import gurobipy as gp
    m=gp.Model(label);m.Params.OutputFlag=0;v=m.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],vtype=d['types'],obj=d['objective']);m.ObjCon=float(d['constant']);m.addMConstr(A,v,d['sense'],d['rhs']);m.update();parameters(m,label,60)
    if label.endswith('_recourse'):m.Params.Method=1
    return m
def test(N,T):
    import gurobipy as gp
    A,d,pure,index=fixture(N,T);name=f'fixture_{N}_{T}';B=np.flatnonzero(d['types']=='B')
    direct=gpbuild(A,d,name+'_direct');paths_audit(name+'_direct',direct);direct.optimize()
    assert direct.Status==2;direct_obj=direct.ObjVal;dx=np.array(direct.getAttr('X'));assert hc.replay(A,d,dx,True)['PASS']
    known=WORK/'artifacts'/f'{name}_known.npz';save(known,x=dx,z=dx[B])
    cols=np.flatnonzero(pure);pure_rows=np.flatnonzero(np.asarray(A[:,~pure].getnnz(axis=1)).ravel()==0)
    master=gp.Model(name+'_master');master.Params.OutputFlag=0;mv=master.addMVar(len(cols),lb=d['lower'][cols],ub=d['upper'][cols],vtype=d['types'][cols]);theta=master.addVar(lb=0,ub=4,obj=1,name='theta');master.addMConstr(A[pure_rows][:,cols],mv,d['sense'][pure_rows],d['rhs'][pure_rows]);master.update();parameters(master,name+'_master',60)
    fd=dict(d,types=np.full(len(d['names']),'C'));rec=gpbuild(A,fd,name+'_recourse');rv=rec.getVars();bvars=[rv[j] for j in B];position={j:k for k,j in enumerate(cols)};mb=[mv[position[j]].item() for j in B]
    accepted=[];trace=[];ub=direct_obj;lb=0.;result=None
    for it in range(100):
        paths_audit(name+'_master_'+str(it),master);master.optimize();assert master.Status==2;lb=master.ObjBound
        if ub-lb<=1e-8:result=True;break
        z=np.rint([v.X for v in mb]);rec.reset();rec.setAttr('LB',bvars,z);rec.setAttr('UB',bvars,z);rec.update();paths_audit(name+'_recourse_'+str(it),rec);rec.optimize()
        if rec.Status==2:
            pi=np.array(rec.getAttr('Pi'));kind='optimality';x=np.array(rec.getAttr('X'));assert hc.replay(A,d,x,True)['PASS'];ub=min(ub,rec.ObjVal)
        elif rec.Status==3:pi=-np.array(rec.getAttr('FarkasDual'));kind='feasibility'
        else:raise AssertionError('FIXTURE_UNRESOLVED')
        cc=certify_with_explicit_projection(A,d,B,pi,WORK/'artifacts'/f'{name}_cut_{it:03d}',kind);assert cc['PASS'],cc
        assert known_witnesses(cc,d,[known])['PASS']
        value=exact_value(cc,z)
        if kind=='feasibility':assert value>1e-8
        expression=gp.LinExpr(cc['beta'].tolist(),mb)+cc['intercept']
        if kind=='optimality':master.addConstr(theta>=expression)
        else:master.addConstr(expression<=0)
        cc.pop('beta');accepted.append(cc);trace.append(dict(it=it,master_LB=lb,UB=ub,kind=kind,source_cut_value=float(value),recourse_status=rec.Status))
    report=dict(PASS=bool(result and abs(direct_obj-ub)<=1e-8 and abs(direct_obj-lb)<=1e-8),N=N,T=T,sites=2,direct_MILP_status=direct.Status,direct_objective=direct_obj,benders_LB=lb,benders_UB=ub,iterations=len(trace),optimality_cuts=sum(c['kind']=='optimality' for c in accepted),feasibility_cuts=sum(c['kind']=='feasibility' for c in accepted),trace=trace,bounded_algebraic_fixture_only=True,fixture_data_not_scientific_inputs=True,all_types_and_bounds_preserved=True)
    direct.dispose();master.dispose();rec.dispose();return report
def main():
    benchmark=json.loads((REPORTS/'RECOURSE_NUMERICAL_AUDIT.json').read_text(encoding='utf-8-sig'));assert benchmark['performance_PASS']
    out=[test(1,2),test(2,3)];write(REPORTS/'BOUNDED_FIXTURE_VERIFICATION.json',dict(PASS=all(x['PASS'] for x in out),fixtures=out,numerical_contract=1e-8,independent_direct_monolithic_MILP=True));print('FIXTURES',json.dumps(clean(out)),flush=True)
if __name__=='__main__':main()

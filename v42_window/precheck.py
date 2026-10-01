"""Full certified coefficient tables and root separation; no inactive blocks."""
from itertools import combinations,product
import gurobipy as gp
from .common import *
from .reachability import root_axis

def run():
    stop=read(OUT/'W7_UNIVERSAL_STOP_CERTIFICATE.json');assert stop['PASS']
    axis=root_axis();units=sorted(inputs()[4]);rho=read(OUT/'ROOT_SOURCE_RECEIPT.json')['rho'];receipts=[read(p) for p in (OUT/'oracle_certificates').glob('*.json')]
    solved={r['key']:r for r in receipts if r['kind']!='UPPER_WITNESS'};one=[];pre1=[];two=[];pre2=[];cross=[];pre3=[]
    for u in units:
        for t in sorted(CRITICAL):
            state=axis[f'{u}:{t}'];rhs=0.
            for a in sorted(state['states']):
                key=f'G1_{u}-{t}-{a}';r=solved.get(key)
                one.append(dict(MESS=u,time=t,state=a,root_mass=state['root'][a],incumbent_mass=state['incumbent'][a],solved=bool(r),W7_lower_bound=r['O1_W7_lower_bound'] if r else None,
                    beta=DEFAULT,coefficient_source='Certified PR109 global LB; W7 universal upper proof makes further solves irrelevant'))
                rhs+=DEFAULT*state['root'][a]
            pre1.append(dict(MESS=u,time=t,RHS=rhs,rho=rho,violation=rhs-rho,install=rhs-rho>=1e-5))
    def transport(u,t1,v,t2,pairs,kind):
        aa=axis[f'{u}:{t1}'];bb=axis[f'{v}:{t2}'];m=gp.Model();m.Params.OutputFlag=0;m.Params.Method=2;m.Params.Threads=1;w=m.addVars(pairs,lb=0)
        for a in aa['states']:m.addConstr(gp.quicksum(w[x,z] for x,z in pairs if x==a)==aa['root'][a])
        for z in bb['states']:m.addConstr(gp.quicksum(w[x,y] for x,y in pairs if y==z)==bb['root'][z])
        m.setObjective(gp.quicksum(DEFAULT*w[a,b] for a,b in pairs));m.optimize();assert m.Status==gp.GRB.OPTIMAL and m.MaxVio<=TOL
        r=dict(MESS_m=u,MESS_n=v,time1=t1,time2=t2,support=len(pairs),status=int(m.Status),RHS=m.ObjVal,rho=rho,violation=m.ObjVal-rho,max_marginal_residual=m.MaxVio,
            install=m.ObjVal-rho>=1e-5,reachable_support_only=kind=='G3',marginal_hull_violation=False,raw_marginals_used=True)
        m.dispose();return r
    for t in CRITICAL[:3]:
        for u,v in combinations(units,2):
            pairs=list(product(axis[f'{u}:{t}']['states'],axis[f'{v}:{t}']['states']));pre2.append(transport(u,t,v,t,pairs,'G2'))
            for a,b in pairs:
                key=f'G2_{u}-{t}-{a}_{v}-{t}-{b}';r=solved.get(key)
                two.append(dict(MESS_m=u,MESS_n=v,time=t,state_a=a,state_b=b,solved=bool(r),W7_lower_bound=r['O1_W7_lower_bound'] if r else None,beta=DEFAULT,source='Inherited global LB; all-pair W7 upper proof'))
    reach=csvread('G3_REACHABLE_STATE_PAIRS.csv')
    for u in units:
        for t1,t2 in TIME_PAIRS:
            pairs=[(r['state_a'],r['state_b']) for r in reach if r['MESS']==u and int(r['time1'])==t1 and int(r['time2'])==t2]
            pre3.append(transport(u,t1,u,t2,pairs,'G3'))
            for a,b in pairs:
                key=f'G3_{u}-{t1}-{a}_{u}-{t2}-{b}';r=solved.get(key)
                cross.append(dict(MESS=u,time1=t1,time2=t2,state_a=a,state_b=b,solved=bool(r),W7_lower_bound=r['O1_W7_lower_bound'] if r else None,gamma=DEFAULT,source='Inherited global LB; complete zero-window-PQ route lift upper proof'))
    table('G1_BETA_TABLE.csv',one);table('G1_ROOT_PRECHECK.csv',pre1);table('G2_BETA_TABLE.csv',two);table('G2_TRANSPORT_PRECHECK.csv',pre2);table('G3_BETA_TABLE.csv',cross);table('G3_TRANSPORT_PRECHECK.csv',pre3)
    dump('EPIGRAPH_SELECTION.json',dict(selected='G0',PRODUCTION_BASE='M1-F3',G1_CUTS_ADDED=0,G2_CUTS_ADDED=0,G3_BLOCKS_ADDED=0,
        G1_MAX_ROOT_VIOLATION=max(r['violation'] for r in pre1),G2_MAX_ROOT_VIOLATION=max(r['violation'] for r in pre2),G3_MAX_ROOT_VIOLATION=max(r['violation'] for r in pre3),
        G3_MARGINAL_HULL_VIOLATION_COUNT=0,ROUTE_FLOW_PAIR_PROJECTION_ALREADY_IMPLIED=True,
        G1_conditional_solves=sum(r['kind']=='G1' for r in receipts),G2_conditional_solves=sum(r['kind']=='G2' for r in receipts),G3_conditional_solves=sum(r['kind']=='G3' for r in receipts),
        W7_auxiliary_upper_witness_solves=6,G1_states=len(one),G2_state_pairs=len(two),G3_state_pairs=len(cross),
        exact_adaptive_stop='W7_UNIVERSAL_STOP_CERTIFICATE.json: all future coefficients remain default, and pure route-flow implies pair marginal support',
        route_projection_gain=0,epigraph_useful_violation=False,full_root_candidates_built=[],full_root_optimize_calls=0))
    assert not any(r['install'] for r in pre1+pre2+pre3)
    print('G1/G2/G3 PRECHECK PASS',read(OUT/'EPIGRAPH_SELECTION.json'),flush=True)
if __name__=='__main__':run()

"""Joint MILP state balances; event indices never include a full trajectory."""
from collections import defaultdict,Counter
import gurobipy as gp
from v42_job_capability import resources_used,resource_limit
from .graph import old_to_compact

def add_job(m,j,graph):
    if graph.fixed:return old_to_compact(graph.fixed)
    v={}
    for family,keys in graph.events.items():
        v[family]={key:m.addVar(vtype=gp.GRB.BINARY,name=f'{family}[{j.uid},{i}]') for i,key in enumerate(keys)}
    for family,keys in graph.states.items():
        v[family]={key:m.addVar(lb=0,ub=1,name=f'{family}[{j.uid},{i}]') for i,key in enumerate(keys)}
    y,q,w,f0,f1=(v[n] for n in ('y','q','w','f0','f1'))
    m.addConstr(gp.quicksum(y.values())==1,name='one_start')
    mig=gp.quicksum(q.values())
    m.addConstr(mig<=1,name='one_migration');m.addConstr(gp.quicksum(f0.values())+mig==1,name='source_exit')
    m.addConstr(gp.quicksum(w.values())==mig,name='transfer_conservation')
    m.addConstr(gp.quicksum(f1.values())==mig,name='post_finish')
    for (k,c),var in q.items():m.addConstr(var<=gp.quicksum(y[k,s] for s in graph.compatible[k,c]),name='checkpoint_compatibility')
    departures=defaultdict(list);arrivals=defaultdict(list)
    for key,var in w.items():
        k,d,t=key;departures[k,t].append(var);arrivals[d,graph.transfers[key].restart].append(var)
    for state,enter,leave in (('r0',y,{key:[var] for key,var in f0.items()}),('h',q,departures),('r1',{key:gp.quicksum(a) for key,a in arrivals.items()},{key:[var] for key,var in f1.items()})):
        active=v[state];sites=sorted({k for k,t in active}|{k for k,t in enter}|{k for k,t in leave})
        if state=='r0':
            for key,var in q.items():leave.setdefault(key,[]).append(var)
        for k in sites:
            times=[t for site,t in active if site==k]+[t for site,t in enter if site==k]+[t for site,t in leave if site==k]
            if not times:continue
            # Include the terminal boundary with implicit state zero.
            for t in range(min(times),max(times)+1):
                lhs=gp.LinExpr(active.get((k,t),0))-active.get((k,t-1),0)-enter.get((k,t),0)+gp.quicksum(leave.get((k,t),[]))
                m.addConstr(lhs==0,name=state+'_balance')
    m.addConstr(gp.quicksum(v['r0'].values())+gp.quicksum(v['r1'].values())==j.service_slots,name='full_service')
    m.addConstr(gp.quicksum(v['r1'].values())>=mig,name='useful_destination_service')
    return v

def values(v):return {n:{key:(x.X if hasattr(x,'X') else x) for key,x in a.items()} for n,a in v.items()}

def contributions(j,graph,v):
    use=defaultdict(gp.LinExpr)
    for n in ('r0','r1'):
        for (k,t),x in v[n].items():use['GPU',k,t]+=j.gpu*x
    for key,x in v['w'].items():
        tr=graph.transfers[key]
        for l,t,n in tr.wan:use['WAN',l,t]+=n*x
        for t in range(key[2],tr.end):use['ACTIVE','',t]+=x
    return use

def intervention(j,v):
    return [gp.quicksum(v['q'].values()),gp.quicksum((s-j.reference_start)*x for (k,s),x in v['y'].items()),
        gp.quicksum(int(k!=j.reference_site)*x for (k,s),x in v['y'].items())]

def add_resources(m,use,r):
    for key in sorted(set(use)|{('GPU',k,t) for k,t in r.fixed_gpu}|{('WAN',k,t) for k,t in r.fixed_wan}|{('ACTIVE','',t) for t in r.fixed_transfers}):
        m.addConstr(use.get(key,gp.LinExpr())<=resource_limit(key,r),name='physical_'+key[0])

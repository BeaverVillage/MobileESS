"""Necessary outer-master proofs across ALL physical same-site rank options.

Neutral options enter only this lower-bound relaxation, never the scientific
restricted model. Each fresh feasibility solve has a 600-second native limit.
No four-pass scientific objective is optimized here.
"""
import csv,sys
from fractions import Fraction as Q
from collections import defaultdict
import numpy as np,scipy.sparse as sp,gurobipy as gp,psutil
from .common import *

def make(day,pool,rank):
    d=load(day);jobs,bounds,r,graphs,classes=d[1],d[2],d[3],d[5],d[7]['classes']
    m=gp.Model('ALL_RANK_PHYSICAL_PREFIX_OUTER_MASTER');m.Params.OutputFlag=0
    for k,v in SETTINGS.items():m.setParam(k,v)
    m.Params.TimeLimit=600;m.Params.InfUnbdInfo=1;m.Params.DualReductions=0
    prefix=min(t for (link,t),cap in r.wan_capacities.items() if cap>0)
    occ=defaultdict(gp.LinExpr);cls={};acts={};counts={};opts=[x for x in pool if int(x['rank_same_site'])<=rank]
    by=defaultdict(list)
    for x in opts:by[x['class_id']].append(x)
    for key,us in sorted(classes.items()):
        j=jobs[us[0]];g=graphs[us[0]];N=len(us);cls[key]=m.addVar(vtype='B',name='expand_class['+key+']');ys=[]
        for site,start in g.events['y']:
            cps=[cp for (s,cp),ss in g.compatible.items() if s==site and start in ss]
            ends=([start+j.service_slots] if (site,start+j.service_slots) in g.events['f0'] else [])+cps
            if not ends:continue
            v=m.addVar(lb=0,ub=N,vtype='I');ys.append(v)
            for t in range(start,min(min(ends),prefix)):occ[site,t]+=j.gpu*v
        for x in by[key]:
            v=m.addVar(lb=0,ub=N,vtype='I');act=m.addVar(vtype='B',name='activate['+x['option_id']+']')
            acts[x['option_id']]=act;counts[x['option_id']]=v;ys.append(v)
            m.addConstr(v<=N*act);m.addConstr(act<=cls[key])
            start=int(x['start'])
            for t in range(start,min(start+j.service_slots,prefix)):occ[x['site'],t]+=j.gpu*v
        m.addConstr(gp.quicksum(ys)==N,name='class_exact_cardinality['+key+']')
    for site,cap in r.capacities.items():
        for t in range(prefix):m.addConstr(occ[site,t]<=cap-r.fixed_gpu.get((site,t),0),name=f'GPU[{site},{t}]')
    mx=m.addVar(lb=0)
    for x in opts:m.addConstr(mx>=int(x['abs_delta_start'])*acts[x['option_id']])
    ob=dict(classes=gp.quicksum(cls.values()),options=gp.quicksum(acts.values()),maximum_displacement=mx,
            sum_displacement=gp.quicksum(int(x['abs_delta_start'])*acts[x['option_id']] for x in opts))
    m.setObjective(0.);m.update();return m,ob,acts,opts

def snapshot_ray(m,folder):
    a=m.getA();sp.save_npz(folder/'MATRIX.npz',a)
    z=dict(lb=np.array(m.getAttr('LB')),ub=np.array(m.getAttr('UB')),rhs=np.array(m.getAttr('RHS')),sense=np.array(m.getAttr('Sense')))
    np.savez_compressed(folder/'ATTRIBUTES.npz',**z);ray=np.array(m.getAttr('FarkasDual'));np.savez_compressed(folder/'RAW_RAY.npz',ray=ray)
    c=defaultdict(Q);b=Q(0);norm=Q(0)
    for i in np.flatnonzero(ray):
        w=Q(float(ray[i]));s=z['sense'][i]
        if s=='<' and w<0 or s=='>' and w>0:raise ValueError('RAY_SIGN')
        norm+=abs(w);b+=w*Q(float(z['rhs'][i]));lo,hi=a.indptr[i:i+2]
        for j,v in zip(a.indices[lo:hi],a.data[lo:hi]):c[int(j)]+=w*Q(float(v))
    low=Q(0)
    for j,w in c.items():
        if not w:continue
        bound=float(z['lb'][j] if w>0 else z['ub'][j])
        if not np.isfinite(bound) or abs(bound)>=1e100:raise ValueError('RAY_UNBOUNDED')
        low+=w*Q(bound)
    allowance=Q(1e-5)*(norm+sum(abs(w) for w in c.values()));margin=low-b
    result=dict(PASS=margin>allowance,margin=str(margin),allowance=str(allowance),all_physical_same_site_rank_options_in_outer_relaxation=True,
                ray=record(folder/'RAW_RAY.npz'),matrix=record(folder/'MATRIX.npz'),attributes=record(folder/'ATTRIBUTES.npz'))
    atomic(folder/'EXACT_RAY.json',result)
    if not result['PASS']:raise ValueError('ALL_RANK_PREFIX_PROOF_FAILED')

def main(day):
    folder=CASE/day/'ALL_PHYSICAL_RANK_MINIMUM_PROBES';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'RESULT.json').exists():raise PermissionError('NO_DUPLICATE_PROBE')
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==psutil.Process().pid:continue
        if str(p.info['name']).lower().startswith('python') and any(x in ' '.join(p.info['cmdline'] or []) for x in ('adaptive.solve_snapshot','adaptive.restricted','adaptive.capacity_master','adaptive.minimum_probe','b1.worker')):raise PermissionError('OTHER_HEAVY_OPTIMIZER:'+str(p.pid))
    d=load(day);pool=[]
    with (OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv')).open(encoding='utf8',newline='') as f:
        for x in csv.DictReader(f):
            if int(x['checkpoint'])==-1 and x['site']==d[1][d[7]['classes'][x['class_id']][0]].reference_site:pool.append(x)
    prior=read(CASE/day/'CAPACITY_SELECTION_V2/RESULT.json');rank=prior['first_prefix_feasible_rank']
    selected=prior['selected'];targets=dict(classes=len({x['class_id'] for x in selected}),options=len(selected),
        maximum_displacement=max(int(x['abs_delta_start']) for x in selected),sum_displacement=sum(int(x['abs_delta_start']) for x in selected))
    trace=[];PASS=True
    for k in range(1,rank):
        f=folder/('RANK_'+str(k));f.mkdir(exist_ok=True);m,ob,acts,opts=make(day,pool,k);lp=m.relax();lp.optimize()
        event=dict(kind='earlier_rank_outer_LP',rank=k,options=len(opts),status=lp.Status,runtime=lp.Runtime,Work=lp.Work)
        if lp.Status==gp.GRB.INFEASIBLE:snapshot_ray(lp,f)
        else:PASS=False
        trace.append(event);atomic(folder/'TRACE.json',trace);lp.dispose();m.dispose()
        print('ALL_RANK_LP',event,flush=True)
        if not PASS:break
    if PASS:
        locks={}
        for name,target in targets.items():
            f=folder/('PROBE_'+name);f.mkdir(exist_ok=True);m,ob,acts,opts=make(day,pool,rank)
            for k,v in locks.items():m.addConstr(ob[k]==v)
            m.addConstr(ob[name]<=target-1);m.update();m.Params.LogFile=str(f/'NATIVE.log');m.Params.OutputFlag=1
            lp=m.relax();lp.optimize();event=dict(kind='strictly_better_domain_outer_feasibility',rank=rank,name=name,target=target,LP_status=lp.Status,LP_runtime=lp.Runtime,LP_Work=lp.Work)
            if lp.Status==gp.GRB.INFEASIBLE:snapshot_ray(lp,f);proved=True
            elif lp.Status==gp.GRB.OPTIMAL:
                m.optimize();event.update(MIP_status=m.Status,MIP_runtime=m.Runtime,MIP_Work=m.Work,nodes=m.NodeCount,solutions=m.SolCount)
                proved=m.Status==gp.GRB.INFEASIBLE
                if m.SolCount:atomic(f/'BETTER_NECESSARY_SELECTION.json',[x for x in opts if acts[x['option_id']].X>.5])
            else:proved=False
            event['strict_improvement_excluded']=proved;trace.append(event);atomic(folder/'TRACE.json',trace);lp.dispose();m.dispose()
            print('ALL_RANK_MIN_PROBE',event,flush=True)
            if not proved:PASS=False;break
            locks[name]=target
    atomic(folder/'RESULT.json',dict(PASS=PASS,scope='first same-site rank conditional lower bound over ALL physical options, not a full-universe global optimum',
        rank=rank,targets=targets,trace=trace,full_integer_feasible_point_checked_elsewhere=True,scientific_objective_calls=0,
        deterministic_unique_tie_proven=False,global_physical_universe_minimum_proven=False))
if __name__=='__main__':main(sys.argv[1])

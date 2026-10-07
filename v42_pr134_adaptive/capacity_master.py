"""Necessary-only class resource master, never a scientific A1 PASS oracle.

It is an outer restriction/projection audit for candidate selection. Every
chosen domain still requires full unchanged native LP/MIP and physical replay.
"""
import csv,sys,time,itertools
from fractions import Fraction
from collections import defaultdict
import numpy as np
import gurobipy as gp
from .common import *
def main(day):
    import psutil
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==psutil.Process().pid:continue
        if str(p.info['name']).lower().startswith('python') and any(x in ' '.join(p.info['cmdline'] or []) for x in ('adaptive.solve_snapshot','adaptive.restricted','adaptive.capacity_master','adaptive.minimum_probe','b1.worker')):raise PermissionError('OTHER_HEAVY_OPTIMIZER:'+str(p.pid))
    data=load(day);bundle,jobs,bounds,r,raw,graphs,old,prep=data
    folder=CASE/day/'CAPACITY_SELECTION_V2';folder.mkdir(parents=True,exist_ok=True)
    if (folder/'RESULT.json').exists():raise PermissionError('NO_DUPLICATE_MASTER_SEARCH')
    pool=[]
    with (OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv')).open(encoding='utf8',newline='') as f:
        for row in csv.DictReader(f):
            if int(row['checkpoint'])==-1 and row['site']==jobs[prep['classes'][row['class_id']][0]].reference_site:pool.append(row)
    admitted={row['option_id'] for row in pool if row['classification']=='CERTIFICATE_BREAKING'}
    history=[];selected=None
    # At every finite rank, retain only previously certified-breaking options.
    for rank in sorted(set(int(row['rank_same_site']) for row in pool)):
        while True:
            candidates=[row for row in pool if row['option_id'] in admitted and int(row['rank_same_site'])<=rank]
            m=gp.Model('NECESSARY_RESOURCE_DOMAIN_MASTER');m.Params.OutputFlag=0
            for key,value in SETTINGS.items():m.setParam(key,value)
            m.Params.TimeLimit=600.;m.Params.InfUnbdInfo=1;m.Params.DualReductions=0
            tail=max(b.latest_completion for b in bounds.values());occ=defaultdict(gp.LinExpr);y={};activation={};classes={};card={}
            # Keep only STAY paths in this master. If migration is present,
            # require it is immutable RUNNING and cannot affect the sampled
            # pre-WAN prefix. This proves prefix infeasibility only, and a
            # feasible point is a constructive STAY schedule, not full A1 PASS.
            prefix=min(t for (link,t),capacity in r.wan_capacities.items() if capacity>0)
            for key,us in sorted(prep['classes'].items()):
                uid=us[0];j=jobs[uid];g=graphs[uid];N=len(us)
                klass=m.addVar(vtype='B',name='expand_class['+key+']');classes[key]=klass
                ys=[]
                for site,start in g.events['y']:
                    if (site,start+j.service_slots) not in g.events['f0']:continue
                    v=m.addVar(lb=0,ub=N,vtype='I',name=f'S0[{key},{site},{start}]');ys.append(v);y[key,site,start]=v
                    # Every actual path consumes its source gang until either
                    # its full STAY finish or its earliest physically supported
                    # checkpoint. Later source/destination load is relaxed.
                    # Pausing before WAN begins is allowed in S0; never freeze
                    # RUNNING compute through the WAN-zero prefix incorrectly.
                    cps=[cp for (s,cp),ss in g.compatible.items() if s==site and start in ss]
                    guaranteed_end=min([start+j.service_slots]+cps)
                    for t in range(start,min(guaranteed_end,prefix)):occ[site,t]+=j.gpu*v
                for row in [x for x in candidates if x['class_id']==key]:
                    site=row['site'];start=int(row['start'])
                    v=m.addVar(lb=0,ub=N,vtype='I',name='added_count['+row['option_id']+']');y[key,site,start]=v;ys.append(v)
                    a=m.addVar(vtype='B',name='activate['+row['option_id']+']');activation[row['option_id']]=a
                    m.addConstr(v<=N*a);m.addConstr(a<=klass)
                    for t in range(start,min(start+j.service_slots,prefix)):occ[site,t]+=j.gpu*v
                card[key]=m.addConstr(gp.quicksum(ys)==N,name='class_exact_cardinality['+key+']')
            capacity={}
            for site,cap in r.capacities.items():
                for t in range(prefix):capacity[site,t]=m.addConstr(occ[site,t]<=cap-r.fixed_gpu.get((site,t),0),name=f'GPU[{site},{t}]')
            m.setObjective(0.);m.update();lp=m.relax();lp.optimize()
            event=dict(rank=rank,added_candidate_options=len(candidates),LP_status=lp.Status,LP_runtime=lp.Runtime,LP_Work=lp.Work,
                master_scope='unchanged pre-WAN GPU/class projection; never full A1',full_scientific_feasibility_claimed=False)
            if lp.Status==gp.GRB.INFEASIBLE:
                # Integer coefficient/RHS master: native rational ray checked
                # against every coefficient and finite bound before use.
                ray=[Fraction(float(x)) for x in lp.getAttr('FarkasDual')]
                a=lp.getA();rhs=np.array(lp.getAttr('RHS'));lb=np.array(lp.getAttr('LB'));ub=np.array(lp.getAttr('UB'))
                c=defaultdict(Fraction);b=Fraction(0)
                for i,w in enumerate(ray):
                    if not w:continue
                    b+=w*Fraction(float(rhs[i]));p,q=a.indptr[i:i+2]
                    for j,v in zip(a.indices[p:q],a.data[p:q]):c[int(j)]+=w*Fraction(float(v))
                minimum=Fraction(0);bad=False
                for j,v in c.items():
                    if not v:continue
                    bound=float(lb[j] if v>0 else ub[j]);bad |= abs(bound)>=1e100
                    if abs(bound)<1e100:minimum+=v*Fraction(bound)
                if bad or minimum<=b:raise ValueError('MASTER_EXACT_RAY_NOT_VALID')
                coefficients={key:ray[row.index] for key,row in capacity.items()};duals={key:ray[row.index] for key,row in card.items()}
                breaking=[]
                for row in pool:
                    if row['option_id'] in admitted:continue
                    j=jobs[prep['classes'][row['class_id']][0]];start=int(row['start']);site=row['site']
                    cost=duals[row['class_id']]+j.gpu*sum((coefficients.get((site,t),Fraction(0)) for t in range(start,min(start+j.service_slots,prefix))),Fraction(0))
                    if cost<0:
                        admitted.add(row['option_id']);row.update(classification='CERTIFICATE_BREAKING',certificate_delta_exact=str(cost),class_delta_exact=str(cost*len(prep['classes'][row['class_id']])))
                        breaking.append(row)
                event.update(exact_margin=str(minimum-b),new_certified_breaking=len(breaking))
                history.append(event);atomic(folder/'TRACE.json',history)
                lp.dispose();m.dispose()
                if any(int(x['rank_same_site'])<=rank for x in breaking):continue
                break
            if lp.Status!=gp.GRB.OPTIMAL:
                history.append(event);atomic(folder/'TRACE.json',history);lp.dispose();m.dispose();raise ValueError('MASTER_LP_UNRESOLVED')
            lp.dispose();m.optimize();event.update(MIP_status=m.Status,MIP_runtime=m.Runtime,MIP_Work=m.Work,solutions=m.SolCount)
            if not m.SolCount:
                history.append(event);atomic(folder/'TRACE.json',history);m.dispose();raise ValueError('MASTER_INTEGER_UNRESOLVED')
            # These are domain-selection objectives, not PR134 four-pass A1.
            displacement=m.addVar(lb=0,name='max_start_displacement')
            for row in candidates:m.addConstr(displacement>=int(row['abs_delta_start'])*activation[row['option_id']])
            objectives=[('classes',gp.quicksum(classes.values())),('options',gp.quicksum(activation.values())),('maximum_displacement',displacement),
                ('sum_displacement',gp.quicksum(int(row['abs_delta_start'])*activation[row['option_id']] for row in candidates))]
            lex=[]
            for name,obj in objectives:
                m.setObjective(obj);m.optimize()
                result=dict(name=name,status=m.Status,runtime=m.Runtime,Work=m.Work,incumbent=m.ObjVal if m.SolCount else None,bound=m.ObjBound,nodes=m.NodeCount)
                lex.append(result)
                atomic(folder/'LEX_PROGRESS.json',dict(rank=rank,passes=lex,started=now()))
                if m.Status!=gp.GRB.OPTIMAL or not m.SolCount or __import__('math').ceil(m.ObjBound-1e-6)<round(m.ObjVal):
                    raise ValueError('MASTER_LEX_MINIMUM_NOT_PROVEN:'+name)
                m.addConstr(obj==round(m.ObjVal))
            # Final deterministic rank on finite candidates; retains all exact
            # earlier objective locks. Not reported as global physical minimum.
            ordered=sorted(candidates,key=lambda x:(int(x['delta_start'])>0,x['site'],int(x['start']),x['option_id']))
            m.setObjective(gp.quicksum((i+1)*activation[row['option_id']] for i,row in enumerate(ordered)));m.optimize()
            if m.Status!=gp.GRB.OPTIMAL:raise ValueError('MASTER_TIE_UNRESOLVED')
            selected=[row for row in ordered if activation[row['option_id']].X>.5]
            event.update(selection_objectives=lex,selected_options=len(selected),selected_classes=len(set(x['class_id'] for x in selected)))
            history.append(event);atomic(folder/'TRACE.json',history);atomic(CASE/day/'MASTER_SELECTION.json',selected)
            atomic(folder/'RESULT.json',dict(PASS=True,first_prefix_feasible_rank=rank,selected=selected,trace=history,
                scope='exact resource-prefix necessity and conditional STAY witness only',global_full_feasible_minimum_proven=False,
                all_full_physical_and_grid_LP_MIP_validation_required=True))
            m.dispose();print('MASTER_SELECTED',rank,len(selected),'classes',event['selected_classes'],flush=True);return
if __name__=='__main__':main(sys.argv[1])

"""Exact raw artificial accounting; influence allocation is explicitly heuristic."""
from fractions import Fraction
from collections import defaultdict
import re
import numpy as np
from v42_pr134_b1.common import atomic,table
from v42_a_stage_phase1.core import phase_objective
from v42_a_stage_phase1.runner import serial
from .policy import POLICY

def context(row,atlas,axes):
    family=str(atlas['rf_names'][atlas['rf'][row]])
    key=next((k for k,r in axes.items() if r==row),None)
    if key is not None:return dict(family=family,category=key[0],time=int(key[2]),site=str(key[1]),node=None)
    if family in ('voltage_lower','voltage_upper'):
        indices=atlas[family+'_rows'];i=int(np.searchsorted(indices,row))
        if i>=len(indices) or indices[i]!=row:raise ValueError('ROW_ATLAS_AXIS')
        slot,node=divmod(i,len(atlas['node_names']));name=str(atlas['node_names'][node])
        match=re.search(r'(?:aidc|mess_(?:idc|sta))(\d+)',name,re.I)
        site=match.group(0).upper() if match else 'BUS_'+name.rsplit('.',1)[0]
        return dict(family=family,category='GRID',time=slot+24,site=site,node=name)
    category='CC4' if 'CC4' in family else 'RUNTIME' if 'RT_' in family else 'GRID'
    return dict(family=family,category=category,time=None,site='GLOBAL_SHARED',node=None)

def analyze(master,raw,data,axes,owned,atlas,folder):
    phi=phase_objective(master,raw['X']);n=master.original.matrix.shape[1]
    byrow=defaultdict(Fraction);signed_effect=defaultdict(float)
    for row,weight,sign,x in zip(master.artificial_rows,master.weights,master.artificial_signs,raw['X'][n:]):
        if x:
            value=weight*Fraction(float(x));byrow[row]+=value
            if x>0:signed_effect[row]+=float(value)*sign
    if sum(byrow.values(),Fraction(0))!=phi:raise ValueError('ARTIFICIAL_ACCOUNTING_MISMATCH')
    ordered=sorted(((row,value) for row,value in byrow.items() if value>0),key=lambda e:(-e[1],e[0]))
    families=defaultdict(Fraction);times=defaultdict(Fraction);sites=defaultdict(Fraction);categories=defaultdict(Fraction)
    rows=[];cumulative=Fraction(0)
    for row,value in sorted(byrow.items(),key=lambda e:(-e[1],e[0])):
        c=context(row,atlas,axes);families[c['family']]+=value;times[str(c['time'])]+=value;sites[c['site']]+=value;categories[c['category']]+=value
        if value>0:cumulative+=value
        rows.append(dict(row=int(row),**c,weighted_artificial=str(value),Phi_share=float(value/phi) if phi else None,
            cumulative_positive_share=float(cumulative/phi) if phi else None,workload_class='GLOBAL_SHARED_GRID' if c['category']=='GRID' else 'SHARED_RESOURCE_ROW'))
    concentration={}
    for target in (50,80,90):
        total=Fraction(0);chosen=[]
        for row,value in ordered:
            total+=value;chosen.append(int(row))
            if total>=phi*Fraction(target,100):break
        concentration[str(target)]=dict(minimum_row_count=len(chosen),rows=chosen,cumulative_share=float(total/phi) if phi else None)
    keys=tuple(axes);effect=np.zeros(len(keys));A=master.original.matrix
    # Binding equations give d(global resource variable)=-d(Bz)/a.
    # This is a ranking derivative with other global controls held fixed.
    # It neither asserts a feasible global direction nor changes native Pi.
    for row,importance in signed_effect.items():
        for j,key in enumerate(keys):
            resource_row=axes[key]
            if row==resource_row:effect[j]+=importance/max(float(phi),1e-30);continue
            if key[0] not in ('GPU','RUNTIME'):continue
            column=int(atlas['resource_variables'][j]);binding=float(A[resource_row,column])
            if not binding:raise ValueError('RESOURCE_BINDING_COEFFICIENT_REQUIRED')
            effect[j]+=importance*(-float(A[row,column])/binding)/max(float(phi),1e-30)
    roster=sorted(data[7]['classes']);ci={k:i for i,k in enumerate(roster)}
    owners=np.full(A.shape[1],-1,dtype=int)
    for j,key in owned.items():owners[j]=ci[key]
    coupling=A[list(axes.values())].tocoo();mask=owners[coupling.col]>=0
    groups=owners[coupling.col[mask]]*len(keys)+coupling.row[mask]
    current=np.bincount(groups,weights=coupling.data[mask]*raw['X'][coupling.col[mask]],minlength=len(roster)*len(keys)).reshape(len(roster),len(keys))
    prefixes={}
    for site in sorted(data[3].capacities):
        horizon=max(k[2] for k in keys if k[0]=='GPU' and k[1]==site)+1
        prefix=np.zeros(horizon+1)
        for t in range(horizon):prefix[t+1]=prefix[t]+effect[keys.index(('GPU',site,t))]
        prefixes[site]=prefix
    ranks=[];baseline={}
    for key in roster:
        uid=data[7]['classes'][key][0];job=data[1][uid];N=len(data[7]['classes'][key]);old=float(current[ci[key]]@effect);baseline[key]=old
        if data[5][uid].fixed:
            from v42_a_stage_early.candidate import physical_price
            _,constant=physical_price(data[5][uid].fixed,job,data[4][uid],data[0],{k:i for i,k in enumerate(keys)},np.zeros(len(keys)),N,0)
            old+=sum(float(v)*effect[j] for j,v in constant.items());baseline[key]=old
        best=-float('inf')
        # All scientific STAY placements are retained; this scan is ranking only.
        for start,site in atlas['domains'][uid].stays:
            score=-N*job.gpu*(prefixes[site][start+job.service_slots]-prefixes[site][start])
            best=max(best,score)
        eligible=not (data[5][uid].fixed and len(atlas['domains'][uid].stays)==1 and not atlas['domains'][uid].blocks)
        ranks.append(dict(class_id=key,cardinality=N,score=float(best-old),migration_capable=bool(atlas['domains'][uid].blocks),inactive_candidates_available=eligible,
            direct_Phi_attribution='shared global grid; no unique causal class allocation'))
    ranks.sort(key=lambda r:(-r['score'],r['class_id']))
    eligible_ranks=[r for r in ranks if r['inactive_candidates_available']]
    target={r['class_id'] for r in eligible_ranks[:POLICY['target_top_overall_classes']]}
    target.update(r['class_id'] for r in [r for r in eligible_ranks if r['migration_capable']][:POLICY['target_top_migration_capable_classes']])
    target=[r['class_id'] for r in ranks if r['class_id'] in target]
    receipt=dict(PASS=True,exact_Phi=str(phi),Phi=float(phi),positive_weighted_sum=str(sum((v for v in byrow.values() if v>0),Fraction(0))),
        negative_weighted_sum=str(sum((v for v in byrow.values() if v<0),Fraction(0))),positive_rows=len(ordered),
        by_original_row_family=serial(dict(families)),by_time=serial(dict(times)),by_site=serial(dict(sites)),by_coupling_category=serial(dict(categories)),
        workload_class_exact_attribution='GLOBAL_SHARED_GRID; independent global voltage rows have no direct local class coefficient',
        concentration=concentration,top_rows=rows,classes_ranked=ranks,target_classes=target,
        ranking_only=True,weights_changed=False,raw_primal_changed=False,
        ranking_derivative='original resource binding elimination; other global controls held fixed; not a feasibility certificate')
    folder.mkdir(parents=True,exist_ok=True);atomic(folder/'RESIDUAL_ATTRIBUTION.json',receipt)
    table(folder/'RESIDUAL_ROWS.csv',rows,['row','family','category','time','site','node','weighted_artificial','Phi_share','cumulative_positive_share','workload_class'])
    return receipt,effect,baseline

def score(candidate,effect,baseline):
    return sum(float(Fraction(v))*effect[int(row)] for row,v in candidate['coupling'])-baseline[candidate['class_id']]

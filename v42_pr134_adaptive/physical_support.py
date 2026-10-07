"""Exact global-row + complete physical-option support separation.

This is an independently valid INTEGER PHYSICAL certificate. It never labels a
native LP status from this projected proof. No native optimizer is imported.
"""
from fractions import Fraction as Q
from collections import defaultdict
from dataclasses import replace
import sys,numpy as np,scipy.sparse as sp,pickle,json,csv
from v42_boundary.generator import Generator
from v42_job_capability import Option,validate
from .common import *

def exact_global(folder):
    a=sp.load_npz(folder/'EXPANDED_MATRIX.npz');z=dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz'));names=dict(np.load(folder/'NATIVE_NAMES.npz'))
    ray=dict(np.load(folder/'RAW_FARKAS.npz'))['ray'];boundary=read(folder/'GLOBAL_NUMERIC_IDENTITY.json')['global_rows']
    weights={int(i):Q(float(ray[i])) for i in np.flatnonzero(ray[:boundary]) if str(names['rows'][i]) not in ('known_GPU_binding','Runtime_risk_binding')}
    allowed=('CC4_','nominal_and_compute_headroom','RT_reserve_target','voltage_','transformer_','line_thermal_face','NormalAmps','physical_ACTIVE')
    for i in weights:
        if not str(names['rows'][i]).startswith(allowed):raise ValueError('GLOBAL_PHYSICAL_COST_FAMILY_UNSUPPORTED:'+str(names['rows'][i]))
    combined=defaultdict(Q)
    def add(i,w):
        weights[i]=weights.get(i,Q(0))+w;p,q=a.indptr[i:i+2]
        for j,c in zip(a.indices[p:q],a.data[p:q]):combined[int(j)]+=w*Q(float(c))
    for i,w in list(weights.items()):weights[i]=Q(0);add(i,w)
    additions=[]
    bad=[j for j,c in combined.items() if c and not str(names['vars'][j]).startswith('known[') and
         (c>0 and (not np.isfinite(z['lb'][j]) or z['lb'][j]<=-1e100) or c<0 and (not np.isfinite(z['ub'][j]) or z['ub'][j]>=1e100))]
    candidates=[int(i) for i in np.flatnonzero((z['sense'][:boundary]=='<')&(z['rhs'][:boundary]>=0)) if str(names['rows'][i])=='nominal_and_compute_headroom']
    for j in bad:
        if combined[j]>=0:raise ValueError('NO_EXACT_LOWER_COMPLETION_ROW')
        found=None
        for i in candidates:
            p,q=a.indptr[i:i+2];ids=a.indices[p:q];cs=a.data[p:q];hits=np.flatnonzero(ids==j)
            if len(hits) and cs[hits[0]]>0 and np.all(cs>=0) and np.all(z['lb'][ids]>=0):found=i,Q(float(cs[hits[0]]));break
        if found is None:raise ValueError('NO_EXACT_ORIGINAL_HEADROOM_COMPLETION')
        i,c=found;before=combined[j];w=-before/c;add(i,w)
        additions.append(dict(variable=j,name=str(names['vars'][j]),old_exact_coefficient=str(before),row=i,name_of_row=str(names['rows'][i]),added_exact_weight=str(w),new_exact_coefficient=str(combined[j])))
    known={};minimum_other=Q(0);otherterms=[];rhs=Q(0);row_norm=Q(0)
    for i,w in weights.items():
        if not w:continue
        if str(z['sense'][i])=='<' and w<0 or str(z['sense'][i])=='>' and w>0:raise ValueError('GLOBAL_ROW_DUAL_SIGN')
        rhs+=w*Q(float(z['rhs'][i]));row_norm+=abs(w)
    for j,c in combined.items():
        if not c:continue
        name=str(names['vars'][j])
        if name.startswith('known['):
            site,t=name[6:-1].split(',');known[site,int(t)]=c;continue
        value=float(z['lb'][j] if c>0 else z['ub'][j])
        if not np.isfinite(value) or abs(value)>=1e100:raise ValueError('UNBOUNDED_EXACT_GLOBAL_TERM:'+name)
        minimum_other+=c*Q(value);otherterms.append(dict(variable=j,name=name,coefficient=str(c),bound=str(Q(value))))
    return known,minimum_other,rhs,row_norm,sum(abs(c) for c in combined.values()),dict(weights={str(i):str(w) for i,w in weights.items() if w},additions=additions,other_terms=otherterms,
        raw_ray=record(folder/'RAW_FARKAS.npz'),matrix=record(folder/'EXPANDED_MATRIX.npz'),ignored_residuals=0,model_changes=0)

def physical_minima(day,folder,known):
    old=load(day);bundle,jobs,bounds,r,raw,graphs,oldgraphs,prep=old
    current=read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected'];extra=defaultdict(list)
    for row in current:extra[row['class_id']].append(row)
    gen=Generator(r,max(b.latest_completion for b in bounds.values()));cache={}
    def cost(site,lo,hi):
        key=site,lo,hi
        if key not in cache:cache[key]=sum((w for (s,t),w in known.items() if s==site and lo<=t<hi),Q(0))
        return cache[key]
    minima={};witnesses={}
    for key,us in sorted(prep['classes'].items()):
        uid=us[0];j=jobs[uid];b=bounds[uid];g=graphs[uid]
        intersects=any((site,t) in known for name in ('r0','r1') for site,t in g.states[name])
        best=None;witness=None
        if not intersects:
            best=Q(0);witness=dict(scope='all old paths have zero overlap with exact global support')
        else:
            domain=gen.domain(j,b)
            for start,site in domain.stays:
                value=j.gpu*cost(site,start,start+j.service_slots)
                if best is None or value<best:best=value;witness=dict(type='STAY',site=site,start=start)
            for start,site,cp,physical,dest,gpu,taus in domain.blocks:
                remaining=j.service_slots-(cp-start);source=cost(site,start,cp)
                for tau in taus:
                    tr=gen.transfer(site,dest,gpu,tau);value=gpu*(source+cost(dest,tr.restart,tr.restart+remaining))
                    if best is None or value<best:best=value;witness=dict(type='MIGRATION',start=start,site=site,checkpoint=cp,dest=dest,transfer=tau)
        for row in extra[key]:
            value=j.gpu*cost(row['site'],int(row['start']),int(row['start'])+j.service_slots)
            if best is None or value<best:best=value;witness=dict(type='RESTORED_STAY',option_id=row['option_id'],site=row['site'],start=int(row['start']))
        if best is None:raise ValueError('NO_COMPLETE_PHYSICAL_S0_PATH:'+uid)
        minima[key]=best;witnesses[key]=dict(exact_minimum_per_job=str(best),count=len(us),minimum_witness=witness)
    return minima,witnesses,old,cost

def run(day,tag):
    folder=CASE/day/tag;known,other,rhs,row_norm,column_norm,proof=exact_global(folder)
    minima,witnesses,data,cost=physical_minima(day,folder,known);r=data[3];classes=data[7]['classes']
    minimum=other+sum((w*Q(float(r.fixed_gpu.get((s,t),0))) for (s,t),w in known.items()),Q(0))+sum((minima[key]*len(us) for key,us in classes.items()),Q(0))
    allowance=Q(1e-5)*(row_norm+column_norm+sum(abs(w) for w in known.values()))
    margin=minimum-rhs
    result=dict(PASS=margin>allowance,certificate_kind='EXACT_GLOBAL_ROWS_PLUS_COMPLETE_INTEGER_PHYSICAL_OPTION_SUPPORT',
        exact_minimum=str(minimum),exact_rhs=str(rhs),exact_positive_margin=str(margin),margin_float=float(margin),
        exact_original_checker_residual_allowance=str(allowance),known_coefficients=[dict(site=s,slot=t,coefficient=str(w)) for (s,t),w in sorted(known.items())],
        all_class_minima=witnesses,global_proof=proof,optimizer_calls=0,LP_infeasibility_claimed=False,integer_physical_infeasibility_proven=margin>allowance,
        coupled_resources_relaxed_only_in_certificate_bound=True,actual_model_resource_constraints_changed=False,
        proof='Valid signed unchanged global rows require c_known*known+c_other*other<=rhs. Complete physical paths and fixed GPU imply the exact joint lower bound. Strict positive margin surviving original numerical authority excludes every physical integer schedule in this restricted domain.')
    atomic(folder/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json',result)
    print('PHYSICAL_SUPPORT_CERTIFICATE',result['PASS'],'margin',float(margin),'allowance',float(allowance),flush=True)
    if not result['PASS']:raise ValueError('PHYSICAL_SUPPORT_CERTIFICATE_NOT_PROVEN')
    # Stream all omitted STAY effects on this exact class support bound.
    current_ids={x['option_id'] for x in read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected']};breaking=[];counts=defaultdict(int)
    out=folder/'REPRICED_STAY_EFFECTS.csv';fields=['class_id','option_id','classification','exact_effect','exact_class_effect','site','start','rank_same_site']
    with out.open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fields,lineterminator='\n');writer.writeheader()
        with (OUT/(label(day)+'_OMITTED_OPTION_UNIVERSE.csv')).open(encoding='utf8',newline='') as source:
            for row in csv.DictReader(source):
                if int(row['checkpoint'])!=-1 or row['option_id'] in current_ids:continue
                key=row['class_id'];j=data[1][classes[key][0]]
                value=j.gpu*cost(row['site'],int(row['start']),int(row['start'])+j.service_slots);effect=min(Q(0),value-minima[key])
                category='CERTIFICATE_BREAKING' if effect<0 else 'CERTIFICATE_NEUTRAL'
                counts[category]+=1;writer.writerow(dict(class_id=key,option_id=row['option_id'],classification=category,exact_effect=str(effect),exact_class_effect=str(effect*len(classes[key])),site=row['site'],start=row['start'],rank_same_site=row['rank_same_site']))
                if effect<0 and row['site']==j.reference_site:
                    row.update(classification=category,certificate_delta_exact=str(effect),class_delta_exact=str(effect*len(classes[key])));breaking.append(row)
    atomic(folder/'BREAKING_SAME_SITE_STAYS.json',breaking)
    atomic(folder/'REPRICE_COUNTS.json',dict(counts=counts,certificate=record(folder/'PHYSICAL_SUPPORT_EXACT_CERTIFICATE.json'),effects=record(out)))
    # Minimal exact necessary class-support cover; further LP/MIP still needed.
    import itertools
    by={}
    for row in breaking:
        key=row['class_id'];score=(int(row['rank_same_site']),int(row['abs_delta_start']),int(row['delta_start'])>0,row['site'],int(row['start']),row['option_id'])
        if key not in by or score<by[key][0]:by[key]=(score,row)
    current=read(folder/'DOMAIN_AUTHORITY_AUDIT.json')['selected'];current_classes={x['class_id'] for x in current}
    ranked=sorted([v[1] for v in by.values()],key=lambda x:(x['class_id'] not in current_classes,int(x['rank_same_site']),int(x['abs_delta_start']),int(x['delta_start'])>0,x['site'],int(x['start']),x['option_id']))
    added=[];reduction=Q(0)
    for row in ranked:
        added.append(row);reduction-=Q(row['class_delta_exact'])
        if reduction>=margin:break
    if reduction<margin:raise ValueError('NO_SAME_SITE_SUPPORT_COVER; compatible site shell required')
    atomic(folder/'NEXT_SELECTION.json',current+added)
    # Convenience index only. Native input authority uses immutable case files.
    atomic(CASE/day/'PHYSICAL_SUPPORT_NEXT_SELECTION.json',current+added)
    atomic(folder/'NEXT_SELECTION_NECESSARY_ONLY.json',dict(PASS=True,added=added,exact_relaxation=str(reduction),margin=str(margin),global_minimum_claimed=False))
    print('SUPPORT_NEXT',len(current),'plus',len(added),'classes',len({x['class_id'] for x in current+added}),flush=True)
if __name__=='__main__':run(*sys.argv[1:])

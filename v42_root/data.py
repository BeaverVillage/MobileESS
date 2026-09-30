from dataclasses import asdict
from collections import defaultdict,Counter
from time import perf_counter
from .common import *
from v42_boundary.boundaries import load_native
from v42_exact.support import ExactFactory
def scientific_signature(j,b,resource_identity,raw,bundle,scientific_costs=None):
    provider={k:raw.get(k) for k in ('runtime_authority','V10_Q50_total_seconds','exact_service_seconds','nominal_remaining_seconds','nominal_slots','duration_authority','overrun_uncertainty','synthetic_completion')}
    return dict(job={k:v for k,v in asdict(j).items() if k!='uid'},boundary=asdict(b),physical_resource_identity=resource_identity,runtime_provider_semantics=provider,runtime_completion_offset=raw['risk_nominal_completion_issue_slot']-raw['reference_end'],runtime_gamma=bundle['runtime_reserve_gamma'],runtime_kernel=bundle['runtime_survival_kernel'],grid_power_interface='identical frozen native per-site/per-time coefficients for identical GPU/site domains',objectives=dict(migration=1,shift_reference=j.reference_start,placement_reference=j.reference_site,**(scientific_costs or {})))
def prepare():
    if (LOCAL/'DATA.pkl').exists():
        with (LOCAL/'DATA.pkl').open('rb') as f:data=pickle.load(f)
        bundle,jobs,bounds,r,raw,graphs,old,prep=data
        factory=ExactFactory(r,max(b.latest_completion for b in bounds.values()));verified=defaultdict(list)
        for u,j in sorted(jobs.items()):verified[digest(scientific_signature(j,bounds[u],factory.original.cache.identity,raw[u],bundle))].append(u)
        # Keep checkpoint labels/order only where the newly verified complete
        # semantic class has exactly the same members. Never trust cached grouping.
        labels={tuple(us):g for g,us in prep['classes'].items()}
        classes={labels.get(tuple(us),g):us for g,us in verified.items()}
        return (*data[:-1],dict(prep,classes=classes,cached_classes_independently_reverified=True))
    start=perf_counter();bundle,jobs,bounds,seconds,r,raw=load_native();load=perf_counter()-start
    factory=ExactFactory(r,max(b.latest_completion for b in bounds.values()));graphs={};old={};classes=defaultdict(list);rows=[];t=perf_counter()
    for uid,j in sorted(jobs.items()):
        g=factory.graph(j,bounds[uid]);graphs[uid]=g;old[uid]=factory.original.graph(j,bounds[uid])
        signature=scientific_signature(j,bounds[uid],factory.original.cache.identity,raw[uid],bundle)
        key=digest(signature);classes[key].append(uid)
        rows.append(dict(uid=uid,signature=key,has_WAN=bool(g.events['w']),fixed=bool(g.fixed)))
        if len(graphs)%100==0:print('complete support',len(graphs),'classes',len(classes),'seconds',perf_counter()-t,flush=True)
    sizes=Counter(map(len,classes.values()))
    dump('SCIENTIFIC_JOB_CLASS_AUDIT.json',dict(PASS=True,jobs=len(jobs),class_count=len(classes),singleton_classes=sizes[1],non_singleton_classes=sum(n for s,n in sizes.items() if s>1),jobs_covered_by_non_singletons=sum(s*n for s,n in sizes.items() if s>1),max_class_size=max(sizes),classes=dict(classes),rows=rows,UID_in_signature=False,original_tie_in_signature=False,method='independently recomputed frozen authorities; no PR102 count used'))
    result=(bundle,jobs,bounds,r,raw,graphs,old,dict(data_prep_seconds=load,graph_seconds=perf_counter()-t,classes=dict(classes)))
    with (LOCAL/'DATA.pkl').open('wb') as f:pickle.dump(result,f,pickle.HIGHEST_PROTOCOL)
    return result

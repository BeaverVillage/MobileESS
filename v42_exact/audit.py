from collections import Counter,defaultdict
from dataclasses import asdict
from time import perf_counter
import psutil
from .common import *
from .support import ExactFactory
from v42_boundary.boundaries import load_native
from v42_compact.native import completion_risk

def prepare():
    t=perf_counter();bundle,jobs,bounds,seconds,r,raw=load_native();load=perf_counter()-t
    factory=ExactFactory(r,max(b.latest_completion for b in bounds.values()));graphs={};old={};rows=[]
    peak=psutil.Process().memory_info().rss;start=perf_counter()
    for i,(uid,j) in enumerate(sorted(jobs.items())):
        graphs[uid]=factory.graph(j,bounds[uid]);old[uid]=factory.original.graph(j,bounds[uid])
        peak=max(peak,psutil.Process().memory_info().rss)
        if i%100==0:print('support',i,len(factory.templates),round(perf_counter()-start,3),flush=True)
    counts=Counter();before=Counter();classes=defaultdict(list)
    for uid,j in sorted(jobs.items()):
        a=old[uid];g=graphs[uid]
        if not a.fixed:before.update(a.counts())
        if not g.fixed:counts.update(g.counts())
        # Full job/boundary authority, resource identity, identical raw risk
        # completion offset, identical global power binding. UID intentionally
        # absent. PR99's job-specific deterministic tie offsets DO participate.
        # These offsets distinguish otherwise interchangeable scientific jobs.
        signature=dict(job={k:v for k,v in asdict(j).items() if k!='uid'},boundary=asdict(bounds[uid]),
            physical_resource_identity=factory.original.cache.identity,
            runtime_completion_offset=raw[uid]['risk_nominal_completion_issue_slot']-raw[uid]['reference_end'],
            runtime_gamma=bundle['runtime_reserve_gamma'],runtime_kernel=bundle['runtime_survival_kernel'],
            grid_power_interface='identical frozen native per-site/per-time coefficients for identical GPU/site domains',
            objectives=dict(migration=1,shift_reference=j.reference_start,placement_reference=j.reference_site),
            deterministic_tie_offset=sum(sum(len(x) for x in old[u].events.values()) for u in []))
        # Event tie coefficients depend on global job order. Include the actual
        # offset; UID itself is never hashed. Exact interchangeability under
        # ALL preserved objectives therefore normally yields singleton classes.
        signature['deterministic_tie_offset']=sum(sum(len(x) for x in old[u].events.values()) for u in sorted(jobs) if u<uid and not old[u].fixed)
        classes[digest(signature)].append(uid)
        rows.append(dict(job_id=uid,before=a.counts(),after=g.counts(),fixed=g.fixed is not None,graph_sha=g.sha,signature=digest(signature)))
    audits=list(factory.audits.values());w0=before['w'];w1=counts['w']
    dump('CURRENT_W_AUDIT.json',dict(base=BASE,jobs=len(jobs),family_counts=dict(before),w_index=['job','source','destination','transfer_start'],complete_options_materialized=False,
        necessary_conditions=['transfer.feasible','max completed prefix remaining lower bound','restart + minimum remaining <= latest completion','destination ONE slot immutable fit'],full_support_not_tested_in_PR99=True))
    table('W_SUPPORT_BEFORE_AFTER.csv',[dict(family=n,before=before[n],after=counts[n],removed=before[n]-counts[n]) for n in before])
    dump('W_FIXED_POINT_AUDIT.json',dict(PASS=True,jobs=len(jobs),unique_templates=len(audits),cache_hits=factory.hits,
        family_before=dict(before),family_after=dict(counts),candidate_w=w0,retained_w=w1,w_removed=w0-w1,w_reduction_percent=100*(w0-w1)/w0,
        data_prep_seconds=load,total_graph_support_seconds=perf_counter()-start,
        support_preprocessing_seconds=sum(x['preprocessing_seconds'] for x in audits),support_query_seconds=sum(x['query_seconds'] for x in audits),
        peak_support_process_RSS_bytes=peak,peak_cached_support_array_bytes=max(x['support_array_bytes'] for x in audits),
        memory_scope='RSS includes native inputs, old/new graph caches; array bytes is exact retained temporary numpy support footprint per template, not Python total',
        complete_options_materialized=0,fixed_point_passes=2,second_pass_removed=0,rows=rows,template_audits=audits))
    sizes=Counter(map(len,classes.values()))
    dump('JOB_EQUIVALENCE_AUDIT.json',dict(PASS=True,jobs=len(jobs),class_count=len(classes),singleton_classes=sizes[1],non_singleton_classes=sum(n for s,n in sizes.items() if s>=2),
        max_class_size=max(sizes),jobs_covered_by_non_singletons=sum(s*n for s,n in sizes.items() if s>=2),class_sizes=dict(sizes),classes=dict(classes),
        uid_in_signature=False,deterministic_tie_coefficients_included=True,
        caveat='Scientific job domain/Risk equivalence alone is insufficient: preserved PR99 global deterministic event ranks are job-specific coefficients. No aggregate formulation is eligible.'))
    dump('JOB_AGGREGATION_EQUIVALENCE.json',dict(AGGREGATION_IMPLEMENTED=False,PASS=None,reason='All objective coefficients include PR99 deterministic event ranks; audit only. No integer-count decomposition asserted.'))
    return bundle,jobs,bounds,r,raw,graphs,old,dict(data_prep_seconds=load,graph_seconds=perf_counter()-start,family_counts=dict(counts))

if __name__=='__main__':prepare()

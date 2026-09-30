import os,pickle
from time import perf_counter
from .common import *
from .boundaries import load_native
from .generator import Generator
from v42_native.supervision import supervise,atomic

def generate(context):
    t0=perf_counter();bundle,jobs,windows,seconds,r,raw=load_native();prepared=perf_counter()
    g=Generator(r,max(b.latest_completion for b in windows.values()),context.check);domains={}
    for i,(uid,j) in enumerate(sorted(jobs.items())):
        context.check();domains[uid]=g.domain(j,windows[uid]);require(len(domains[uid])>0,'EMPTY_AUTHORIZED_DOMAIN:'+uid)
        if i%10==0:context.progress(dict(phase='DOMAIN_GENERATION',jobs_complete=i+1,jobs_total=len(jobs),
            complete_options=sum(map(len,domains.values())),seconds=perf_counter()-t0,unique_templates=len(g.templates)))
    completed=perf_counter();require(len(domains)==1499,'ALL_1499_REQUIRED')
    import hashlib,json
    domain_sha=hashlib.sha256(json.dumps([(u,d.sha) for u,d in sorted(domains.items())]).encode()).hexdigest()
    result=dict(PASS=True,all_jobs_complete=True,jobs_complete=len(domains),jobs_required=1499,complete_options=sum(map(len,domains.values())),
        unique_physical_templates=len(g.templates),unique_template_options=sum(len(d) for d,a in g.templates.values()),
        lazy_migration_blocks=sum(len(d.blocks) for d,a in g.templates.values()),data_prep_seconds=prepared-t0,
        domain_seconds=completed-prepared,total_seconds=completed-t0,phase_seconds=dict(g.times),counters=dict(g.counts),
        domain_sha=domain_sha,parallel_generation_used=False,Option_objects_materialized=0,
        representation='Complete lazy descriptor domains, shared exact templates; every physical option enumerable; no omitted/truncated job',
        compact_fallback_activated=False)
    atomic(context.folder/'DOMAIN_COMPLETE.json',result)
    # Only our locally generated, hash-bound pickle is consumed by the worker.
    g.check=None
    with (context.folder/'domains.pkl').open('wb') as f:pickle.dump((bundle,jobs,windows,seconds,r,raw,domains,g),f,protocol=5)
    atomic(context.folder/'DOMAIN_ARTIFACT.json',rec(context.folder/'domains.pkl'))
    atomic(context.folder/'job_profiles.json',g.per_job);atomic(context.folder/'site_prescreen.json',g.site_audit)

def main():
    os.environ['PYTHONUTF8']='1';LOCAL.mkdir(exist_ok=True)
    require(read(OUT/'A1_LEGACY_ACCELERATED_EQUIVALENCE.json')['PASS'],'EQUIVALENCE_BEFORE_MAY')
    _,receipt=supervise('A1','v42_native.boundary_worker:worker','v42_native.boundary_worker:validator',
        dict(phase='DOMAIN',sources=[rec(p) for p in (ROOT/'v42_boundary').glob('*.py')]),GEN,seconds=600)
    dump('GENERATION_SUPERVISOR_RECEIPT.json',receipt)
    if (GEN/'DOMAIN_ARTIFACT.json').exists():
        result=read(GEN/'DOMAIN_COMPLETE.json');dump('A1_GENERATION_PROFILE_ACCELERATED.json',dict(result,supervisor=receipt))
        print(result)
    else:print(dict(status='COMPACT_FALLBACK_REQUIRED',supervisor=receipt))

if __name__=='__main__':main()

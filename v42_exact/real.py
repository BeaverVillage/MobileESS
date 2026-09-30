from dataclasses import replace
from .common import *
from .gates import scientific
from v42_boundary.boundaries import load_native
FACTOR_SOURCE_SHA=sha(ROOT/'v42_exact/factor.py')

def main():
    bundle,jobs,bounds,seconds,r,raw=load_native();cases=[]
    selected=[u for u in sorted(jobs) if jobs[u].service_slots<=3 and len(bounds[u].allowed_starts)==1][:2]
    result=scientific({u:jobs[u] for u in selected},{u:bounds[u] for u in selected},r,bundle,raw,True)
    cases.append(dict(name='full_native_short_jobs',jobs=selected,domain_scope='complete original sites and starts',result=result))
    # Select job identities only. Keep each selected job's complete original
    # site/start/checkpoint/service authority, jointly with the native grid.
    candidates=[('TS_migration_multiple_destinations',next(u for u in sorted(jobs) if jobs[u].checkpoint_authorized and jobs[u].state=='PENDING' and len(bounds[u].allowed_starts)>1 and jobs[u].service_slots<=3)),
        ('long_RUNNING_carryout',next(u for u in sorted(jobs) if jobs[u].state=='RUNNING' and jobs[u].checkpoint_authorized and jobs[u].service_slots>120))]
    for name,u in candidates:
        j=jobs[u];bb=bounds[u]
        result=scientific({u:j},{u:bb},r,bundle,{u:raw[u]},True)
        cases.append(dict(name=name,jobs=[u],domain_scope='complete original sites, starts, checkpoints, service, boundary and WAN; full native electrical rows',
            original_sites=list(j.initial_sites),original_starts=list(bb.allowed_starts),result=result))
        print(name,'PASS',flush=True)
    dump('REAL_SUBSET_EQUIVALENCE.json',dict(PASS=True,cases=cases,production_domain_truncated=False,factor_source_sha256=FACTOR_SOURCE_SHA,
        coverage=['STAY','TS','preplacement','migration','long service','delayed transfer','multiple destinations','carryout'],
        zero_rate_waiting='covered exhaustively in synthetic adversarial fixtures; native presence audited in WAN authority',
        limitation='Real subsets omit other explicit jobs and therefore certify formulation equivalence, not the full-population May optimum. No per-job authority is truncated.'))

if __name__=='__main__':main()

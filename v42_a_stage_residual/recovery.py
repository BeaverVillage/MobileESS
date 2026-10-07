"""Exact compact-block physical migration recovery with reusable tail costs."""
from fractions import Fraction
from v42_job_capability import Option
from v42_sparse.runtime import coefficient_vector

def migration_options(job,raw,bundle,domain,axes,pi,cardinality,potential,active,epsilon,budget,stats):
    gpu={};horizon=max(k[2] for k in axes if k[0]=='GPU')+1
    for site in sorted({k[1] for k in axes if k[0]=='GPU'}):
        prefix=[Fraction(0)]
        for t in range(horizon):prefix.append(prefix[-1]+Fraction(float(pi[axes['GPU',site,t]])))
        gpu[site]=prefix
    ap=[Fraction(0)]
    for t in range(domain.cache.r.control_end):ap.append(ap[-1]+Fraction(float(pi[axes['ACTIVE','',t]])))
    runtime={};txcost={};tails={};minima={}
    stats.update(blocks_examined=0,paths_evaluated=0,exact_tail_terms_evaluated=0,
        nonnegative_blocks_pruned=0,physical_paths_covered_by_exact_pruning=0,full_physical_scan=False)
    def tail(source,dest,remaining,tau):
        key=source,dest,remaining,tau
        if key not in tails:
            tx=domain.cache.transfer(source,dest,job.gpu,tau);end=tx.restart+remaining
            rk=dest,end
            if rk not in runtime:
                runtime[rk]=sum((Fraction(float(pi[axes['RUNTIME',k,t]]))*Fraction(float(v)) for (k,t),v in coefficient_vector(job,raw,dest,end,bundle)),Fraction(0))
            tk=source,dest,tau
            if tk not in txcost:
                txcost[tk]=-sum((Fraction(float(pi[axes['WAN',link,t]]))*Fraction(float(v))/(2**20) for link,t,v in tx.wan),Fraction(0))-(ap[tx.end]-ap[tau])
            tails[key]=job.gpu*(gpu[dest][end]-gpu[dest][tx.restart])+runtime[rk]+txcost[tk]
            stats['exact_tail_terms_evaluated']+=1
        return tails[key]
    for start,source,cp,physical,dest,gpu_count,taus in domain.blocks:
        budget.remaining();stats['blocks_examined']+=1
        remaining=job.service_slots-(cp-start)
        first=job.gpu*(gpu[source][cp]-gpu[source][start])
        key=source,dest,remaining,taus
        if key not in minima:
            minima[key]=min(tail(source,dest,remaining,tau) for tau in taus)
        if cardinality*(first+minima[key])-Fraction(potential)>=-epsilon:
            stats['nonnegative_blocks_pruned']+=1
            stats['physical_paths_covered_by_exact_pruning']+=len(taus)
            continue
        for tau in taus:
            if (start,source,cp,physical,dest,tau) in active:continue
            stats['paths_evaluated']+=1
            if stats['paths_evaluated']%128==0:budget.remaining()
            price=cardinality*(first+tail(source,dest,remaining,tau))-Fraction(potential)
            if price < -epsilon:
                tx=domain.cache.transfer(source,dest,job.gpu,tau);end=tx.restart+remaining
                yield Option(start,source,((source,start,cp),(dest,tx.restart,end)),cp,physical,dest,tau,tx.end,tx.restart,tx.wan),price
    stats['full_physical_scan']=True

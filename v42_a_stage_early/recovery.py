"""Streaming exact physical migration recovery, without path variables."""
from fractions import Fraction
from v42_job_capability import Option
from v42_sparse.runtime import coefficient_vector

def omitted_migration_witness(job,raw,bundle,domain,axes,pi,cardinality,potential,active,epsilon,budget):
    # Exact prefix sums preserve every original binary64 coefficient. They
    # change evaluation cost, not the scientific column or feasible domain.
    horizon=domain.cache.r.control_end
    gpu={};active_prefix=[Fraction(0)]
    sites=sorted({key[1] for key in axes if key[0]=='GPU'})
    for site in sites:
        prefix=[Fraction(0)]
        for t in range(horizon):prefix.append(prefix[-1]+Fraction(float(pi[axes['GPU',site,t]])))
        gpu[site]=prefix
    for t in range(horizon):active_prefix.append(active_prefix[-1]+Fraction(float(pi[axes['ACTIVE','',t]])))
    runtime={};transfer_cost={};scanned=0
    for start,source,cp,physical,dest,gpu_count,taus in domain.blocks:
        budget.remaining()
        remaining=job.service_slots-(cp-start)
        first_cost=job.gpu*(gpu[source][cp]-gpu[source][start])
        for tau in taus:
            identity=(start,source,cp,physical,dest,tau)
            if identity in active:continue
            transfer=domain.cache.transfer(source,dest,job.gpu,tau)
            end=transfer.restart+remaining
            key=dest,end
            if key not in runtime:
                runtime[key]=sum((Fraction(float(pi[axes['RUNTIME',k,t]]))*Fraction(float(v))
                    for (k,t),v in coefficient_vector(job,raw,dest,end,bundle)),Fraction(0))
            txkey=source,dest,tau
            if txkey not in transfer_cost:
                transfer_cost[txkey]=-sum((Fraction(float(pi[axes['WAN',link,t]]))*Fraction(float(amount))/(2**20)
                    for link,t,amount in transfer.wan),Fraction(0))-(active_prefix[transfer.end]-active_prefix[tau])
            price=cardinality*(first_cost+job.gpu*(gpu[dest][end]-gpu[dest][transfer.restart])+runtime[key]+transfer_cost[txkey])-Fraction(potential)
            scanned+=1
            if scanned%1024==0:budget.remaining()
            if price < -epsilon:
                option=Option(start,source,((source,start,cp),(dest,transfer.restart,end)),cp,physical,dest,tau,transfer.end,transfer.restart,transfer.wan)
                # First canonical exact negative is sufficient for bounded
                # recovery. Only independently validated candidates count.
                return option,price,scanned
    return None,None,scanned

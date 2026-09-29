"""Necessary capacity bound retaining every migrated job's resumed service.

For a job live in its unshifted nominal interval, migration cannot have
completed its service early. It is computing or is between checkpoint and
restart. Map each such suspended job to the LAST slot of its transfer. If
restart length is r, suspension at t implies last_transfer >= t-r. Since
restart_end < H, last_transfer <= H-r-2. There are H-t-1 slots in this
interval. At most m transfers can occupy each slot, giving m*(H-t-1)
suspended jobs. This remains true for arbitrary waiting before transfer,
long transfers, and r>1. All gang/site/path restrictions are relaxed.
"""
from time import perf_counter
from .common import *


def bounds(jobs, nominal, capacities, *, begin=24, end=120, max_active=1):
    require(len(nominal)>=end-begin and end>begin,'RESOURCE_HORIZON')
    require(type(max_active) is int and max_active>0,'WAN_ACTIVE_AUTHORITY')
    require(all(j['can_timeshift'] is False for j in jobs),'BOUND_REQUIRES_ZERO_TS')
    require(all(j['reference_end']-j['reference_start_if_authorized']==j['service_slots']
                and j['GPU_gang']>0 for j in jobs),'NOMINAL_SERVICE_IDENTITY')
    rows=[]
    for t in range(begin,end):
        live=sorted((j for j in jobs if j['reference_start_if_authorized']<=t<j['reference_end']),
                    key=lambda j:(-j['GPU_gang'],j['job_uid']))
        budget=max_active*(end-t-1)
        removable=sum(j['GPU_gang'] for j in live[:budget])
        known=sum(j['GPU_gang'] for j in live);unknown=float(nominal[t-begin])
        require(np.isfinite(unknown) and unknown>=0,'UNKNOWN_NOMINAL_GPU')
        rows.append(dict(issue_slot=t,Dday_slot=t-begin,live_reference_jobs=len(live),
            known_reference_GPU=known,max_suspended_jobs=budget,
            generous_suspension_GPU=removable,known_GPU_lower_bound=known-removable,
            CC4_nominal_GPU=unknown,necessary_GPU_lower_bound=known-removable+unknown,
            capacity_GPU=sum(capacities.values()),excess_GPU=max(0.,known-removable+unknown-sum(capacities.values()))))
    return rows


def main():
    require(not (OUT/'MAY01_RESUMED_SERVICE_CERTIFICATE.json').exists(),'PRESERVE_PRIOR_CERTIFICATE')
    started=perf_counter();path=OUT/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json';b=read(path)
    jobs=[j for j in b['known_population'] if j['planning_eligible']]
    require(b['WAN']['maximum_active_transfers']==1,'NATIVE_WAN_AUTHORITY')
    rows=bounds(jobs,b['unknown_nominal_GPU'],b['capacities'])
    csv('MAY01_RESUMED_SERVICE_CAPACITY_BOUND.csv',rows)
    worst=max(rows,key=lambda r:r['excess_GPU']);failed=worst['excess_GPU']>1e-8
    result=dict(status='INFEASIBLE_PROVEN_BEFORE_A1' if failed else 'NECESSARY_CONDITION_PASS_NOT_FULL_FEASIBILITY',
        PASS=not failed,full_A1_infeasible_proven=failed,full_A1_run=False,accepted_plan_exists=False,
        reason='Fixed nominal starts, preserved resumed service, one active WAN transfer, and restart_end<120',
        certificate='LAST_TRANSFER_SLOT_INJECTION_PLUS_TOP_GANG_BOUND',worst=worst,
        violated_slots=sum(r['excess_GPU']>1e-8 for r in rows),wall_seconds=perf_counter()-started,
        solver_seconds=None,full_A1_gap=None,resource_reserve_shortfall_allowed=True,
        reserve_achieved_relaxed_to_zero=True,nominal_service_shortfall_allowed=False,
        source=rec(path),option_law_source=rec(ROOT/'v42_job_capability.py'),
        earlier_loose_check=rec(OUT/'MAY01_CHECKPOINT_RESOURCE_CERTIFICATE.json'),
        old_PR93_certificate='SUPERSEDED_FOR_V42_FINAL_INTERFACE',CC4_direct_GPUh_error_removed=True,
        assumption_scope='Every full-service complete option has one fixed-length restart and resumes before H; no TS. Earlier relaxations omitted resumed compute.',
        does_not_prove_architecture_infeasible_for_other_days_or_authorities=True,
        full_A1_authorized_after_this_PASS=not failed)
    dump('MAY01_RESUMED_SERVICE_CERTIFICATE.json',result)
    dump('MAY01_RESOURCE_FEASIBILITY_V42_FINAL.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

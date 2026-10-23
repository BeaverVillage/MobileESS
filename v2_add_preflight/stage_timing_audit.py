"""Independent all-job adjudication of the legacy WINDOW intersection."""
from dataclasses import replace,asdict
from collections import Counter
from .stage_common import *
from .prestart_acceptance import source_domain,certify

def audit():
    from v42_a_stage_domain_v2.domain import physical_starts,flexible
    from v42_boundary.generator import Generator
    from v42_job_capability import Option,validate
    row=day_inputs();bundle=read(row['files']['native']['path']);windows=read(row['files']['windows']['path'])
    jobs,bounds,seconds,resources,raw=source_domain(bundle,windows)
    start=time.perf_counter();rows=[];qos=Counter();checked=0;valid_stays=0;reference={}
    for uid,job in sorted(jobs.items()):
        bound=bounds[uid];physical=physical_starts(job,bound,resources.control_end)
        extra=sorted(set(physical)-set(bound.allowed_starts));wide=replace(bound,allowed_starts=physical)
        assert all(t>=max(job.submit,job.event) and t+job.service_slots<=bound.latest_completion for t in physical)
        if not flexible(job):assert physical==(job.reference_start,) and not extra
        gen=Generator(resources,bound.latest_completion);sites,_=gen.static_sites(job);feasible=0
        for t in extra:
            for site in sites:
                if gen.fits(site,t,job.service_slots,job.gpu):
                    option=Option(t,site,((site,t,t+job.service_slots),));validate(job,option,wide,resources)
                    feasible+=1;break
            checked+=1
        valid_stays+=feasible
        if extra:
            qos[job.qos]+=1
            rows.append(dict(uid=uid,state=job.state,qos=job.qos,protected=job.protected,
                reference_start=job.reference_start,input_WINDOW_starts=len(bound.allowed_starts),
                physical_starts=len(physical),restored_start_choices=len(extra),with_locally_hard_valid_STAY=feasible,
                submit=job.submit,event=job.event,representation_latest_completion=bound.latest_completion,
                maximum_start=max(physical),customer_deadline_inferred=False))
        reference[uid]=asdict(Option(job.reference_start,job.reference_site,((job.reference_site,job.reference_start,job.reference_start+job.service_slots),)))
    full=certify(reference,bundle,windows,identity={},expected_identity={});assert full['PASS']
    result=dict(PASS=True,jobs=len(jobs),affected_jobs=len(rows),restored_start_choices=checked,
        restored_starts_with_locally_hard_valid_STAY=valid_stays,affected_QoS=dict(qos),rows=rows,
        decision='ORIGINAL_R043_PHYSICAL_TIMING_AUTHORITY',
        source_intent=['domain.physical_starts explicitly says reference start and old WINDOW endpoint are not hard releases',
          'service.boundary explicitly says latest_completion is a representation ceiling, not a job deadline',
          'nonflexible/protected/high/urgent/unknown timing remains source reference-only',
          'all resource, rack, WAN, checkpoint, restart, exact service and carryout validators remain active'],
        input_WINDOWS_preserved_as_source_lineage_and_reference_TS_metadata=True,
        coupled_schedulability_of_all_candidates_claimed=False,full_reference_joint_capacity_QoS_and_tail=full,
        legacy_PR236_WINDOW_intersection_removed=True,legacy_PR236_mathematical_domain_changed=True,
        original_r043_physical_domain_equivalence=True,new_hard_WINDOW_or_customer_SLA_authority_invented=False,
        files=[record(ROOT/p) for p in ('v42_a_stage_domain_v2/domain.py','v42_native/service.py','v42_job_capability.py','v2_add_preflight/stage_source_windows.py')],
        input_WINDOWS=row['files']['windows'],Native_calls=0,wall_seconds=time.perf_counter()-start)
    return put('A_STAGE_R043_TIMING_AUTHORITY_20261023.json',result)

if __name__=='__main__':
    r=audit();print('TIMING_AUTHORITY_PASS',r['jobs'],r['restored_start_choices'],r['restored_starts_with_locally_hard_valid_STAY'],flush=True)

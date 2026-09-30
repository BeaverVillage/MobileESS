"""Read-only source plan audit, independent of the selected formulation."""
from dataclasses import asdict
from collections import defaultdict
from .common import *
from .data import prepare
from v42_job_capability import Option,validate,resources_used,resource_limit
def main():
    start=time.perf_counter();data=prepare();bundle,jobs,bounds,r,raw,graphs,old,prep=data
    selected={};violations=[];used=defaultdict(float)
    for uid,j in sorted(jobs.items()):
        o=Option(j.reference_start,j.reference_site,((j.reference_site,j.reference_start,j.reference_start+j.service_slots),))
        try:validate(j,o,bounds[uid],r)
        except Exception as e:violations.append(dict(job=uid,reason=str(e)))
        selected[uid]=asdict(o)
        for key,n in resources_used(j,o).items():used[key]+=n
    resource_violations=[dict(resource=key,used=n,available=resource_limit(key,r),violation=n-resource_limit(key,r)) for key,n in sorted(used.items()) if n>resource_limit(key,r)+1e-5]
    prior=read(ROOT/'docs/v42_exact_wan_factorized_milp/MAY_A1_OPTIMIZATION.json')
    audit=dict(source='frozen PR102 native Job.reference_start/reference_site and unchanged Q50 service; inherited raw reference rows',baseline_plan_authority='load_native returns the authorized current issue snapshot; per-job identity and boundaries unchanged',all_jobs=len(jobs),individual_violations=violations,global_resource_violations=resource_violations,earlier_exact_source=dict(PR102_incumbent_available=prior['passes'][0]['incumbent'] is not None,prior_plan_reused=False,reason='PR102 has no incumbent; older native reports are not accepted current-authority plans'),physical_precheck_PASS=not violations and not resource_violations,grid_Runtime_CC4_pending=not violations and not resource_violations,no_silent_repair=True,artificial_slack_used=False,audit_seconds=time.perf_counter()-start)
    dump('MIP_START_AUTHORITY_AUDIT.json',audit);atomic(LOCAL/'REFERENCE_PLAN.json',selected)
    if violations or resource_violations:dump('MIP_START_PHYSICAL_VALIDATION.json',dict(PASS=False,status='SOURCE_REFERENCE_REJECTED',all_jobs=len(jobs),individual_violations=len(violations),resource_violations=len(resource_violations),grid_Runtime_CC4='NOT_RUN_AFTER_PHYSICAL_FAILURE',incumbent_claimed=False))
    print('source audit',audit['physical_precheck_PASS'],'individual failures',len(violations),'resource failures',len(resource_violations),flush=True)
if __name__=='__main__':main()

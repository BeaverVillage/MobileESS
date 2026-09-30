from collections import Counter
import numpy as np
from v42_may01.state import cohort_key, DIMS
from .common import *

LEVELS = (
    ('qos','protected','partition','workload_class','gpu_bucket','wall_bucket','requested_nodes'),
    ('qos','protected','partition','workload_class','gpu_bucket','wall_bucket'),
    ('qos','protected','workload_class','gpu_bucket','wall_bucket'),
    ('qos','protected','gpu_bucket','wall_bucket'),
    ('qos','protected','wall_bucket'),
)

def dimensions(cohort):
    return dict(zip(DIMS, cohort.split('|'), strict=True))

class WaitAuthority:
    def __init__(self, frame, cutoff):
        require((frame.submit_time < cutoff).all() and (frame.start_time < cutoff).all(), 'TRAIN_ONLY_WAIT')
        f = frame.copy()
        ds = [dimensions(cohort_key(r.qos,r.partition,r.num_gpus_req,r.requested_seconds,r.num_nodes_req)) for r in f.itertuples()]
        for key in DIMS: f[key] = [d[key] for d in ds]
        f['wait'] = (f.start_time-f.submit_time).dt.total_seconds()
        require(np.isfinite(f.wait).all() and (f.wait>=0).all(), 'WAIT_SOURCE')
        self.groups = [{tuple(k): np.sort(g.wait.to_numpy()) for k,g in f.groupby(list(level),sort=False)} for level in LEVELS]

    def evaluate(self, state, cohort, age):
        d=dimensions(cohort)
        require(np.isfinite(age) and age>=0, 'CAUSAL_AGE')
        row=dict(state=state,qos=d['qos'],protected=d['protected']=='True',age_seconds=age,
                 selected_backoff_level=None,N_cond=0,residual_Q50_seconds=None,total_wait_Q90_seconds=None,
                 final_budget_seconds=0.,TS_slots=0,can_timeshift=False,fail_reason=None,attempted_N_cond=[])
        if state!='PENDING' or row['protected'] or d['qos'] in ('high','urgent'):
            row['fail_reason']='STATE_OR_PROTECTION';return row
        for i,(level,groups) in enumerate(zip(LEVELS,self.groups)):
            waits=groups.get(tuple(d[k] for k in level),np.array([]))
            conditional=waits[waits>age]
            row['attempted_N_cond'].append(int(len(conditional)))
            if len(conditional)<100:continue
            residual=float(np.quantile(conditional-age,.5,method='linear'))
            cap=float(np.quantile(waits,.9,method='linear'))
            budget=max(0.,min(residual,cap-age));slots=int(np.floor(budget/900))
            row.update(selected_backoff_level='L'+str(i),N_cond=len(conditional),residual_Q50_seconds=residual,
                       total_wait_Q90_seconds=cap,final_budget_seconds=budget,TS_slots=slots,can_timeshift=slots>=1,
                       fail_reason=None if slots>=1 else 'AGE_CAP_BELOW_ONE_SLOT' if cap-age<900 else 'RESIDUAL_BELOW_ONE_SLOT')
            return row
        row['N_cond']=row['attempted_N_cond'][-1]
        row['fail_reason']='NO_SUPPORTED_BACKOFF_LEVEL'
        return row

def main():
    require(not (OUT/'TS_HIERARCHICAL_BACKOFF_AUTHORITY.json').exists(),'TS_ALREADY_FROZEN')
    f,cutoff=train_frame();authority=WaitAuthority(f,cutoff)
    b=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json');issue=pd.Timestamp(b['issue_time']);rows=[]
    for j in b['known_population']:
        if not j['planning_eligible']:continue
        row=authority.evaluate(j['state'],j['cohort'],(issue-pd.Timestamp(j['submit_time'])).total_seconds())
        rows.append(dict(job_id=j['job_uid'],**row,nominal_GPUh=j['service_slots']*j['GPU_gang']/4))
    csv('TS_HIERARCHICAL_BACKOFF_LEDGER.csv',rows)
    dump('TS_HIERARCHICAL_BACKOFF_AUTHORITY.json',dict(preregistration=rec(OUT/'PREREGISTRATION.json'),TRAIN_source=rec(TRAIN),
        TRAIN_cutoff=cutoff.isoformat(),levels=LEVELS,minimum_conditional_N=100,quantile_method='linear',
        interpretation='Empirical historical additional-delay budget; not SLA or user tolerance',May_outcomes_used=False,
        runtime_criterion=False,standby_shortcut=False,no_target_share=True))
    yes=[r for r in rows if r['can_timeshift']];mass=sum(r['nominal_GPUh'] for r in rows)
    summary=dict(admitted_jobs=len(rows),TS_jobs=len(yes),TS_job_share=len(yes)/len(rows),
        nominal_GPUh=mass,TS_nominal_GPUh=sum(r['nominal_GPUh'] for r in yes),
        TS_nominal_GPUh_share=sum(r['nominal_GPUh'] for r in yes)/mass,
        backoff_level_usage_counts=Counter(r['selected_backoff_level'] for r in rows if r['selected_backoff_level']),
        failures=Counter(r['fail_reason'] for r in rows if r['fail_reason']),
        support_failures=sum(r['fail_reason']=='NO_SUPPORTED_BACKOFF_LEVEL' for r in rows),
        age_cap_failures=sum(r['fail_reason']=='AGE_CAP_BELOW_ONE_SLOT' for r in rows),
        unresolved_external_records_preserved=sum(not j['planning_eligible'] for j in b['known_population']))
    dump('TS_HIERARCHICAL_CAPABILITY_SUMMARY.json',summary);print(summary)

if __name__=='__main__':main()

"""User-confirmed occupancy and TRAIN-only T2-Q25 authority.

Current physical occupancy is not a counterfactual reservation. The latter is
still hard in the current planning problem. Neither operation fabricates an
execution, completion, requeue, or migration event.
"""
from math import floor,isfinite
from v42_native.contracts import require

RULE='T2_CONSERVATIVE_Q25'
DIMS=('qos','partition','workload_class','protected','gpu_bucket','wall_bucket','requested_nodes')
TRAIN_CUTOFF='2025-01-01T00:00:00+00:00'


def physical_occupancy(state,gpu,*,known=True):
    require(state in ('PENDING','RUNNING'),'CAUSAL_STATE_REQUIRED')
    require(isfinite(gpu) and gpu>0 and int(gpu)==gpu,'WHOLE_GANG_REQUIRED')
    return int(gpu) if state=='RUNNING' else 0


def observe(previous,current):
    require(current['observed_at']>=previous['observed_at'],'NONCAUSAL_STATE_ORDER')
    require(current['uid']==previous['uid'],'JOB_IDENTITY')
    if previous['state']=='RUNNING' and current['state']=='RUNNING':
        require(current['site']==previous['site'],'RUNNING_SITE_REWRITE')
    result=dict(current)
    result['current_physical_occupancy']=physical_occupancy(current['state'],current['gpu'],known=current['known'])
    result['prior_reservation_is_physical']=False
    # The current authorized planning schedule is separate and never deleted.
    result['previous_counterfactual_plan']=previous.get('planning_segments')
    return result


def reservation(gpu,segments):
    result={};last=None
    for site,a,b in segments:
        require(type(a) is int and type(b) is int and a<b,'EXECUTION_INTERVAL')
        require(last is None or a>=last,'DUPLICATE_EXECUTION');last=b
        for slot in range(a,b):result[site,slot]=gpu
    return result


def cohort_key(qos,partition,gpu,wall,nodes):
    protected=qos not in ('normal','standby')
    kind={'normal':'NORMAL_QUEUE_CONTROLLED','standby':'STANDBY_QUEUE_CONTROLLED','high':'HIGH_PROTECTED','urgent':'HIGH_PROTECTED'}.get(qos,'FIXED_PROTECTED')
    gb='1' if gpu<=1 else '2-4' if gpu<=4 else '5-16' if gpu<=16 else '17-64' if gpu<=64 else '65+'
    wb='<=1h' if wall<=3600 else '1-4h' if wall<=14400 else '4-24h' if wall<=86400 else '>24h'
    return '|'.join(map(str,(qos,partition,kind,protected,gb,wb,int(nodes))))


def t2(state,protected,cohort,*,known=True,admitted=True):
    if not known or state!='PENDING' or protected or not admitted:return False,0,'STATE_PROTECTION_OR_ADMISSION'
    if cohort is None:return False,0,'UNSUPPORTED_TRAIN_COHORT'
    # Latest user instruction explicitly applies N/Q25/budget requirements to
    # every eligible job, including standby. PR90's standby shortcut is removed.
    require(cohort['cutoff'][:10]=='2025-01-01' and cohort['max_observed_start'][:10]<'2025-01-01','NONTRAIN_COHORT')
    n=int(cohort['N']);q=float(cohort['Q25_seconds'])
    if n<100:return False,0,'COHORT_N_BELOW_100'
    if not isfinite(q) or q<900:return False,0,'Q25_BELOW_900'
    return True,floor(q/900),'TRACE_DERIVED_CONSERVATIVE_DELAY_PROXY'

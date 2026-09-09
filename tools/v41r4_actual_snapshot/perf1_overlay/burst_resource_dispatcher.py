"""Temporary user-approved Actual backlog burst; scientific sources stay sealed."""
import time
import dispatcher as campaign

OUT=campaign.OUT
base_verify=campaign.verify_method
base_choose=campaign.choose
last_policy_check=0.

def limits_for(mode,pending_actual,active_actual,dispatchable_actual=None):
    remaining=pending_actual if dispatchable_actual is None else dispatchable_actual
    if mode=='NORMAL_4' or (remaining==0 and active_actual==0):
        return dict(mode='NORMAL_4',total=4,actual=4,da=4,split=False)
    assert mode=='ACTUAL_BURST_8'
    return dict(mode=mode,total=10,actual=8,da=2,split=True)

def apply_policy(method):
    authority=campaign.read(OUT/'RESOURCE_BURST_AUTHORITY.json')
    assert campaign.sha(__file__)==authority['dispatcher_adapter_SHA']
    assert campaign.sha(OUT/'PERFORMANCE_FREEZE.json')==authority['unchanged_performance_freeze_SHA']
    state_path=OUT/'RESOURCE_BURST_STATE.json'
    previous=campaign.read(state_path) if state_path.exists() else dict(mode='ACTUAL_BURST_8')
    live=campaign.scan_workers()
    actual=sum(any(str(x).endswith('performance_worker.py') for x in r['cmd']) for r in live)
    pending=[dict(day=day,policy=policy) for day in method['all_days'] for policy in campaign.POLICIES
             if campaign.da_pass(day,policy) and not campaign.actual_done(day,policy)]
    occupied={r['day'] for r in live}
    dispatchable=[r for r in pending if r['day'] not in occupied]
    limits=limits_for(previous['mode'],len(pending),actual,len(dispatchable))
    campaign.CAP=limits['total']
    resource=dict(status='ACTIVE' if limits['split'] else 'RESTORED_NORMAL_4',temporary=limits['split'],
        MAX_TOTAL_WORKERS=limits['total'],MAX_DA_FRESH_WORKERS=limits['da'],MAX_ACTUAL_WORKERS=limits['actual'],
        diagnostics_count_against_Actual=True,mode=limits['mode'],
        transition='After dispatchable Actual backlog and live Actual workers drain, restore total4 and date/policy DA/Fresh then Actual pipelines; no global Actual priority',
        original_2_plus_2_policy_superseded_by_user=True)
    path=OUT/'TEMPORARY_RESOURCE_POLICY.json'
    if not path.exists() or campaign.read(path)!=resource:campaign.atomic(path,resource)
    state=dict(mode=limits['mode'],at=time.time(),pending_eligible_Actual=len(pending),active_Actual=actual,
        dispatchable_pending_Actual=len(dispatchable),pending_on_occupied_days=len(pending)-len(dispatchable),
        active_day_workers=len(live),limits=limits,returned_at=previous.get('returned_at'))
    if previous['mode']!='NORMAL_4' and limits['mode']=='NORMAL_4':
        state['returned_at']=time.time()
        campaign.atomic(OUT/'RESOURCE_BURST_RESTORED.json',dict(status='COMPLETE',at=state['returned_at'],
            reason='No dispatchable pending Actual and no active Actual workers; occupied DA dates continue in normal pipelines',normal_total_workers=4,
            subsequent_DA_completion_enables_Actual_immediately=True,worker_preemptions=0))
        print('RESOURCE_RESTORE_NORMAL_4',flush=True)
    campaign.atomic(state_path,state)
    return limits

def verify_with_policy():
    global last_policy_check
    method=base_verify()
    if time.monotonic()-last_policy_check>=1:
        apply_policy(method);last_policy_check=time.monotonic()
    return method

def choose_with_pipeline(days,occupied,blocked,recovery_used):
    mode=campaign.read(OUT/'RESOURCE_BURST_STATE.json')['mode']
    if mode=='ACTUAL_BURST_8':return base_choose(days,occupied,blocked,recovery_used)
    # Normal mode keeps work in chronological date pipelines. Within one date,
    # an eligible Actual follows its completed DA/Fresh policy before advancing
    # to the next policy. Later dates' ready Actual never jump ahead globally.
    for day in sorted(days):
        if day in occupied:continue
        job=base_choose([day],occupied,blocked,recovery_used)
        if job:return job
    return None

base_atomic=campaign.atomic
def atomic_with_policy(path,value):
    if isinstance(value,dict) and 'Actual_priority' in value:
        mode=campaign.read(OUT/'RESOURCE_BURST_STATE.json')['mode']
        value={**value,'Actual_priority':mode=='ACTUAL_BURST_8','resource_mode':mode,
            'normal_dispatch_order':'chronological date/policy DA/Fresh then its Actual'}
    return base_atomic(path,value)

if __name__=='__main__':
    campaign.verify_method=verify_with_policy
    campaign.choose=choose_with_pipeline
    campaign.atomic=atomic_with_policy
    try:campaign.main()
    except BaseException:
        campaign.atomic(OUT/'RESOURCE_DISPATCHER_FATAL.json',dict(at=time.time(),traceback=campaign.traceback.format_exc()))
        raise

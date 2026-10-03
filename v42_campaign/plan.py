"""Arm-major order: finish all 31 days of evaluation before the next arm/loop."""
from .authority import GROUPS,MAIN,CONVERGENCE,may_days,INPUT_KINDS,FORBIDDEN_KINDS,authority_sha
def stage_id(group,day,stage):return f'{group}/{day}/{stage}'
def planning_stages(group):
    return ('A1','M1','A2','M2') if group.startswith('B3_') else {'B0':('B0_PLANNING',),'B1':('A1',),'B2':('M1',)}[group]
def dependencies(group,day,stage):
    allowed=['D1_SOURCE','FORECAST','RUNTIME_CC4'];fixed=None;warm=None;free=[];previous=[]
    if group.startswith('B3_'):
        k=int(group[-1]);previous_group=f'B3_L{k-1}'
        if stage=='A1':
            free=['AIDC'];fixed='MESS_final_previous_Planning' if k>1 else 'D1_initial_MESS'
            if k>1:
                warm='AIDC_final_previous_Planning_validated_candidate_only';previous=[stage_id(previous_group,day,'PLANNING_FREEZE')];allowed+=['PREVIOUS_PLANNING_FREEZE','PREVIOUS_PLANNING_STATE']
        elif stage=='M1':fixed='A1.AIDC';free=['MESS.route','MESS.movement','MESS.P','MESS.Q','MESS.SOC'];previous=[stage_id(group,day,'A1')]
        elif stage=='A2':fixed='M1.MESS';free=['AIDC'];previous=[stage_id(group,day,'M1')]
        elif stage=='M2':fixed='A2.AIDC';free=['MESS.route','MESS.movement','MESS.P','MESS.Q','MESS.SOC'];warm='M1.MESS_validated_candidate_only';previous=[stage_id(group,day,'A2'),stage_id(group,day,'M1')]
    elif stage=='A1':fixed='MESS_OFF';free=['AIDC']
    elif stage=='M1':fixed='D1_fixed_AIDC';free=['MESS.route','MESS.movement','MESS.P','MESS.Q','MESS.SOC']
    elif stage=='B0_PLANNING':fixed='D1_workload_and_MESS_OFF';free=[]
    if previous and stage!='A1':allowed+=['CURRENT_PLANNING_FREEZE']
    return dict(allowed_input_kinds=allowed,forbidden_input_kinds=list(FORBIDDEN_KINDS),Planning_dependencies=previous,fixed_counterpart=fixed,warm_start=warm,free_decisions=free,Actual_values_allowed=False)
def build_plan(days=None):
    days=tuple(days or may_days());nodes=[];predecessor=None
    for group in GROUPS:
        for day in days:
            for stage in (*planning_stages(group),'PLANNING_FREEZE','ACTUAL','FRESH_AC','VALIDATION_FREEZE'):
                sid=stage_id(group,day,stage);planning=stage in planning_stages(group)
                dep=dependencies(group,day,stage) if planning else dict(allowed_input_kinds=['CURRENT_PLANNING_FREEZE'] if stage in ('PLANNING_FREEZE','ACTUAL') else ['CURRENT_PLANNING_FREEZE','ACTUAL'] if stage=='FRESH_AC' else ['CURRENT_PLANNING_FREEZE','ACTUAL','FRESH_AC'],forbidden_input_kinds=list(FORBIDDEN_KINDS) if stage=='PLANNING_FREEZE' else [],Planning_dependencies=[],Actual_values_allowed=False)
                required=[] if predecessor is None else [predecessor]
                if planning:required+=dep['Planning_dependencies']
                if stage=='PLANNING_FREEZE':
                    dep['Planning_dependencies']=[stage_id(group,day,s) for s in (('A2','M2') if group.startswith('B3_') else planning_stages(group))]
                    required+=dep['Planning_dependencies']
                if stage in ('FRESH_AC','VALIDATION_FREEZE'):required+=[stage_id(group,day,'PLANNING_FREEZE'),stage_id(group,day,'ACTUAL')]
                nodes.append(dict(id=sid,group=group,arm=group.split('_')[0],loop=int(group[-1]) if group.startswith('B3_') else None,day=day,stage=stage,phase='MAIN' if group in MAIN else 'CONVERGENCE',predecessor=predecessor,required_accepted_freezes=list(dict.fromkeys(required)),output_freeze=sid+'/ACCEPTED_IMMUTABLE',execution_status='NOT_RUN',planning=planning,**dep));predecessor=sid
        if group=='B3_L1':
            nodes.append(dict(id='MAIN_MAY_CAMPAIGN_COMPLETE',group=None,arm=None,loop=None,day=None,stage='MAIN_COMPLETE',phase='MAIN',predecessor=predecessor,required_accepted_freezes=[stage_id(g,day,'VALIDATION_FREEZE') for g in MAIN for day in days],output_freeze='MAIN_MAY_CAMPAIGN_COMPLETE/ACCEPTED_IMMUTABLE',execution_status='NOT_RUN',planning=False,allowed_input_kinds=[],forbidden_input_kinds=list(FORBIDDEN_KINDS),Planning_dependencies=[],Actual_values_allowed=False));predecessor='MAIN_MAY_CAMPAIGN_COMPLETE'
    return dict(authority_sha256=authority_sha(),days=list(days),main_order=list(MAIN),convergence_order=list(CONVERGENCE),production_executed=False,nodes=nodes)

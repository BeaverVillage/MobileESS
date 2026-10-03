"""Scientific-state hashes exclude loop labels, parent hashes and timestamps."""
import math,copy
from .authority import digest,canonical
STATE_KEYS={'aidc','mess','objective','authority_sha256','D1_source_hashes','population_sha256'}
AIDC_KEYS={'decisions','migration_count','shift_slots','prestart_changes','p','q'}
MESS_KEYS={'route','location','movement','p','q','soc'}
def validate_state(state):
    if set(state)!=STATE_KEYS or set(state['aidc'])!=AIDC_KEYS or set(state['mess'])!=MESS_KEYS:raise ValueError('PLANNING_STATE_SCHEMA_OR_ACTUAL_FEEDBACK')
    if not state['authority_sha256'] or not state['D1_source_hashes'] or not state['population_sha256']:raise ValueError('FROZEN_AUTHORITY_REQUIRED')
    canonical(state) # Reject NaN/Infinity and nonserializable foreign state.
    return state
def freeze_state(state,*,group,day):
    validate_state(state)
    return dict(group=group,day=day,state=copy.deepcopy(state),state_sha256=digest(state),AIDC_final='A2' if group.startswith('B3_') else 'arm_Planning',MESS_final='M2' if group.startswith('B3_') else 'arm_Planning',Actual_feedback=False)
def detector(hashes):
    if len(hashes)>1 and hashes[-1]==hashes[-2]:return dict(EXACT_FIXED_POINT=True,TWO_CYCLE=False,STILL_EVOLVING=False,stop_requested=False)
    if len(hashes)>2 and hashes[-1]==hashes[-3] and hashes[-1]!=hashes[-2]:return dict(EXACT_FIXED_POINT=False,TWO_CYCLE=True,STILL_EVOLVING=False,stop_requested=False)
    return dict(EXACT_FIXED_POINT=False,TWO_CYCLE=False,STILL_EVOLVING=True,stop_requested=False)
def distance(a,b,hamming=False):
    if isinstance(a,dict):
        if not isinstance(b,dict) or set(a)!=set(b):raise ValueError('STATE_AXIS_DRIFT')
        return sum(distance(a[k],b[k],hamming) for k in a)
    if isinstance(a,list):
        if not isinstance(b,list) or len(a)!=len(b):raise ValueError('STATE_AXIS_DRIFT')
        return sum(distance(x,y,hamming) for x,y in zip(a,b))
    return int(a!=b) if hamming else abs(float(a)-float(b))
def metrics(previous,current,actual=None):
    validate_state(current)
    from .firewall import active
    if active():raise PermissionError('EVALUATION_COLLECTOR_NOT_A_PLANNING_CAPABILITY')
    if actual is not None:validate_actual_metrics(actual)
    result=dict(rho=current['objective']['rho'],comparison_scope='B3_convergence_only',Actual_metrics=actual,Actual_metrics_used_for_Planning=False)
    if previous is None:return dict(result,previous_loop=None,differences=None)
    validate_state(previous)
    if any(previous[k]!=current[k] for k in ('authority_sha256','D1_source_hashes','population_sha256')):raise ValueError('CAUSAL_OR_POPULATION_AUTHORITY_DRIFT')
    a,b=previous['aidc'],current['aidc'];m,n=previous['mess'],current['mess']
    if set(a['decisions'])!=set(b['decisions']):raise ValueError('COMMON_JOB_POPULATION_DRIFT')
    differences=dict(changed_job_count=sum(canonical(a['decisions'][j])!=canonical(b['decisions'][j]) for j in a['decisions']),migration_count_difference=b['migration_count']-a['migration_count'],shift_difference=b['shift_slots']-a['shift_slots'],prestart_difference=b['prestart_changes']-a['prestart_changes'],AIDC_P_L1=distance(a['p'],b['p']),AIDC_Q_L1=distance(a['q'],b['q']),route_Hamming=distance(m['route'],n['route'],True),location_state_difference=distance(m['location'],n['location'],True),movement_count_difference=total(n['movement'])-total(m['movement']),MESS_P_L1=distance(m['p'],n['p']),MESS_Q_L1=distance(m['q'],n['q']),SOC_L1=distance(m['soc'],n['soc']))
    return dict(result,differences=differences)
def total(value):
    if isinstance(value,dict):return sum(total(v) for v in value.values())
    if isinstance(value,list):return sum(total(v) for v in value)
    return float(value)
ACTUAL_KEYS={'voltage_min','voltage_max','line_loading_max','transformer_current_max','transformer_kVA_max','violation_counts'}
def validate_actual_metrics(value):
    if set(value)!=ACTUAL_KEYS:raise ValueError('ACTUAL_METRICS_SCHEMA')
    canonical(value)
    if value['voltage_min']>value['voltage_max'] or any(v<0 for v in value['violation_counts'].values()):raise ValueError('ACTUAL_METRICS_RANGE')
    return value
def main_comparison(results):
    required=('B0','B1','B2','B3_L1')
    if any(k not in results for k in required):raise ValueError('INCOMPLETE_MAIN_COMPARISON')
    return {key:results[key] for key in required}

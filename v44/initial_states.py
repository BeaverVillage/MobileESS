"""Issue-only reuse of the existing V43 deterministic Running initializer."""
from pathlib import Path
from functools import partial
import ast
import inspect

from .common import ROOT,DOC,RUNTIME,read,record,verify,atomic,now,digest
from .config import DAYS,ARMS,axis

OWNED=RUNTIME/'initial_states_revision01'
READY_INPUT_STATES=('INPUT_READY','SOURCE_VERIFIED','MODEL_ASSUMED_VERIFIED')


def mess_contract(day,native):
    # PR189's unchanged producer explicitly deep-copies the common native model
    # and replaces the daily issue/population/forecast, not the four MESS states.
    producer=ROOT/'v42_pr134_b1/inputs.py'
    tree=ast.parse(producer.read_text(encoding='utf8'))
    copies=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n)=='deepcopy(template)']
    if len(copies)!=1:raise ValueError('PR189_DAILY_FIXED_INITIAL_MODEL_PRODUCER_DRIFT')
    template=ROOT/'docs/v42_final_integration/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'
    original=read(template);sites=dict(MESS01='STA01',MESS02='STA12',MESS03='STA08',MESS04='STA06')
    if native['initial_MESS_sites']!=sites or original['initial_MESS_sites']!=sites or native['battery']!=original['battery']:
        raise ValueError('INDEPENDENT_DAILY_INITIAL_MESS_MODEL_DRIFT')
    b=native['battery']
    if b['initial']!=760. or not b['minimum']<=760.<=b['maximum'] or b['p_limit']>b['pcs_kva']:
        raise ValueError('INITIAL_SOC_OR_PCS_MODEL_INVALID')
    return dict(PASS=True,day=day,issue_seconds=axis(day)['issue_seconds'],
        status='MODEL_ASSUMED_VERIFIED',policy='INDEPENDENT_DAILY_MESS_INITIAL_STATE_ASSUMPTION',
        initial_sites=sites,SOC=b['initial'],SOC_unit='kWh_per_MESS',battery=b,
        vehicles=[dict(vehicle=u,site=s,SOC_kWh=b['initial'],PCS_kVA=b['pcs_kva'],
            energy_min_kWh=b['minimum'],energy_max_kWh=b['maximum'],P_limit_kW=b['p_limit']) for u,s in sites.items()],
        source=[record(producer),record(template),record(ROOT/'v42_may_campaign_native90/inputs.py')],
        same_initialization_for_arms=list(ARMS),observed_geolocation_or_SOC=False,
        previous_optimized_day_reads=0,future_state_reads=0)


def prepare(root=OWNED):
    from .daily import clone
    from v43_actual.vendor.initial_state import prepare_initialization
    from v43_actual.vendor.initialization import initialize_running,load_initialization
    root=Path(root);bindings=read(DOC/'DAILY_AUTHORITY_BINDINGS.json');rows=[]
    base=read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')
    for day in DAYS:
        row=next(r for r in base['days'] if r['day']==day);native=read(row['files']['native']['path'])
        owned=root/day;owned.mkdir(parents=True,exist_ok=True)
        running={r['job_uid']:r for r in native['known_population'] if r['state']=='RUNNING'}
        absent=sorted(uid for uid,r in running.items() if r['current_site_if_running'] is None)
        if day==DAYS[0]:
            path=Path(row['files']['initial_running_authority']['path'])
        else:
            path=owned/'RUNNING/SYNTHETIC_INITIALIZATION_POLICY.json'
            if not path.exists():
                inputs=owned/'INPUT';inputs.mkdir(exist_ok=True)
                for source,name in [(row['files']['native'],'NATIVE_INPUT_TEMPLATE_B1.json'),
                        (row['files']['planning_input'],'PLANNING_INPUT_BUNDLE.json')]:
                    verify([source]);target=inputs/name;raw=Path(source['path']).read_bytes()
                    if target.exists() and target.read_bytes()!=raw:raise ValueError('INITIAL_STATE_INPUT_BYTES_DRIFT')
                    if not target.exists():target.write_bytes(raw)
                def dated_initialize(*args,**kwargs):
                    kwargs['expected_counts']=None
                    return initialize_running(*args,**kwargs)
                routed=clone(prepare_initialization,initialize_running=dated_initialize)
                result=routed(inputs,owned/'RUNNING',budget=None,source_assessment=dict(
                    policy='INITIAL_RUNNING_SITE_MODEL_ASSUMED',
                    reuse='Exact V43 May01 initializer; issue-only UID, GPU, rack, compatible-site observations',
                    observed_missing_site_recovery_claimed=False,private_completion_or_runtime_reads=0))
                if not result['policy']['PASS']:raise ValueError('INITIAL_RUNNING_PHYSICAL_ASSIGNMENT_UNRESOLVED:'+day)
        policy=load_initialization(path)
        if policy['inputs']['issue_seconds']!=axis(day)['issue_seconds'] or set(policy['mapping'])!=set(running):
            raise ValueError('DATED_INITIAL_RUNNING_ROSTER_DRIFT')
        jobs={r['uid']:r for r in policy['inputs']['jobs']}
        if any(jobs[u]['gpu']!=r['GPU_gang'] or jobs[u]['known_start_seconds']!=axis(day)['issue_seconds']-r['elapsed_seconds'] for u,r in running.items()):
            raise ValueError('DATED_INITIAL_RUNNING_ISSUE_OBSERVATION_DRIFT')
        if any(r['current_site_if_running'] is not None and policy['mapping'][u]!=r['current_site_if_running'] for u,r in running.items()):
            raise ValueError('INITIAL_FROZEN_SOURCE_SITE_CHANGED')
        mess=mess_contract(day,native);atomic(owned/'MESS_DAILY_INITIAL_STATE.json',mess)
        detail=dict(day=day,status='MODEL_ASSUMED_VERIFIED',running=len(running),
            source_model_site_retained=len(running)-len(absent),
            source_model_site_is_not_new_geolocation_certification=True,
            assumed=len(absent),unresolved=0,
            assumed_UIDs=[dict(uid=u,site=policy['mapping'][u],label='INITIAL_RUNNING_SITE_MODEL_ASSUMED') for u in absent],
            policy=record(path),MESS=record(owned/'MESS_DAILY_INITIAL_STATE.json'),
            Actual_outcomes_read=0,Native_calls=0,same_initialization_for_arms=list(ARMS))
        atomic(owned/'AUDIT.json',detail);rows.append(detail)
        bindings.setdefault(day,{}).update(initial_running=record(path),initial_MESS=detail['MESS'])
    atomic(DOC/'DAILY_AUTHORITY_BINDINGS.json',bindings)
    audit=dict(PASS=True,UTC=now(),days=rows,
        May02_07_missing_UIDs=sum(r['assumed'] for r in rows[1:]),
        May02_07_assumed_resolved=sum(r['assumed'] for r in rows[1:]),
        unresolved=0,Native_calls=0,algorithm_reused=record(Path(inspect.getfile(initialize_running))),
        observed_source_promotions=0,original_results_modified=False)
    atomic(DOC/'V44_MAY02_07_INITIAL_RUNNING_AUDIT.json',audit)
    atomic(DOC/'V44_MESS_DAILY_INITIAL_STATE_CONTRACT.json',dict(PASS=True,days=[r['MESS'] for r in rows],
        policy='INDEPENDENT_DAILY_MESS_INITIAL_STATE_ASSUMPTION',independent_daily_cases=True,
        previous_optimized_day_reads=0,observed_SOC_claimed=False))
    return audit


if __name__=='__main__':
    result=prepare();print(dict(PASS=result['PASS'],resolved=result['May02_07_assumed_resolved'],unresolved=result['unresolved']))

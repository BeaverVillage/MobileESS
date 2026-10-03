"""One-day deterministic state-machine exercise, with zero solver/backend calls."""
import copy,json
from pathlib import Path
from .authority import authority_sha,digest,file_sha,MAIN,CONVERGENCE
from .plan import build_plan
from .engine import CampaignEngine,atomic,handoff,final_planning_state
from .state import detector,metrics,main_comparison

DAY='2025-05-01'
ISSUE='2025-04-30T12:00:00+10:00'
CERTIFICATE=dict(scientifically_accepted=True,NUMERICAL_AUDIT_PASS=True,PHYSICAL_AUDIT_PASS=True,synthetic_assertion_only=True)
def aidc(value):return dict(decisions={'job1':dict(slot=value,site='site1')},migration_count=0,shift_slots=value,prestart_changes=0,p={'t0':float(value)},q={'t0':float(value)/10})
def mess(value):return dict(route={'t0':int(value!=0)},location={'t0':value},movement={'t0':int(value!=0)},p={'t0':float(value)},q={'t0':float(value)/10},soc={'t0':760.-value})
def source_fixture(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);entries=[]
    for key,kind,value in (('D1','D1_SOURCE',dict(initial_AIDC=aidc(3),initial_MESS=mess(0),population_sha256=digest(['job1']))),('forecast','FORECAST',dict(load=42,PV=5)),('Runtime_CC4','RUNTIME_CC4',dict(queue_active=True,capacity_active=True,common_population=['job1']))):
        path=root/(key+'.json');atomic(path,value)
        entries.append(dict(key=key,kind=kind,path=str(path),sha256=file_sha(path),producer_phase='D1',known_at_issue=True,available_at='2025-04-30T11:00:00+10:00'))
    return entries,{e['key']:e['sha256'] for e in entries}
def planning_state(sources):return dict(aidc=aidc(3),mess=mess(0),objective=dict(rho=.7),authority_sha256=authority_sha(),D1_source_hashes=sources,population_sha256=digest(['job1']))

def exercise(root):
    root=Path(root);entries,sources=source_fixture(root/'D1_inputs')
    # These values exist before later-loop Planning, but are never in its inputs.
    actual=root/'ACTUAL_EXISTING.json';atomic(actual,dict(realized_load=999999,Actual_tap=888,Fresh_voltage=777))
    engine=CampaignEngine(root/'campaign',source_hashes=sources,plan=build_plan([DAY]),mode='SYNTHETIC')
    handoffs=[];order=[]
    def handler(node,loaded,completion):
        assert completion==dict(predecessor_accepted=True)
        if node['planning']:
            deps={sid:loaded[sid] for sid in node['Planning_dependencies']}
            transfer=handoff(node,deps);handoffs.append(dict(stage=node['id'],**transfer))
            state=planning_state(sources)
            if deps:
                state=copy.deepcopy(next(iter(deps.values()))['data'].get('state') or next(iter(deps.values()))['data'].get('Planning_state'))
            fixed=transfer['fixed_counterpart'] or {}
            if 'AIDC' in fixed:state['aidc']=copy.deepcopy(fixed['AIDC'])
            if 'MESS' in fixed:state['mess']=copy.deepcopy(fixed['MESS'])
            target=2 if node['loop']==2 else 1
            if node['stage'] in ('A1','A2'):state['aidc']=aidc(target)
            if node['stage'] in ('M1','M2'):state['mess']=mess(target)
            if node['arm'] in ('B0','B1'):state['mess']=mess(0)
            state['objective']=dict(rho=.7-.01*target)
            return dict(Planning_state=state,certificate=CERTIFICATE,handoff=transfer)
        if node['stage']=='PLANNING_FREEZE':return final_planning_state(node,loaded)
        if node['stage']=='ACTUAL':return dict(Actual_complete=True,synthetic_evaluation=dict(realized_load=999999,Actual_tap=888))
        if node['stage']=='FRESH_AC':return dict(Fresh_AC_complete=True,synthetic_evaluation=dict(voltage=777))
        return dict(validated_synthetic_artifacts=True)
    while (node:=engine.next_stage()) is not None:
        engine.synthetic_stage(node['id'],handler,entries=entries if node['planning'] else [],issue_time=ISSUE);order.append(node['id'])
    # Resume rechecks every immutable freeze and all original authority hashes.
    resumed=CampaignEngine(root/'campaign',source_hashes=sources,plan=build_plan([DAY]),mode='SYNTHETIC')
    assert resumed.next_stage() is None
    states={group:engine.accepted(f'{group}/{DAY}/PLANNING_FREEZE')['data'] for group in (*MAIN,*CONVERGENCE)}
    hashes=[states[g]['state_sha256'] for g in ('B3_L1',*CONVERGENCE)]
    analysis=[dict(loop=k,state_sha256=hashes[k-1],**detector(hashes[:k]),metrics=metrics(None if k==1 else states[f'B3_L{k-1}']['state'],states[f'B3_L{k}']['state'])) for k in range(1,5)]
    return dict(synthetic_only=True,fixture_days=[DAY],stage_count=len(order),order=order,handoffs=handoffs,state_freezes=states,convergence=analysis,main_comparison=main_comparison(states),all_four_loops_completed=True,fixed_point_did_not_stop=True,two_cycle_did_not_stop=True,resume_immutable_PASS=True,read_audits=engine.read_audits,preexisting_Actual_file_sha256=file_sha(actual),optimizer_calls_for_campaign=0,Actual_calls_for_campaign=0,Fresh_AC_calls_for_campaign=0)

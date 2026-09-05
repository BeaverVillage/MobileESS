"""Predeclared April-01 comparison smoke. This entry point cannot launch May."""
from __future__ import annotations
from pathlib import Path
import argparse
from datetime import datetime,timezone
import json
import os
import sys
import threading
import time
import traceback
import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:sys.path.insert(0,str(REPO))
from dayahead.v39l.infrastructure import durable_atomic_json
from dayahead.v40a.contracts import ARTIFACT_ROOT,DEVELOPMENT_DAY,TOLERANCE,CONTRACTS
from dayahead.v40a.invariants import digest,feedback_delta,validate_joint,joint_decision
from dayahead.v40a import firewall,observability


def write(path,payload):durable_atomic_json(path,payload)


def parquet(path,frame):
    temp=path.with_suffix('.parquet.tmp');frame.to_parquet(temp,index=False);os.replace(temp,path)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--day',choices=[DEVELOPMENT_DAY],default=DEVELOPMENT_DAY)
    parser.add_argument('--reuse-m1-from',type=Path,help='Exact April development M1 checkpoint; no route search is rerun')
    args=parser.parse_args();day=args.day;root=REPO/ARTIFACT_ROOT;out=root/'days'/day;out.mkdir(parents=True,exist_ok=True)
    if (out/'FINAL_JOINT_DECISION.json').exists():raise RuntimeError('FROZEN_SMOKE_ALREADY_EXISTS_NO_OVERWRITE')
    lock=out/'SMOKE_INSTANCE.lock'
    handle=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.write(handle,str(os.getpid()).encode());os.close(handle)
    state={'phase':'STARTING','day':day,'pid':os.getpid(),'status':'RUNNING'};stop=threading.Event();started=time.perf_counter()
    write(root/'V40A_DEVELOPMENT_SMOKE_RESULT.json',{'status':'RUNNING','day':day,'pid':os.getpid(),
          'phase':'STARTING','started_utc':datetime.now(timezone.utc).isoformat()})
    def heartbeat():
        while not stop.wait(10):
            write(root/'V40A_DEVELOPMENT_HEARTBEAT.json',{**state,'heartbeat_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-started})
    threading.Thread(target=heartbeat,daemon=True).start()
    def progress(payload):
        state.update(stage_details=payload)
        write(out/'M1_PROGRESS.json',payload)
    context=None;result=None;prefix_receipt=None;outcome_guard=None;context_seconds=a0_seconds=evaluation_seconds=0.0
    try:
        from dayahead.v40a.context import load_planning_context,file_sha
        from dayahead.v40a.initial import build_initial
        from dayahead.v40a.feedback import solve_feedback,pcc_from_jobs
        from dayahead.v40a.mobility import search_once
        from dayahead.v40a.recourse import solve_fixed_route,validate_physics
        from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
        from dayahead.v40a.coordination import coordinate
        from dayahead.v40a.authority import source_authority,mobility_input_authority
        from dayahead.v40a.outcome_guard import prohibit_fresh_calls
        from dayahead.v40a.prefix import load_exact_m1
        from dayahead.v33m.mess_trajectory import MessTrajectory
        from dayahead.tools.run_v35r3e_r1_beam import _restore_slots
        from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
        _install_windows_safe_k_archive()
        for name,contract in CONTRACTS.items():
            current=json.loads((root/name).read_text(encoding='utf-8'))
            if current!=contract:raise RuntimeError('PREFROZEN_CONTRACT_DRIFT:'+name)
        outcome_guard=prohibit_fresh_calls();outcome_calls=outcome_guard.__enter__()
        firewall.activate(day);observability.install(out/'solver_events','A0')
        state['phase']='D1_CONTEXT';t=time.perf_counter();context=load_planning_context(REPO,day);context_seconds=time.perf_counter()-t
        write(out/'D1_INPUT_PROVENANCE.json',{'source_shas':context.input_shas,**context.provenance})
        traffic_authority=mobility_input_authority(day);write(out/'D1_TRAFFIC_AUTHORITY.json',traffic_authority)
        context_seconds=time.perf_counter()-t
        write(out/'COOPT_TIME_AXES.json',{'timezone':'FIXED_AEST_UTC_PLUS_10','slot_minutes':15,
              'AIDC_job_slot_0':'D-1 18:00 issue time','AIDC_target_day_interval':[24,120],
              'AIDC_post_H_boundary':120,'MESS_and_grid_slot_0':'D 00:00','MESS_and_grid_slots':96,
              'conversion':'grid_slot = AIDC_job_slot - 24; complete job intervals retain slots outside the grid window'})
        state['phase']='A0';t=time.perf_counter();a0=build_initial(REPO,day,context);a0_seconds=time.perf_counter()-t
        parquet(out/'AIDC_PASS0_DECISION.parquet',pd.DataFrame([{**r,'per_job_decision_SHA':digest(r)} for r in a0['jobs']]))
        write(out/'A0_AUTHORITY.json',{k:v for k,v in a0.items() if k not in ('jobs','PCC','GPU')})
        print(f'A0 materialized {len(a0["jobs"])} jobs in {a0_seconds:.3f}s',flush=True)
        evaluation_seconds=0
        def evaluate(jobs,mess):
            nonlocal evaluation_seconds
            t=time.perf_counter();pcc,_=pcc_from_jobs(jobs,context)
            result=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pcc,() if mess is None else mess.slots),context.nodes)
            if mess is not None and validate_physics(mess)['status']!='PASS':result['status']='FAIL'
            evaluation_seconds+=time.perf_counter()-t;return result
        def m1(jobs):
            nonlocal prefix_receipt
            state['phase']='M1';observability.install(out/'solver_events','M1')
            pcc,_=pcc_from_jobs(jobs,context)
            if args.reuse_m1_from:
                beam,prefix_receipt=load_exact_m1(args.reuse_m1_from,REPO,day,pcc,context)
                write(out/'M1_EXACT_PREFIX_REUSE.json',prefix_receipt)
            else:
                beam=search_once(REPO,day,pcc,context,out,progress)
            write(out/'M1_FULL_SEARCH_RESULT.json',beam)
            traj=MessTrajectory(tuple(_restore_slots(beam['trajectory_slots'])))
            frame=pd.DataFrame([r.to_dict() for r in traj.slots])
            frame=frame.assign(origin_service=frame.origin_service_id,destination_service=frame.destination_service_id,
                               P_kw=frame.p_kw,Q_kvar=frame.q_kvar,SoC=frame.soc_fraction,battery_energy_kWh=frame.battery_energy_kwh,
                               travel_energy_kWh=np.where(frame.departure_slot==frame.slot,frame.energy_safe_kwh,0),ETA_Q50=frame.route_q50_eta_sec,ETA_Q90=frame.route_q90_eta_sec)
            parquet(out/'MESS_PASS1_TRAJECTORY.parquet',frame)
            return traj,beam
        def a1(jobs,traj):
            state['phase']='A1';observability.install(out/'solver_events','A1')
            return solve_feedback(jobs,traj,context,tolerance=TOLERANCE)
        def mf(jobs,traj):
            state['phase']='MF';observability.install(out/'solver_events','MF')
            pcc,_=pcc_from_jobs(jobs,context);return solve_fixed_route(pcc,traj,context,tolerance=TOLERANCE)
        authority={'day':day,'input_SHAs':context.input_shas,'A0_source_SHAs':a0['source_SHAs'],
                   'D1_traffic_authority':traffic_authority,
                   'contract_SHAs':{name:file_sha(root/name) for name in CONTRACTS},
                   **source_authority(REPO,root),
                   'numerical_tolerance':TOLERANCE}
        result=coordinate(a0['jobs'],m1,a1,mf,evaluate,authority,TOLERANCE)
        outcome_guard.__exit__(None,None,None);outcome_guard=None
        if prefix_receipt:
            result['runtime']['M1_checkpoint_load']=result['runtime']['M1']
            result['runtime']['M1']=prefix_receipt['measured_M1_seconds']
        from dayahead.v40a.runtime import comparison
        write(root/'V40A_OLD_VS_NEW_RUNTIME_COMPARISON.json',{'day':day,**comparison(result,context_seconds,a0_seconds)})
        write(out/'COOPT_PLANNING_CHECKPOINT.json',{
            'a0':result['a0'],'a1':result['a1'],'m1':[r.to_dict() for r in result['m1'].slots],
            'mf':[r.to_dict() for r in result['mf'].slots],'authority':authority,
            'objectives':result['objectives'],'runtime':result['runtime'],'counts':result['counts']})
        # The complete joint authority exists on disk before the first Fresh call.
        state['phase']='JOINT_FREEZE';write(out/'FINAL_JOINT_DECISION.json',result['joint'])
        write(out/'COOPT_STAGE_OBJECTIVES.json',result['objectives'])
        write(out/'COOPT_TERMINAL_AUDIT.json',result['terminal_audit'])
        write(out/'MESS_PASS1_GRID_FEEDBACK.json',result['M1_grid']);write(out/'AIDC_FEEDBACK_GRID_RESULT.json',result['A1_grid'])
        parquet(out/'AIDC_FEEDBACK_PASS1_DECISION.parquet',pd.DataFrame([{**r,'per_job_decision_SHA':digest(r)} for r in result['a1']]))
        deltas,coupling=feedback_delta(result['a0'],result['a1']);pd.DataFrame(deltas).to_csv(out/'AIDC_FEEDBACK_DELTA.csv',index=False)
        write(out/'COOPT_COUPLING_SUMMARY.json',{**coupling,'AIDC_FEEDBACK_ACCEPTED':result['AIDC_FEEDBACK_ACCEPTED'],'MF_ACCEPTED':result['FINAL_PQ_RECOURSE_ACCEPTED'],
              'V40A_A0_RUNNING_migrations':sum(bool(r['migration_selected']) for r in result['a0']),
              'V40A_A1_RUNNING_migrations':sum(bool(r['migration_selected']) for r in result['a1']),
              'historical_V39K_fallback_count_is_not_a_V40A_count':True})
        before={(r.mess_id,r.slot):r for r in result['m1'].slots}
        parquet(out/'MESS_FINAL_PQ_RECOURSE.parquet',pd.DataFrame([{'mess_id':r.mess_id,'slot':r.slot,
           'P_kw_M1':before[r.mess_id,r.slot].p_kw,'Q_kvar_M1':before[r.mess_id,r.slot].q_kvar,
           'P_kw_final':r.p_kw,'Q_kvar_final':r.q_kvar,'delta_P_kw':r.p_kw-before[r.mess_id,r.slot].p_kw,
           'delta_Q_kvar':r.q_kvar-before[r.mess_id,r.slot].q_kvar,'SoC_final':r.soc_fraction} for r in result['mf'].slots]))
        write(out/'A1_SOLVER_RESULT.json',{k:v for k,v in result['a1_candidate_result'].items() if k!='jobs'})
        write(out/'MF_SOLVER_RESULT.json',{k:v for k,v in result['mf_candidate_result'].items() if k!='trajectory'})
        write(out/'COOPT_DATA_FIREWALL.json',{**firewall.status(),**outcome_calls});firewall.deactivate()
        state['phase']='FRESH';joint_sha=validate_joint(json.loads((out/'FINAL_JOINT_DECISION.json').read_text(encoding='utf-8')))
        from dayahead.v40a.postfreeze import production_verification
        post=production_verification(REPO,day,result['a1'],result['mf'],authority,context,out/'postfreeze',write,
                                     lambda value:state.update(stage_details=value))
        # Retain the pre-AC co-optimization ledger independently of any AC correction.
        write(out/'COOPT_JOINT_DECISION_BEFORE_AC.json',result['joint'])
        result['joint']=post['joint'];joint_sha=validate_joint(post['joint'])
        write(out/'FINAL_JOINT_DECISION.json',post['joint'])
        write(out/'FINAL_JOINT_DECISION_PAYLOAD.json',{
            'joint_decision':post['joint'],'AIDC_decision':result['a1'],
            'MESS_trajectory':[r.to_dict() for r in post['trajectory'].slots]})
        parquet(out/'FINAL_MESS_COMPLETE_TRAJECTORY.parquet',pd.DataFrame([r.to_dict() for r in post['trajectory'].slots]))
        from dayahead.v40a.invariants import route_sha
        write(out/'COOPT_MOBILITY_IDENTITY.json',{
            'M1_route_SHA':route_sha(result['m1'].slots),'MF_route_SHA':route_sha(result['mf'].slots),
            'final_post_AC_route_SHA':route_sha(post['trajectory'].slots),
            'FINAL_MESS_ROUTE_CHANGED':False,'FINAL_MESS_DESTINATION_CHANGED':False,
            'FINAL_MESS_DEPARTURE_CHANGED':False,'FINAL_MESS_MOVE_STAY_CHANGED':False,
            'identity_rule':'All immutable mobility fields, including ETA, ready time and travel energy, hash identically'})
        write(out/'FRESH_JOINT_BINDING.json',{'FINAL_JOINT_DECISION_SHA':joint_sha,
              'Fresh_schedule_sha256':post['fresh'].schedule_sha256,'summary':post['fresh'].summary})
        write(out/'ACTUAL_FIXED_REPLAY.json',post['actual'])
        write(out/'FINAL_POST_AC_PLANNING_GRID.json',evaluate(result['a1'],post['trajectory']))
        events=observability.read_events(out/'solver_events')
        if prefix_receipt:
            events=[e for e in observability.read_events(args.reuse_m1_from.parent/'solver_events') if e['stage']=='M1']+events
        from dayahead.v40a.runtime import runtime_profile,comparison
        current_seconds=time.perf_counter()-started
        total_seconds=current_seconds+(result['runtime']['M1']-result['runtime']['M1_checkpoint_load'] if prefix_receipt else 0)
        runtime=runtime_profile(result,events,materialization=context_seconds,a0=a0_seconds,verification=evaluation_seconds,
                 fresh=post['report']['Fresh_seconds'],restoration=post['report']['AC_restoration_seconds'],total=total_seconds,
                 current_execution=current_seconds if prefix_receipt else None,rsp_base=a0['RSP_base_materialization_seconds'])
        runtime['POSTFREEZE_FRESH_CALLS']=post['report']['Fresh_calls']
        write(out/'COOPT_RUNTIME_PROFILE.json',runtime)
        write(root/'V40A_OLD_VS_NEW_RUNTIME_COMPARISON.json',{'day':day,**comparison(result,context_seconds,a0_seconds)})
        write(root/'V40A_DEVELOPMENT_SMOKE_RESULT.json',{'status':'PASS','day':day,'A0':'PASS','M1':'PASS',
              'A1':'PASS' if result['AIDC_FEEDBACK_ACCEPTED'] else 'ACCEPTED_ZERO_CHANGE','MF':'PASS' if result['FINAL_PQ_RECOURSE_ACCEPTED'] else 'FEASIBLE_FIXED_ROUTE_FALLBACK',
              'Fresh':'PASS','Actual_fixed_replay':'PASS','postfreeze':post['report'],
              'FINAL_JOINT_DECISION_SHA':joint_sha,'objectives':result['objectives'],'runtime':runtime})
        state.update(status='PASS',phase='COMPLETE');print('V40A_DEVELOPMENT_SMOKE PASS',flush=True)
    except BaseException as error:
        firewall.deactivate();state.update(status='FAIL_CLOSED',phase='FAILED',error=repr(error))
        write(root/'V40A_DEVELOPMENT_SMOKE_RESULT.json',{'status':'FAIL_CLOSED','day':day,'error':repr(error),'traceback':traceback.format_exc(),
                'elapsed_seconds':time.perf_counter()-started,'completed_artifacts':[p.name for p in out.iterdir() if p.is_file()]})
        write(out/'FAILED_ATTEMPT_RUNTIME.json',{'elapsed_seconds':time.perf_counter()-started,
             'RSP_base_materialization':context_seconds,'A0':a0_seconds,'Planning_verification':evaluation_seconds,
             'completed_coordination_runtime':result['runtime'] if result else None,
             'solver_events':observability.read_events(out/'solver_events')})
        if result is not None:
            from dayahead.v40a.runtime import runtime_profile
            events=observability.read_events(out/'solver_events')
            if prefix_receipt:
                events=[e for e in observability.read_events(args.reuse_m1_from.parent/'solver_events') if e['stage']=='M1']+events
            p=out/'postfreeze/POSTFREEZE_VERIFICATION.json'
            post_report=json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}
            fresh_rows=[json.loads(p.read_text(encoding='utf-8')) for p in (out/'postfreeze').glob('round_*/FRESH_JOINT_BINDING.json')]
            current_seconds=time.perf_counter()-started
            elapsed=current_seconds+(result['runtime']['M1']-result['runtime']['M1_checkpoint_load'] if prefix_receipt else 0)
            profile=runtime_profile(result,events,materialization=context_seconds,a0=a0_seconds,verification=evaluation_seconds,
                 fresh=post_report.get('Fresh_seconds',sum(r['Fresh_seconds'] for r in fresh_rows)),
                 restoration=post_report.get('AC_restoration_seconds'),total=elapsed,
                 current_execution=current_seconds if prefix_receipt else None,rsp_base=a0['RSP_base_materialization_seconds'])
            profile.update(status='FAIL_CLOSED',unavailable_stage_times_are_null=True,error=repr(error))
            write(out/'COOPT_RUNTIME_PROFILE.json',profile)
        raise
    finally:
        if outcome_guard is not None:outcome_guard.__exit__(None,None,None)
        stop.set();firewall.deactivate();lock.unlink(missing_ok=True)
        if context is not None:context.electrical.voltage.close();context.electrical.current.close()
        write(root/'V40A_DEVELOPMENT_HEARTBEAT.json',{**state,'heartbeat_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-started})


if __name__=='__main__':main()

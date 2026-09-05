"""May B3 execution using the sealed V40A stages, with complete saved evidence."""
from pathlib import Path
import time
import numpy as np
import pandas as pd
from .common import REPO,ROOT,V40A,read,write,sha,digest
from .may_adapter import accepted_a0,admit_day,traffic_authority

def parquet(path,rows):
    frame=rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows)
    frame.to_parquet(path,index=False)

def run(day,progress):
    from dayahead.v40a.context import load_planning_context
    from dayahead.v40a.feedback import solve_feedback,pcc_from_jobs
    from dayahead.v40a.mobility import search_once
    from dayahead.v40a.recourse import solve_fixed_route,validate_physics
    from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
    from dayahead.v40a.coordination import coordinate
    from dayahead.v40a.authority import source_authority
    from dayahead.v40a.outcome_guard import prohibit_fresh_calls
    from dayahead.v40a import firewall,observability
    from dayahead.v40a.invariants import validate_joint,feedback_delta,route_sha
    from dayahead.v40a.contracts import CONTRACTS,TOLERANCE
    from dayahead.v40a.postfreeze import production_verification
    from dayahead.v40a.runtime import runtime_profile
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.tools.run_v35r3e_r1_beam import _restore_slots
    from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
    _install_windows_safe_k_archive()
    output=ROOT/'days'/day/'B3';output.mkdir(parents=True,exist_ok=True)
    if (output/'FINAL_JOINT_DECISION.json').exists():raise ValueError('EXISTING_B3_JOINT_NO_SILENT_RERUN')
    freeze=read(ROOT/'V40B_V40A_METHOD_FREEZE.json');started=time.perf_counter();context=None;evaluation_seconds=0
    def stage(name,details=None):progress({'case':'B3','current_stage':name,**(details or {})})
    try:
        with admit_day(day):
            with prohibit_fresh_calls() as outcome_calls:
                firewall.activate(day);observability.install(output/'solver_events','A0')
                stage('A0',{'substage':'D1_CONTEXT'});t=time.perf_counter();context=load_planning_context(REPO,day)
                traffic=traffic_authority(day);context_seconds=time.perf_counter()-t
                write(output/'D1_INPUT_PROVENANCE.json',{'source_shas':context.input_shas,**context.provenance})
                write(output/'D1_TRAFFIC_AUTHORITY.json',traffic)
                t=time.perf_counter();a0=accepted_a0(day,context);a0_seconds=time.perf_counter()-t
                parquet(output/'AIDC_PASS0_DECISION.parquet',[{**r,'per_job_decision_SHA':digest(r)} for r in a0['jobs']])
                write(output/'A0_AUTHORITY.json',{k:v for k,v in a0.items() if k not in ('jobs','PCC','GPU')})
                write(output/'COOPT_TIME_AXES.json',{'timezone':'FIXED_AEST_UTC_PLUS_10','slot_minutes':15,
                  'AIDC_target_day_interval':[24,120],'AIDC_post_H_boundary':120,'MESS_and_grid_slots':96})
                def evaluate(jobs,mess):
                    nonlocal evaluation_seconds
                    start=time.perf_counter();pcc,_=pcc_from_jobs(jobs,context)
                    value=evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pcc,() if mess is None else mess.slots),context.nodes)
                    if mess is not None and validate_physics(mess)['status']!='PASS':value['status']='FAIL'
                    evaluation_seconds+=time.perf_counter()-start;return value
                def m1(jobs):
                    stage('M1_ROUTE_PQ');observability.install(output/'solver_events','M1')
                    pcc,_=pcc_from_jobs(jobs,context)
                    def detail(value):
                        write(output/'M1_PROGRESS.json',value);stage('M1_ROUTE_PQ',{'solver_detail':value})
                    beam=search_once(REPO,day,pcc,context,output,detail)
                    write(output/'M1_FULL_SEARCH_RESULT.json',beam)
                    trajectory=MessTrajectory(tuple(_restore_slots(beam['trajectory_slots'])))
                    parquet(output/'MESS_PASS1_TRAJECTORY.parquet',[r.to_dict() for r in trajectory.slots])
                    return trajectory,beam
                def a1(jobs,mess):
                    stage('A1_FEEDBACK');observability.install(output/'solver_events','A1')
                    return solve_feedback(jobs,mess,context,tolerance=TOLERANCE)
                def mf(jobs,mess):
                    stage('MF_FIXED_ROUTE_PQ');observability.install(output/'solver_events','MF')
                    pcc,_=pcc_from_jobs(jobs,context);return solve_fixed_route(pcc,mess,context,tolerance=TOLERANCE)
                authority={'day':day,'input_SHAs':context.input_shas,'A0_source_SHAs':a0['source_SHAs'],
                    'D1_traffic_authority':traffic,'contract_SHAs':{name:sha(V40A/name) for name in CONTRACTS},
                    **source_authority(REPO,V40A),'numerical_tolerance':TOLERANCE,
                    'V40A_METHOD_SHA':freeze['method_SHA'],'V40B_execution_SHA':read(ROOT/'V40B_EXECUTION_FREEZE.json')['execution_SHA']}
                result=coordinate(a0['jobs'],m1,a1,mf,evaluate,authority,TOLERANCE)
                assert result['counts']=={'MESS_FULL_DISCRETE_ROUTE_SEARCH_CALLS':1,'SECOND_MESS_FULL_ROUTE_SEARCH_CALLS':0,
                    'AIDC_FEEDBACK_PASSES':1,'FINAL_FIXED_ROUTE_PQ_RECOURSE_CALLS':1,'FRESH_CALLS_INSIDE_COOPT_LOOP':0}
            write(output/'COOPT_DATA_FIREWALL.json',{**firewall.status(),**outcome_calls});firewall.deactivate()
            write(output/'COOPT_PLANNING_CHECKPOINT.json',{'a0':result['a0'],'a1':result['a1'],
               'm1':[r.to_dict() for r in result['m1'].slots],'mf':[r.to_dict() for r in result['mf'].slots],
               'authority':authority,'objectives':result['objectives'],'runtime':result['runtime'],'counts':result['counts']})
            write(output/'FINAL_JOINT_DECISION.json',result['joint'])
            write(output/'COOPT_JOINT_DECISION_BEFORE_AC.json',result['joint'])
            write(output/'COOPT_STAGE_OBJECTIVES.json',result['objectives'])
            write(output/'COOPT_TERMINAL_AUDIT.json',result['terminal_audit'])
            write(output/'MESS_PASS1_GRID_FEEDBACK.json',result['M1_grid'])
            write(output/'AIDC_FEEDBACK_GRID_RESULT.json',result['A1_grid'])
            parquet(output/'AIDC_FEEDBACK_PASS1_DECISION.parquet',[{**r,'per_job_decision_SHA':digest(r)} for r in result['a1']])
            deltas,coupling=feedback_delta(result['a0'],result['a1'])
            pd.DataFrame(deltas).to_csv(output/'AIDC_FEEDBACK_DELTA.csv',index=False)
            write(output/'COOPT_COUPLING_SUMMARY.json',{**coupling,'AIDC_FEEDBACK_ACCEPTED':result['AIDC_FEEDBACK_ACCEPTED'],
                 'MF_ACCEPTED':result['FINAL_PQ_RECOURSE_ACCEPTED'],'POSTHOC_EFFECT_ATTRIBUTION':'SKIPPED_TO_AVOID_CAMPAIGN_DELAY'})
            before={(r.mess_id,r.slot):r for r in result['m1'].slots}
            parquet(output/'MESS_FINAL_PQ_RECOURSE.parquet',[{'mess_id':r.mess_id,'slot':r.slot,
              'P_kw_M1':before[r.mess_id,r.slot].p_kw,'Q_kvar_M1':before[r.mess_id,r.slot].q_kvar,
              'P_kw_final':r.p_kw,'Q_kvar_final':r.q_kvar,'delta_P_kw':r.p_kw-before[r.mess_id,r.slot].p_kw,
              'delta_Q_kvar':r.q_kvar-before[r.mess_id,r.slot].q_kvar,'SoC_final':r.soc_fraction} for r in result['mf'].slots])
            write(output/'A1_SOLVER_RESULT.json',{k:v for k,v in result['a1_candidate_result'].items() if k!='jobs'})
            write(output/'MF_SOLVER_RESULT.json',{k:v for k,v in result['mf_candidate_result'].items() if k!='trajectory'})
            stage('FRESH')
            def fresh_progress(value):
                stage('FRESH',{'solver_detail':value})
            original_install=observability.install
            def show_restoration(event_root,event_stage):
                if event_stage=='AC_RESTORATION':stage('AC_RESTORATION')
                return original_install(event_root,event_stage)
            observability.install=show_restoration
            try:
                post=production_verification(REPO,day,result['a1'],result['mf'],authority,context,output/'postfreeze',write,fresh_progress)
            finally:observability.install=original_install
            joint_sha=validate_joint(post['joint'])
            write(output/'FINAL_JOINT_DECISION.json',post['joint'])
            write(output/'FINAL_JOINT_DECISION_SHA256.json',{'FINAL_JOINT_DECISION_SHA':joint_sha,'file_SHA':sha(output/'FINAL_JOINT_DECISION.json')})
            write(output/'FINAL_JOINT_DECISION_PAYLOAD.json',{'joint_decision':post['joint'],'AIDC_decision':result['a1'],
                  'MESS_trajectory':[r.to_dict() for r in post['trajectory'].slots]})
            parquet(output/'FINAL_MESS_COMPLETE_TRAJECTORY.parquet',[r.to_dict() for r in post['trajectory'].slots])
            planning=evaluate(result['a1'],post['trajectory'])
            write(output/'PLANNING_PHYSICAL_GATES.json',{'FINAL_JOINT_DECISION_SHA':joint_sha,**planning})
            write(output/'FRESH_AC_RESULT.json',{'FINAL_JOINT_DECISION_SHA':joint_sha,'Fresh_schedule_sha256':post['fresh'].schedule_sha256,'summary':post['fresh'].summary})
            write(output/'ACTUAL_FIXED_REPLAY.json',post['actual'])
            routes=[route_sha(t.slots) for t in (result['m1'],result['mf'],post['trajectory'])]
            assert len(set(routes))==1
            write(output/'COOPT_MOBILITY_IDENTITY.json',{'status':'PASS','M1_route_SHA':routes[0],'MF_route_SHA':routes[1],'final_route_SHA':routes[2]})
            runtime=runtime_profile(result,observability.read_events(output/'solver_events'),materialization=context_seconds,a0=a0_seconds,
                 verification=evaluation_seconds,fresh=post['report']['Fresh_seconds'],restoration=post['report']['AC_restoration_seconds'],
                 total=time.perf_counter()-started,rsp_base=a0['RSP_base_materialization_seconds'])
            write(output/'COOPT_RUNTIME_PROFILE.json',runtime)
            assert post['fresh'].summary['convergence_count']==96 and not post['fresh'].summary['physical_violation']
            assert planning['status']=='PASS' and post['actual']['status']=='PASS'
            files={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
            certificate={'status':'PASS','day':day,'case':'B3','method':freeze['identity']['method'],'method_SHA':freeze['method_SHA'],
              'FINAL_JOINT_DECISION_SHA':joint_sha,'files':files,'full_route_search_passes':1,'second_route_search':0,
              'Fresh_coverage':96,'Actual_scope':'EXISTING_FIXED_DECISION_REPLAY_IDENTITY_GATE'}
            write(output/'CASE_CERTIFICATE.json',certificate);return certificate
    finally:
        firewall.deactivate()
        if context is not None:context.electrical.voltage.close();context.electrical.current.close()

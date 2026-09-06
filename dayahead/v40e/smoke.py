"""May-01 only, corrected electrical authorities and unchanged scientific stages."""
from pathlib import Path
from types import FunctionType
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import inspect,os,time,json
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,write_parquet,reference,sha
from dayahead.v40a.invariants import digest,terminal_audit,joint_decision,validate_joint
from dayahead.v40e.audit import REL,OLD,source
from dayahead.v40e.electrical import planning_context
from dayahead.v40e.case_semantics import enforce,matrix

_RW_REFERENCE_STATE=None

def _preserved_initial_state(*args,**kwargs):
    return deepcopy(_RW_REFERENCE_STATE)


def initial(repo,day,context,output):
    """Run the original RSP placement stage with the common frozen RW initial state."""
    global _RW_REFERENCE_STATE
    from dayahead.v39e import initial_state
    from dayahead.v40a.initial import build_initial
    d=read(repo/f'dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_{day}_B0.json')['decision']
    state={str(r['job_uid']):r['initial_AIDC'] for r in d['common_initial_RUNNING_AIDC_state']}
    _RW_REFERENCE_STATE={'status':'PASS','initial_state':state,'initial_state_SHA256':digest(state),
                         'policy':'PRESERVE_FROZEN_COMMON_RW_RUNNING_STATE_NO_NEW_INITIALIZATION_OPTIMIZATION',
                         'reference_source':reference(repo/f'dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_{day}_B0.json')}
    original=initial_state.build_rw_anchored_initial_state
    initial_state.build_rw_anchored_initial_state=_preserved_initial_state
    try:result=build_initial(repo,day,context)
    finally:initial_state.build_rw_anchored_initial_state=original
    result['AIDC_solver_calls']=1
    result['RW_initial_state_optimization_calls']=0
    result['old_A0_decision_reused']=False
    result['common_inherited_state_preserved']=True
    result['terminal_audit']=terminal_audit(result['jobs'],result['jobs'])
    assert result['terminal_audit']['status']=='PASS'
    write_json(output/'CORRECTED_ACCEPTED_A0.json',result)
    return result


def search(repo,day,case,pcc,context,output,progress):
    """Same search algorithm/parameters; redirect only outputs and case label."""
    from dayahead.v40a import mobility
    from dayahead.v36 import runner as old
    from dayahead.v40b.windows_paths import install_beam_paths
    from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
    _install_windows_safe_k_archive();install_beam_paths()
    workspace=output/'execution_workspace';workspace.mkdir(parents=True,exist_ok=True)
    text=inspect.getsource(mobility.search_once)
    # These are output namespaces, not optimization constants.
    replacement=(output/'search_cache').resolve().as_posix()
    text=text.replace("'dayahead/cache/v40a'",repr(replacement))
    if case=='B2':
        text=text.replace("_prepare_seed_npz(repo,day,'B1'","_prepare_seed_npz(repo,day,'B0'")
        text=text.replace("beam._run_case('B3',width,1)","beam._run_case('B2',width,1)")
    ns=dict(mobility.__dict__);exec(compile(text,'<V40E_namespace_only_search_adapter>','exec'),ns)
    seed=old._prepare_seed_npz
    old._prepare_seed_npz=lambda _repo,*a,**kw:seed(workspace,*a,**kw)
    previous=Path.cwd()
    try:
        os.chdir(workspace)
        result=ns['search_once'](repo,day,pcc,context,output,progress)
    finally:old._prepare_seed_npz=seed;os.chdir(previous)
    write_json(output/'SEARCH_SOURCE_ADAPTER.json',{'original_source':reference(Path(inspect.getsourcefile(mobility.search_once))),
        'adapter_source':text,'case':case,'path_only_changes':True,'case_label_preserved':True,
        'K':200,'K_fallback':[200,400,800,'FULL'],'beam':2,'beam_fallback':4,'seed':2,'WorkLimit':[60,180,300],
        'old_M1_route_PQ_production_reuse':False,'full_search_passes':1})
    return result


def evaluate(context,jobs,mess=None,pcc_override=None):
    from dayahead.v40a.feedback import pcc_from_jobs
    from dayahead.v40a.grid import controls_from_trajectory,evaluate_grid
    pcc=pcc_from_jobs(jobs,context)[0] if pcc_override is None else pcc_override
    return evaluate_grid(context.coefficients,controls_from_trajectory(context.coefficients,pcc,() if mess is None else mess.slots),context.nodes)


def prepare(repo):
    from dayahead.v40a import observability
    from dayahead.v40a.feedback import pcc_from_jobs
    from dayahead.v40d_actual.inputs import frozen_jobs
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v36.contracts import PF_TAN
    repo=Path(repo).resolve();day='2025-05-01';out=repo/REL/'smoke'/day;out.mkdir(parents=True,exist_ok=True)
    assert read(repo/REL/'V40E_CORRECTED_ELECTRICAL_AUTHORITY_GATE.json')['status']=='PASS'
    ctx=planning_context(repo,day)
    bs=read(repo/OLD/'V40D_ACTUAL_DECISION_BINDING_AUDIT.json')['cases'];b=next(b for b in bs if b['day']==day and b['case']=='B0')
    ref=frozen_jobs(repo,b)[0]
    d=read(b['AIDC_decision_source'])['decision']
    refarrays={'gpu':matrix(d['site_GPU_trajectory'],'active_GPU'),'it':matrix(d['site_IT_power_trajectory'],'IT_power_kW'),
               'pcc':matrix(d['site_PCC_power_trajectory'],'PCC_P_kW'),'qcc':matrix(d['site_PCC_power_trajectory'],'PCC_Q_kvar')}
    # Save the actual B0 objective control input before evaluating it.
    np.savez_compressed(out/'B0_PRE_OBJECTIVE_AIDC_INPUT.npz',**refarrays)
    b0=evaluate(ctx,ref,pcc_override=refarrays['pcc'])
    write_json(out/'B0_CORRECTED_PLANNING_GATE.json',b0)
    print('Corrected B0 Planning '+json.dumps(b0,default=str)[:800],flush=True)
    if b0['status']!='PASS':raise RuntimeError('CORRECTED_B0_REFERENCE_PLANNING_FAIL_NO_BASELINE_RETUNING')
    a0path=out/'A0/CORRECTED_ACCEPTED_A0.json';a0path.parent.mkdir(parents=True,exist_ok=True)
    if a0path.exists():
        a0=read(a0path)
        if a0.get('corrected_input_SHAs')!=ctx.input_shas:raise RuntimeError('A0_CORRECTED_INPUT_DRIFT')
    else:
        observability.install(out/'A0/solver_events','A0')
        a0=initial(repo,day,ctx,out/'A0');a0['corrected_input_SHAs']=ctx.input_shas;write_json(a0path,a0)
    metadata={r['job_uid']:r for r in ref}
    for j in a0['jobs']:
        for key in ('submit_time','partition','requested_walltime_seconds'):
            j[key]=metadata[j['job_uid']][key]
    write_json(a0path,a0)
    pcc,gpu=pcc_from_jobs(a0['jobs'],ctx)
    it=np.array([[float(site_it_power_kw(ctx.capacity.site_capacity[s],int(gpu[t,k]))) for k,s in enumerate(sorted(ctx.capacity.site_capacity))] for t in range(96)])
    aa={'gpu':gpu,'it':it,'pcc':pcc,'qcc':pcc*PF_TAN}
    jobs={'B0':ref,'B1':deepcopy(a0['jobs']),'B2':deepcopy(ref),'B3':deepcopy(a0['jobs'])}
    arrays={'B0':refarrays,'B1':aa,'B2':deepcopy(refarrays),'B3':deepcopy(aa)}
    gate=enforce(jobs,arrays)
    assert digest(jobs['B1'])==digest(jobs['B3'])
    gate.update(B1_B3_INITIAL_A0_IDENTITY='PASS',B0_B2_JOB_UNIVERSE_IDENTITY='PASS',B0_B2_START_IDENTITY='PASS',B0_B2_SITE_IDENTITY='PASS',
                B0_B2_GPU_OCCUPANCY_MAX_DIFF=0,B0_B2_IT_POWER_MAX_DIFF_KW=0,B0_B2_PCC_P_MAX_DIFF_KW=0,B0_B2_PCC_Q_MAX_DIFF_KVAR=0,
                B0_JOB_COUNT=len(ref),B0_ACTIVE_GPU_MAX=int(refarrays['gpu'].sum(axis=1).max()),
                B0_IT_POWER_MAX_KW=float(refarrays['it'].sum(axis=1).max()),B0_PCC_POWER_MAX_KW=float(refarrays['pcc'].sum(axis=1).max()),
                B0_B2_inherited_state_exact_equal=True,B0_NEW_TEMPORAL_OPTIMIZATION=0,B0_NEW_SPATIAL_OPTIMIZATION=0,B0_NEW_MIGRATION_OPTIMIZATION=0,
                ALL_SHARED_LOAD_GROUPS='PASS',PLANNING_ELECTRICAL_AUTHORITY_REBUILT='PASS',
                OLD_RESULT_STATUS='INVALIDATED_BY_BACKGROUND_MAPPING_DEFECT',full_May_campaign_authorized=False)
    write_json(out/'V40E_PRE_MESS_INTEGRATED_GATE.json',gate)
    write_json(out/'PRE_MESS_JOBS.json',jobs)
    for c in arrays:np.savez_compressed(out/(c+'_PRE_MESS_AIDC.npz'),**arrays[c])
    b1=evaluate(ctx,jobs['B1']);write_json(out/'B1_CORRECTED_PLANNING_GATE.json',b1)
    assert b1['status']=='PASS'
    ctx.electrical.voltage.close();ctx.electrical.current.close()
    print('INTEGRATED PRE-MESS GATE PASS',flush=True)
    return gate


def b0_b1(repo):
    """No MESS search is reachable here; stop after the two-case attribution."""
    from uuid import uuid4
    from dayahead.v40e.mapping import corrected_mapping
    from dayahead.v40e.readback import observe
    from dayahead.v28r2.trajectory import FrozenTrajectory
    from dayahead.v28r2.opendss_backend import run_fresh_opendss
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v35.execution import MESS_INITIAL
    from dayahead.v40d_actual.inputs import observations,capacity
    from dayahead.v40d_actual.job_replay import replay_jobs,validate_jobs
    from dayahead.v40d_actual.rack_dispatch import Rack
    from dayahead.v40d_actual.power_replay import power_from_execution
    from dayahead.v40d_actual.exogenous import load as load_exogenous
    from dayahead.v40d_actual.mobility_inputs import actual_mobility
    from dayahead.v40d_actual.grid_replay import replay as grid_replay
    from dayahead.v40d_actual.physical_audit import c1_recalculation
    from dayahead.v40d_actual.capacity_audit import write_runtime_audits
    from dayahead.paper_analysis.storage import canonical
    import gurobipy as gp
    repo=Path(repo).resolve();out=repo/REL/'smoke/2025-05-01';day='2025-05-01'
    gate=read(out/'V40E_PRE_MESS_INTEGRATED_GATE.json');assert gate['CASE_SEMANTICS_GATE']=='PASS'
    jobs=read(out/'PRE_MESS_JOBS.json');context=planning_context(repo,day)
    arrays={}
    for c in ('B0','B1'):
        with np.load(out/(c+'_PRE_MESS_AIDC.npz')) as z:arrays[c]={k:z[k] for k in z.files}
    ids=tuple(sorted(MESS_INITIAL));loc=np.array([[MESS_INITIAL[i] for i in ids] for _ in range(96)],dtype=str)
    run_results={};old_opt=gp.Model.optimize;optimization_attempts=0
    def forbidden(*a,**k):
        nonlocal optimization_attempts
        optimization_attempts+=1;raise RuntimeError('POST_FREEZE_OPTIMIZATION_FORBIDDEN')
    gp.Model.optimize=forbidden
    previous=Path.cwd()
    try:
        for case in ('B0','B1'):
            dst=out/case;dst.mkdir(parents=True,exist_ok=True)
            frozen={'case':case,'day':day,'AIDC_decision':jobs[case],'MESS':'OFF',
                    'AIDC_PCC_SHA':digest(arrays[case]['pcc']),'electrical_input_SHAs':context.input_shas}
            decision_sha=digest(frozen);write_json(dst/'CORRECTED_PLANNING_DECISION_FREEZE.json',{'decision':frozen,'decision_SHA':decision_sha})
            value=FrozenTrajectory(day,'DAYAHEAD',case,arrays[case]['pcc'],arrays[case]['qcc'],np.zeros((96,4)),np.zeros((96,4)),ids,loc,decision_sha)
            print('CORRECTED Fresh '+case,flush=True)
            with corrected_mapping():
                with observe(dst/'fresh_readback',case,'Fresh') as seen:
                    fresh=run_fresh_opendss(repo=SOURCE_DATA_REPOSITORY,context=context.electrical,voltage=context.electrical.voltage,trajectory=value,output=dst/'fresh')
            os.chdir(previous)
            assert seen['AIDC_positive_all_slots']
            write_json(dst/'CORRECTED_FRESH_GATE.json',{'status':'PASS' if not fresh.summary['physical_violation'] else 'FAIL',
                'fresh':fresh.summary,'decision_SHA':decision_sha,'B0_B1_MESS':'OFF','readback_max_error':seen['max_setpoint_error']})
            if fresh.summary['physical_violation']:raise RuntimeError('CORRECTED_'+case+'_FRESH_FAIL_NO_UNAUTHORIZED_AIDC_REPAIR')
            run_results[case]={'Planning':read(out/(case+'_CORRECTED_PLANNING_GATE.json')),'Fresh':fresh.summary}
        # Actual inputs open only after both corrected Planning freezes and Fresh PASS.
        obs=observations(repo/OLD);authority,_,*_=capacity(repo);sites=authority['frozen_V39C_site_capacity']
        racks=[Rack(r['aidc_id'],r['rack_pool_id'],int(r['compatibility_GPU_limit'])) for r in authority['logical_Rack_pools']]
        issue=datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))-timedelta(hours=6)
        exo=load_exogenous(repo,day)
        write_json(out/'CORRECTED_ACTUAL_EXOGENOUS_AUTHORITY.json',exo['authority'])
        np.savez_compressed(out/'CORRECTED_ACTUAL_EXOGENOUS.npz',demand=exo['demand_mw'],pv=exo['pv_mw'],weather=exo['weather'].to_numpy())
        historical_bindings=read(repo/OLD/'V40D_ACTUAL_DECISION_BINDING_AUDIT.json')['cases']
        zero_binding=next(b for b in historical_bindings if b['day']==day and b['case']=='B0')
        # The OFF actuator has no optimized route or P/Q decision to reuse.
        mess=actual_mobility(repo,zero_binding)
        assert np.count_nonzero(mess['p'])==np.count_nonzero(mess['q'])==0 and not mess['moves']
        for case in ('B0','B1'):
            dst=out/case;frozen=read(dst/'CORRECTED_PLANNING_DECISION_FREEZE.json')
            assert digest(frozen['decision'])==frozen['decision_SHA'] and digest(frozen['decision']['AIDC_decision'])==digest(jobs[case])
            failures=validate_jobs(jobs[case],obs,sites,issue)
            if failures:raise RuntimeError('CORRECTED_ACTUAL_PREFLIGHT:'+case+':'+str(failures[:5]))
            print('CORRECTED Actual jobs '+case,flush=True)
            executed=replay_jobs(jobs[case],obs,issue_time=issue,site_capacity=sites,racks=racks)
            power=power_from_execution(repo,executed,sites,exo['weather'])
            write_runtime_audits(dst,day,case,jobs[case],executed,sites,racks,power)
            write_json(dst/'V40E_C1_RECALCULATION.json',c1_recalculation(repo,power,exo['weather']))
            for name,data in [('job_ledger',executed['job_ledger']),('rack_ledger',executed['rack_ledger']),('job_GPU_contributions',power['job_slot_contributions'])]:
                f=pd.DataFrame(data)
                for column in ('stable_priority_key','WAN_state','accepted_A0_assignment_and_WAN','checks'):
                    if column in f:f[column]=f[column].map(lambda v:canonical(v).decode().strip() if isinstance(v,(dict,list,str)) else None)
                write_parquet(dst/(name+'.parquet'),f)
            write_parquet(dst/'aidc_site_timeseries.parquet',power['frame'])
            write_parquet(dst/'MESS_executed_trajectory.parquet',mess['frame'])
            write_json(dst/'V40E_ACTUAL_POWER_AUDIT.json',power['power_audit'])
            write_json(dst/'V40E_ACTUAL_OCCUPANCY_AUDIT.json',power['occupancy_audit'])
            identity=digest({'decision':frozen['decision_SHA'],'jobs':executed['job_ledger'],'zero_MESS_commands':mess['frozen_commands_SHA']})
            print('CORRECTED Actual OpenDSS '+case,flush=True)
            runid=str(uuid4())
            with corrected_mapping():
                with observe(dst/'actual_readback',case,'Actual') as seen:
                    result,binding=grid_replay(repo,day,case,context,power,exo,mess,identity,dst/'actual_grid')
            os.chdir(previous)
            assert seen['AIDC_positive_all_slots']
            run_results[case]['Actual']=result.summary
            run_results[case]['Actual_OpenDSS_run_id']=runid
            write_json(dst/'CORRECTED_ACTUAL_RESULT.json',{'status':'REPLAY_COMPLETE','Actual_OpenDSS_run_id':runid,'summary':result.summary,
                'decision_SHA':frozen['decision_SHA'],'Actual_optimizer_calls':optimization_attempts,'binding':binding,'job_counters':executed['counters']})
        write_json(out/'V40E_B0_B1_CORRECTED_RESULTS.json',run_results)
        deltas={'Delta_Planning':run_results['B0']['Planning']['rho_max']-run_results['B1']['Planning']['rho_max'],
                'Delta_Fresh':run_results['B0']['Fresh']['rho_max_AC']-run_results['B1']['Fresh']['rho_max_AC'],
                'Delta_Actual':run_results['B0']['Actual']['rho_max_AC']-run_results['B1']['Actual']['rho_max_AC']}
        write_json(out/'V40E_B0_B1_EXECUTION_STOP_GATE.json',{'deltas_B0_minus_B1':deltas,'B2_B3_search_started':False,'full_May_campaign_started':False,
            'Actual_UNASSIGNED_44_case_blocker_preserved':True,'next_action':'ADDITIONAL_FORENSIC_REQUIRED' if deltas['Delta_Actual']<=0 else 'CRITICAL_LINE_ATTRIBUTION_AND_USER_ACCEPTANCE_REQUIRED',
            'FULL_CAMPAIGN_AUTHORIZED':False})
        print('B0/B1 corrected deltas '+json.dumps(deltas),flush=True)
    finally:
        gp.Model.optimize=old_opt;os.chdir(previous);context.electrical.voltage.close();context.electrical.current.close()

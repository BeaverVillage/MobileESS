"""Read-only frozen May-01 evidence forensic; diagnostic occupancy, never policy selection."""
from pathlib import Path
from copy import deepcopy
from collections import defaultdict, Counter
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, sha
from dayahead.v40h.identity import manifest, file_record, verify_manifest

ROOT = Path('dayahead/artifacts/v40i_authority_electrical_closure/may01_actual_forensic')
G = Path('dayahead/artifacts/v40g_joint_aidc')
SMOKE = G/'smoke/2025-05-01'
ISSUE = pd.Timestamp('2025-04-30T08:00:00Z')
SLOT = 73
AXIS = SLOT + 24
SITES = tuple(f'AIDC{i:02d}' for i in range(1,13))


def parse(value):
    if isinstance(value,str): return json.loads(value)
    return value


def planned_segments(row):
    parts=parse(row.get('compute_segments'))
    return parts if isinstance(parts,list) else [
        {'site':row['AIDC_site'],'start':row['start_slot'],'end':row['end_slot']}]


def actual_segments(row):
    parts=parse(row.get('actual_compute_segments'))
    if isinstance(parts,list): return parts
    if row['status']!='EXECUTION_ACCOUNTED': return []
    return [{'site':row['AIDC_site'],'start':row['actual_residual_start'],'end':row['actual_execution_end']}]


def observed_service_no_delay(job, ledger):
    """Replace only compute service, keeping frozen admission/checkpoint/WAN choices."""
    if ledger['status']!='EXECUTION_ACCOUNTED': return []
    d=float(ledger['actual_service_seconds'])/900
    if job.get('migration_selected'):
        checkpoint=float(job['migration_checkpoint_slot'])
        result=[{'site':job['initial_AIDC'],'start':0.,'end':min(d,checkpoint)}]
        if d>checkpoint:
            ready=float(job['frozen_execution_ready_slot'])
            result.append({'site':job['AIDC_site'],'start':ready,'end':ready+d-checkpoint})
        return result
    start=float(job['start_slot'])
    return [{'site':job['AIDC_site'],'start':start,'end':start+d}]


def vector(parts, gpu, axis=AXIS):
    value=np.zeros(12,dtype=int)
    active=[p for p in parts if p['start']<=axis<p['end']]
    if len(active)>1: raise ValueError('OVERLAPPING_JOB_COMPUTE_SEGMENTS')
    for part in active:
        if part['site'] not in SITES: raise ValueError('ACTIVE_SITE_AUTHORITY_MISSING')
        value[SITES.index(part['site'])]+=int(gpu)
    return value


def downstream(elements, target='line.sw2'):
    graph=defaultdict(set)
    line=next(r for r in elements if r['name']==target)
    for r in elements:
        if r['name']==target or not r['name'].startswith(('line.','transformer.')): continue
        buses=[b.split('.')[0] for b in r['buses']]
        for a in buses:
            for b in buses:
                if a!=b:graph[a].add(b)
    start=line['buses'][1].split('.')[0];seen={start};queue=[start]
    while queue:
        for bus in graph[queue.pop()]:
            if bus not in seen:seen.add(bus);queue.append(bus)
    assert line['buses'][0].split('.')[0] not in seen,'NONRADIAL_CUT_UNSUPPORTED'
    sites={f'AIDC{i:02d}':f'idc_idc{i:02d}_pcc' in seen for i in range(1,13)}
    return {'line':line,'sites':sites,'downstream_buses':sorted(seen),
            'basis':'Frozen engine line/transformer terminal connectivity; open endpoints are distinct buses.'}


def all_occupancy(rows, kind):
    result=np.zeros((96,12),dtype=int)
    for row in rows:
        parts=planned_segments(row) if kind=='Planning' else actual_segments(row)
        for t in range(96):
            result[t]+=vector(parts,row['requested_GPU'],t+24)
    return result


def hybrid_jobs(b0,b1,temporal,spatial,migration=False):
    """Factorial intervention on frozen choices. No candidate search or reselection."""
    rhs={r['job_uid']:r for r in b1}; result=[]
    for a in b0:
        b=rhs[a['job_uid']];r=deepcopy(a)
        if a['state_at_issue']=='PENDING':
            if temporal:
                r['start_slot']=b['start_slot'];r['end_slot']=b['start_slot']+r['safe_duration_slots']
            if spatial:
                r['AIDC_site']=b['AIDC_site'];r['Rack_label']=b['Rack_label']
        elif migration and b.get('migration_selected'): r=deepcopy(b)
        result.append(r)
    return result


def run(repo):
    repo=Path(repo).resolve();out=repo/ROOT;out.mkdir(parents=True,exist_ok=True)
    inputs=set(); first_read={}
    def source(path):
        path=repo/path if not Path(path).is_absolute() else Path(path);inputs.add(path)
        if path not in first_read:first_read[path]=file_record(path,root=repo)
        return path
    def js(path):return read(source(path))
    def frame(path):return pd.read_parquet(source(path))
    jobs=js(SMOKE/'PRE_MESS_JOBS.json')
    service=js(G/'common_service/COMMON_DA_SERVICE_AUTHORITY.json')
    final=js(G/'V40G_MAY01_FINAL_REPORT.json')
    dayroot=Path('dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01')
    daymanifest=js(dayroot/'V37_R4A_DAY_MANIFEST.json')
    causality=js(Path('dayahead/artifacts/v37_r4a_per_day_aidc/V37_R4A_AIDC_CAUSALITY_AUDIT.json'))
    origin=frame(dayroot/'V37_R4A_JOB_LEDGER.parquet').set_index('job_id')
    snapshot=frame(dayroot/'V37_R4A_D1_SNAPSHOT.parquet')
    observed=frame(Path('dayahead/artifacts/v40d_actual_realized_replay/V40D_FROZEN_JOB_OBSERVATIONS.parquet'))
    observed={str(r['id']):r for r in observed.to_dict('records')}
    engine=js(SMOKE/'B0/actual_readback/ENGINE_MAPPING_RATINGS_SOURCE.json')
    cut=downstream(engine['elements']);down=np.array([cut['sites'][s] for s in SITES])
    write_json(out/'FROZEN_TOPOLOGY_CUT.json',cut)
    from dayahead.v39a.contracts import CENTER_SWING_W_PER_GPU
    swing=float(CENTER_SWING_W_PER_GPU)/1000
    actual={};arrays={};times={};contrib={};rows=[];piece=[];no_delay={}
    for c in ('B0','B1'):
        actual[c]=frame(SMOKE/c/'job_ledger.parquet').to_dict('records')
        actual[c]={r['job_uid']:r for r in actual[c]}
        contrib[c]=frame(SMOKE/c/'job_GPU_contributions.parquet')
        times[c]=frame(SMOKE/c/'aidc_site_timeseries.parquet')
        with np.load(source(SMOKE/(c+'_PRE_MESS_AIDC.npz'))) as z:arrays[c]={k:z[k] for k in z.files}
        assert len(jobs[c])==len(actual[c])==1649
        assert set(actual[c])=={r['job_uid'] for r in jobs[c]}
        np.testing.assert_array_equal(all_occupancy(jobs[c],'Planning'),arrays[c]['gpu'])
        actual_gpu=all_occupancy(list(actual[c].values()),'Actual')
        expected=times[c].pivot(index='slot',columns='site_id',values='occupied_GPU').to_numpy()
        np.testing.assert_array_equal(actual_gpu,expected)
        cv=contrib[c].pivot_table(index='slot',columns='site',values='occupied_GPU',aggfunc='sum',fill_value=0).reindex(index=range(96),columns=SITES,fill_value=0).to_numpy()
        np.testing.assert_array_equal(actual_gpu,cv)
        no_delay[c]=np.zeros(12,dtype=int)
        for job in jobs[c]:
            uid=job['job_uid'];a=actual[c][uid];orig=origin.loc[uid];obs=observed[uid]
            pparts=planned_segments(job);aparts=actual_segments(a)
            # UNASSIGNED post-H rows keep all service and remain unresolved; no fabricated intervals.
            p=vector(pparts,job['requested_GPU']);v=vector(aparts,job['requested_GPU'])
            n=vector(observed_service_no_delay(job,a),job['requested_GPU']);no_delay[c]+=n
            sec=(pd.Timestamp(obs['end_time'])-pd.Timestamp(obs['start_time'])).total_seconds()
            remaining=(pd.Timestamp(obs['end_time'])-ISSUE).total_seconds() if job['state_at_issue']=='RUNNING' else sec
            assert abs(sec-float(a['actual_runtime_seconds']))<1e-6
            if a['status']=='EXECUTION_ACCOUNTED':assert abs(remaining-float(a['actual_service_seconds']))<1e-6
            row={'case':c,'job_uid':uid,'D1_state':job['state_at_issue'],'submit_timestamp':job['submit_time'],
                 'post_cutoff_arrival':pd.Timestamp(job['submit_time'])>ISSUE,'requested_GPU':job['requested_GPU'],
                 'DA_start_issue_slot':job['start_slot'],'DA_finish_issue_slot':job['end_slot'],
                 'DA_compute_service_seconds':job['safe_duration_seconds'],'DA_compute_service_slots_ceil':job['safe_duration_slots'],
                 'DA_site':job['AIDC_site'],'DA_segments':json.dumps(pparts),'DA_duration_authority':job['duration_authority'],
                 'point_total_seconds':orig['diagnostic_point_total_seconds'],'safe_total_seconds':orig['diagnostic_safe_total_seconds'],
                 'raw_observed_start':str(obs['start_time']),'raw_observed_finish':str(obs['end_time']),
                 'raw_observed_total_runtime_seconds':sec,'actual_service_seconds':remaining,
                 'actual_minus_DA_service_seconds':remaining-float(job['safe_duration_seconds']),
                 'actual_replay_start_issue_slot':aparts[0]['start'] if aparts else None,
                 'actual_replay_finish_issue_slot':aparts[-1]['end'] if aparts else None,
                 'actual_segments':json.dumps(aparts),'actual_status':a['status'],
                 'timing_authority':'Raw observed runtime/residual; frozen-policy admission plus capacity dispatcher. Raw PENDING start is not replay admission.',
                 'execution_site_authority':'Frozen synthetic policy and derived Actual ledger; NOT an observed physical-node-to-AIDC allocation certificate.' if aparts else 'NO_ACTIVE_REPLAY_SEGMENT; do not infer site authority',
                 'critical_DA_sites':json.dumps([SITES[i] for i,x in enumerate(p) if x]),
                 'critical_Actual_sites':json.dumps([SITES[i] for i,x in enumerate(v) if x]),
                 'critical_DA_GPU':int(p.sum()),'critical_Actual_GPU':int(v.sum()),
                 'critical_DA_downstream_GPU':int(p[down].sum()),'critical_Actual_downstream_GPU':int(v[down].sum()),
                 'runtime_only_no_delay_downstream_GPU':int(n[down].sum()),
                 'migration_selected':bool(job.get('migration_selected')),'migration_executed':bool(a.get('migration_executed')),
                 'capacity_delay_slots':a.get('start_delay_slots'),
                 'pre_day_complete_authority':'INDEPENDENT_RAW_RUNNING_TIMING' if a['status']=='PRE_DAY_COMPLETE' and job['state_at_issue']=='RUNNING' else None}
            rows.append(row)
            for i,s in enumerate(SITES):
                piece.append({'case':c,'job_uid':uid,'state':job['state_at_issue'],'site':s,'downstream':bool(down[i]),
                    'DA_GPU':int(p[i]),'runtime_only_GPU':int(n[i]),'Actual_GPU':int(v[i]),
                    'runtime_effect_GPU':int(n[i]-p[i]),'admission_delay_effect_GPU':int(v[i]-n[i]),
                    'runtime_effect_IT_kW':float(n[i]-p[i])*swing,'admission_delay_effect_IT_kW':float(v[i]-n[i])*swing,
                    'migration_selected':bool(job.get('migration_selected'))})
        write_json(out/(c+'_CRITICAL_ACTIVE_UID_SET.json'),{'slot':SLOT,'issue_axis_slot':AXIS,
            'jobs':contrib[c][contrib[c].slot==SLOT].to_dict('records')})
    comparisons=pd.DataFrame(rows);comparisons.to_csv(out/'DA_VS_ACTUAL_JOB_COMPARISON.csv',index=False,encoding='utf-8-sig')
    comparisons.to_parquet(out/'DA_VS_ACTUAL_JOB_COMPARISON.parquet',index=False)
    parts=pd.DataFrame(piece);parts.to_parquet(out/'JOB_SITE_RUNTIME_ADMISSION_DECOMPOSITION.parquet',index=False)
    parts.groupby(['case','state','site','downstream'],as_index=False).sum(numeric_only=True).to_csv(out/'RUNTIME_ADMISSION_BY_STATE_SITE.csv',index=False)
    critical=[]
    for i,s in enumerate(SITES):
        row={'site':s,'line_sw2_downstream':bool(down[i])}
        for c in ('B0','B1'):
            a=times[c][(times[c].slot==SLOT)&(times[c].site_id==s)].iloc[0]
            row.update({c+'_DA_GPU':int(arrays[c]['gpu'][SLOT,i]),c+'_Actual_GPU':int(a.occupied_GPU),
                        c+'_DA_IT_kW':float(arrays[c]['it'][SLOT,i]),c+'_Actual_IT_kW':float(a.P_IT_kW),
                        c+'_Actual_PCC_kW':float(a.P_PCC_kW),c+'_runtime_effect_GPU':int(no_delay[c][i]-arrays[c]['gpu'][SLOT,i]),
                        c+'_admission_effect_GPU':int(a.occupied_GPU-no_delay[c][i])})
        for field in ['DA_GPU','Actual_GPU','DA_IT_kW','Actual_IT_kW','Actual_PCC_kW','runtime_effect_GPU','admission_effect_GPU']:
            row['B1_minus_B0_'+field]=row['B1_'+field]-row['B0_'+field]
        critical.append(row)
    pd.DataFrame(critical).to_csv(out/'CRITICAL_SLOT_73_BY_AIDC.csv',index=False)
    # A fixed cohort includes 508 unscheduled post-H backlog rows. Their observed duration
    # is known but counterfactual execution/site is not; preserve that limitation explicitly.
    workload={'cutoff':ISSUE.isoformat(),'local_cutoff':'2025-04-30T18:00:00+10:00','Dday_slots':96,'issue_axis_Dday':[24,120],
        'critical_operating_slot':SLOT,'critical_issue_slot':AXIS,'jobs':1649,'RUNNING':254,'PENDING':1395,
        'RUNNING_QOS':dict(Counter(r['qos'] for r in jobs['B0'] if r['state_at_issue']=='RUNNING')),
        'PENDING_QOS':dict(Counter(r['qos'] for r in jobs['B0'] if r['state_at_issue']=='PENDING')),
        'fixed_nondeferrable':'254 RUNNING are already running at issue; service/duration immutable; eligible in-day jobs may use a frozen checkpoint migration.',
        'flexible':'1395 PENDING standby jobs have causal resource requests and common safe durations; temporal/spatial choices within authorized domain.',
        'future_arrival_forecast':'NONE; post-cutoff arrivals excluded from Planning AND this frozen Actual cohort',
        'post_cutoff_UIDs_Planning':0,'post_cutoff_UIDs_Actual':int(comparisons.post_cutoff_arrival.sum()),
        'future_arrival_contribution_to_saved_replay_GPU':0,
        'raw_snapshot_exclusion_count_scope':'not_yet_submitted count is from loaded multi-date state source, NOT May-01 arrival count',
        'raw_snapshot_audit':daymanifest['Kestrel_D1_snapshot_audit'],
        'UNASSIGNED_POST_H_BACKLOG_each_case':508,'PRE_DAY_COMPLETE_each_case':44,'EXECUTION_ACCOUNTED_each_case':1097,
        'full_real_world_arrival_coverage_claimed':False,'new_actual_site_authorizations_from_this_forensic':0}
    assert not comparisons.post_cutoff_arrival.any()
    write_json(out/'DAY_AHEAD_WORKLOAD_REPRESENTATION.json',workload)
    for f in ['dayahead/v37/aidc_materializer.py','dayahead/v40f/common_service.py','dayahead/v40g/authority.py',
              'dayahead/v40g/domain.py','dayahead/v40g/actual.py','dayahead/v40d_actual/job_replay.py',
              'dayahead/v40d_actual/power_replay.py','dayahead/v39a/power.py']:
        if (repo/f).is_file():source(Path(f))
    forecast=[]
    components=[
      ('RUNNING state/resource', 'OBSERVATION', dayroot/'V37_R4A_D1_SNAPSHOT.parquet',
       'submit <= cutoff; known start <= cutoff; not completed at cutoff; requested GPU and walltime',
       'NONE', 'RUNNING membership/resources at cutoff', 'instantaneous D-1 state', 'NONE', 'Missing/invalid requests excluded fail-closed'),
      ('RUNNING remaining service', 'ASSUMPTION_FROM_OBSERVATIONS', dayroot/'V37_R4A_JOB_LEDGER.parquet',
       'max(requested walltime - observed elapsed at issue, 900); ceil to 15-minute slots',
       'NONE; requested remaining heuristic', 'remaining compute service seconds', 'per-job completion including post-H tail',
       'deterministic point reservation', '900-second minimum even when elapsed exceeds requested walltime'),
      ('PENDING membership/resources', 'OBSERVATION', dayroot/'V37_R4A_D1_SNAPSHOT.parquet',
       'submitted <= cutoff and not started by cutoff; future start/end removed before scheduler',
       'NONE', 'PENDING membership/request', 'instantaneous D-1 state', 'NONE', 'Missing/invalid resource requests excluded'),
      ('PENDING duration', 'PREDICTION', dayroot/'V37_R4A_JOB_LEDGER.parquet',
       'Apr-01 frozen model; training labels end before 2025-03-31 08:00 UTC; May labels not read',
       'hpc_oda_commons job_runtime_moe_xgboost MoEXGBoostModel; reg:absoluteerror',
       'total runtime_seconds per pending job', 'per-job total service; 30-hour issue-to-end Planning window plus terminal accounting',
       'point estimate + frozen q=5576.44921875s; min(requested,max(point+q,900)); nominal quantile coverage NOT_RECORDED in consumed audit',
       'requested walltime when prediction unavailable; 0 fallback jobs in this May-01 cohort'),
      ('fixed/nondeferrable service', 'OBSERVATION_PLUS_RESERVATION', G/'common_service/COMMON_DA_SERVICE_AUTHORITY.json',
       'common causal duration/residual and exact terminal obligations shared by B0/B1; RUNNING start held at issue',
       'RUNNING requested remaining; no new estimator', 'immutable compute service/terminal profile',
       'issue through completion', 'same common service values for all cases', 'No service reduction or omission permitted'),
      ('flexible start/site/migration', 'OPTIMIZATION_DECISION_FROZEN_BEFORE_ACTUAL', SMOKE/'PRE_MESS_JOBS.json',
       'D-1 model uses common service; B0 reference admission/site inherited; B1 joint temporal/spatial choices; checkpoint/WAN frozen',
       'V40G existing joint min-rho formulation; no new optimization in this forensic',
       'start/site/checkpoint and compute intervals', 'issue slots [0,120) plus immutable post-H service',
       'decisions, not predictions', 'No Actual-informed selection, fit or fallback'),
      ('post-cutoff future arrivals', 'EXCLUDED_COMPONENT', dayroot/'V37_R4A_DAY_MANIFEST.json',
       'submit after cutoff excluded; both Actual and Planning use same D-1 cohort',
       'NONE', 'NONE; no arrival count/GPU forecast consumed', 'NOT_MODELED', 'NONE',
       'No synthetic arrivals added; real-world arrival coverage remains outside this replay'),
    ]
    for component,role,path,causal,model,target,horizon,kind,fallback in components:
        p=source(path)
        forecast.append({'component':component,'role':role,'source_file':str(p),'source_sha256':sha(p),
          'source_timestamp':{'logical_cutoff_UTC':ISSUE.isoformat(),
             'artifact_mtime_UTC':datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(),
             'mtime_is_not_historical_availability_proof':True},
          'D1_causality':causal,'model_estimator':model,'target':target,'prediction_horizon':horizon,
          'point_or_quantile':kind,'fallback':fallback})
    write_json(out/'WORKLOAD_FORECAST_SOURCE_LINEAGE.json',{'components':forecast,
       'runtime_model_frozen_audit':causality['runtime'],'raw_source_authority':causality['source'],
       'causal_model_source_HEAD':causality['runtime']['model_source_HEAD'],
       'training_window':'120 days before 2025-03-31T08:00Z; 1,288,805 completed pre-cutoff rows',
       'model_retrained_in_forensic':False,
       'historical_artifact_generation_timestamp':'Not durably recorded in consumed manifest; filesystem mtime reported separately without treating it as D-1 evidence.'})
    # Actual dispatcher replay of fixed factorial interventions is explicitly diagnostic.
    from dayahead.v40d_actual.inputs import capacity
    from dayahead.v40d_actual.rack_dispatch import Rack
    from dayahead.v40g.actual import replay_jobs
    cap,*_=capacity(repo);capacities=cap['frozen_V39C_site_capacity']
    source(Path('dayahead/artifacts/v39d_independent_daily_temporal_first_migration/V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json'))
    source(Path('dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze/V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json'))
    racks=[Rack(r['aidc_id'],r['rack_pool_id'],int(r['compatibility_GPU_limit'])) for r in cap['logical_Rack_pools']]
    scenarios={'B0_REFERENCE':jobs['B0'],
       'TEMPORAL_ONLY':hybrid_jobs(jobs['B0'],jobs['B1'],True,False),
       'SPATIAL_ONLY_PENDING':hybrid_jobs(jobs['B0'],jobs['B1'],False,True),
       'JOINT_WITHOUT_RUNNING_MIGRATION':hybrid_jobs(jobs['B0'],jobs['B1'],True,True),
       'JOINT_B1':jobs['B1']}
    diag={};diag_gpu={}
    for label,choices in scenarios.items():
        print('DIAGNOSTIC_FIXED_DISPATCH',label,flush=True)
        replay=replay_jobs(choices,observed,issue_time=ISSUE.to_pydatetime(),site_capacity=capacities,racks=racks)
        gpu=all_occupancy(replay['job_ledger'],'Actual');diag_gpu[label]=gpu
        diag[label]={'slot73_GPU':gpu[SLOT].tolist(),'downstream_GPU':int(gpu[SLOT,down].sum()),
            'total_GPU':int(gpu[SLOT].sum()),'physical_capacity_violations':int(sum((gpu[:,i]>capacities[s]).sum() for i,s in enumerate(SITES))),
            'runtime_optimization_calls':0,'policy_selection':False,'new_power_flow_calls':0,
            'planning_terminal_feasibility_certified':False,
            'scope':'Fixed decision component intervention with identical observed service and original capacity dispatcher; not a newly optimized/admissible Planning policy.'}
        write_json(out/(label+'_DIAGNOSTIC_LEDGER.json'),{'jobs':replay['job_ledger'],'diagnostic_only':True})
    np.testing.assert_array_equal(diag_gpu['B0_REFERENCE'],all_occupancy(list(actual['B0'].values()),'Actual'))
    np.testing.assert_array_equal(diag_gpu['JOINT_B1'],all_occupancy(list(actual['B1'].values()),'Actual'))
    b=diag_gpu['B0_REFERENCE'][SLOT];t=diag_gpu['TEMPORAL_ONLY'][SLOT];s=diag_gpu['SPATIAL_ONLY_PENDING'][SLOT]
    j=diag_gpu['JOINT_WITHOUT_RUNNING_MIGRATION'][SLOT];m=diag_gpu['JOINT_B1'][SLOT]
    effects={'temporal':t-b,'spatial_pending':s-b,'temporal_spatial_interaction':j-t-s+b,'running_migration_in_joint_context':m-j}
    assert np.array_equal(sum(effects.values()),m-b)
    diag['additive_decomposition']={k:{'per_site_GPU':v.tolist(),'downstream_GPU':int(v[down].sum()),'downstream_IT_kW':float(v[down].sum())*swing} for k,v in effects.items()}
    diag['B0_and_joint_endpoint_occupancy_exactly_reproduce_frozen_results']=True
    diag['existing_independently_optimized_temporal_diagnostic']=js(SMOKE/'TEMPORAL_ONLY_COMPARISON.json')
    diag['existing_temporal_diagnostic_note']='Historical temporal-only optimum uses a different frozen temporal schedule; factorial TEMPORAL_ONLY uses final B1 starts. No old or new policy is selected.'
    write_json(out/'TEMPORAL_SPATIAL_DIAGNOSTIC.json',diag)
    np.savez_compressed(out/'DIAGNOSTIC_OCCUPANCY.npz',**diag_gpu)
    ds=parts[parts.downstream].groupby(['case','state'])[['DA_GPU','Actual_GPU','runtime_effect_GPU','admission_delay_effect_GPU']].sum()
    signparts=parts[parts.downstream].merge(comparisons[['case','job_uid','actual_minus_DA_service_seconds']],on=['case','job_uid'])
    signparts['service_error']=np.where(signparts.actual_minus_DA_service_seconds>0,'UNDERPREDICTED',
                                      np.where(signparts.actual_minus_DA_service_seconds<0,'OVERPREDICTED','EXACT'))
    signs=signparts.groupby(['case','state','site','service_error'],as_index=False)[['runtime_effect_GPU','admission_delay_effect_GPU']].sum()
    signs.to_csv(out/'RUNTIME_UNDER_OVER_PREDICTION_BY_SITE.csv',index=False)
    decomp=[{'case':c,'state':s,**{k:int(v) for k,v in row.items()}} for (c,s),row in ds.iterrows()]
    write_json(out/'DOWNSTREAM_RUNTIME_ADMISSION_DECOMPOSITION.json',{'rows':decomp,
        'ordering':'Hold frozen site/checkpoint/start; replace service; then account for realized dispatcher delay. Effects are order-dependent accounting, not independently fitted causes.',
        'future_arrival_GPU':0})
    # Per-job placement/activity Shapley accounting at the critical slot; migration is separate.
    records=[]
    by0={r['job_uid']:r for r in jobs['B0']};by1={r['job_uid']:r for r in jobs['B1']}
    for uid in sorted(by0):
        a,b=by0[uid],by1[uid];v0=vector(actual_segments(actual['B0'][uid]),a['requested_GPU']);v1=vector(actual_segments(actual['B1'][uid]),b['requested_GPU'])
        changed=a['AIDC_site']!=b['AIDC_site']
        if changed or a['start_slot']!=b['start_slot'] or b.get('migration_selected'):
            records.append({'job_uid':uid,'state':a['state_at_issue'],'site_changed':changed,'start_changed':a['start_slot']!=b['start_slot'],
                'migration_selected':bool(b.get('migration_selected')),'B0_site':a['AIDC_site'],'B1_site':b['AIDC_site'],
                'B0_critical_downstream_GPU':int(v0[down].sum()),'B1_critical_downstream_GPU':int(v1[down].sum()),
                'delta_downstream_GPU':int((v1-v0)[down].sum())})
    changed=pd.DataFrame(records);changed.to_csv(out/'CHANGED_DECISION_CRITICAL_UID_AUDIT.csv',index=False)
    assert int(changed.site_changed.sum())==539 and int(changed.migration_selected.sum())==10
    runtime_delta=int(ds.loc['B1','runtime_effect_GPU'].sum()-ds.loc['B0','runtime_effect_GPU'].sum())
    da0=int(arrays['B0']['gpu'][SLOT,down].sum());da1=int(arrays['B1']['gpu'][SLOT,down].sum())
    act0=diag['B0_REFERENCE']['downstream_GPU'];act1=diag['JOINT_B1']['downstream_GPU']
    hypotheses={
      'H1':{'classification':'PARTIAL','evidence':'B1 PENDING underprediction adds 29 downstream GPU, overprediction removes 3, admission delay removes 3; B0 corresponding runtime effects +9/-20. RUNNING overprediction removes 32 (B1) versus 41 (B0); no RUNNING underprediction contribution at this critical downstream slot.',
            'runtime_error_differential_downstream_GPU':runtime_delta,'state_decomposition':decomp},
      'H2':{'classification':'REJECTED','scope':'Cause of this saved May-01 B0/B1 replay difference only',
            'reason':'Both Planning and Actual contain the same 1649 pre-cutoff UIDs; zero post-cutoff additions. Real-world future-arrival forecasting adequacy is outside this closed-cohort replay.'},
      'H3':{'classification':'CONFIRMED','scope':'Increased downstream active GPU in the fixed-decision diagnostic, not exact ampere attribution or independent raw site authority.',
            'reason':'539 frozen site changes are confirmed. PENDING spatial-only intervention adds 9 downstream GPU, while temporal and migration interactions reduce the joint net to +2; not all 539 are active at slot 73.',
            'changed_site_jobs':539,'changed_site_critical_active_B0':int(sum(bool(vector(actual_segments(actual['B0'][uid]),by0[uid]['requested_GPU']).sum()) for uid in changed[changed.site_changed].job_uid)),
            'changed_site_critical_active_B1':int(sum(bool(vector(actual_segments(actual['B1'][uid]),by1[uid]['requested_GPU']).sum()) for uid in changed[changed.site_changed].job_uid)),
            'diagnostic_effects':diag['additive_decomposition']}}
    summary={'status':'FORENSIC_COMPLETE_WITH_EXPLICIT_AUTHORITY_LIMITS','no_optimization_executed':True,'no_retuning_or_policy_selection':True,
        'critical_line':'line.sw2','phase':'A','slot':SLOT,'downstream_sites':[s for s,v in cut['sites'].items() if v],
        'DA_downstream_GPU':{'B0':da0,'B1':da1,'B1_minus_B0':da1-da0},
        'Actual_downstream_GPU':{'B0':act0,'B1':act1,'B1_minus_B0':act1-act0},
        'Actual_downstream_delta_IT_kW':(act1-act0)*swing,
        'hypotheses':hypotheses,'inherited_V40G_metrics':final['critical_metrics'],
        'exact_phase_current_causal_allocation':'INSUFFICIENT_EVIDENCE: only endpoint AC outputs are frozen; no new electrical diagnostic solves or coefficient fitting performed.',
        'real_world_site_authority':'INSUFFICIENT_AUTHORITY: synthetic policy replay placement is not an independent raw-node allocation certificate.',
        'unassigned_postH_job_authority':'508 rows retained per case with unknown actual execution placement/admission; no full-universe site closure is claimed.',
        'Actual_integrity_failure_due_to_rho_sign':False,
        'root_cause_statement':f'Frozen B1 Planning predicted sw2-downstream occupancy {da1} GPU versus B0 {da0}; observed-service fixed-policy replay realized {act1} versus {act0} GPU at slot 73. PENDING runtime underprediction adds 29 downstream GPU in B1 versus 9 in B0; reductions from overprediction and capacity delay partly offset this. PENDING placement contributes +9 GPU in the spatial-only diagnostic, temporal effect -2, interaction -4 and migration -1, yielding {act1-act0:+d} GPU ({(act1-act0)*swing:+.9f} IT kW). This downstream increase accompanies the saved phase-A current increase. Post-cutoff arrivals contribute zero in this closed cohort. Exact ampere allocation to individual causes is INSUFFICIENT_EVIDENCE.',
        'certified_regeneration_permitted_after_forensic_complete':True}
    write_json(out/'MAY01_ACTUAL_REVERSAL_FORENSIC.json',summary)
    for path,record in first_read.items():assert file_record(path,root=repo)==record,'FORENSIC_INPUT_CHANGED'
    before=manifest(inputs,repo);write_json(out/'FROZEN_FORENSIC_INPUT_MANIFEST.json',before);verify_manifest(before)
    report(repo,out,summary,workload,critical,diag,decomp)
    print(json.dumps({'DA':summary['DA_downstream_GPU'],'Actual':summary['Actual_downstream_GPU'],'decomposition':diag['additive_decomposition'],'runtime':decomp},ensure_ascii=False),flush=True)
    return summary


def report(repo,out,summary,workload,critical,diag,decomp):
    text=[
      '# May-01 B0/B1 Actual 역전 forensic',
      '',
      '기존 frozen V40G 증거와 고정 결정의 진단 dispatch만 사용했다. 최적화, 모델 학습, 파라미터 조정, 정책 재선택, 새 전기계수 생성은 0회다.',
      '',
      'D-1 cutoff는 2025-04-30 18:00 AEST(08:00 UTC)이다. RUNNING 254개와 PENDING 1,395개, 총 1,649 UID를 두 정책이 공유한다. D-day slot 73(18:15)은 issue 기준 slot 97이다.',
      '',
      'RUNNING은 관측된 경과시간을 요청 walltime에서 뺀 잔여시간(최소 900초)을 사용한다. PENDING은 2025-03-31 08:00 UTC 이전 완료 데이터 1,288,805행으로 고정한 MoE XGBoost point prediction에 5,576.44921875초를 더하고 요청 walltime으로 상한을 둔다. 최종 슬롯은 올림한다. May-01 PENDING의 requested-walltime fallback은 0개다. B0와 B1 모두 같은 safe duration을 사용하며 B0만 requested-walltime duration을 쓴다고 해석하면 안 된다.',
      '',
      '관측은 UID·요청 GPU·state·RUNNING 경과시간이다. Duration은 예측 또는 예약 가정이고, start/site/migration은 frozen decision이다. RUNNING은 issue에서 계속 실행하되 허용된 checkpoint migration이 가능하다. PENDING은 모두 standby이며 허용된 시간·위치 선택 영역 안에서 조정된다. 미래 도착 workload 예측은 없고 해당 UID는 Planning과 기존 Actual 모두에 포함되지 않는다.',
      '',
      '소스별 경로·SHA·논리적 cutoff·파일 mtime·모델·target·horizon·point/quantile·fallback은 WORKLOAD_FORECAST_SOURCE_LINEAGE.json에, 3,298개 case/UID 비교는 DA_VS_ACTUAL_JOB_COMPARISON.csv에 기록했다. 파일 mtime을 과거 D-1 가용성 증명으로 사용하지 않았다. 보정 q의 명목 신뢰수준은 소비된 audit에 없어 NOT_RECORDED로 남겼다.',
      '',
      'Actual timing과 site 권위는 별개다. raw start/end는 실행시간 관측이며 PENDING의 counterfactual admission 시간이 아니다. Actual start/finish는 고정 정책과 capacity dispatcher의 파생 결과다. 합성 AIDC 위치·migration 구간은 frozen policy replay의 출처를 명시했으며 독립 raw site 권위로 승격하지 않았다. 각 case의 PRE_DAY_COMPLETE 44건과 UNASSIGNED_POST_H_BACKLOG 508건도 보존했다. 후자의 실제 admission/site는 여전히 미확정이다.',
      '',
      '| AIDC | sw2 하류 | DA B0 GPU | DA B1 GPU | Actual B0 GPU | Actual B1 GPU | ΔGPU | ΔIT kW |',
      '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in critical:
        text.append(f"| {r['site']} | {'YES' if r['line_sw2_downstream'] else 'NO'} | {r['B0_DA_GPU']} | {r['B1_DA_GPU']} | {r['B0_Actual_GPU']} | {r['B1_Actual_GPU']} | {r['B1_minus_B0_Actual_GPU']:+d} | {r['B1_minus_B0_Actual_IT_kW']:+.6f} |")
    text.extend(['',
      '전체 Actual GPU는 398→383으로 감소하지만 하류 AIDC05/09/10/11/12는 171→173 GPU로 증가한다. 하류 IT와 PCC의 증분은 각각 +1.095447818 kW다. Planning 하류 223→182 GPU(−41)와 달리 Actual은 +2이므로 정책 간 realization gap은 +43 GPU다.',
      '',
      '| case/state | DA 하류 GPU | runtime 효과 | admission 지연 효과 | Actual 하류 GPU |',
      '|---|---:|---:|---:|---:|'])
    for r in decomp:text.append(f"| {r['case']}/{r['state']} | {r['DA_GPU']} | {r['runtime_effect_GPU']:+d} | {r['admission_delay_effect_GPU']:+d} | {r['Actual_GPU']} |")
    text.extend(['',
      'B1 PENDING의 runtime 효과 +26은 과소예측 +29와 과대예측 −3의 합이다. B0 PENDING은 +9−20=−11이다. RUNNING 과대예측의 감소 효과는 B0 −41, B1 −32이며, 이 slot에서 RUNNING 과소예측의 증가 기여는 없다. Runtime differential +46과 admission differential −3을 더하면 +43 GPU의 realization gap이 정확히 맞는다.',
      '',
      '고정 결정의 5개 진단 시나리오는 동일 realized service와 capacity dispatcher를 사용했다. B0·joint B1의 96×12 occupancy는 기존 frozen 배열과 정확히 일치했다. 중간 시나리오는 원인 분해용이며 Planning terminal 적합성이나 새 정책 후보로 인증하지 않았다.',
      '',
      '| 진단 효과 | sw2 하류 ΔGPU | ΔIT kW |','|---|---:|---:|'])
    for label,r in diag['additive_decomposition'].items():text.append(f"| {label} | {r['downstream_GPU']:+d} | {r['downstream_IT_kW']:+.9f} |")
    text.extend(['',
      '과거 독립 temporal-only 최적값 0.5920473944907508도 그대로 보존했다. 이 값은 final B1 start만 교차 적용한 위 진단과 다른 frozen schedule의 결과이며 재선택에 사용하지 않았다.',
      '',
      'H1 = PARTIAL: PENDING 과소예측 overlap 증가를 확인했지만 RUNNING은 감소 방향이다. H2 = REJECTED: 저장된 폐쇄 cohort replay의 원인으로는 미래 도착 기여가 0이다. 실제 운영의 future-arrival forecast 적정성까지 검증한 것은 아니다. H3 = CONFIRMED: 고정 PENDING 위치 변경은 spatial-only 진단에서 하류 +9 GPU를 만든다. 539개 모두가 해당 slot에서 실행 중이거나 동일 방향의 기여를 한다는 뜻은 아니다.',
      '',
      'line.sw2 / phase A / slot 73에서 기존 전류는 246.3005630208428→246.44680474732297 A(+0.146241726480 A), rho는 0.5892357967005808→0.5895856572902464다. 실제 전류 변화의 job별·원인별 정확한 A 단위 분해는 INSUFFICIENT_EVIDENCE로 남긴다. 새로운 AC 진단이나 계수 fitting으로 이 값을 추정하지 않았다.',
      '',
      '원인 진술: B1은 D-1 safe duration의 예상 occupancy로 하류 부하를 줄였으나, Actual에서는 PENDING runtime 과소예측과 고정 위치·시간 결정의 상호작용으로 감소 폭이 사라졌다. AIDC05 +5, AIDC12 +7 GPU 증가를 AIDC09 −5, AIDC10 −5가 일부 상쇄하여 sw2 하류에 순 +2 GPU가 남았고, 기존 phase-A 전류 증가가 함께 관측됐다. 이 결과는 ACTUAL_GENERALIZATION_DEGRADATION_OBSERVED이며 rho 부호만으로 integrity failure가 되지 않는다.',
      '',
      '모든 결과는 원인 규명에만 사용한다. Model fitting, parameter tuning, B1 reselection, migration penalty tuning, robust-margin calibration에 사용하지 않는다. Authority closure의 남은 72건과 별도 production authorization 차단은 유지한다.',
      ''])
    (out/'MAY01_ACTUAL_REVERSAL_FORENSIC.md').write_text('\n'.join(text),encoding='utf-8')


if __name__=='__main__':run(Path.cwd())

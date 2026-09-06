"""Read-only decision/service audit. No optimization, policy change or campaign."""
from pathlib import Path
import math
import numpy as np
import pandas as pd
from dayahead.paper_analysis.storage import read, reference, write_json, write_parquet, sha
from dayahead.v40e.audit import REL, OLD


def table(out, name, frame):
    write_parquet(out / (name + '.parquet'), frame)
    frame.to_csv(out / (name + '.csv'), index=False, float_format='%.17g', encoding='utf-8-sig')


def audit(repo):
    repo=Path(repo).resolve();root=repo/REL;smoke=root/'smoke/2025-05-01'
    out=root/'neutral_move_forensic';out.mkdir(parents=True,exist_ok=True)
    jobs=read(smoke/'PRE_MESS_JOBS.json')
    frozen={c:pd.DataFrame(jobs[c]).set_index('job_uid').sort_index() for c in ('B0','B1')}
    service={c:pd.read_parquet(root/f'service_equivalence/2025-05-01/{c}_SERVICE_PARTITION.parquet').set_index('job_uid').sort_index() for c in frozen}
    a,b=frozen['B0'],frozen['B1'];assert a.index.equals(b.index)
    assert a.requested_GPU.equals(b.requested_GPU)
    assert service['B0'].realized_runtime_seconds.equals(service['B1'].realized_runtime_seconds)
    issue=pd.Timestamp('2025-04-30T18:00:00+10:00')
    paired=pd.DataFrame(index=a.index)
    for c,f in frozen.items():
        for short,field in [('start','start_slot'),('end','end_slot'),('site','AIDC_site'),('migration','migration_selected')]:paired[c+'_'+short]=f[field]
        paired[c+'_start_timestamp']=[(issue+pd.Timedelta(minutes=15*int(x))).isoformat() for x in f.start_slot]
        paired[c+'_planned_duration_slots']=f.end_slot-f.start_slot
        paired[c+'_actual_status']=service[c].status
        for field in ('actual_start','actual_end','Dday_GPU_hours','postH_GPU_hours'):
            paired[c+'_'+field]=service[c][field]
    paired['state_at_issue']=a.state_at_issue
    paired['delta_start']=b.start_slot-a.start_slot
    paired['site_changed']=a.AIDC_site!=b.AIDC_site
    paired['migration_changed']=a.migration_selected!=b.migration_selected
    paired['requested_GPU']=a.requested_GPU
    paired['realized_runtime']=service['B0'].realized_runtime_seconds
    paired['start_changed']=paired.delta_start!=0
    paired['duration_changed']=paired.B0_planned_duration_slots!=paired.B1_planned_duration_slots
    paired['any_decision_changed']=paired.start_changed|paired.site_changed|paired.migration_changed|paired.duration_changed
    # Per UID/site/slot symmetric difference. UNASSIGNED is kept as a virtual label
    # for decision accounting, never interpreted as physical execution.
    symmetric=[];symmetric_day=[]
    for uid,r in paired.iterrows():
        def measure(lo,hi):
            s0,e0=max(lo,int(r.B0_start)),min(hi,int(r.B0_end))
            s1,e1=max(lo,int(r.B1_start)),min(hi,int(r.B1_end))
            n0,n1=max(0,e0-s0),max(0,e1-s1)
            intersection=max(0,min(e0,e1)-max(s0,s1)) if r.B0_site==r.B1_site else 0
            return int(r.requested_GPU)*(n0+n1-2*intersection)
        symmetric.append(measure(-math.inf,math.inf))
        symmetric_day.append(measure(24,120))
    paired['changed_GPU_slots']=symmetric;paired['changed_GPU_hours']=paired.changed_GPU_slots*.25
    paired['Dday_planned_symmetric_GPU_slots']=symmetric_day
    table(out,'B0_B1_EXACT_DECISION_DELTA',paired.reset_index())
    counts={
        'JOB_COUNT':len(paired),'START_CHANGED_JOB_COUNT':int(paired.start_changed.sum()),
        'START_ADVANCED_JOB_COUNT':int((paired.delta_start<0).sum()),'START_DELAYED_JOB_COUNT':int((paired.delta_start>0).sum()),
        'SITE_CHANGED_JOB_COUNT':int(paired.site_changed.sum()),'MIGRATION_CHANGED_JOB_COUNT':int(paired.migration_changed.sum()),
        'PLANNED_DURATION_CHANGED_JOB_COUNT':int(paired.duration_changed.sum()),
        'SITE_TO_SITE_CHANGED_JOB_COUNT':int((paired.site_changed&(paired.B0_site!='UNASSIGNED')&(paired.B1_site!='UNASSIGNED')).sum()),
        'UNASSIGNED_TO_SITE_JOB_COUNT':int(((paired.B0_site=='UNASSIGNED')&(paired.B1_site!='UNASSIGNED')).sum()),
        'PRE_D00_INHERITED_SITE_LABEL_DIFFERENCE_JOB_COUNT':int((paired.site_changed&(paired.B0_actual_status=='PRE_DAY_COMPLETE')).sum()),
        'POSTH_UNASSIGNED_TO_SITE_JOB_COUNT':int((paired.site_changed&(paired.B0_actual_status=='UNASSIGNED_POST_H_BACKLOG')).sum()),
        'changed_GPU_slots':int(paired.changed_GPU_slots.sum()),'changed_GPU_hours':float(paired.changed_GPU_hours.sum()),
        'Dday_planned_symmetric_GPU_slots':int(paired.Dday_planned_symmetric_GPU_slots.sum()),
        'changed_GPU_measure':'Full planned-interval per-UID/site/slot symmetric difference weighted by GPU; no division by two. UNASSIGNED remains a virtual decision label. RW and RSP planned durations differ.',
        'changed_jobs_full_realized_service_GPU_hours':float((paired.loc[paired.any_decision_changed,'requested_GPU']*paired.loc[paired.any_decision_changed,'realized_runtime']/3600).sum()),
        'GPU_weighted_start_displacement_slots':int((paired.delta_start.abs()*paired.requested_GPU).sum())}
    # Independently prove fixed temporal input identity, without calling the scheduler.
    rsp=pd.read_parquet(repo/'dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_RSP_SCHEDULE.parquet')
    rsp['job_uid']=rsp.job_id.astype(str);rsp=rsp.set_index('job_uid').sort_index()
    counts['B1_start_equals_frozen_RSP_each_job']=bool(np.array_equal(b.start_slot,rsp.scheduled_start_slot))
    counts['B1_end_equals_frozen_RSP_each_job']=bool(np.array_equal(b.end_slot,rsp.scheduled_end_slot))
    assert counts['B1_start_equals_frozen_RSP_each_job'] and counts['B1_end_equals_frozen_RSP_each_job']
    times={c:pd.read_parquet(smoke/c/'aidc_site_timeseries.parquet').sort_values(['slot','site_id']) for c in frozen}
    contrib={c:pd.read_parquet(smoke/c/'job_GPU_contributions.parquet') for c in frozen}
    for c in frozen:
        f=contrib[c]
        assert not f.duplicated(['job_uid','slot']).any()
        rec=f.groupby(['slot','site']).occupied_GPU.sum().reindex(pd.MultiIndex.from_product([range(96),sorted(times[c].site_id.unique())]),fill_value=0)
        assert np.array_equal(rec.to_numpy(),times[c].occupied_GPU.to_numpy())
    results=read(smoke/'V40E_B0_B1_CORRECTED_RESULTS.json')
    values={}
    for label,section,key in [('DA','Planning','rho_max'),('FRESH','Fresh','rho_max_AC'),('ACTUAL','Actual','rho_max_AC')]:
        v0,v1=results['B0'][section][key],results['B1'][section][key]
        values.update({f'J_B0_{label}':v0,f'J_B1_{label}':v1,f'Delta_{label}':v0-v1})
    values['binary64_full_precision_decimal']={k:format(v,'.17g') for k,v in values.items()}
    # A0 explicitly overrides only these parameters. Other values are read from
    # the installed solver; this probe never calls optimize.
    import gurobipy as gp
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();model=gp.Model(env=env)
    try:
        from dayahead.v39e.contracts import GUROBI_THREADS_PER_MODEL,SOLVER_SEED
        model.Params.Threads=GUROBI_THREADS_PER_MODEL;model.Params.Seed=SOLVER_SEED;model.Params.MIPGap=0
        solver={k:getattr(model.Params,k) for k in ['Threads','Seed','MIPGap','MIPGapAbs','FeasibilityTol','IntFeasTol','OptimalityTol']}
        solver['version']=list(gp.gurobi.version())
    finally:model.dispose();env.dispose()
    tolerances={'A0_solver':solver,'A0_B0_relative_acceptance_tolerance':None,
        'A0_primary_improvement_gate':'ABSENT','Planning_physical_evaluator_tolerance':1e-7,
        'A0_voltage_range_pu':[.95-1e-7,1.05+1e-7],
        'V40A_A1_MF_nondegradation_tolerance':1e-6,'V40A_A1_MF_applies_to_B1_A0':False,
        'significance_diagnostic_threshold':1e-6,'threshold_authority':'Existing V40A tolerance; used for reporting, not added to A0 acceptance.',
        'A0_no_lexicographic_secondary_or_tertiary_tolerance':True}
    # Critical-coordinate attribution from saved independent OpenDSS readbacks.
    with np.load(smoke/'B1/actual_grid/OPENDSS_PHASE_ARRAYS.npz') as z:z1={k:z[k] for k in z.files}
    with np.load(smoke/'B0/actual_grid/OPENDSS_PHASE_ARRAYS.npz') as z:z0={k:z[k] for k in z.files}
    idx=np.flatnonzero(np.char.startswith(z1['branch_names'].astype(str),'line.'))
    t,k0=np.unravel_index(z1['phase_current_loading_pu'][:,idx].argmax(),(96,len(idx)));k=int(idx[k0]);t=int(t)
    site=times['B0'][times['B0'].slot==t].set_index('site_id')[['occupied_GPU','P_IT_kW','P_PCC_kW','Q_PCC_kvar']].add_prefix('B0_')
    other=times['B1'][times['B1'].slot==t].set_index('site_id')[['occupied_GPU','P_IT_kW','P_PCC_kW','Q_PCC_kvar']].add_prefix('B1_')
    site=site.join(other)
    for key in ['occupied_GPU','P_IT_kW','P_PCC_kW','Q_PCC_kvar']:site['Delta_'+key]=site['B1_'+key]-site['B0_'+key]
    for c in frozen:
        rb=pd.read_parquet(smoke/c/'actual_readback/OPENDSS_COMPONENT_ELEMENTS.parquet')
        rb=rb[(rb.slot==t)&(rb.component=='AIDC')].set_index('AIDC_site_id').sort_index()
        assert np.array_equal(rb.P_kw,site[c+'_P_PCC_kW']) and np.array_equal(rb.Q_kvar,site[c+'_Q_PCC_kvar'])
        site[c+'_OpenDSS_bus']=rb.OpenDSS_bus
    table(out,'ACTUAL_CRITICAL_SLOT_SITE_GPU_PQ',site.reset_index())
    components={c:pd.read_parquet(smoke/c/'actual_readback/OPENDSS_COMPONENTS_96.parquet').set_index('slot') for c in frozen}
    for field in ['background_P_kw','background_Q_kvar','PV_P_kw','PV_Q_kvar','MESS_P_kw','MESS_Q_kvar']:
        assert np.array_equal(components['B0'][field],components['B1'][field])
    for field in ['observed_t_wb_c','observed_rh_pct']:assert np.array_equal(times['B0'][field],times['B1'][field])
    assert np.array_equal(z0['regulator_taps'],z1['regulator_taps']) and np.array_equal(z0['capacitor_states'],z1['capacitor_states'])
    from dayahead.v28r2.opendss_mapping import REGULATORS,CAPACITORS
    critical={'line':str(z1['branch_names'][k]),'phase':str(z1['branch_phases'][k]),'slot':t,'time_AEST':f'{t//4:02d}:{t%4*15:02d}',
        'B0_rho_same_coordinate':float(z0['phase_current_loading_pu'][t,k]),'B1_rho_same_coordinate':float(z1['phase_current_loading_pu'][t,k]),
        'B0_current_A':float(z0['phase_current_a'][t,k]),'B1_current_A':float(z1['phase_current_a'][t,k]),
        'Delta_current_A':float(z1['phase_current_a'][t,k]-z0['phase_current_a'][t,k]),
        'line_rating_A':float(z1['phase_current_a'][t,k]/z1['phase_current_loading_pu'][t,k]),
        'site_rows':site.reset_index().to_dict('records'),
        'regulator_order':list(REGULATORS),'capacitor_order':list(CAPACITORS),
        'B0_regulator_taps':z0['regulator_taps'][t].tolist(),'B1_regulator_taps':z1['regulator_taps'][t].tolist(),
        'B0_capacitor_states':z0['capacitor_states'][t].tolist(),'B1_capacitor_states':z1['capacitor_states'][t].tolist(),
        'background_PV_weather_native_controls_all96_exact_equal':True}
    for c in frozen:
        critical[c+'_components']={key:float(components[c].loc[t,key]) for key in components[c].columns if key not in ['case','namespace']}
        critical[c+'_weather']={key:float(times[c][times[c].slot==t].iloc[0][key]) for key in ['observed_t_wb_c','observed_rh_pct']}
    # Exact interval service around the slot's timestamp, with half-open windows.
    # Separate signed net, positive per-job differences, negative differences,
    # and slot-sampled quantities; do not mix integration conventions.
    windows=[];window_jobs=[]
    for hours in [1,2,12]:
        lo,hi=(t*900-hours*3600,t*900+hours*3600) if hours!=12 else (0,86400)
        lo=max(0,lo);hi=min(86400,hi);start=21600+lo;end=21600+hi
        p=pd.DataFrame(index=a.index)
        for c in frozen:
            f=service[c]
            overlap=(np.minimum(f.actual_end_issue_relative_seconds,end)-np.maximum(f.actual_start_issue_relative_seconds,start)).clip(lower=0).fillna(0)
            p[c+'_exact_GPU_hours']=overlap*f.requested_GPU/3600
            p[c+'_sampled_GPU_hours']=contrib[c][(contrib[c].slot*900>=lo)&(contrib[c].slot*900<hi)].groupby('job_uid').occupied_GPU.sum().reindex(a.index,fill_value=0)*.25
        p['Delta_exact_GPU_hours']=p.B1_exact_GPU_hours-p.B0_exact_GPU_hours
        p['window']='Dday' if hours==12 else f'plus_minus_{hours}h'
        window_jobs.append(p.reset_index())
        windows.append({'window':p.window.iloc[0],'start_AEST':(pd.Timestamp('2025-05-01T00:00:00+10:00')+pd.Timedelta(seconds=lo)).isoformat(),
            'end_exclusive_AEST':(pd.Timestamp('2025-05-01T00:00:00+10:00')+pd.Timedelta(seconds=hi)).isoformat(),
            'sampled_slots':list(range(lo//900,hi//900)),
            **{key:float(p[key].sum()) for key in ['B0_exact_GPU_hours','B1_exact_GPU_hours','Delta_exact_GPU_hours','B0_sampled_GPU_hours','B1_sampled_GPU_hours']},
            'positive_per_job_delta_GPU_hours':float(p.Delta_exact_GPU_hours.clip(lower=0).sum()),
            'negative_per_job_delta_GPU_hours':float(p.Delta_exact_GPU_hours.clip(upper=0).sum())})
    delta_day=windows[-1]['Delta_exact_GPU_hours']
    for w in windows:w['net_fraction_of_corrected_Dday_delta']=w['Delta_exact_GPU_hours']/delta_day
    table(out,'CRITICAL_WINDOW_PER_JOB_SERVICE',pd.concat(window_jobs,ignore_index=True))
    table(out,'CRITICAL_WINDOW_SERVICE_SUMMARY',pd.DataFrame(windows))
    # UID accounting at the critical slot links the net GPU increase to decisions.
    active=paired.copy()
    for c in frozen:
        q=contrib[c][contrib[c].slot==t].set_index('job_uid')
        active[c+'_GPU_at_critical']=q.occupied_GPU.reindex(active.index,fill_value=0)
    active['Delta_GPU_at_critical']=active.B1_GPU_at_critical-active.B0_GPU_at_critical
    active=active[(active.B0_GPU_at_critical!=0)|(active.B1_GPU_at_critical!=0)]
    table(out,'CRITICAL_SLOT_PAIRED_ACTIVE_JOBS',active.reset_index())
    attribution={'B0_only_job_count':int(((active.B0_GPU_at_critical>0)&(active.B1_GPU_at_critical==0)).sum()),
        'B1_only_job_count':int(((active.B1_GPU_at_critical>0)&(active.B0_GPU_at_critical==0)).sum()),
        'both_active_job_count':int(((active.B1_GPU_at_critical>0)&(active.B0_GPU_at_critical>0)).sum()),
        'net_GPU_delta':int(active.Delta_GPU_at_critical.sum()),
        'net_GPU_from_start_changed_jobs':int(active.loc[active.start_changed,'Delta_GPU_at_critical'].sum()),
        'net_GPU_from_start_unchanged_jobs':int(active.loc[~active.start_changed,'Delta_GPU_at_critical'].sum())}
    for group,mask in [('B1_only',(active.B1_GPU_at_critical>0)&(active.B0_GPU_at_critical==0)),('B0_only',(active.B0_GPU_at_critical>0)&(active.B1_GPU_at_critical==0))]:
        attribution[group+'_GPU']=int(active.loc[mask,group[:2]+'_GPU_at_critical'].sum())
        attribution[group+'_frozen_start_advanced_jobs']=int((active.loc[mask,'delta_start']<0).sum())
    old=read(repo/OLD/'service_equivalence/2025-05-01/V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json')
    a0=read(smoke/'A0/CORRECTED_ACCEPTED_A0.json')
    path_evidence=[('dayahead/v37/aidc_materializer.py',373,413,'RSP first-fit, QoS/submit/UID priority, no electrical objective'),
        ('dayahead/v37/aidc_materializer.py',438,476,'RW requested walltime vs causal-safe RSP runtime'),
        ('dayahead/v39e/full_spatial.py',241,260,'This call has allow_running_migration=False: objective is constant zero'),
        ('dayahead/v39e/full_preflight.py',301,311,'Earlier authority accepts feasible RSP independent of RW rho'),
        ('dayahead/v40a/initial.py',22,67,'Original A0 loads RSP fixed starts, obtains OPTIMAL feasible placement, materializes all jobs'),
        ('dayahead/v40a/README.md',9,31,'A0 is inherited; rho/deviation lexicography is explicitly A1'),
        ('dayahead/v40a/contracts.py',15,34,'B1 current AIDC-only authority; A1 baseline is accepted A0, not B0'),
        ('dayahead/v40a/feedback.py',47,100,'A1-only rho/deviation/tie objectives; not called for B1'),
        ('dayahead/v40a/invariants.py',134,137,'monotone permits equality and only gates A1/MF'),
        ('dayahead/v40e/smoke.py',17,42,'Preserved common RUNNING state; original A0 function'),
        ('dayahead/v40e/smoke.py',89,125,'B1 takes a0.jobs directly; B1 Planning status PASS, no B0 comparison'),
        ('tests/dayahead/test_v40a_coordination.py',1,70,'Tests cover A1/MF fallback; not RW-to-A0 retention')]
    evidence=[{'source':reference(repo/path),'start_line':lo,'end_line':hi,'finding':finding} for path,lo,hi,finding in path_evidence]
    result={'schema':'V40E_B1_NEUTRAL_MOVE_ACCEPTANCE_FORENSIC_V1','status':'AUDIT_COMPLETE',
        'classification':'C. METHOD_DESIGN_GAP','PRIMARY_IMPROVEMENT_SIGNIFICANT':'NO','FULL_MAY_AUTHORIZED':'NO','B2_B3_AUTHORIZED':'NO',
        'method_changed':False,'optimization_calls_during_audit':0,'objectives':values,'tolerances':tolerances,'decision_delta':counts,
        'acceptance_path':{'reported_primary_grid_metric':'rho_max, evaluated after A0 construction',
            'actual_A0_solver_primary':a0['placement']['objective'],'actual_A0_solver_secondary':None,'actual_A0_solver_tertiary':None,
            'actual_A0_solver_selection':a0['placement']['secondary_tie_break'],
            'temporal_policy':'Frozen causal RSP first-fit in QoS/submit/UID order, using safe predicted runtime, not grid-aware start optimization',
            'earlier_completion_reward_in_A0_MILP':False,'earliest_feasible_start_in_upstream_RSP':True,
            'occupancy_deviation_objective_in_A0':False,'reference_schedule_preservation_objective_in_A0':False,
            'B0_rho_used_in_A0_model_or_acceptance':False,'rho_primary_optimum_certified':False,
            'OPTIMAL_means':'Optimal for constant-zero feasibility objective, not optimal grid rho',
            'B1_selection':'Direct assignment of accepted feasible RSP/A0 jobs; no RW-vs-A0 objective comparison',
            'gates':['A0 placement solver OPTIMAL','case/job/capacity/terminal checks','B1 Planning physical PASS','B1 Fresh physical PASS'],
            'later_B3_A1_primary':'MIN rho','later_B3_A1_secondary':'MIN per-job site/time occupancy deviation from A0',
            'later_B3_A1_tertiary':'additional RUNNING migrations fixed zero; deterministic tie follows',
            'later_A1_MF_rule':'hard_pass and candidate <= previous + 1e-6; equality is permitted; not reached in B1',
            'solver_events':[read_event for p in (smoke/'A0/solver_events').glob('*.jsonl') for read_event in __import__('json').loads('['+','.join(p.read_text().splitlines())+']')]},
        'reference_preservation':{'rule_found_for_B0_to_B1_A0':False,'specification':'No RW-on-neutral rule found in applicable supplied requests or frozen current contracts',
            'earlier_authority':'Feasibility-only RSP selection is explicit in V39E full_preflight and full_spatial',
            'comments_and_tests':'A1 deviation preservation is relative to A0 and is not a B0/A0 acceptance requirement',
            'classification_reason':'An existing RW-neutral preservation requirement is not established. Adding one, or replacing zero feasibility by grid-primary A0, would change the method and is not done.'},
        'critical_slot':critical,'critical_active_job_attribution':attribution,'critical_windows':windows,
        'service_version_reconciliation':{'quoted_old_Dday_delta':old['deltas_B1_minus_B0']['Delta_Dday_GPU_h'],
            'quoted_old_source':reference(repo/OLD/'service_equivalence/2025-05-01/V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json'),
            'corrected_Dday_delta':delta_day,'difference_from_old':delta_day-old['deltas_B1_minus_B0']['Delta_Dday_GPU_h'],
            'corrected_source':reference(root/'service_equivalence/2025-05-01/V40D_ACTUAL_SERVICE_EQUIVALENCE_AUDIT.json'),
            'explanation':'Old number belongs to original V40D B1 placement. Corrected A0 was solved again, changing placement and same-site Actual queuing. Do not mix versions.'},
        'same_realized_runtime_and_GPU_per_UID':True,'source_evidence':evidence,
        'actual_run_ids':{c:results[c]['Actual_OpenDSS_run_id'] for c in frozen},
        'scientific_performance_degradation_claim_authorized':False,'UNASSIGNED_44_case_blocker':'PRESERVED'}
    write_json(root/'V40E_B1_NEUTRAL_MOVE_ACCEPTANCE_FORENSIC.json',result)
    print(__import__('json').dumps({'decision_delta':counts,'critical':attribution,'windows':windows,'objectives':values,'classification':result['classification']}),flush=True)
    return result

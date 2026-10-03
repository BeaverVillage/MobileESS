"""Read exact frozen May-01 inputs. Never fit, regenerate or read Actual outcomes."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,sys,math
from types import SimpleNamespace
import numpy as np
import pandas as pd
from .state import physical_occupancy,cohort_key,t2,DIMS,RULE
from v42_native.contracts import require,digest
from v42_native.voltage import Stage,voltage_for
from v42_job_capability import Job,checkpoint_records

ROOT=Path(__file__).resolve().parents[1];WORK=ROOT.parent
OUT=ROOT/'docs/v42_may01_native_canary';LOCAL=WORK/'V42_MAY01_NATIVE_LOCAL'
NATIVE=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
DAY='2025-05-01';ISSUE=pd.Timestamp('2025-04-30T08:00:00Z')
SOURCES={}


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [clean(x) for x in v]
    if isinstance(v,Path):return str(v)
    if isinstance(v,np.generic):return clean(v.item())
    if isinstance(v,float) and not math.isfinite(v):return None
    return v
def dump(name,v):(OUT/name).write_text(json.dumps(clean(v),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csv(name,rows):pd.DataFrame(rows).to_csv(OUT/name,index=False,lineterminator='\n')
def record(p,role,unit='metadata',period=DAY,status='FROZEN_SOURCE_REUSED',expected=None):
    p=Path(p);h=sha(p)
    if expected:require(h==expected,'SOURCE_HASH_DRIFT:'+str(p))
    row=dict(path=str(p),sha256=h,bytes=p.stat().st_size,period=period,units=unit,role=role,authority_status=status)
    SOURCES[str(p)]=row;return row


def reaudits():
    folder=WORK/'v42_reference_episode_pr/docs/v42_aidc_reference_episode_continuity'
    record(folder/'CONTINUING_CAPACITY_CONFLICT_DETAILS.csv','PR79 conflicting future reservation intervals',period='2024-2025 pre-May')
    record(folder/'CANONICAL_REFERENCE_LEDGER.parquet','PR79 causal state and reservations',period='2024-2025 pre-May')
    conflicts=pd.read_csv(folder/'CONTINUING_CAPACITY_CONFLICT_DETAILS.csv')
    ledger=pd.read_parquet(folder/'CANONICAL_REFERENCE_LEDGER.parquet',columns=['operating_day','reference_AIDC_site','state_at_issue','requested_GPU'])
    physical=ledger[ledger.state_at_issue.eq('RUNNING')].groupby(['operating_day','reference_AIDC_site']).requested_GPU.sum()
    rows=[]
    for key,g in conflicts.groupby(['day','site','start','end'],sort=True):
        day,site,start,end=key;running=float(g.loc[g.state.eq('RUNNING'),'requested_GPU'].sum());pending=float(g.loc[g.state.eq('PENDING'),'requested_GPU'].sum())
        current=float(physical.get((day,site),0));cap=float(g.site_cap.iloc[0]);true=current>cap or running>cap
        rows.append(dict(day=day,site=site,start=start,end=end,site_cap=cap,old_reservation_GPU=running+pending,
            old_pending_reservation_GPU=pending,running_reservation_GPU_at_old_interval=running,current_RUNNING_physical_GPU=current,
            pending_current_physical_GPU=0,physical_conflict_resolved_by_semantics=not true,remaining_true_physical_conflict=true,
            classification='TRUE_RUNNING_CAPACITY_CONFLICT' if true else 'OLD_PENDING_RESERVATION_WRONGLY_CARRIED_AS_PHYSICAL_OCCUPANCY',
            planning_classification='CURRENT_PLANNING_FUTURE_RESERVATION_COLLISION',
            planning_collision_still_requires_current_rescheduling=True,planning_collision_resolved=False,
            source_contribution_rows=len(g),episode_ids='|'.join(sorted(g.episode_id.unique())),
            exact_reason='Assigned RUNNING exceeds cap; retain without moving' if true else 'RUNNING current and interval-residual occupancy fit; old PENDING schedule is not current physical occupancy',
            qualification='Original PR79 table was a future-reservation audit, not proof of physical occupancy. Current planning must re-reserve full service.'))
    require(len(rows)==321,'PR79_INTERVAL_MEMBERSHIP');csv('PR79_CONFLICT_REAUDIT.csv',rows)
    dump('PR79_CONFLICT_REAUDIT_SUMMARY.json',dict(original_conflicts=321,source_contribution_rows=len(conflicts),
        resolved_by_corrected_PENDING_physical_semantics=sum(r['physical_conflict_resolved_by_semantics'] for r in rows),
        remaining_true_physical_conflicts=sum(r['remaining_true_physical_conflict'] for r in rows),
        current_future_reservation_collision_records=321,future_planning_collisions_proven_resolved=0,
        classification_counts={k:sum(r['classification']==k for r in rows) for k in ('OLD_PENDING_RESERVATION_WRONGLY_CARRIED_AS_PHYSICAL_OCCUPANCY','TRUE_RUNNING_CAPACITY_CONFLICT','SITE_MAPPING_OR_CAPACITY_AUTHORITY_CONFLICT','OTHER_SOURCE_BACKED_CAUSE')},
        two_accounting_views_are_not_interchangeable=True,jobs_moved=0,gangs_reduced=0,services_shortened=0,requeue_or_completion_invented=0))


def job_ledger(capacities,racks):
    reference=NATIVE/f'frozen_artifacts/v41r3_may/inputs/{DAY}/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'
    ref=record(reference,'Authoritative known-job independent-day reference and exact service','GPU,seconds,issue-origin 900s slots')
    jobs=read(reference);require(len({r['job_uid'] for r in jobs})==len(jobs),'DUPLICATE_KNOWN_JOB')
    metadata=WORK/'v42_flexibility_pr/docs/v42_aidc_workload_flexibility/REFERENCE_POPULATION.csv'
    record(metadata,'Frozen requested-node/cohort metadata; May01 rows only','requested attributes',period='historical May source inventory')
    meta=pd.read_csv(metadata,usecols=['day','job_uid','requested_nodes']).query('day == @DAY');meta.job_uid=meta.job_uid.astype(str);nodes=meta.set_index('job_uid').requested_nodes.to_dict()
    stats_path=ROOT/'docs/v42_job_capability_joint_flexibility/TRAIN_COHORT_LATENCY_STATISTICS.csv'
    stats_record=record(stats_path,'Unmodified PR90 TRAIN Q25 statistics','seconds,count',period='TRAIN before 2025-01-01')
    stats=pd.read_csv(stats_path).set_index('cohort').to_dict('index')
    require(all(s['cutoff'][:10]=='2025-01-01' and s['max_observed_start'][:10]<'2025-01-01' for s in stats.values()),'TRAIN_CUTOFF')
    snapshot_path=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt')/f'dayahead/artifacts/v37_r4a_per_day_aidc/days/{DAY}/V37_R4A_D1_SNAPSHOT.parquet'
    require(len({r['source_snapshot_sha256'] for r in jobs})==1,'MIXED_JOB_SOURCE')
    sr=record(snapshot_path,'Causal issue snapshot membership; projected columns exclude future start/end','timestamps,GPU',expected=jobs[0]['source_snapshot_sha256'])
    sf=pd.read_parquet(snapshot_path,columns=['id','state_at_issue','known_running_start','submit_time'])
    sf['uid']=sf.id.astype(str);sf=sf.set_index('uid')
    require(set(sf.index)=={j['job_uid'] for j in jobs} and sf.submit_time.le(ISSUE).all(),'KNOWN_CAUSAL_MEMBERSHIP')
    result=[]
    for r in jobs:
        uid=r['job_uid'];state=r['state_at_issue'];gpu=int(r['requested_GPU']);site=r['AIDC_site'];admitted=site in capacities
        require(state==sf.loc[uid,'state_at_issue'],'STATE_DRIFT')
        seconds=float(r['safe_duration_seconds']);slots=int(r['safe_duration_slots'])
        require(seconds>0 and math.ceil(seconds/900)==slots and r['end_slot']-r['start_slot']==slots,'FULL_DURATION_IDENTITY')
        protected=r['qos'] not in ('normal','standby')
        key=cohort_key(r['qos'],r['partition'],gpu,r['requested_walltime_seconds'],nodes[uid]);cohort=stats.get(key)
        ts,budget,reason=t2(state,protected,cohort,admitted=admitted)
        elapsed=float((ISSUE-sf.loc[uid,'known_running_start']).total_seconds()) if state=='RUNNING' else None
        if state=='RUNNING':
            require(elapsed>=0 and r['duration_authority']=='REQUESTED_REMAINING','RUNNING_SERVICE_AUTHORITY')
            require(abs(max(0,float(r['requested_walltime_seconds'])-elapsed)-seconds)<1e-6,'EXACT_REMAINING_IDENTITY')
        compatible=tuple(s for s in capacities if gpu<=capacities[s] and any(p['aidc_id']==s and gpu<=p['compatibility_GPU_limit'] for p in racks))
        ps=admitted and state=='PENDING' and len(compatible)>1
        mg=False
        if admitted and len(compatible)>1:
            j=Job(uid,state,0,0,int(r['start_slot']),site,slots,gpu,qos=r['qos'],initial_sites=compatible,checkpoint_authorized=True,
                elapsed_seconds=elapsed,duration_authority=r['duration_authority'])
            mg=any(24<=cp<118 and cp<j.reference_start+slots for cp,_ in checkpoint_records(j,j.reference_start,min(j.reference_start+slots,120)))
        # Unassigned legacy pre-D00 remaining service stays unresolved/off-feeder,
        # not FIX and not deleted. It is not in the source-admitted D-day cohort.
        require(admitted or (state=='RUNNING' and int(r['end_slot'])<=24),'UNASSIGNED_IN_DAY_JOB')
        result.append(dict(job_uid=uid,state=state,known_at_issue=True,issue_time=ISSUE.isoformat(),submit_time=sf.loc[uid,'submit_time'].isoformat(),
            current_physical_occupancy=physical_occupancy(state,gpu),current_site_if_running=site if state=='RUNNING' and admitted else None,
            planning_eligible=admitted,planning_site=site,reference_start_if_authorized=int(r['start_slot']),reference_end=int(r['end_slot']),
            exact_service_seconds=seconds,remaining_service_seconds=seconds if state=='RUNNING' else None,elapsed_seconds=elapsed,
            full_requested_seconds=float(r['requested_walltime_seconds']),service_slots=slots,GPU_gang=gpu,rack=r['Rack_label'],
            duration_authority=r['duration_authority'],source_snapshot_sha=sr['sha256'],reference_sha=ref['sha256'],
            cohort=key,cohort_N=cohort['N'] if cohort else 0,Q25_seconds=cohort['Q25_seconds'] if cohort else None,
            T2_reason=reason,delay_budget_slots=budget,can_timeshift=ts if admitted else None,
            can_prestart_place=ps if admitted else None,can_checkpoint_migrate=mg if admitted else None,
            FLEX=(ts or ps or mg) if admitted else None,FIX=not(ts or ps or mg) if admitted else None,
            full_reservation_GPUh=slots*gpu/4,exact_compute_GPUh=seconds*gpu/3600,
            post_H_reserved_GPUh=max(0,int(r['end_slot'])-120)*gpu/4,
            authority_status='NATIVE_KNOWN_CASE_STUDY_AUTHORITY' if admitted else 'UNRESOLVED_SITE_PRE_D00_RESIDUAL_PRESERVED_EXTERNAL_LEDGER',
            mask_scope='SOURCE_AUTHORIZED_CANDIDATE_CAPABILITY_NOT_GLOBAL_FEASIBILITY_WITNESS',prior_PENDING_reservation_is_physical=False))
    csv('MAY01_JOB_STATE_LEDGER.csv',result);csv('MAY01_TIMESHIFT_CAPABILITY.csv',[{k:r[k] for k in ('job_uid','state','planning_eligible','cohort','cohort_N','Q25_seconds','delay_budget_slots','can_timeshift','T2_reason','full_reservation_GPUh')} for r in result])
    active=[r for r in result if r['planning_eligible']];den=sum(r['full_reservation_GPUh'] for r in active)
    overlap=[]
    masks={'TS':lambda r:r['can_timeshift'],'PS':lambda r:r['can_prestart_place'],'MG':lambda r:r['can_checkpoint_migrate'],
        'TS_ONLY':lambda r:r['can_timeshift'] and not r['can_prestart_place'] and not r['can_checkpoint_migrate'],
        'PS_ONLY':lambda r:r['can_prestart_place'] and not r['can_timeshift'] and not r['can_checkpoint_migrate'],
        'MG_ONLY':lambda r:r['can_checkpoint_migrate'] and not r['can_timeshift'] and not r['can_prestart_place'],
        'TS_PS':lambda r:r['can_timeshift'] and r['can_prestart_place'],'TS_MG':lambda r:r['can_timeshift'] and r['can_checkpoint_migrate'],
        'PS_MG':lambda r:r['can_prestart_place'] and r['can_checkpoint_migrate'],'TRIPLE':lambda r:r['can_timeshift'] and r['can_prestart_place'] and r['can_checkpoint_migrate'],
        'FLEX':lambda r:r['FLEX'],'FIX':lambda r:r['FIX']}
    for name,mask in masks.items():
        selected=[r for r in active if mask(r)];mass=sum(r['full_reservation_GPUh'] for r in selected)
        overlap.append(dict(mask=name,jobs=len(selected),job_share=len(selected)/len(active),GPUh=mass,GPUh_share=mass/den,
            denominator_jobs=len(active),denominator_GPUh=den,scope='CANDIDATE_AUTHORITY_NOT_EXECUTABLE_DOMAIN'))
    overlap.append(dict(mask='UNRESOLVED',jobs=len(result)-len(active),job_share=(len(result)-len(active))/len(result),GPUh=sum(r['full_reservation_GPUh'] for r in result if not r['planning_eligible']),denominator_jobs=len(result),scope='ALL_ISSUE_RECORDS'))
    csv('MAY01_CAPABILITY_OVERLAP.csv',overlap)
    dump('MAY01_TIMESHIFT_SUMMARY.json',dict(rule=RULE,all_issue_records=len(result),source_admitted_jobs=len(active),unresolved=len(result)-len(active),
        TS_jobs=sum(r['can_timeshift'] for r in active),TS_job_share=overlap[0]['job_share'],TS_GPUh_share=overlap[0]['GPUh_share'],
        uses_May_outcomes=False,cohort_backoff=False,target_share=None,standby_shortcut_removed=True))
    dump('T2_Q25_FINAL_RULE.json',dict(rule=RULE,status='FROZEN_BY_EXPLICIT_USER_DECISION',frozen_at=datetime.now(timezone.utc).isoformat(),
        statistical_freeze=stats_record,train_membership=record(WORK/'v42_flexibility_pr/docs/v42_aidc_workload_flexibility/TRAIN_MEMBERSHIP.csv.gz','PR75 TRAIN membership','historical queue observations',period='before 2025-01-01'),
        cohort_dimensions=DIMS,minimum_N=100,minimum_Q25_seconds=900,delay_budget_seconds='floor(Q25/900)*900',
        protected_and_RUNNING_timeshift=False,standby_exception=False,semantic='TRACE_DERIVED_CONSERVATIVE_DELAY_PROXY',SLA=False,May_outcomes_used=False))
    reconciliation=[]
    for s,cap in capacities.items():
        group=[r for r in active if r['planning_site']==s];run=sum(r['GPU_gang'] for r in group if r['state']=='RUNNING')
        for t in range(max(r['reference_end'] for r in group)):
            scheduled=sum(r['GPU_gang'] for r in group if r['reference_start_if_authorized']<=t<r['reference_end'])
            reconciliation.append(dict(site=s,slot_issue_origin=t,site_capacity=cap,current_RUNNING_GPU=run,current_PENDING_GPU=0,
                selected_reference_future_reservation_GPU=scheduled,reservation_feasible=scheduled<=cap,current_physical_feasible=run<=cap,
                physical_occupancy_is_not_future_reservation=True))
    require(all(r['reservation_feasible'] and r['current_physical_feasible'] for r in reconciliation),'KNOWN_REFERENCE_CAPACITY')
    csv('MAY01_GPU_CAPACITY_RECONCILIATION.csv',reconciliation)
    return result,ref


def native_coefficients(certificate):
    outputs=certificate['outputs'];arrays={}
    for key in ('voltage','current','planning_coefficients','transformer_coefficients'):
        row=outputs[key];record(row['path'],'IEEE123 May01 '+key,'kW,kvar,pu,pu squared',expected=row['sha256'])
        with np.load(row['path'],allow_pickle=False) as z:arrays[key]={k:z[k].copy() for k in z.files}
    v=arrays['voltage'];p=arrays['planning_coefficients'];tx=arrays['transformer_coefficients'];branches=list(map(str,p['branch_names']))
    require(str(v['operating_day'])==DAY and v['anchor_control'].shape==(96,60),'GRID_NATIVE_AXIS')
    require(np.array_equal(p['branch_names'],v['branch_names']),'GRID_BRANCH_AXIS')
    ids=[i for i,s in enumerate(branches) if s.startswith('transformer.')]
    require(len(ids)==len(tx['ratings']),'TRANSFORMER_AXIS')
    ratings=[None]*len(branches)
    for i,rate in zip(ids,tx['ratings']):ratings[i]=float(rate)
    coefficients=[]
    fields=('voltage_constant','voltage_matrix','current_constant','current_matrix','flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix','branch_limits')
    for t in range(96):coefficients.append(SimpleNamespace(**{f:p[f][t] for f in fields},slot=t,
        control_names=tuple(map(str,v['control_names'])),branch_names=tuple(branches),transformer_ratings=tuple(ratings),
        anchor=v['anchor_control'][t],coefficient_sha256=outputs['planning_coefficients']['sha256']))
    from v42_thermal.planning import bind_coefficient
    # Preserve every archived cache byte. Only normalized transformer-current
    # constants/gradients change; voltage, line and transformer-kVA rows do not.
    return [bind_coefficient(c,arrays['current']['rating_a']) for c in coefficients]


def main():
    OUT.mkdir(exist_ok=True);LOCAL.mkdir(exist_ok=True)
    record(OUT/'PREREGISTRATION.json','User-authorized computational protocol',period='current implementation freeze')
    reaudits()
    caproot=Path('C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v41r2_780gpu_capacity_rebase')
    cap=read(caproot/'V41R2_780GPU_CAPACITY_AUTHORITY.json');rack=read(caproot/'V41R2_LOGICAL_RACK_AUTHORITY.json')
    for name in ('V41R2_780GPU_CAPACITY_AUTHORITY.json','V41R2_LOGICAL_RACK_AUTHORITY.json'):record(caproot/name,'V41R2 native whole-gang capacity','GPU',period='static 780-GPU case study')
    capacities=cap['site_capacity'];require(sum(capacities.values())==780 and not rack['gang_splitting_allowed'],'CAPACITY_AUTHORITY')
    jobs,reference=job_ledger(capacities,rack['logical_Rack_pools'])
    certpath=NATIVE/'frozen_artifacts/v41r4_may/e/20250501/V41_ELECTRICAL_CERTIFICATE.json';cert=read(certpath)
    record(certpath,'Frozen IEEE123 electrical generation certificate')
    inputs=cert['input_identity']['identity']['inputs'];require(inputs['day']==DAY and inputs['V41R4_FINAL_DATE_BINDING']['alpha_BG']==1.15,'SAME_DAY_SCALE')
    coefficients=native_coefficients(cert)
    # Freeze transitive physical inputs. Old generation source is provenance,
    # not imported as a generator, and no compatibility assertion is bypassed.
    physical_keys=('OpenDSS_master','PCC_mapping','service_PCC_mapping','weather','demand','PV','feeder_manifest','line_ratings','transformer_ratings','native_controls','background_mapping','AIDC_power_C1')
    missing=[];recovered=[]
    recovery_file=LOCAL/'recovery_candidates.txt'
    candidates=recovery_file.read_text(encoding='utf-8-sig').splitlines() if recovery_file.exists() else []
    def walk(v,role):
        if isinstance(v,dict):
            if 'path' in v and 'sha256' in v:
                try:record(v['path'],role,expected=v['sha256'])
                except (FileNotFoundError,ValueError) as e:
                    matches=[Path(p) for p in candidates if Path(p).name==Path(v['path']).name and Path(p).is_file() and sha(p)==v['sha256']]
                    if matches:
                        found=record(matches[0],role,expected=v['sha256']);recovered.append(dict(original=v['path'],resolved=found,byte_identical=True))
                    else:missing.append(dict(role=role,path=v['path'],reason=str(e)))
            else:
                for item in v.values():walk(item,role)
        elif isinstance(v,list):
            for item in v:walk(item,role)
    for k in physical_keys:walk(inputs[k],k)
    dump('EXACT_SOURCE_PATH_RECOVERY.json',dict(recovered=recovered,missing=missing,source_bytes_changed=False))
    traffic=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/cache/v37_may_locked_final/traffic/shared/traffic')/DAY
    route_path=traffic/'ROUTE_TABLE.json.gz';route=read_route=json.loads(gzip.decompress(route_path.read_bytes()))
    with np.load(traffic/'TRAFFIC_FORECAST.npz') as z:meta=json.loads(str(z['metadata']))
    require(meta['forecast_day']==DAY and meta['causality_pass'] and meta['future_actual_read_count']==0 and pd.Timestamp(meta['max_input_timestamp'])<=ISSUE,'TRAFFIC_CAUSALITY')
    require(all(r['traffic_forecast_sha']==meta['bundle_sha'] for r in route['routes']),'ROUTE_FORECAST_IDENTITY')
    record(route_path,'All 96x24x24 frozen traffic route choices','seconds,kWh');record(traffic/'TRAFFIC_FORECAST.npz','D-1 native traffic forecast','seconds')
    for p in ('dayahead/mess_physics.py','dayahead/v33m/mess_mobility_milp.py','dayahead/v35/execution.py','pfr/slow_fast.py','dayahead/v38/authority.py','pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json'):
        record(NATIVE/p,'Frozen MESS/WAN equation or case-study authority',period='static reused by May01 native implementation')
    sys.path.insert(0,str(NATIVE))
    from dayahead.v38.authority import load_wan_authority
    wan=load_wan_authority(NATIVE)
    require(wan.historical.maximum_active_transfers==1,'WAN_CONCURRENCY')
    wan_data=dict(maximum_active_transfers=1,bytes_per_gpu=wan.payload_bytes(1),
        paths=[dict(source=s,destination=d,links=wan.path(s,d)) for s in capacities for d in capacities if s!=d],
        link_capacity_bytes_15min=wan.link_capacity_bytes_15min)
    ccpath=WORK/'v42_integrated_pr/docs/v42_final/AGGREGATE_BINDING.json';cc=read(ccpath)['interface'];record(ccpath,'Prior V42 C0 adapter lineage')
    for role in ('prediction','ledger','selection'):record(cc[role]['path'],'C0 '+role,'GPUh per target hour' if role=='prediction' else 'metadata',expected=cc[role]['sha256'])
    # Project only day/index and issue-time identity. Do not open label/runtime
    # columns of the historical evaluation ledger.
    days=pd.read_csv(cc['ledger']['path'],usecols=['target_day','issue_time']);indices=days.index[days.target_day.eq(DAY)]
    require(len(indices)==1 and pd.Timestamp(days.loc[indices[0],'issue_time'])==ISSUE,'C0_DAY_AXIS')
    with np.load(cc['prediction']['path'],allow_pickle=False) as z:q=z['q'][int(indices[0])].copy()
    require(q.shape==(24,2) and np.isfinite(q).all() and np.all(q[:,1]>=q[:,0]),'C0_QUANTILE_AXIS')
    dump('MAY01_CC4_P2_BINDING.json',dict(status='BOUND_USER_AUTHORIZED_C0',model=cc['model'],selected_baseline='T0_B0_C0',
        prediction_index=int(indices[0]),issue_time=ISSUE.isoformat(),Q50=q[:,0].tolist(),Q90=q[:,1].tolist(),
        nominal='Q50_GPUh_DIVIDED_BY_SAME_ONE_HOUR_SUPPORT',uncertainty='Q90_MINUS_Q50',
        unknown_jobs_created=False,aggregate_shift=False,known_service_slack=False,
        training_calls=0,semantic_ML_merged=False,artifact_freeze_wall_time=read(cc['selection']['path'])['time'],
        experiment_is_retrospective=True,historically_deployed_model_claim=False))
    bundle=dict(schema='V42_MAY01_IEEE123_NATIVE_INPUT_BUNDLE',day=DAY,issue_time=ISSUE.isoformat(),role='DEVELOPMENT_NATIVE_COMPUTATIONAL_CANARY',
        network='IEEE123',alpha_BG=1.15,reference=reference,capacities=capacities,racks=rack['logical_Rack_pools'],
        known_population=jobs,electrical_certificate=record(certpath,'Native IEEE123 frozen coefficient source'),grid_outputs=cert['outputs'],
        initial_MESS_sites={'MESS01':'STA01','MESS02':'STA12','MESS03':'STA08','MESS04':'STA06'},
        battery=dict(minimum=440.,maximum=1080.,initial=760.,terminal=760.,p_limit=300.,pcs_kva=400.,eta_charge=.95,eta_discharge=.95,dt_hours=.25),
        route_table=record(route_path,'May01 route table','seconds,kWh'),traffic_forecast_sha=meta['bundle_sha'],WAN=wan_data,
        C0_Q50=q[:,0].tolist(),C0_Q90=q[:,1].tolist(),RUNTIME_PROVIDER_READY=False,unknown_arrival_actions=False,
        response_kernel_required_before_planning=False,unresolved_transitive_physical_inputs=missing,
        source_versions='May01 frozen V41R4 independent-day native known reference; PR79 historical counterfactual mapping not merged or used to rewrite RUNNING sites')
    dump('MAY01_NATIVE_INPUT_BUNDLE.json',bundle)
    dump('MAY01_GRID_BINDING_AUDIT.json',dict(status='BOUND_FROZEN_NUMERIC_COEFFICIENTS' if not missing else 'PARTIAL_TRANSITIVE_INPUT_AUDIT',
        network='IEEE123',day=DAY,slots=96,controls=60,branch_phases=len(coefficients[0].branch_names),
        voltage_lower=voltage_for(Stage.A1).lower_pu,voltage_upper=voltage_for(Stage.A1).upper_pu,rho_upper=1,alpha_BG=1.15,coefficient_sha=cert['outputs']['planning_coefficients']['sha256'],
        post_H_electrical_claim=False,synthetic_coefficients=False,stale_response_kernel_used=False,
        hard_constraints=['voltage','line thermal','transformer current','transformer kVA'],missing_transitive=missing,
        actual_full_A1_grid_rows_built=False,source_binding_is_not_executed_grid_model=True))
    dump('MAY01_NATIVE_INPUT_MANIFEST.json',dict(schema='V42_MAY01_NATIVE_SOURCE_MANIFEST',files=list(SOURCES.values())))
    dump('SOURCE_MANIFEST.json',dict(files=list(SOURCES.values()),future_actual_runtime_decision_reads=0,no_ML_fit=True))
    print(json.dumps(dict(jobs=len(jobs),admitted=sum(r['planning_eligible'] for r in jobs),TS=sum(r['can_timeshift'] is True for r in jobs),
        grid_branches=len(coefficients[0].branch_names),route_records=len(route['routes']),missing=missing),ensure_ascii=False,indent=2))


if __name__=='__main__':main()

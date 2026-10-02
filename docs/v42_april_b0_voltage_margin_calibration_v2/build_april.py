"""Source recovery and 30-day current-V42 input inventory. Never impute GPUs.

Run AFTER the initial audit. Reference/execution cannot start before input PASS.
Actual request and observation tables stay separate from Planning inference.
"""
from collections import Counter
import json
import zipfile
from pathlib import Path
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from .audit import ROOT,OUT,LOCAL,RAW,SNAP,DAYS,CAPACITIES,record,write,table,clean
from v42_final.runtime import FrozenQ50
from v42_final.native_inputs import memory_mib
from v42_final.common import MODEL
from v42_april_b0_v2.contracts import digest
from v42_april_b0_v2.recovery import recover_gpu,reconcile_population,validate_date_axis,positive_integer

RECOVERY='APRIL_V42_SOURCE_RECOVERY/'
BUNDLE='APRIL_V42_INPUT_BUNDLE/'


def iso(value):return pd.Timestamp(value).isoformat()


def main():
    validate_date_axis(DAYS)
    external=json.loads((OUT/RECOVERY/'EXTERNAL_RAW_REJOIN_AUDIT.json').read_text(encoding='utf8'))
    assert external['available_April_source_audit_complete'], 'WHOLE_EXTERNAL_RAW_ROOT_AUDIT_REQUIRED'
    assert external['additional_exact_recoverable_requests']==0, 'NEW_SOURCE_REQUESTS_REQUIRE_INTEGRATION'
    manifest=LOCAL/'runtime_vnext6_callable_total_pr/docs/runtime_vnext8_trace_feature_total/SOURCE_MANIFEST.json'
    original=json.loads(manifest.read_text(encoding='utf8'))['raw']
    assert record(original['path'])['sha256']==original['sha256']
    source_root=Path(original['path']).parents[1]/'NLR_scheduler_authority'
    descriptor=source_root/'07_hpc-oda-commons/src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml'
    docs=[Path(original['path']).parent/'datacard.md',descriptor,source_root/'99_manifest/kestrel_integrity.txt',
          source_root/'06_official_web_docs/NLR_Kestrel_Running.html',source_root/'06_official_web_docs/Slurm_sacct.html']
    mirrors=[Path(original['path']),Path(original['path']).parents[1]/'NLR Kestrel Jobs/esif.hpc.kestrel.job-anon.zip']
    mirror_records=[record(p) for p in mirrors if p.exists()]
    assert all(r['sha256']==original['sha256'] for r in mirror_records)
    request_cols=['id','submit_time','gpus_requested','nodes_req','processors_req','memory_req','wallclock_req',
                  'partition','qos','account_hash','array_pos','submit_line_hash','submit_script_hash']
    event_cols=['id','submit_time','start_time','end_time']
    request_frames=[];event_frames=[];schemas=[];members=[]
    # Only submission-month March/April sources. May member payloads are not read.
    with zipfile.ZipFile(original['path']) as archive:
        for member in archive.namelist():
            if not member.endswith('.parquet') or not any(f'year=2025/month={m}/' in member for m in (3,4)):continue
            members.append(member)
            with archive.open(member) as stream:
                parquet=pq.ParquetFile(stream)
                schemas.append(dict(member=member,rows=parquet.metadata.num_rows,fields=parquet.schema.names,
                                    raw_ReqTRES_present='ReqTRES' in parquet.schema.names,
                                    raw_Slurm_JSONB_present='slurm_data' in parquet.schema.names))
                offset=0
                for batch in parquet.iter_batches(columns=request_cols,batch_size=32768,use_threads=False):
                    f=batch.to_pandas();f.id=f.id.astype(str)
                    f['source_member']=member;f['source_row']=np.arange(offset,offset+len(f));offset+=len(f)
                    request_frames.append(f[f.partition.astype(str).str.contains('h100',case=False,regex=False)])
            # Actual-only observation projection. Never merged into Planning features.
            with archive.open(member) as stream:
                event_frames.append(pq.read_table(stream,columns=event_cols,use_threads=False).to_pandas())
    requests=pd.concat(request_frames,ignore_index=True)
    assert requests.id.is_unique
    requests=requests.set_index('id',drop=False)
    events=pd.concat(event_frames,ignore_index=True);events.id=events.id.astype(str)
    assert events.id.is_unique
    events=events.set_index('id')
    provider=FrozenQ50()
    integrity=json.loads((provider.root/'INTEGRITY.json').read_text(encoding='utf8'))
    write(RECOVERY+'RUNTIME_AUTHORITY.json',dict(PASS=True,model=MODEL,model_files=integrity['files'],
          integrity=record(provider.root/'INTEGRITY.json'),calibration=record(provider.root/'calibration_state.json'),
          available_at=provider.state['day'],max_completion_used=provider.state['max_completion_used'],
          feature_contract=record(ROOT/'v42_final/inference/features.py'),request_projection=request_cols,
          prediction='Total Q50 seconds; remaining=max(Q50-elapsed,0); ceil remaining/900',
          horizon='Q50 total service, LAST_RATE calibrated tail; service not truncated at calendar boundary',
          requested_walltime_role='Frozen predictor feature only; never service authority',
          physical_GPU_imputation=False,fit_calls=0,May_used=False,request_version_history='UNVERIFIED_SOURCE_PROXY_RETAINED'))
    write(RECOVERY+'SOURCE_JOIN_AUDIT.json',dict(archive=original,mirrors=mirror_records,schemas=schemas,
          request_members=members,Planning_projection=request_cols,Actual_observation_projection=event_cols,
          May_members_read=[],sources=[record(p) for p in docs if p.exists()],
          official_catalog='https://data.nlr.gov/submissions/302',official_catalog_current_archive_MD5='8f1d3be1cbe6345ef45e658a783c2aa0',
          official_version_history='One public archive version, matching local immutable archive',
          official_GPU_policy='https://natlabrockies.github.io/HPC/Documentation/Systems/Kestrel/Running/',
          source_priority=['Exact full UID and submission event in immutable archive',
             'Upstream current V42 snapshot and raw daily source, same request event',
             'Hash-identical local mirror and official public dataset version',
             'Schema/descriptor/raw scheduler documentation for uniquely determined request fields'],
          result='Raw gpus_requested is null for initial missing rows; ReqTRES/Slurm JSONB/job steps not exported; scripts/submit lines hashed',
          deterministic_derivation='NOT_UNIQUE: H100 nodes are shareable and explicit GPU request can vary on the same requested node count',
          rejected=['nodes_req*4','gpu_nodes_occupied*4','neighbor/array-parent request','request hash inversion','statistical filling'],
          other_sources='Eagle traces and controlled H100 power benchmarks have different identities/workloads; not Kestrel April request authority',
          external_raw_audit=record(OUT/RECOVERY/'EXTERNAL_RAW_REJOIN_AUDIT.json'),
          audit_scope='Whole user-specified external raw-data root, all archive/schema candidates, current snapshot/daily sources and official public upstream. Private NLR raw Slurm request database is not accessible; no contact sent.'))
    missing=[];recovered=[];gates=[];day_records=[];initial_counts=Counter();new_missing=Counter()
    for day in DAYS:
        folder='DAY_'+day.replace('-','')
        initial=json.loads((OUT/folder/'B0_REFERENCE_SCHEDULE.json').read_text(encoding='utf8'))
        known=initial['population'];issue=pd.Timestamp(day+'T00:00:00+10:00')-pd.Timedelta(hours=6)
        start=pd.Timestamp(day+'T00:00:00+10:00');end=start+pd.Timedelta(days=1)
        authority=json.loads((OUT/folder/'INPUT_AUTHORITY.json').read_text(encoding='utf8'))
        raw_daily=pd.read_parquet(RAW/day/'kestrel_realized_jobs.parquet',columns=['id','submit_time','partition','gpus_requested'])
        initial_actual=raw_daily[raw_daily.partition.astype(str).str.contains('h100',case=False,regex=False)
                      &raw_daily.gpus_requested.isna()&(raw_daily.submit_time>=start)&(raw_daily.submit_time<end)]
        # Complete archive arrivals from after D-1 cutoff through D-day end.
        arrivals=requests[(requests.submit_time>issue)&(requests.submit_time<end)].copy()
        arrival_metadata=pd.DataFrame(dict(num_gpus_req=arrivals.gpus_requested.to_numpy(),num_nodes_req=arrivals.nodes_req.to_numpy(),
          num_cores_req=arrivals.processors_req.to_numpy(),requested_memory_mib=arrivals.memory_req.map(memory_mib).to_numpy(),
          requested_seconds=arrivals.wallclock_req.dt.total_seconds().to_numpy(),array_index=arrivals.array_pos.to_numpy(),
          account=arrivals.account_hash.to_numpy(),qos=arrivals.qos.to_numpy(),partition=arrivals.partition.to_numpy()))
        q=provider.predict_batch(arrival_metadata.to_dict('records'),submit_times=list(arrivals.submit_time),event_time=end) if len(arrivals) else []
        actual_rows=[]
        for i,r in enumerate(arrivals.to_dict('records')):
            uid=r['id'];observed=events.loc[uid]
            observed_start=iso(observed.start_time) if pd.notna(observed.start_time) and observed.start_time<end else None
            observed_end=iso(observed.end_time) if pd.notna(observed.end_time) and observed.end_time<=end else None
            actual_rows.append(dict(job_uid=uid,submit_time=iso(r['submit_time']),GPU_gang=int(r['gpus_requested']) if positive_integer(r['gpus_requested']) else None,
               service_slots=int(np.ceil(float(q[i])/900)),Q50_total_seconds=float(q[i]),runtime_authority=MODEL,
               start_observed_by_day_end=observed_start,end_observed_by_day_end=observed_end,
               source_member=r['source_member'],source_row=int(r['source_row']),source_sha256=original['sha256'],
               arrival_period='POST_ISSUE_PRE_DAY_CARRYIN' if pd.Timestamp(r['submit_time'])<start else 'DDAY_ARRIVAL'))
        known_ids={j['job_uid'] for j in known};actual_ids={j['job_uid'] for j in actual_rows}
        assert not known_ids.intersection(actual_ids),'PLANNING_FUTURE_ARRIVAL_LEAK'
        old_known=[dict(j) for j in known]
        def recovery_row(day,role,j,raw_path,event_time):
            uid=j['job_uid'];candidates=[]
            if uid in requests.index:
                raw=requests.loc[uid]
                source_event=digest(dict(job_uid=uid,submit_time=iso(raw.submit_time),submit_line_hash=raw.submit_line_hash))
                candidates=[dict(job_uid=uid,submit_time=iso(raw.submit_time),gpus_requested=clean(raw.gpus_requested),
                   nodes_req=clean(raw.nodes_req),source_event_identity=source_event,
                   source_member=raw.source_member,source_row=int(raw.source_row))]
            else:raw=None;source_event=None
            row=dict(day=day,role=role,job_uid=uid,source_event_identity=source_event,raw_source_path=raw_path,
                raw_archive_path=original['path'],source_sha256=original['sha256'],submission_timestamp=j['submit_time'],
                state=j.get('state_at_D1_cutoff','ARRIVAL_OBSERVED'),requested_nodes=None if raw is None else clean(raw.nodes_req),
                requested_CPUs=None if raw is None else clean(raw.processors_req),requested_memory=None if raw is None else raw.memory_req,
                GPU_type='H100_PARTITION_SOURCE',GPU_request=None,runtime_authority=MODEL,
                requested_walltime_seconds=None if raw is None else float(raw.wallclock_req.total_seconds()),
                Q50_total_seconds=j['Q50_total_seconds'],service_slots=j['service_slots'],
                matching_candidate_source_records=candidates)
            result=recover_gpu(dict(job_uid=uid,submit_time=j['submit_time'],source_event_identity=source_event),candidates,event_time=iso(event_time))
            row.update(recovery_status=result['status'],recovery_method=result['method'],candidate_count=result['candidate_count'],
                       ambiguity_count=result['ambiguity_count'],recovered_GPU_request=result['GPU_gang'])
            return row,result
        for j in known:
            if j['GPU_gang'] is None:
                row,result=recovery_row(day,'KNOWN_D1',j,str(SNAP/day/'D1_AIDC_SNAPSHOT.parquet'),issue)
                missing.append(row);recovered.append(row);initial_counts['known']+=1
                if result['status']=='SOURCE_RECOVERED':j['GPU_gang']=result['GPU_gang']
        # Re-audit exactly the original Actual missing rows, in addition to the
        # fuller post-issue archive population. No initial row can disappear.
        by_actual={j['job_uid']:j for j in actual_rows}
        initial_actual_ids=set(initial_actual.id.astype(str))
        assert initial_actual_ids <= set(by_actual),'INITIAL_ACTUAL_MISSING_ROW_DROPPED'
        for uid in sorted(initial_actual_ids):
            row,result=recovery_row(day,'INITIAL_DDAY_ACTUAL',by_actual[uid],str(RAW/day/'kestrel_realized_jobs.parquet'),pd.Timestamp(by_actual[uid]['submit_time']))
            missing.append(row);recovered.append(row);initial_counts['actual']+=1
        for j in actual_rows:
            if j['GPU_gang'] is None:
                row,result=recovery_row(day,'COMPLETE_ARCHIVE_POST_ISSUE_ACTUAL',j,original['path'],pd.Timestamp(j['submit_time']))
                new_missing[day]+=1
                if j['job_uid'] not in initial_actual_ids:recovered.append(row)
                if result['status']=='SOURCE_RECOVERED':j['GPU_gang']=result['GPU_gang']
        reconciliation=reconcile_population(old_known,known)
        assert all(pd.Timestamp(j['submit_time'])<=issue for j in known)
        assert len(actual_ids)==len(actual_rows)
        known_complete=all(positive_integer(j['GPU_gang']) for j in known)
        actual_gpu_complete=all(positive_integer(j['GPU_gang']) for j in actual_rows)
        compatibility={j['job_uid']:[s for s,c in CAPACITIES.items() if j['GPU_gang'] is not None and j['GPU_gang']<=c] for j in known}
        actual_compatibility={j['job_uid']:[s for s,c in CAPACITIES.items() if positive_integer(j['GPU_gang']) and j['GPU_gang']<=c] for j in actual_rows}
        carryin=[]
        for j in known:
            e=events.loc[j['job_uid']]
            carryin.append(dict(job_uid=j['job_uid'],GPU_gang=j['GPU_gang'],
                start_observed_by_day_end=iso(e.start_time) if pd.notna(e.start_time) and e.start_time<end else None,
                end_observed_by_day_end=iso(e.end_time) if pd.notna(e.end_time) and e.end_time<=end else None,
                observations_role='ACTUAL_ONLY_NEVER_PLANNING_FEATURE'))
        gate=dict(day=day,known_workload_complete=known_complete,actual_workload_complete=actual_gpu_complete and known_complete,
          GPU_authority_complete=known_complete and actual_gpu_complete,runtime_authority_complete=True,
          compatibility_complete=all(compatibility.values()) and all(actual_compatibility.values()),capacity_complete=True,
          load_forecast_complete=authority['forecast_causal'],load_actual_complete=authority['actual_grid_96_finite_aligned'],
          PV_forecast_complete=authority['forecast_causal'],PV_actual_complete=authority['actual_grid_96_finite_aligned'],
          feeder_authority_complete=False,D1_causal_boundary_PASS=None,submission_cutoff_PASS=True,
          request_version_causality='UNVERIFIED_SOURCE_PROXY',no_synthetic_fill=True,
          known_jobs=len(known),actual_post_issue_jobs=len(actual_rows),actual_DDAY_arrivals=sum(j['arrival_period']=='DDAY_ARRIVAL' for j in actual_rows),
          missing_known_GPU=sum(j['GPU_gang'] is None for j in known),missing_actual_GPU=sum(j['GPU_gang'] is None for j in actual_rows),
          PASS=False,scientific_execution='NOT_RUN')
        # Downstream feeder/electrical binding has not been executed through
        # an incomplete physical-workload gate. Raw topology availability does
        # not attest a complete April planning/Actual electrical adapter.
        gate['reason']='SOURCE_FIELD_ABSENT: exact UID/submission request GPU null; no unique derivation. April feeder/electrical adapter binding pending upstream workload authority.'
        assert not gate['GPU_authority_complete'],'READY_INPUT_REQUIRES_REAL_REFERENCE_AND_PHYSICAL_ADAPTER'
        planning=dict(day=day,status='INCOMPLETE_NONEXECUTABLE',issue_time=iso(issue),known_population=known,
          runtime_authority=MODEL,runtime_integrity_sha256=record(provider.root/'INTEGRITY.json')['sha256'],
          capacities=CAPACITIES,rack_compatibility={s:[c] for s,c in CAPACITIES.items()},compatible_sites=compatibility,
          input_sources={k:v for k,v in authority['files'].items() if k in ('aemo_forecast.json','gfs_d1_weather.parquet')},
          forecast=json.loads((RAW/day/'aemo_forecast.json').read_text(encoding='utf8')),
          same_initial_state_authority='MESS_OFF_P_Q_MOVEMENT_ZERO; AIDC observed RUNNING state retained',
          future_arrival_IDs_in_Planning=False,CC4_anonymous_forecast_binding='PENDING_CURRENT_V42_COMPLETE_BUNDLE',
          mass_reconciliation=reconciliation,input_gate_PASS=False)
        actual=dict(day=day,status='INCOMPLETE_NONEXECUTABLE',actual_as_of=iso(end),post_issue_arrivals=actual_rows,
          observed_known_episodes=carryin,known_GPU_request_map={j['job_uid']:j['GPU_gang'] for j in known},
          runtime_authority=MODEL,source_derived_episode_projection=event_cols,compatible_sites=actual_compatibility,
          realized_load_PV_source=authority['files']['aemo_actual.parquet'],actual_occupancy_reconstructed=False,
          physical_arrays_generated=False,IT_recomputed_from_actual_occupancy=None,DayAhead_power_arrays_copied=None,
          future_source_start_end_values_exported=False,source_May_completion_times_used=False,input_gate_PASS=False)
        write(BUNDLE+folder+'/PLANNING_INPUT_BUNDLE.json',planning)
        write(BUNDLE+folder+'/ACTUAL_INPUT_BUNDLE.json',actual)
        write(BUNDLE+folder+'/SOURCE_PROVENANCE.json',dict(day=day,raw_archive=original,source_members=members,
              snapshot=authority['snapshot'],daily_sources=authority['files'],request_join='full UID + submission event',
              request_version_history_limitation='Source retrospective proxy; original submission-version ledger not exported',
              Planning_observation_columns_used=False,raw_unknown_arrival_ids_exported_to_Planning=False))
        write(BUNDLE+folder+'/INPUT_GATE.json',gate)
        day_records.append(dict(day=day,planning=record(OUT/(BUNDLE+folder+'/PLANNING_INPUT_BUNDLE.json')),
                               actual=record(OUT/(BUNDLE+folder+'/ACTUAL_INPUT_BUNDLE.json')),gate=gate))
        gates.append(gate)
        write('B0/'+folder+'/EXECUTION_STATUS.json',dict(status='NOT_RUN',reason='APRIL_DAY_INPUT_GATE_FAIL',
              input_gate=BUNDLE+folder+'/INPUT_GATE.json',AIDC_PRESENT=True,flexibility_optimization=False,MESS_ACTIVE=False,
              V_PLAN=None,V_DA_AC=None,V_DDAY_AC=None,physical_PASS=None,OpenDSS_calls=0))
    assert initial_counts==Counter(known=5173,actual=16284)
    ledger_columns=list(missing[0])
    table(RECOVERY+'GPU_REQUEST_MISSING_LEDGER.csv',missing,ledger_columns)
    table(RECOVERY+'GPU_REQUEST_RECOVERY_LEDGER.csv',recovered,ledger_columns)
    # Top-level exact requested names, with the same complete evidence.
    table('APRIL_GPU_REQUEST_MISSING_LEDGER.csv',missing,ledger_columns)
    counts=Counter(r['recovery_status'] for r in recovered)
    summary=dict(initial_missing_known=5173,initial_missing_Actual=16284,initial_missing_observations=21457,
       initial_unique_jobs=len({r['job_uid'] for r in missing}),initial_recovered=sum(r['recovery_status']=='SOURCE_RECOVERED' for r in missing),
       initial_unresolved=sum(r['recovery_status']!='SOURCE_RECOVERED' for r in missing),recovery_percent=0.,
       full_archive_post_issue_missing=sum(new_missing.values()),full_archive_missing_by_day=dict(new_missing),
       recovery_ledger_observations=len(recovered),recovery_ledger_unique_jobs=len({r['job_uid'] for r in recovered}),
       unresolved_reasons=dict(counts),unresolved_GPUh=None,
       GPUh_unknown_reason='Missing physical GPU demand; current Q50 seconds alone cannot determine GPUh',
       initial_known_missing_share=5173/29350,full_archive_actual_missing_share=sum(g['missing_actual_GPU'] for g in gates)/sum(g['actual_post_issue_jobs'] for g in gates),
       complete_days=0,target_days=30,source_recovery_attempted=True,arbitrary_fill=False,rows_dropped=0,May_used=False,
       external_raw_audit=external,initial_known_recovered=0,initial_known_unresolved=5173,
       initial_Actual_recovered=0,initial_Actual_unresolved=16284)
    write(RECOVERY+'GPU_REQUEST_RECOVERY_SUMMARY.json',summary)
    write('APRIL_GPU_REQUEST_RECOVERY_SUMMARY.json',summary)
    table(BUNDLE+'APRIL_DAY_INPUT_GATE.csv',gates,list(gates[0]))
    write(BUNDLE+'APRIL_INPUT_MANIFEST.json',dict(status='INCOMPLETE_NONEXECUTABLE',complete_days=0,target_days=30,
       date_axis=DAYS,days=day_records,raw_grid_forecast_actual_dates=30,current_runtime_PASS=True,
       input_gate_precedes_reference_and_OpenDSS=True,reference_ready_days=0,scientific_execution_days=0))
    rule=json.loads((OUT/'V42_COMMON_REFERENCE_SCHEDULE_AUTHORITY.json').read_text(encoding='utf8'))
    write('REFERENCE/V42_COMMON_REFERENCE_SCHEDULE_AUTHORITY.json',dict(**rule,input_gate_required=True))
    table('REFERENCE/V42_COMMON_REFERENCE_SCHEDULE.csv',[],['day','job_uid','state_at_D1_cutoff','reference_site','reference_start','service_slots','GPU_gang','runtime_authority','site_authority_source','start_authority_source','fallback_used','queue_rule','compatible_sites'])
    write('REFERENCE/REFERENCE_MAPPING_AUDIT.json',dict(status='NOT_GENERATED_INPUT_GATE_FAIL',accepted_reference_days=0,
        initial_diagnostic_only='Root DAY_*/B0_REFERENCE_SCHEDULE.json and root V42_COMMON_REFERENCE_SCHEDULE.csv are initial mapping diagnostics, not accepted executable common references.',
        old_known_only_complete_days_not_selected=[r['day'] for r in json.loads((OUT/'V42_REFERENCE_MAPPING_AUDIT.json').read_text(encoding='utf8'))['days'] if r['full_reference_ready']]))
    table('APRIL_DATE_FREEZE.csv',[dict(day=g['day'],usable=False,excluded=True,reason=g['reason'],voltage_outcomes_read=0) for g in gates],
          ['day','usable','excluded','reason','voltage_outcomes_read'])
    flags=json.loads((OUT/'FINAL_FLAGS.json').read_text(encoding='utf8'));flags.update(COMMON_REFERENCE_GENERATED_DAYS=0,
          INITIAL_REFERENCE_DIAGNOSTIC_DAYS=30,APRIL_INPUT_BUNDLE_COMPLETE_DAYS=0)
    write('FINAL_FLAGS.json',flags)
    write('FINAL_VERDICT.json',dict(verdict='BLOCKED_AFTER_SOURCE_BACKED_RECOVERY_AUDIT',calibration_complete=False,
          input_bundle_complete_days=0,current_runtime_PASS=True,common_reference_generated=False,
          initial_missing_known=5173,initial_missing_Actual=16284,recovered=summary['initial_recovered'],unresolved=summary['initial_unresolved'],
          exact_reason='SOURCE_FIELD_ABSENT: full UID/submission joins all match but GPU request is null in upstream immutable public export. ReqTRES/Slurm JSONB/job steps are not available; shareable H100 nodes do not uniquely determine request GPU.',
          source_recovery_complete_for_available_sources=True,external_raw_audit=record(OUT/RECOVERY/'EXTERNAL_RAW_REJOIN_AUDIT.json'),private_upstream_request_export_needed=True,
          mapping_file_absence_is_STOP=False,FINAL_MARGIN_ACCEPTED=False,B1_B2_B3_May_M1='NOT_RUN'))
    write('CALIBRATION/STATUS.json',dict(status='NOT_ESTIMABLE_INPUT_GATE_FAIL',primary_band=[.95,1.05],
          statistics_sources=['../APRIL_POINTWISE_QUANTILES.csv','../APRIL_DAY_WORST_QUANTILES.csv','../CURRENT_005_MARGIN_COVERAGE.json'],
          samples=0,pointwise_Q95_Q99=None,day_worst_Q95_Q99=None,candidate_band=None,FINAL_MARGIN_ACCEPTED=False))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()

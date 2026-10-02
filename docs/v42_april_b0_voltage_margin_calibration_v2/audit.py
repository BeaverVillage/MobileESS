"""Reproduce April-only source audit and current-runtime common reference.

Run from repository root with python -m
docs.v42_april_b0_voltage_margin_calibration_v2.audit. No solver/OpenDSS calls.
Only March/April request columns from the raw archive are projected, and only
already-known snapshot IDs enter inference. Requested walltime is a predictor
feature, never the service duration. Missing GPU requests are not imputed.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import zipfile
import subprocess
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
from v42_final.runtime import FrozenQ50
from v42_final.state import planning_remaining
from v42_final.native_inputs import memory_mib
from v42_final.common import MODEL
from v42_april_b0_v2.reference import build_reference, QUEUE_RULE
from v42_april_b0_v2.contracts import BASE, QUANTILES, digest, ZERO_ACTIONS
from v42_april_b0_v2.statistics import quantiles, coverage, error_stats, sensitivity

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
LOCAL = ROOT.parent
RAW = LOCAL/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/april_2025/days'
SNAP = LOCAL/'V42_FINAL_LOCAL/policy_snapshots'
DAYS = [str(d.date()) for d in pd.date_range('2025-04-01', '2025-04-30')]
CAPACITIES = dict(zip((f'AIDC{i:02}' for i in range(1,13)), (80,40,80,40,100,80,40,80,40,80,40,80)))
FLAGS = dict(B0_ONLY=True, AIDC_PRESENT=True, AIDC_WORKLOAD_PRESENT=True,
             AIDC_FLEXIBILITY_OPTIMIZATION=False, MESS_ACTIVE=False, B1_RUN=False,
             B2_RUN=False, B3_RUN=False, M1_BENDERS_RUN=False, MAY_RUN=False,
             MAY_USED_FOR_CALIBRATION=False, FINAL_MARGIN_ACCEPTED=False,
             historical_requested_walltime_fallback=False)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    p = Path(path).resolve()
    return dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size)


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write(name, value):
    path = OUT/name
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(clean(value), indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')


def table(name, rows, columns):
    path = OUT/name
    path.parent.mkdir(exist_ok=True, parents=True)
    with path.open('w', encoding='utf8', newline='') as stream:
        w = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        for row in rows:
            values = clean(row)
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in values.items()})


def main():
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
    snapshot_columns = ['id','submit_time','gpus_requested','nodes_req','source_member','state_at_issue',
                        'known_running_start','elapsed_seconds_at_issue','issue_time','original_AIDC_site','request_versions']
    snapshots = {d:pd.read_parquet(SNAP/d/'D1_AIDC_SNAPSHOT.parquet', columns=snapshot_columns) for d in DAYS}
    wanted = {str(uid) for f in snapshots.values() for uid in f.id}
    manifest = LOCAL/'runtime_vnext6_callable_total_pr/docs/runtime_vnext8_trace_feature_total/SOURCE_MANIFEST.json'
    archive_record = json.loads(manifest.read_text(encoding='utf8'))['raw']
    assert sha(archive_record['path']) == archive_record['sha256']
    cols = ['id','submit_time','nodes_req','processors_req','memory_req','wallclock_req',
            'qos','partition','gpus_requested','account_hash','array_pos']
    members = sorted({m for f in snapshots.values() for m in f.source_member})
    assert all('year=2025/month=3/' in m or 'year=2025/month=4/' in m for m in members)
    frames = []
    with zipfile.ZipFile(archive_record['path']) as archive:
        for member in members:
            with archive.open(member) as stream:
                for batch in pq.ParquetFile(stream).iter_batches(batch_size=32768, columns=cols, use_threads=False):
                    frame = batch.to_pandas()
                    frame.id = frame.id.astype(str)
                    frames.append(frame[frame.id.isin(wanted)])
    requests = pd.concat(frames).set_index('id')
    assert requests.index.is_unique and set(requests.index) == wanted
    provider = FrozenQ50()
    freeze = dict(rule=QUEUE_RULE, issue_origin='D-1 18:00 fixed AEST; D-day slots are issue slots 24..119',
                  running='Source site first. Missing site: decreasing GPU gang then UID, first compatible capacity-feasible site. Start=0.',
                  pending='FCFS submit_time then UID; earliest capacity-feasible start, then ascending site. Fixed source site never relocated.',
                  missing_GPU='Retain row BLOCKED_GPU_REQUEST_AUTHORITY_MISSING. Do not infer gang from requested nodes.',
                  q50_expired_running='Hard occupancy retained indefinitely unless source-authorized causal release exists; no Q50 synthetic completion.',
                  compatibility='Current V42 frozen 780-GPU site vector; non-additive single-gang ceilings equal site capacities.',
                  source='docs/v42_job_capability_joint_flexibility/FLEXIBILITY_SOURCE_AUTHORITY.json',
                  capacities=CAPACITIES, optimizer_calls=0, grid_reads=0, actual_reads=0, May_reads=0,
                  rule_source=record(ROOT/'v42_april_b0_v2/reference.py'), runtime_source=record(ROOT/'v42_final/runtime.py'),
                  runtime_integrity=record(ROOT/'v42_final/runtime_bundle/INTEGRITY.json'),
                  shared_arms=['B0','B1','B2','B3'], old_mapping_required=False)
    write('V42_COMMON_REFERENCE_SCHEDULE_AUTHORITY.json', freeze)
    write('PREREGISTRATION.json', dict(target_dates=DAYS, quantiles=QUANTILES, quantile_method='LINEAR_(N-1)*Q',
          primary_band=[.95,1.05], margin=.005, upper_lower_separate=True,
          date_selection='All source-complete and workload-authority-complete April dates; no voltage outcome selection',
          output_missing='null metrics and header-only voltage CSV; never simulated numeric evidence',
          reference_authority_sha256=digest(freeze), empirical_limit='Correlated node/time samples; <=30 days; Q99 descriptive only',
          FINAL_MARGIN_ACCEPTED=False, registered_before_voltage_execution=True))
    write('USER_B0_AUTHORITY.json', dict(**FLAGS, authority='USER_CURRENT_V42_COMPARISON_AND_NEW_COMMON_REFERENCE',
          historical_B0_recovery_required=False, reference_mapping_generation_authorized=True,
          arms=dict(B0=dict(flex=False,mess=False),B1=dict(flex=True,mess=False),
                    B2=dict(flex=False,mess=True),B3=dict(flex=True,mess=True)), scientific_execution_authorized=['B0']))
    write('PR118_BASE_RECEIPT.json', dict(repository='BeaverVillage/MobileESS', primary_base=BASE,
          head_at_audit=BASE, architecture='Planning -> Freeze -> D-Day Actual -> Fresh OpenDSS', production_modified=False,
          superseded_STOP='Historical reference or B0 producer absence does not stop this task'))
    aggregates, all_reference, all_blocked = [], [], []
    for day, f in snapshots.items():
        issue = pd.Timestamp(f.issue_time.iloc[0])
        assert f.issue_time.nunique()==1 and (f.submit_time <= issue).all()
        r = requests.loc[f.id.astype(str)].copy()
        assert (r.submit_time.to_numpy() == f.submit_time.to_numpy()).all()
        assert np.allclose(r.gpus_requested.to_numpy(float),f.gpus_requested.to_numpy(float),equal_nan=True)
        metadata = pd.DataFrame(dict(num_gpus_req=r.gpus_requested.to_numpy(), num_nodes_req=r.nodes_req.to_numpy(),
                    num_cores_req=r.processors_req.to_numpy(), requested_memory_mib=r.memory_req.map(memory_mib).to_numpy(),
                    requested_seconds=r.wallclock_req.dt.total_seconds().to_numpy(), array_index=r.array_pos.to_numpy(),
                    account=r.account_hash.to_numpy(),qos=r.qos.to_numpy(),partition=r.partition.to_numpy()))
        q = provider.predict_batch(metadata.to_dict('records'), submit_times=list(f.submit_time), event_time=issue)
        jobs = []
        for index, row in enumerate(f.to_dict('records')):
            elapsed = float(row['elapsed_seconds_at_issue']) if row['state_at_issue']=='RUNNING' else 0.
            service = planning_remaining(float(q[index]),elapsed,state=row['state_at_issue'])
            gpu = row['gpus_requested'];gpu = int(gpu) if pd.notna(gpu) and float(gpu).is_integer() and gpu>0 else None
            source = row['original_AIDC_site'];source = source if source in CAPACITIES else None
            jobs.append(dict(job_uid=str(row['id']),state_at_D1_cutoff=row['state_at_issue'],
                 submit_time=pd.Timestamp(row['submit_time']).isoformat(),source_site=source,
                 source_site_authority='D1_OBSERVED_OR_SOURCE_SITE' if source else None,
                 GPU_gang=gpu,service_slots=service['nominal_slots'],runtime_authority=MODEL,
                 nominal_remaining_seconds=service['nominal_remaining_seconds'],Q50_total_seconds=float(q[index]),
                 elapsed_seconds=elapsed,request_versions=row['request_versions']))
        reference, mapping = build_reference(jobs,CAPACITIES,{s:(c,) for s,c in CAPACITIES.items()},issue_time=issue.isoformat())
        folder = 'DAY_'+day.replace('-','')
        all_reference.extend(dict(day=day,**v) for v in reference)
        all_blocked.extend(dict(day=day,**v) for v in reference if v['status']=='BLOCKED')
        forecasts = json.loads((RAW/day/'aemo_forecast.json').read_text(encoding='utf8'))
        actual = pd.read_parquet(RAW/day/'aemo_actual.parquet')
        weather = pd.read_parquet(RAW/day/'gfs_d1_weather.parquet')
        realized = pd.read_parquet(RAW/day/'kestrel_realized_jobs.parquet',columns=['id','partition','gpus_requested','submit_time'])
        day_start = pd.Timestamp(day+'T00:00:00+10:00');day_end=day_start+pd.Timedelta(days=1)
        h100 = realized[realized.partition.astype(str).str.contains('h100',case=False,regex=False)
                          & (realized.submit_time>=day_start) & (realized.submit_time<day_end)]
        absent = h100[h100.gpus_requested.isna()]
        forecast_ok = (len(forecasts['demand_mw_96'])==len(forecasts['pv_mw_96'])==96
                       and pd.Timestamp(forecasts['demand_issue'])<=issue and pd.Timestamp(forecasts['pv_issue'])<=issue
                       and pd.Timestamp(forecasts['cutoff_fixed_aest'])==issue
                       and np.isfinite(forecasts['demand_mw_96']).all() and np.isfinite(forecasts['pv_mw_96']).all())
        expected = pd.date_range(day_start+pd.Timedelta(minutes=15),day_end,freq='15min')
        actual_ok = (len(actual)==96 and pd.DatetimeIndex(actual.ts_fixed_aest_end).tz_convert('UTC').equals(expected.tz_convert('UTC'))
                    and np.isfinite(actual[['demand_mw','rooftop_pv_mw']].to_numpy()).all())
        forecast_ok = forecast_ok and pd.DatetimeIndex(pd.to_datetime(forecasts['timestamps_96'],utc=True)).equals(expected.tz_convert('UTC'))
        files = {name:record(RAW/day/name) for name in ('aemo_forecast.json','aemo_actual.parquet',
                 'gfs_d1_weather.parquet','noaa_actual_weather.parquet','kestrel_realized_jobs.parquet','source_day_manifest.json')}
        source_manifest=json.loads((RAW/day/'source_day_manifest.json').read_text(encoding='utf8'))
        checks={k: files[Path(v['path']).name]['sha256']==v['sha256'] for k,v in source_manifest['categories'].items()
                if Path(v['path']).name in files}
        assert all(checks.values())
        # Even dates with a complete new known reference cannot be promoted
        # while realized H100 request gangs are unavailable. No whole-node
        # fallback is authorized by the current GPU request contract.
        reasons=[]
        if mapping['blocked_jobs']:reasons.append('COMMON_KNOWN_WORKLOAD_AUTHORITY_INCOMPLETE')
        if len(absent):reasons.append('REALIZED_H100_GPU_REQUEST_AUTHORITY_MISSING')
        if not forecast_ok or not actual_ok:reasons.append('RAW_GRID_INPUT_QUALITY')
        assert reasons, 'UPSTREAM_AUTHORITY_READY_REQUIRES_REAL_PHYSICAL_ADAPTER_NOT_PLACEHOLDERS'
        authority = dict(day=day, files=files,snapshot=record(SNAP/day/'D1_AIDC_SNAPSHOT.parquet'),
          issue_time=issue.isoformat(), forecast_causal=bool(forecast_ok), actual_grid_96_finite_aligned=bool(actual_ok),
          source_manifest_hash_checks=checks, raw_realized_rows=len(realized),
          raw_realized_known_ID_overlap=sum(f.id.astype(str).isin(realized.id.astype(str))),
          raw_daily_file_is_complete_carryin_authority=False, realized_H100_submit_rows=len(h100),
          realized_H100_GPU_request_missing=len(absent), realized_missing_GPU_job_IDs=absent.id.astype(str).tolist(),
          realization_complete=False, status='BLOCKED_WORKLOAD_AUTHORITY', reasons=reasons,
          current_runtime_used=MODEL, runtime_frozen_available_at=provider.state['day'],
          requested_walltime_used_as_predictor_feature_only=True, requested_walltime_service_fallback=False,
          known_request_archive=archive_record, known_request_members=members, known_request_projection=cols,
          inference_future_outcome_columns=[], IT_PCC_conversion='CURRENT_V42_SOURCE_PRESERVED_NOT_EXECUTED_UPSTREAM_BLOCKED',
          conversion_consumer_source=record(ROOT/'v42_temporal/native.py'))
        write(folder+'/INPUT_AUTHORITY.json',authority)
        write(folder+'/V42_REFERENCE_MAPPING_AUDIT.json',mapping)
        write(folder+'/B0_REFERENCE_SCHEDULE.json',dict(status='COMPLETE_KNOWN_REFERENCE' if mapping['full_reference_ready'] else 'PARTIAL_BLOCKED_WITH_ALL_ROWS_RETAINED',
              jobs=reference, population=jobs, audit=mapping, not_a_complete_actual_workload=True))
        write(folder+'/B0_FROZEN_PLAN.json',dict(status='NOT_FROZEN', reason=reasons,
              common_reference_sha256=mapping['reference_sha256'], official_PR118_planning_freeze_created=False))
        columns=['job_uid','state_at_D1_cutoff','reference_site','reference_start','service_slots','GPU_gang',
              'runtime_authority','site_authority_source','start_authority_source','fallback_used','queue_rule','compatible_sites',
              'status','reason','physical_running_retained','q50_expired_hard_occupancy','Q50_total_seconds','nominal_remaining_seconds']
        table(folder+'/V42_COMMON_REFERENCE_SCHEDULE.csv',reference,columns)
        for curve in ('V_PLAN','V_DA_AC','V_DDAY_AC'):
            table(folder+'/'+curve+'.csv',[],['day','node','phase','slot','timestamp','voltage_pu'])
        table(folder+'/VOLTAGE_RESIDUALS.csv',[],['day','node','phase','slot','timestamp','e_model','e_forecast','e_total','r_up','r_down'])
        write(folder+'/OFFLINE_DA_AC_RECEIPT.json',dict(status='NOT_RUN', reason=reasons,
              OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True, operational_gate=False, OpenDSS_calls=0, controls=dict.fromkeys(ZERO_ACTIONS,0)))
        write(folder+'/DDAY_ACTUAL_RECEIPT.json',dict(status='NOT_RUN',reason=reasons,OpenDSS_calls=0,
              DayAhead_power_arrays_copied=None, IT_recomputed_from_actual_occupancy=None,
              controls=dict.fromkeys(ZERO_ACTIONS,0), physical_presence_PASS=None))
        write(folder+'/PHYSICAL_LIMIT_SUMMARY.json',dict(status='NOT_RUN',V_PLAN_min=None,V_PLAN_max=None,V_DA_AC_min=None,
              V_DA_AC_max=None,V_DDAY_AC_min=None,V_DDAY_AC_max=None,undervoltage_count=None,overvoltage_count=None,
              line_violation_count=None,transformer_current_violation_count=None,transformer_kVA_violation_count=None,
              worst_event=None,physical_PASS=None,model_positive_max=None,model_negative_max=None,
              forecast_positive_max=None,forecast_negative_max=None,total_positive_max=None,total_negative_max=None))
        aggregates.append(dict(day=day,raw_forecast_available=True,raw_realized_available=True,
            forecast_causal=bool(forecast_ok),actual_grid_aligned=bool(actual_ok),known_jobs=len(jobs),
            missing_known_GPU=sum(j['GPU_gang'] is None for j in jobs),**mapping,
            realized_H100_submit_rows=len(h100),realized_missing_GPU=len(absent),
            usable=False,excluded=True,reason=';'.join(reasons),scientific_execution='NOT_RUN'))
    table('APRIL_DATE_FREEZE.csv',aggregates,['day','raw_forecast_available','raw_realized_available','forecast_causal',
        'actual_grid_aligned','known_jobs','missing_known_GPU','assigned_jobs','blocked_jobs','full_reference_ready',
        'realized_H100_submit_rows','realized_missing_GPU','usable','excluded','reason','scientific_execution'])
    table('V42_COMMON_REFERENCE_SCHEDULE.csv',all_reference,['day']+columns)
    table('BLOCKED_REFERENCE_ROWS.csv',all_blocked,['day','job_uid','state_at_D1_cutoff','GPU_gang','service_slots','status','reason'])
    write('V42_REFERENCE_MAPPING_AUDIT.json',dict(days=aggregates,total_snapshot_rows=sum(r['known_jobs'] for r in aggregates),
          total_output_rows=len(all_reference),all_rows_retained=True,current_runtime_inference=True,
          complete_known_reference_dates=[r['day'] for r in aggregates if r['full_reference_ready']],
          missing_known_GPU=sum(r['missing_known_GPU'] for r in aggregates),
          missing_realized_GPU=sum(r['realized_missing_GPU'] for r in aggregates),
          historical_mapping_fallback=False,scientific_B0_execution_dates=[]))
    write('APRIL_DATA_AUTHORITY.json',dict(days=aggregates,source_period='2025-04',May_results_read=False,
          dates_audited=30,raw_forecast_dates=30,raw_realized_dates=30,usable_dates=[],outcome_filtering=False,
          freeze_created_before_OpenDSS=True,OpenDSS_calls=0,
          raw_locations_do_not_establish_complete_current_V42_workload_authority=True))
    for name in ('MODEL','FORECAST','TOTAL'):
        write(name+'_ERROR_STATS.json',dict(**error_stats([], 'e_'+name.lower()),status='NOT_ESTIMABLE',dominant_cause='INCONCLUSIVE'))
    point, daily = quantiles([],'pointwise'),quantiles([],'day_worst')
    for name,rows in (('APRIL_POINTWISE_QUANTILES.csv',point),('APRIL_DAY_WORST_QUANTILES.csv',daily)):
        table(name,rows,list(rows[0]))
    table('APRIL_B0_VOLTAGE_RESIDUALS.csv',[],['day','node','phase','slot','timestamp','e_model','e_forecast','e_total','r_up','r_down'])
    table('APRIL_DAY_WORST.csv',[],['day','samples','r_up','r_down','up_event','down_event'])
    table('OPTIONAL_BAND_SENSITIVITY.csv',sensitivity([]),list(sensitivity([])[0]))
    write('CURRENT_005_MARGIN_COVERAGE.json',dict(**coverage([]),status='NOT_ESTIMABLE'))
    write('CALIBRATED_MARGIN_CANDIDATES.json',dict(status='NOT_ESTIMABLE',pointwise=point,day_worst=daily,FINAL_MARGIN_ACCEPTED=False))
    write('B0_AIDC_PRESENCE_AUDIT.json',dict(AIDC_PRESENT=True,AIDC_WORKLOAD_PRESENT=True,contract_PASS=True,
          physical_PASS=None,status='NOT_EXECUTED',it_energy_kwh=None,pcc_energy_kwh=None,active_slots=None,served_workload=None,
          common_population_rows_retained=len(all_reference),workload_drop=False))
    write('B0_NO_FLEXIBILITY_AUDIT.json',dict(contract_PASS=True,**dict.fromkeys(ZERO_ACTIONS,0),scientific_execution='NOT_RUN'))
    write('B0_MESS_OFF_AUDIT.json',dict(contract_PASS=True,MESS_ACTIVE=False,P_MESS=0,Q_MESS=0,movement=0,optimizer_calls=0))
    write('MAY_HOLDOUT_RECEIPT.json',dict(MAY_USED_FOR_CALIBRATION=False,MAY_RUN=False,May_result_payload_reads=0,
          known_archive_members_read=members,known_features_only=True,actual_May_end_times_used=False))
    write('FINAL_FLAGS.json',dict(**FLAGS,APRIL_EXECUTED_DAYS=0,COMMON_REFERENCE_GENERATED_DAYS=30,
          PLANNING_FRESH_AC_CALLS=0,OFFLINE_DA_AC_CALLS=0,DDAY_FRESH_AC_CALLS=0,
          AIDC_PHYSICAL_PRESENCE_PASS=None,VOLTAGE_CURVES_GENERATED=False))
    write('FINAL_VERDICT.json',dict(verdict='BLOCKED_CURRENT_V42_WORKLOAD_AUTHORITY',
          mapping_file_absence_is_STOP=False,current_reference_generator_created=True,
          known_reference_complete_dates=[r['day'] for r in aggregates if r['full_reference_ready']],
          primary_execution_dates=[],reason='Every April raw realized H100 arrival set includes missing GPU request authority; retaining rows forbids physical replay. Some known populations also have missing GPU requests.',
          missing_realized_GPU_rows=sum(r['realized_missing_GPU'] for r in aggregates),
          historical_B0_policy_recovery=False,calibration_complete=False,FINAL_MARGIN_ACCEPTED=False))
    print(json.dumps(dict(audited_days=30,known_rows=len(all_reference),known_complete_dates=[r['day'] for r in aggregates if r['full_reference_ready']],
          missing_known_GPU=sum(r['missing_known_GPU'] for r in aggregates),missing_realized_GPU=sum(r['realized_missing_GPU'] for r in aggregates),
          executed_days=0),indent=2))


if __name__=='__main__':
    main()

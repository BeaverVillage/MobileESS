"""Read-only scientific readiness audit. Never launches a replay or optimizer.

Writes only the separate v40d_actual_realized_replay artifact namespace.
Missing observations and absent execution semantics are blockers, not zeroes.
"""
from __future__ import annotations

import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / 'dayahead/artifacts/v40d_actual_realized_replay'
CAMPAIGN = REPO / 'dayahead/artifacts/v40b_v40a_may_launch'
RAW = Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터')
WSL = Path(r'\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline')
DAYS = tuple(f'2025-05-{d:02d}' for d in range(1, 32))
CASES = ('B0', 'B1', 'B2', 'B3')
AEST = timezone(timedelta(hours=10))
METHOD_SHA = '9af44cb41650c0e3c5643800f6600a4f8e91bb213a775a12b8d4cc47560b584a'
READ_FILES: dict[str, dict] = {}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def evidence(path):
    p = Path(path)
    result = {'path': str(p), 'exists': p.is_file()}
    if p.is_file():
        result.update(sha256=sha(p), bytes=p.stat().st_size)
        READ_FILES[str(p)] = result
    return result


def read(path):
    evidence(path)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True,
        ensure_ascii=False, default=str, allow_nan=False) + '\n', encoding='utf-8')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


# Explicit source reading inventory. No dynamic imports of planning code.
AUTHORITY = [
 ('dayahead/v33m3/actual_replay.py', ['SumoActualAuthority', 'replay_committed_move'], 'V33M3 / PR19 lineage 7064014,e02ea8d', 'PRESERVED_EXECUTION_SEMANTICS', True, 'V40A commitments adapter', 'Fixed route; link-entry 5-minute final_tt_sec; deterministic physics energy; ceil connection readiness; fails when link-entry exceeds day.'),
 ('dayahead/v33m/mess_trajectory.py', ['PlannedMoveCommitment', 'MessTrajectory'], 'V33M', 'CURRENT_PLANNING_REPRESENTATION', True, 'Restore final accepted slots only', 'One frozen vehicle, origin, destination, departure and reduced-link sequence per move.'),
 ('dayahead/v33m/road_graph_authority.py', ['load_road_graph_authority'], 'V33M', 'PRESERVED', True, 'None', 'Frozen 509-link order, service mapping, physical geometry and grade.'),
 ('dayahead/v33m/mobility_physics_adapter.py', ['PhysicsMobilityEnergyAdapter'], 'V33M / PFR physics', 'PRESERVED', True, 'None', 'Longitudinal deterministic physics; actual elapsed time supplied; no ML energy.'),
 ('pfr/mobility_physics.py', ['MobilityPhysics'], 'PFR', 'PRESERVED_PHYSICS', True, 'None', 'Geometry and realized travel time determine energy under frozen vehicle parameters.'),
 ('dayahead/v28r2/mess_replay.py', ['replay_mess', 'MessReplay'], 'V28R2 / V29', 'PRESERVED_COMMAND_RULE_OLD_ROUTE_SOURCE_SUPERSEDED', False, 'Feed V33M3 actual state and actual energy; do not reuse engineering routes', 'Gate fixed-slot commands by connected state and PCS; drop both P/Q if SoC infeasible; no time shift or substitute. Old safe_travel_energy field is not a valid V33M3 actual source.'),
 ('dayahead/v28/actual_replay.py', ['execute_workload', 'execute_mess', 'actual_it_residual'], 'V28', 'SUPERSEDED_SIMPLE_AGGREGATE_API', False, 'Not compatible with V40A job identities', 'Aggregate min(command, available); does not define shifted observed job durations.'),
 ('dayahead/realized_compute_replay.py', ['replay_compute'], 'V16 realized replay', 'PRESERVED_COHORT_SEMANTICS_SUPERSEDED_MODEL', False, 'Not compatible with V40A individual jobs', 'Same cohort/rack/time service cap, backlog and rack headroom; no observed-duration rescheduling.'),
 ('dayahead/aidc_realized_decomposition.py', ['realized_replay'], 'V16 realized decomposition', 'PRESERVED_NO_DOUBLE_COUNT_PRINCIPLE_SUPERSEDED_POWER_MODEL', False, 'Do not revive old residual power in CENTER model', 'Remove natural flexible component before adding executed flexible component once.'),
 ('dayahead/realized_mess_replay.py', ['replay_mess'], 'V16 realized replay', 'PRESERVED_COMMAND_GATE', True, 'Actual physical connectivity input required', 'Fixed-slot P/Q becomes zero when unavailable; no catch-up.'),
 ('dayahead/v29/actual_replay.py', ['replay_actual_case_v29'], 'V29', 'SUPERSEDED_COHORT_MODEL', False, 'No per-job V40A mapping', 'Calls V28R2 cohort-service replay with causal initial backlog.'),
 ('dayahead/v28r2/workload_replay.py', ['materialize_actual_workload', 'replay_workload'], 'V28R2', 'SUPERSEDED_COHORT_RACK_POWER_AND_WORKLOAD_MODEL', False, 'Scientific mapping unresolved', '15 cohorts x 48 racks x 96 slots; min(DA service, backlog, residual capacity), observed service enters at submit slot. No per-job frozen-start plus realized-duration execution rule.'),
 ('dayahead/v28r2/actual_replay.py', ['replay_actual_case', '_residuals', 'exact_pcc_from_site_it'], 'V28R2', 'PRESERVED_NO_DOUBLE_COUNT_PRINCIPLE_OLD_POWER_MODEL_SUPERSEDED', False, 'CENTER site occupancy and observed-weather adapter needed', 'Old natural-flex residual plus replayed service is applied once; ESIF alpha and kappa are not current CENTER power authority.'),
 ('dayahead/v28r2/source_preflight.py', ['materialize_aemo', 'materialize_noaa'], 'V28R2', 'PRESERVED_INPUT_ALIGNMENT_APRIL_WRAPPER', False, 'May range and new output namespace', 'Actual demand sampled at quarter-hour interval ends; PV MEASUREMENT half-hour averages repeated twice; observed weather time-interpolated to quarter-hour starts.'),
 ('dayahead/thermal/noaa_isd.py', ['decode_global_hourly'], 'V24T', 'PRESERVED', True, 'None', 'Melbourne station 94866099999; accepted QC, pressure priority, hourly dedup, derived RH and wet bulb.'),
 ('dayahead/v28r2/c1_affine.py', ['load_c1', 'exact_c1_pcc_kw'], 'V24T / V28R2 / V40A', 'CURRENT_EXACT_C1', True, 'Observed weather instead of forecast', 'Exact C1 once. Preserve current scale and normalization; no extra PUE, beta or refit.'),
 ('dayahead/v39a/power.py', ['site_it_power_kw', 'validate_power_conservation'], 'V39A / V40A', 'CURRENT_CENTER_SITE_POWER', False, 'Fractional occupancy/capacity-overrun execution semantics unresolved', 'Frozen idle + CENTER active GPU swing; integer GPU argument and capacity checks; cannot silently truncate fractional occupied GPU averages.'),
 ('dayahead/v39d/actual.py', ['validate_actual_fixed_replay', 'deterministic_rack_assignment'], 'V39D / V39E / V40B', 'CURRENT_IDENTITY_GATE_NOT_REALIZED_PERFORMANCE', True, 'Identity and rack compatibility only', 'Checks DA SHA and uses supplied intervals. No realized start/end reader or job duration transformation.'),
 ('dayahead/v39e/campaign_adapter.py', ['build_day'], 'V39E', 'CURRENT_FROZEN_DA_LOADER', True, 'Read-only final decision binding', 'Loads frozen planned GPU/IT/PCC arrays without replaying observed workload.'),
 ('dayahead/v28r2/electrical_context.py', ['with_realized_background'], 'V28R2', 'PRESERVED_ACTUAL_BACKGROUND_BINDING', True, 'May read-only context', 'Accepted grid/background authority applied to realized demand/PV; no optimization.'),
 ('dayahead/v28r2/opendss_backend.py', ['run_fresh_opendss', '_branch_measurement'], 'V28R2', 'PRESERVED_ENGINE_AND_MEASUREMENT_PRIMITIVES', False, 'Actual namespace and explicit native-control semantics/root power output', 'Clean engine, sequential slots; historical driver reapplies planned native taps every slot. Do not silently replace with a new autonomous regulator policy.'),
 ('dayahead/v28r2/opendss_results.py', ['OpenDSSResult'], 'V28R2', 'PRESERVED_PHASE_LINE_OBJECTIVE', False, 'Requested new Actual schema and root import/export fields', 'Line-only max normalized phase current; separate transformer metrics, energy losses and physical violations.'),
 ('dayahead/v40b/b3.py', ['run'], 'V40B / V40D restoration', 'CURRENT_ACCEPTED_PLANNING_OUTPUT', False, 'Read outputs only; NEVER call run', 'Final P/Q and joint SHA written after restoration; pre-restoration MF must not be substituted.'),
]


def authority_audit():
    rows = []
    for relative, functions, lineage, status, reusable, adapter, boundary in AUTHORITY:
        p = REPO / relative
        tree = ast.parse(p.read_text(encoding='utf-8-sig'))
        definitions = {n.name: {'line': n.lineno, 'end_line': n.end_lineno}
                       for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        rows.append({'source': evidence(p), 'requested_functions': functions,
          'functions': {name: definitions.get(name) for name in functions},
          'lineage': lineage, 'status': status, 'reusable_unchanged': reusable,
          'adapter_required': adapter, 'scientific_semantic_boundary': boundary})
    missing_symbols = [(r['source']['path'], name) for r in rows for name, loc in r['functions'].items() if loc is None]
    result = {'status': 'FAIL', 'audit_completed': True, 'sources': rows,
      'symbol_lookup_errors': missing_symbols,
      'blocker': 'NO_ACCEPTED_PER_JOB_REALIZED_DURATION_EXECUTION_RULE_FOR_V40A',
      'description': 'V28 cohort-service replay cannot establish frozen per-job counterfactual duration semantics. V39D/V39E preserve identity/planned intervals only.',
      'campaign_authorized': False, 'current_method_SHA': METHOD_SHA,
      'old_semantics_not_reintroduced': True}
    write('V40D_EXISTING_ACTUAL_AUTHORITY_AUDIT.json', result)
    return result


def traffic_audit():
    order_path = WSL/'10_ml_stage1_multires_traffic_v1/graph/link_order_509.csv'
    order = pd.read_csv(order_path).sort_values('tensor_index')
    links = order.reduced_link_id.astype(str).tolist()
    assert len(links) == len(set(links)) == 509
    assert order.tensor_index.tolist() == list(range(509))
    order_ev = evidence(order_path)
    def one(day):
        p = WSL/f'08_production_5min_validated_stage25f/year=2025/date={day}/link_tt_5min_24h.parquet'
        ev = evidence(p)
        if not ev['exists']: return {'day': day, 'status': 'FAIL', 'source': ev, 'missing': 'entire daily file'}
        f = pd.read_parquet(p, columns=['calendar_date', 'slot5', 'reduced_link_id', 'final_tt_sec'])
        unique = f.drop_duplicates(['slot5','reduced_link_id'])
        expected = pd.MultiIndex.from_product([range(288), links])
        observed = pd.MultiIndex.from_frame(unique[['slot5','reduced_link_id']])
        missing = len(expected.difference(observed)); extra = len(observed.difference(expected))
        duplicates = len(f)-len(unique); finite = np.isfinite(f.final_tt_sec.to_numpy(float))
        pivot = f.pivot(index='slot5', columns='reduced_link_id', values='final_tt_sec') if not duplicates else None
        ok = not (missing or extra or duplicates) and finite.all() and f.final_tt_sec.gt(0).all() and set(f.calendar_date)=={day}
        return {'day':day, 'status':'PASS' if ok else 'FAIL', 'source':ev,
          'rows':len(f),'required_rows':288*509,'missing_keys':missing,'extra_keys':extra,
          'duplicate_keys':duplicates,'nonfinite_values':int((~finite).sum()),
          'link_order_SHA':order_ev['sha256'],'canonical_link_ids_SHA':digest(links),
          'ordered_values_SHA':hashlib.sha256(pivot.reindex(index=range(288),columns=links).to_numpy(np.float64).tobytes()).hexdigest() if ok else None}
    with ThreadPoolExecutor(max_workers=4) as pool: days=list(pool.map(one,DAYS))
    result={'status':'PASS' if all(r['status']=='PASS' for r in days) else 'FAIL','days':days,
      'link_order':order_ev,'calendar_timezone':'AEST_FIXED_UTC_PLUS_10',
      'semantics':'Observation-anchored calibrated SUMO final_tt_sec, not direct native 5-minute observations',
      'geometry_sources':[evidence(WSL/'21_ml_stage9_v11_fixed_station_full_traffic_freeze_v1/freeze_assets/stage8/optimizer_interface/final_service_nodes_24.csv'),
        evidence(WSL/'24c_energy_stage_e1r_canonical_physical_route_library_v1_1_metric_repair/library/reduced_link_physical_edge_congestion_catalog.csv.gz'),
        evidence(WSL/'24e_energy_stage_e1g_grade_validation_v1_7_resolution_aware_grade_profile/network/network_elevated_conditioned.net.xml')]}
    write('V40D_TRAFFIC_COMPLETENESS.json',result); return result


def archive_rows(path):
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith('.csv'): continue
            with z.open(name) as stream:
                headers={}
                for row in csv.reader(io.TextIOWrapper(stream,encoding='utf-8-sig')):
                    if row and row[0]=='I': headers[tuple(row[1:4])]=row[4:]
                    elif row and row[0]=='D' and tuple(row[1:4]) in headers:
                        yield dict(zip(headers[tuple(row[1:4])],row[4:]))


def aemo_audit():
    results={}
    for kind, sub, filename, ts, val, minutes in (
      ('demand','Realized demand','DISPATCHREGIONSUM','SETTLEMENTDATE','TOTALDEMAND',5),
      ('pv','AEMO Rooftop PV — forecast + actual/Actual','ROOFTOP_PV_ACTUAL','INTERVAL_DATETIME','POWER',30)):
        p=RAW/f'AEMO/{sub}/PUBLIC_ARCHIVE#{filename}#FILE01#202505010000.zip'
        records=[r for r in archive_rows(p) if r.get('REGIONID')=='VIC1' and ts in r and (kind!='pv' or r.get('TYPE')=='MEASUREMENT')]
        f=pd.DataFrame(records); f['timestamp']=pd.to_datetime(f[ts],format='%Y/%m/%d %H:%M:%S').dt.tz_localize(AEST)
        f['value']=pd.to_numeric(f[val],errors='coerce')
        source=evidence(p); days=[]
        for day in DAYS:
            start=pd.Timestamp(day,tz=AEST);end=start+pd.Timedelta(days=1)
            selected=f[(f.timestamp>start)&(f.timestamp<=end)]
            axis=pd.date_range(start+pd.Timedelta(minutes=minutes),end,freq=f'{minutes}min')
            duplicates=int(selected.timestamp.duplicated().sum())
            missing=axis.difference(pd.DatetimeIndex(selected.timestamp))
            nonfinite=selected.loc[~np.isfinite(selected.value),'timestamp'].astype(str).tolist()
            values=selected.set_index('timestamp').value.reindex(axis) if not duplicates else pd.Series(dtype=float)
            aligned=values.reindex(pd.date_range(start+pd.Timedelta(minutes=15),end,freq='15min')) if kind=='demand' else pd.Series(np.repeat(values.to_numpy(),2))
            finite_aligned=int(np.isfinite(aligned.to_numpy(float)).sum())
            conservation=None
            if kind=='pv' and finite_aligned==96: conservation=float(abs(values.sum()*.5-aligned.sum()*.25))
            ok=not duplicates and not len(missing) and not nonfinite and finite_aligned==96
            days.append({'day':day,'status':'PASS' if ok else 'FAIL','rows':len(selected),'required_rows':len(axis),
              'duplicate_timestamps':duplicates,'missing_timestamps':list(map(str,missing)),
              'nonfinite_timestamps':nonfinite,'finite_15min_slots':finite_aligned,
              '15min_energy_conservation_error_mwh':conservation})
        results[kind]={'status':'PASS' if all(r['status']=='PASS' for r in days) else 'FAIL','source':source,'days':days,
          'region':'VIC1','unit':'MW','timestamp':'interval-end fixed AEST UTC+10','native_resolution_minutes':minutes,
          'selection':'TYPE=MEASUREMENT' if kind=='pv' else 'Inherited VIC1 rows; no unapproved intervention filtering',
          'alignment':'Repeat each 30-min MEASUREMENT twice; conserve energy' if kind=='pv' else 'Inherited exact quarter-hour end sampling of 5-min dispatch demand; not a 15-min mean',
          'fallback_used':False,'forecast_substitution':False,
          'types':dict(Counter(f.TYPE)) if kind=='pv' else {'RUNNO':dict(Counter(f.RUNNO)),'INTERVENTION':dict(Counter(f.INTERVENTION))}}
    write('V40D_AEMO_COMPLETENESS.json',results);return results


def weather_audit():
    root=REPO/'dayahead/artifacts/v24t_thermal_aware_aidc'
    authority=read(root/'V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json')
    source=evidence(authority['path']);p=root/'V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet';derived=evidence(p)
    assert source['sha256']==authority['sha256'] and derived['sha256']==authority['output_sha256']
    f=pd.read_parquet(p); f.index=pd.DatetimeIndex(f.ts).tz_convert(AEST); numeric=f.drop(columns='ts').select_dtypes(include=[np.number])
    days=[]
    for day in DAYS:
        target=pd.date_range(day,periods=96,freq='15min',tz=AEST)
        x=numeric.reindex(numeric.index.union(target)).sort_index().interpolate(method='time').reindex(target)
        required=['t_db_c','t_dew_c','rh_pct','t_wb_c','pressure_pa']
        counts={c:int((~np.isfinite(x[c])).sum()) for c in required}
        days.append({'day':day,'status':'PASS' if not any(counts.values()) else 'FAIL','slots':len(x),'nonfinite_by_field':counts,
          'interpolation_contract':'V28R2 materialize_noaa: time-linear hourly to quarter-hour starts',
          'observations_before_and_after_target': bool(f.index.min()<=target.min() and f.index.max()>=target.max())})
    result={'status':'PASS' if all(r['status']=='PASS' for r in days) else 'FAIL','source':source,'derived':derived,
      'station':authority['station_id'],'quality_audit':evidence(root/'V24T_NOAA_ISD_DECODE_AUDIT.json'),
      'days':days,'GFS_used':False,'refit':False}
    write('V40D_WEATHER_COMPLETENESS.json',result);return result


def workload_audit():
    archive=RAW/'데이터 센터/NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip'
    frames=[]; ledgers={}; needed=set()
    for day in DAYS:
        p=REPO/f'dayahead/artifacts/v37_r4a_per_day_aidc/days/{day}/V37_R4A_JOB_LEDGER.parquet'
        evidence(p);f=pd.read_parquet(p);ledgers[day]=f;needed.update(f.job_id.astype(str))
    columns=['id','job_id','start_time','end_time','submit_time','gpus_requested','state','state_simple']
    members=[]
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not name.endswith('.parquet'):continue
            # Search all available members for exact frozen IDs, including boundary records.
            # BytesIO prevents repeated seek/decompression through ZipExtFile.
            f=pq.read_table(io.BytesIO(z.read(name)),columns=columns).to_pandas()
            f=f[f.id.astype(str).isin(needed)].copy()
            if len(f): f['source_member']=name;frames.append(f);members.append({'name':name,'matched_rows':len(f),'crc':z.getinfo(name).CRC})
    f=pd.concat(frames,ignore_index=True);f.id=f.id.astype(str)
    duplicates=f.loc[f.id.duplicated(keep=False),'id'].tolist()
    if duplicates: raise RuntimeError('RAW_KESTREL_ID_AMBIGUITY:'+str(duplicates[:5]))
    f=f.set_index('id');invalid_rows=[];days=[]
    f.reset_index().to_parquet(OUT/'V40D_FROZEN_JOB_OBSERVATIONS.parquet',index=False)
    for day, ledger in ledgers.items():
        ids=ledger.job_id.astype(str).tolist();x=f.reindex(ids);duration=(x.end_time-x.start_time).dt.total_seconds()
        missing_start=x.start_time.isna();missing_end=x.end_time.isna();bad=missing_start|missing_end|~np.isfinite(duration)|duration.le(0)
        requested=pd.to_numeric(ledger.set_index(ledger.job_id.astype(str)).requested_gpus)
        resource_bad=(x.gpus_requested-requested).abs().gt(1e-9)
        day_bad=[]
        for uid in x.index[bad|resource_bad]:
            row=x.loc[uid];entry={'day':day,'job_uid':uid,'observed_start':str(row.start_time),'observed_end':str(row.end_time),
              'duration_seconds':None if not np.isfinite(duration.loc[uid]) else float(duration.loc[uid]),
              'raw_state':None if pd.isna(row.state) else str(row.state),
              'source_member':None if pd.isna(row.source_member) else str(row.source_member),
              'missing_fields': [k for k,v in [('start_time',missing_start.loc[uid]),('end_time',missing_end.loc[uid])] if v],
              'reason':'Observed positive service duration unavailable; cancellation/zero-duration policy is not declared' if bad.loc[uid] else 'GPU identity mismatch'}
            invalid_rows.append(entry);day_bad.append(uid)
        days.append({'day':day,'status':'PASS' if not day_bad else 'FAIL','frozen_job_count':len(ids),'matched_raw_ids':int(x.source_member.notna().sum()),
          'positive_duration_count':int((~bad).sum()),'invalid_duration_count':int(bad.sum()),'GPU_mismatch_count':int(resource_bad.sum()),'affected_job_uids':day_bad})
    result={'status':'PASS' if all(r['status']=='PASS' for r in days) else 'FAIL','source':evidence(archive),'members':members,
      'identity_key':'raw id == frozen ledger job_id == V40A job_uid (not raw numeric job_id)',
      'days':days,'invalid_observations':invalid_rows,'unique_frozen_jobs':len(needed),'duplicate_raw_ids':duplicates,
      'realized_duration_replay_semantics':'NOT_ESTABLISHED_BY_INHERITED_AUTHORITY',
      'future_end_times_used_for_DA_decisions':False,'raw_observations_relabelled_as_counterfactual_execution':False}
    write('V40D_WORKLOAD_COMPLETENESS.json',result);return result


def decision_audit():
    rows=[]; errors=[]; protected={}
    def verify(path,expected):
        p=Path(path);ev=evidence(p);protected[str(p)]=ev
        if not ev['exists'] or ev['sha256']!=expected: errors.append({'path':str(p),'expected_SHA':expected,'actual':ev})
    method=read(CAMPAIGN/'V40B_V40A_METHOD_FREEZE.json');assert method['method_SHA']==METHOD_SHA
    for day in DAYS:
        dc=read(CAMPAIGN/'days'/day/'DAY_CERTIFICATE.json');assert dc['status']=='PASS'
        for case in CASES:
            ref=dc['cases'][case];cp=Path(ref['certificate']);verify(cp,ref['certificate_SHA']);cert=read(cp);assert cert['status']=='PASS'
            before=len(errors)
            if case=='B3':
                for name,expected in cert['files'].items():verify(cp.parent/name,expected)
                final=read(cp.parent/'FINAL_JOINT_DECISION.json');payload=read(cp.parent/'FINAL_JOINT_DECISION_PAYLOAD.json')
                actual=read(cp.parent/'ACTUAL_FIXED_REPLAY.json');fresh=read(cp.parent/'FRESH_AC_RESULT.json');terminal=read(cp.parent/'COOPT_TERMINAL_AUDIT.json')
                assert final==payload['joint_decision']
                joint_sha=cert['FINAL_JOINT_DECISION_SHA']
                assert actual['FINAL_JOINT_DECISION_SHA']==fresh['FINAL_JOINT_DECISION_SHA']==joint_sha
                assert actual['Fresh_FINAL_JOINT_DECISION_SHA']==joint_sha
                assert fresh['summary']['convergence_count']==96 and not fresh['summary']['physical_violation']
                jobs=payload['AIDC_decision'];unsited=[r['job_uid'] for r in jobs if r['AIDC_site']=='UNASSIGNED']
                row={'day':day,'case':case,'final_executed_joint_sha':joint_sha,'joint_identity_kind':'ORIGINAL_V40A_FINAL_AFTER_RESTORATION',
                  'AIDC_decision_source':str(cp.parent/'FINAL_JOINT_DECISION_PAYLOAD.json'),
                  'MESS_final_source':str(cp.parent/'FINAL_MESS_COMPLETE_TRAJECTORY.parquet'),
                  'final_PQ_source':str(cp.parent/'FINAL_JOINT_DECISION_PAYLOAD.json'),
                  'Fresh_schedule_SHA':fresh['Fresh_schedule_sha256'],'Fresh_PASS':True,'terminal_audit':terminal,
                  'unassigned_outside_planned_target_job_count':len(unsited),'unassigned_job_uids':unsited,
                  'unassigned_semantics':'Not a Planning defect. Actual overrun into target day has no automatically inferable frozen site.'}
            else:
                cr=Path(cert.get('case_root') or cert['historical_case_root'])
                for item in cert['files']:verify(cr/item['relative_path'],item['sha256'])
                checkpoint=Path(cert.get('checkpoint') or cert['historical_checkpoint'])
                verify(checkpoint,cert.get('checkpoint_SHA') or cert['historical_checkpoint_SHA'])
                data=read(checkpoint);fresh=data['result']['Fresh'];assert fresh['convergence_count']==96 and not fresh['physical_violation']
                assert data['result']['Planning']['pass']
                # Production runner deliberately uses B0 AIDC decisions for B2.
                aidc_case='B0' if case=='B2' else case
                freeze_path=REPO/f'dayahead/artifacts/v39e_full_may_2025/V39E_DAYAHEAD_DECISION_FREEZE_{day}_{aidc_case}.json'
                freeze=read(freeze_path);assert digest(freeze['decision'])==freeze['DA_decision_SHA256']
                fp=data['execution_fingerprint']['AIDC_operating_day_fingerprints']
                assert fp['V39E_DA_decision_SHA256']==freeze['DA_decision_SHA256']
                assert fp['V39E_DA_freeze_SHA256']==sha(freeze_path)
                binding={'DA_decision_SHA':freeze['DA_decision_SHA256'],'Fresh_schedule_SHA':fresh['schedule_sha256'],
                   'MESS_executed_file_SHA':sha(cr/'mess/MESS_TRAJECTORY_96.parquet'),'case':case,'day':day}
                row={'day':day,'case':case,'final_executed_joint_sha':digest(binding),
                  'joint_identity_kind':'AUDIT_COMPOSITE_OF_EXISTING_BASELINE_EXECUTED_IDENTITIES_NOT_ORIGINAL_V40A_SHA',
                  'binding_components':binding,'AIDC_decision_source':str(freeze_path),'MESS_final_source':str(cr/'mess/MESS_TRAJECTORY_96.parquet'),
                  'final_PQ_source':str(cr/'mess/MESS_TRAJECTORY_96.parquet'),'Fresh_PASS':True,
                  'terminal_gate':'Accepted frozen DA temporal/terminal certification; no Actual terminal outcome asserted',
                  'execution_fingerprint_SHA':data['execution_fingerprint_sha256'],'AIDC_source_case':aidc_case}
            row.update(status='PASS' if len(errors)==before else 'FAIL',certificate=str(cp),certificate_SHA=sha(cp),origin=ref['status'])
            rows.append(row)
        print('DECISION_AUDIT',day,flush=True)
    result={'status':'PASS' if not errors else 'FAIL','days':31,'cases':rows,'verified_case_count':sum(r['status']=='PASS' for r in rows),
      'errors':errors,'method_SHA':METHOD_SHA,'protected_file_count':len(protected),'no_DA_rerun':True}
    write('V40D_ACTUAL_DECISION_BINDING_AUDIT.json',result)
    write('V40D_PROTECTED_PLANNING_MANIFEST.json',{'files':protected,'method_SHA':METHOD_SHA})
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    start={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'repo':str(REPO),
      'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
      'git_status_before':subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True),
      'scope':'Read-only audit; no campaign code, no optimization, no OpenDSS execution',
      'request':evidence(Path('C:/Users/kjw39/.codex/attachments/13cda25c-c67c-497b-b3c8-0ad1753d5bab/pasted-text.txt'))}
    write('V40D_AUDIT_START_STATE.json',start)
    authority=authority_audit();print('AUTHORITY_AUDIT',authority['status'],authority['symbol_lookup_errors'],flush=True)
    traffic=traffic_audit();print('TRAFFIC',traffic['status'],flush=True)
    aemo=aemo_audit();print('AEMO',{k:v['status'] for k,v in aemo.items()},flush=True)
    weather=weather_audit();print('WEATHER',weather['status'],flush=True)
    workload=workload_audit();print('WORKLOAD',workload['status'],len(workload['invalid_observations']),flush=True)
    data={'status':'PASS' if all(x['status']=='PASS' for x in [traffic,*aemo.values(),weather,workload]) else 'FAIL',
      'categories':{'traffic':traffic,'demand':aemo['demand'],'pv':aemo['pv'],'weather':weather,'workload':workload},
      'forecast_substitutions':0,'fabricated_observations':0}
    write('V40D_ACTUAL_DATA_PREFLIGHT.json',data)
    decisions=decision_audit();print('DECISIONS',decisions['status'],decisions['verified_case_count'],flush=True)
    write('V40D_AUDIT_SOURCE_MANIFEST.json',{'files':READ_FILES})


if __name__=='__main__':
    main()

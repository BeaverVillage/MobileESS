"""Read April sources and construct retained, explicitly gated day inventories.

python -m v42_april_port.audit --source-root <local> --output-root <new docs>
Requires completed May lineage/GPU forensic artifacts before any April build.
No May request payload, numerical coefficient, policy, or outcome is opened.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from collections import Counter, defaultdict
import zipfile
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from v42_final.runtime import FrozenQ50
from v42_april_b0_v2.recovery import validate_date_axis
from .builder import BASE, MODEL, B0_FLAGS, build_v42_day_input_bundle, timestamp

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT/'docs/v42_april_b0_voltage_margin_calibration_v2'


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def record(p):
    return dict(path=str(Path(p).resolve()), sha256=sha(p), bytes=Path(p).stat().st_size)


def clean(v):
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [clean(x) for x in v]
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not np.isfinite(v):
        return None
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    return v


def write(out, name, obj):
    p = out/name
    p.parent.mkdir(parents=True, exist_ok=True)
    value = clean(obj)
    # One job per line keeps large inventories inspectable without millions
    # of formatting-only lines. This does not copy external raw files.
    if isinstance(value, dict):
        entries = []
        for k, v in value.items():
            if isinstance(v, list) and len(v) > 32 and all(isinstance(x, dict) for x in v):
                encoded = '[\n' + ',\n'.join('    '+json.dumps(x, ensure_ascii=False, allow_nan=False) for x in v) + '\n  ]'
            else:
                encoded = json.dumps(v, ensure_ascii=False, allow_nan=False)
            entries.append('  '+json.dumps(k)+': '+encoded)
        text = '{\n'+',\n'.join(entries)+'\n}\n'
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    p.write_text(text, encoding='utf8', newline='\n')


def table(out, name, rows, columns):
    p = out/name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        for row in rows:
            w.writerow({k:json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k,v in clean(row).items()})


def checked(recorded):
    p = Path(recorded['path'])
    if sha(p) != recorded['sha256']:
        raise ValueError('SOURCE_SHA_DRIFT:'+str(p))
    return p


def load_april_requests(archive_record):
    p = checked(archive_record)
    cols = ['id', 'submit_time', 'gpus_requested', 'nodes_req', 'processors_req', 'memory_req',
            'wallclock_req', 'partition', 'qos', 'account_hash', 'array_pos']
    requests = defaultdict(list); observations = {}; projections = []
    with zipfile.ZipFile(p) as z:
        members = sorted(n for n in z.namelist() if n.endswith('.parquet') and
                         any(f'year=2025/month={m}/' in n for m in (3, 4)))
        for member in members:
            with z.open(member) as f:
                pf = pq.ParquetFile(f); offset = 0
                projections.append(dict(member=member, rows=pf.metadata.num_rows, request_columns=cols,
                    Actual_only_columns=['id', 'start_time', 'end_time']))
                for batch in pf.iter_batches(columns=cols, batch_size=32768, use_threads=False):
                    frame = batch.to_pandas(); frame['source_row'] = np.arange(offset, offset+len(frame)); offset += len(frame)
                    frame = frame[frame.partition.astype(str).str.contains('h100', case=False, regex=False)]
                    frame['requested_seconds'] = frame.wallclock_req.dt.total_seconds(); frame.drop(columns='wallclock_req', inplace=True)
                    for row in frame.to_dict('records'):
                        uid = str(row.pop('id')); row['source_member'] = member
                        row['source_sha256'] = archive_record['sha256']; row['submit_time'] = timestamp(row['submit_time']).isoformat()
                        requests[uid].append(clean(row))
            # Separate realized-state channel. Future completion observations
            # are clipped by the builder; they never reach request inference.
            with z.open(member) as f:
                frame = pq.read_table(f, columns=['id', 'start_time', 'end_time'], use_threads=False).to_pandas()
                for row in frame.to_dict('records'):
                    uid = str(row['id'])
                    if uid not in requests:
                        continue
                    if uid in observations:
                        raise ValueError('DUPLICATE_ACTUAL_UID')
                    observations[uid] = {k: timestamp(row[k]).isoformat() if pd.notna(row[k]) else None for k in ('start_time', 'end_time')}
    if any(len(r) != 1 for r in requests.values()):
        raise ValueError('RAW_DUPLICATE_UID_REQUIRES_VERSION_RECONCILIATION')
    return dict(requests), observations, projections


def run(source_root, out):
    gpu = read(out/'MAY_PIPELINE/MAY_GPU_AUTHORITY_AUDIT.json')
    lineage = read(out/'MAY_PIPELINE/MAY_V42_PIPELINE_MANIFEST.json')
    # Distinguish completed code/source forensic from an executable authority.
    if not gpu.get('forensic_complete') or not lineage.get('lineage_forensic_complete'):
        raise ValueError('FULL_MAY_FORENSIC_REQUIRED_BEFORE_APRIL_BUILD')
    prereg = read(out/'PREREGISTRATION.json')
    if prereg['exact_base'] != BASE or prereg['May_values_as_donor']:
        raise ValueError('PREREGISTRATION_CONTRACT')
    source_join = read(PRIOR/'APRIL_V42_SOURCE_RECOVERY/SOURCE_JOIN_AUDIT.json')
    archive = source_join['archive']
    power = read(out/'MAY_PIPELINE/MAY_POWER_CONVERSION_AUDIT.json')
    static = power['grid']['static_input_metadata_projection']
    recovery = read(ROOT/'docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json')
    replacements = {r['original']:r['resolved'] for r in recovery['recovered']}
    def resolve_static(obj):
        if isinstance(obj, dict):
            if 'path' in obj and 'sha256' in obj:
                if Path(obj['path']).exists():
                    checked(obj)
                    return obj
                replacement = replacements.get(obj['path'])
                if not replacement or replacement['sha256'] != obj['sha256']:
                    raise ValueError('MISSING_STATIC_RAW_AUTHORITY:'+obj['path'])
                checked(replacement)
                return dict(obj, original_path=obj['path'], path=replacement['path'])
            return {k:resolve_static(v) for k,v in obj.items()}
        if isinstance(obj, list):
            return [resolve_static(v) for v in obj]
        return obj
    static = resolve_static(static)
    def all_records(obj):
        if isinstance(obj, dict):
            if 'path' in obj and 'sha256' in obj:
                yield obj
            else:
                for v in obj.values():
                    yield from all_records(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from all_records(v)
    static_records = list(all_records(static))
    for r in static_records:
        checked(r)
    print('Static topology/mapping/rating SHAs verified; loading March/April request projections', flush=True)
    requests, observations, projections = load_april_requests(archive)
    print('April request identities', len(requests), 'Actual observation identities', len(observations), flush=True)
    provider = FrozenQ50()
    capacities = dict(zip((f'AIDC{i:02}' for i in range(1, 13)), power['capacity']['site_GPU']))
    physical = dict(capacities=capacities, rack_compatibility={s:[c] for s,c in capacities.items()},
                    network_static_complete=bool(static_records), electrical_adapter_bound=False,
                    static_input_metadata=static, alpha_BG=1.15,
                    grid_numeric_coefficients_source='REGENERATE_APRIL_AFTER_GPU_GATE; NO_MAY_COEFFICIENT_DONOR',
                    power_authority=record(out/'MAY_PIPELINE/MAY_POWER_CONVERSION_AUDIT.json'))
    days = pd.date_range('2025-04-01', '2025-04-30').strftime('%Y-%m-%d').tolist()
    validate_date_axis(days)
    gates = []; ledger = []; records = []; initial_actual_missing = 0
    for day in days:
        snap = source_root/'V42_FINAL_LOCAL/policy_snapshots'/day/'D1_AIDC_SNAPSHOT.parquet'
        authority = read(PRIOR/('DAY_'+day.replace('-', ''))/'INPUT_AUTHORITY.json')
        checked(authority['snapshot'])
        frame = pd.read_parquet(snap, columns=['id', 'submit_time', 'state_at_issue', 'elapsed_seconds_at_issue', 'original_AIDC_site'])
        known = [dict(job_uid=str(r.id), submit_time=timestamp(r.submit_time).isoformat(),
                      state_at_D1_cutoff=r.state_at_issue,
                      elapsed_seconds=float(r.elapsed_seconds_at_issue) if pd.notna(r.elapsed_seconds_at_issue) else 0.,
                      source_site=r.original_AIDC_site if r.original_AIDC_site in capacities else None,
                      source_site_authority='CURRENT_PHYSICAL_SOURCE_SITE' if r.original_AIDC_site in capacities else None)
                 for r in frame.itertuples()]
        files = authority['files']
        for r in files.values():
            checked(r)
        forecast = read(files['aemo_forecast.json']['path'])
        af = pd.read_parquet(files['aemo_actual.parquet']['path'])
        fi = dict(complete=authority['forecast_causal'], AEMO=forecast,
                  weather_source=files['gfs_d1_weather.parquet'], CC4_bound=False,
                  CC4_authority='CURRENT_V42_Q50/Q90_AND_EXECUTION_LAG; DATE_BINDING_REQUIRED',
                  input_schema='96x15min; total regional MW; network allocation required')
        ai = dict(complete=authority['actual_grid_96_finite_aligned'],
                  load_PV_source=files['aemo_actual.parquet'], field_names=list(af.columns),
                  weather_source=files['noaa_actual_weather.parquet'], rows=len(af),
                  input_schema='96 interval-ending UTC instants; separate realized P/Q recomputation')
        planning, actual, gate, recovery = build_v42_day_input_bundle(day, known_snapshot=known,
            raw_requests=requests, actual_observations=observations, runtime_provider=provider,
            physical_authority=physical, forecast_inputs=fi, actual_inputs=ai)
        # Reconcile all populations with preserved PR121 source receipts.
        old_day = PRIOR/'APRIL_V42_INPUT_BUNDLE'/('DAY_'+day.replace('-', ''))
        old_planning = read(old_day/'PLANNING_INPUT_BUNDLE.json'); old_actual = read(old_day/'ACTUAL_INPUT_BUNDLE.json')
        for key, new_rows, old_rows in [('known_population', planning['known_population'], old_planning['known_population']),
                                       ('post_issue_arrivals', actual['post_issue_arrivals'], old_actual['post_issue_arrivals'])]:
            previous = {r['job_uid']:r for r in old_rows}
            assert {r['job_uid'] for r in new_rows} == set(previous), 'POPULATION_DROP_OR_ADD'
            for r in new_rows:
                old = previous[r['job_uid']]
                assert r['GPU_gang'] == old['GPU_gang'], 'GPU_IMMUTABLE_ATTRIBUTE_CHANGED'
                assert r['service_slots'] == old['service_slots'], 'CURRENT_RUNTIME_SERVICE_DRIFT'
                assert math_close(r['Q50_total_seconds'], old['Q50_total_seconds']), 'CURRENT_Q50_DRIFT'
        gate['source_population_reconciliation_PASS'] = True
        gate['historical_missing_exclusion_ported'] = False
        folder = 'APRIL/DAY_'+day.replace('-', '')
        write(out, folder+'/PLANNING_INPUT_BUNDLE.json', planning)
        write(out, folder+'/ACTUAL_INPUT_BUNDLE.json', actual)
        write(out, folder+'/INPUT_PROVENANCE.json', dict(day=day, snapshot=record(snap), archive=archive,
            request_projection=projections, daily_sources=files, provider_integrity=record(provider.root/'INTEGRITY.json'),
            immutable_rule='full UID + normalized submission instant; explicit positive raw request only',
            historical_missing_GPU_exclusion_superseded=True, request_version_history='UNVERIFIED_SOURCE_PROXY',
            May_request_payload_members_read=[], May_scientific_results_read=[], Runtime_fit_calls=0,
            runtime_row_event_causality_checked=True, actual_observations_in_Planning=False,
            preserved_PR121_day_evidence=record(old_day/'PLANNING_INPUT_BUNDLE.json')))
        write(out, 'B0/DAY_'+day.replace('-', '')+'/EXECUTION_STATUS.json', dict(status='NOT_RUN',
            reason='RETAINED_UNRESOLVED_PHYSICAL_GPU; FULL_MAY_FORENSIC_COMPLETED', flags=B0_FLAGS,
            V_PLAN=None, V_DA_AC=None, V_DDAY_AC=None, physical_PASS=None, served_jobs=None, served_GPUh=None,
            AIDC_IT_energy_kWh=None, AIDC_PCC_energy_kWh=None, active_AIDC_slots=None,
            Planning_calls=0, OpenDSS_calls=0, full_reoptimization=0, P_repair=0, Q_repair=0,
            route_repair=0, schedule_repair=0))
        gates.append(gate); ledger.extend(r for r in recovery if r['GPU_gang'] is None)
        records.append(dict(day=day, planning=record(out/(folder+'/PLANNING_INPUT_BUNDLE.json')),
            actual=record(out/(folder+'/ACTUAL_INPUT_BUNDLE.json')), gate=gate))
        # Initial Actual list is a subset of complete post-issue arrivals.
        daily = pd.read_parquet(files['kestrel_realized_jobs.parquet']['path'], columns=['id', 'submit_time', 'partition', 'gpus_requested'])
        start = pd.Timestamp(day+'T00:00:00+10:00'); end = start+pd.Timedelta(days=1)
        ids = set(daily.loc[daily.partition.astype(str).str.contains('h100', case=False, regex=False) &
            daily.gpus_requested.isna() & daily.submit_time.ge(start) & daily.submit_time.lt(end), 'id'].astype(str))
        initial_actual_missing += len(ids)
        assert ids <= {r['job_uid'] for r in actual['post_issue_arrivals'] if r['GPU_gang'] is None}
        print(day, 'known', gate['known_jobs'], 'Actual', gate['actual_post_issue_jobs'],
              'missing', gate['missing_known_GPU'], gate['missing_actual_GPU'], flush=True)
    counts = Counter(r['status'] for r in ledger)
    summary = dict(initial_known_missing=5173, initial_Actual_missing=initial_actual_missing,
        expanded_missing_observations=len(ledger), expanded_unique_jobs=len({r['job_uid'] for r in ledger}),
        recovered=0, unresolved=len(ledger), unresolved_statuses=dict(counts), ambiguous=counts['AMBIGUOUS_SOURCE_MATCH'],
        source_field_absent=counts['SOURCE_FIELD_ABSENT'], known_unresolved=sum(g['missing_known_GPU'] for g in gates),
        Actual_unresolved=sum(g['missing_actual_GPU'] for g in gates), complete_days=sum(g['PASS'] for g in gates),
        target_days=30, known_jobs=sum(g['known_jobs'] for g in gates), actual_post_issue_jobs=sum(g['actual_post_issue_jobs'] for g in gates),
        May_rule_identified=True, May_rule='raw positive gpus_requested; historical invalid row exclusion',
        May_missing_exclusion_ported=False, synthetic_fill=False, rows_dropped=0,
        current_Runtime_used=True, requested_walltime_service=False, May_job_values_used=False)
    assert summary['known_unresolved'] == 5173 and initial_actual_missing == 16284
    assert len(ledger) == 25632 and summary['expanded_unique_jobs'] == 16574
    table(out, 'APRIL/APRIL_DAY_INPUT_GATE.csv', gates, list(gates[0]))
    table(out, 'APRIL/APRIL_GPU_AUTHORITY_REPROCESS_LEDGER.csv', ledger, list(ledger[0]))
    write(out, 'APRIL/APRIL_GPU_AUTHORITY_SUMMARY.json', summary)
    write(out, 'APRIL/APRIL_INPUT_MANIFEST.json', dict(status='INCOMPLETE_NONEXECUTABLE_AFTER_FULL_MAY_FORENSIC',
        schema='V42_DAY_INPUT_BUNDLE_V1', date_axis=days, days=records, complete_days=summary['complete_days'],
        reusable_builder=record(ROOT/'v42_april_port/builder.py'), source_archive=archive,
        request_projection=projections, May_values_as_donor=False, science_executed_days=0))
    table(out, 'REFERENCE/V42_COMMON_REFERENCE_SCHEDULE.csv', [],
        ['day', 'job_uid', 'state_at_D1_cutoff', 'reference_site', 'reference_start', 'service_slots',
         'GPU_gang', 'runtime_authority', 'site_authority_source', 'start_authority_source', 'fallback_used', 'queue_rule', 'compatible_sites'])
    write(out, 'REFERENCE/V42_COMMON_REFERENCE_AUTHORITY.json', dict(status='NOT_GENERATED_INPUT_GATE_FAIL',
        scheduler=record(ROOT/'v42_april_b0_v2/reference.py'), generated_days=0, same_B0_B1_B2_B3_reference=True,
        grid_blind=True, deterministic=True, policy_independent=True, D1_causal=True,
        missing_historical_mapping_is_STOP_condition=False, historical_GPU_missing_exclusion_ported=False))
    return summary


def math_close(a, b):
    return a is not None and b is not None and np.isclose(a, b, rtol=1e-12, atol=1e-8)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, default=ROOT.parent)
    parser.add_argument('--output-root', type=Path, default=ROOT/'docs/v42_april_port_from_may_pipeline')
    args = parser.parse_args()
    print(json.dumps(run(args.source_root, args.output_root), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

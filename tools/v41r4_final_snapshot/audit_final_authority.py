"""Read-only archive/CSV integration audit; never imports scientific execution code.

Reads the compressed archive once, retaining only selected JSON authorities in
memory. Writes small evidence JSONs under --repo; never extracts or rewrites data.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import time

RAW = 'V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz'
RAW_SHA = '1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3'
METHOD = '710a50cd439a9bb42cc8e6ea77b47eb1a5536c37cef894456a0859aeae9db368'
CLASS = 'CSV_EXPORT_VALID_BUT_SCIENTIFIC_TERMINAL_BIAS_REQUIRES_PAPER_LIMITATION'
NA = 'NOT_AVAILABLE'
REV = 'frozen_artifacts/v41r4_restoration_revision_v1/'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def readj(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def readcsv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def span(parts, lo=-math.inf, hi=math.inf):
    intervals = sorted((float(x['start']), float(x['end'])) for x in parts)
    assert all(b >= a for a, b in intervals)
    assert all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:]))
    return math.fsum(max(0, min(b, hi) - max(a, lo)) for a, b in intervals)


def corr(a, b):
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    return sum((x-ma)*(y-mb) for x, y in zip(a, b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))


def rank(a):
    return [sum(v < x for v in a)+(sum(v == x for v in a)+1)/2 for x in a]


class HashReader:
    def __init__(self, handle):
        self.handle, self.digest = handle, hashlib.sha256()

    def read(self, size=-1):
        data = self.handle.read(size)
        self.digest.update(data)
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    repo, results = args.repo.resolve(), args.results.resolve()
    corrected = results/'MobileESS_V41R4_Paper_CSV_Export_corrected_20260909_112635'
    original = results/'MobileESS_V41R4_Paper_CSV_Export'
    deadline = corrected/'deadline_audit_20260909_115731'
    evidence = repo/'docs/v41r4_final/evidence/final_reaudit'
    m, dm = readj(corrected/'MANIFEST.json'), readj(deadline/'DEADLINE_AUDIT_MANIFEST.json')
    assert m['status'] == CLASS and dm['classification_name'] == 'DEADLINE_AUTHORITY_NOT_ESTABLISHED'
    tables, inventory, protected = {}, [], {}
    counts = [1, 124, 124, 124, 47616, 43392, 188036, 22, 4, 31, 124]
    for i, spec in enumerate(m['CSV_files']):
        part = spec['parts'][0]
        path = corrected/part['filename']
        data = path.read_bytes()
        protected[path] = sha(data)
        txt = data.decode('utf-8-sig', errors='strict')
        assert txt.encode('utf-8-sig') == data
        reader = csv.DictReader(io.StringIO(txt, newline=''))
        rows = list(reader)
        assert reader.fieldnames == spec['columns'] and len(set(reader.fieldnames)) == len(reader.fieldnames)
        assert len(rows) == counts[i] == part['row_count']
        assert all(None not in row and all(v is not None for v in row.values()) for row in rows)
        assert sha(data) == part['SHA256'] and len(data) == part['byte_size'] < 500_000_000
        special = collections.Counter(v for r in rows for v in r.values() if v in ('TRUE', 'FALSE', NA, 'NaN', 'nan', 'true', 'false', ''))
        assert not any(special[v] for v in ('nan', 'true', 'false', ''))
        # Preserve full binary64 values through representation/readback, including
        # undefined NaN separately from the unavailable/not-applicable sentinel.
        numeric = 0
        for row in rows:
            for value in row.values():
                try:
                    f = float(value)
                except ValueError:
                    continue
                if math.isfinite(f):
                    assert float(repr(f)) == f
                    numeric += 1
                else:
                    assert value == 'NaN'
        old = (original/path.name).read_bytes()
        if i:
            assert old == data, path.name
        else:
            oldrow = readcsv(original/path.name)[0]
            changes = {k: (oldrow[k], rows[0][k]) for k in rows[0] if oldrow[k] != rows[0][k]}
            assert changes == {'method_SHA': (NA, METHOD)}
        tables[i] = rows
        inventory.append(dict(filename=path.name, rows=len(rows), bytes=len(data), sha256=sha(data),
                              schema=reader.fieldnames, UTF8_roundtrip=True, numeric_roundtrips=numeric,
                              special_values=dict(special), identical_to_original=i != 0))
    assert len(list(corrected.glob('[0-9][0-9]_*.csv'))) == 11
    assert sum(x['bytes'] for x in inventory) == 86880591
    print('11 CSVs: schemas, counts, byte identities, UTF-8, numeric and sentinel checks PASS', flush=True)
    source_index = {x['source_inside_archive']: x for x in m['source_artifacts']}
    source_index.update(dm['raw_member_reads_verified_by_sha256'])
    wanted = {u['accepted_joint'] for u in m['unit_source_map']}
    wanted.update([REV+'FINAL_AUDIT.json', REV+'2025-05-31/B2/ACCEPTANCE.json', 'FINAL_RESULT_INDEX.json'])
    wanted.update(x['member'] for x in dm['boundary_audits'])
    wanted.update(x['archive_member'] for x in dm['method_source_hash_bindings'])
    wanted.update(k for k, v in source_index.items() if v['sha256'] == METHOD)
    assert all(k in source_index for k in wanted)
    archive = results/RAW
    before = archive.stat()
    assert before.st_size == 13524418762
    payload, bound = {}, []
    files, expanded, last = 0, 0, time.monotonic()
    with archive.open('rb') as handle:
        hashing = HashReader(handle)
        with tarfile.open(fileobj=hashing, mode='r|gz') as stream:
            for member in stream:
                p = PurePosixPath(member.name)
                assert member.isfile() and not p.is_absolute() and '..' not in p.parts and ':' not in member.name
                name = str(PurePosixPath(*p.parts[1:]))
                files += 1
                expanded += member.size
                if name in wanted:
                    assert name not in payload
                    data = stream.extractfile(member).read()
                    expected = source_index[name]
                    assert len(data) == expected['bytes'] and sha(data) == expected['sha256'], name
                    payload[name] = json.loads(data)
                    bound.append(dict(member=name, bytes=len(data), sha256=sha(data)))
                if time.monotonic()-last > 25:
                    print(f'Archive static read: {files} members, {expanded/1e9:.2f} GB uncompressed traversed', flush=True)
                    last = time.monotonic()
        while hashing.read(8*1024*1024):
            pass
        assert hashing.digest.hexdigest() == RAW_SHA
    after = archive.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert files == 69297 and expanded == 39106987471 and wanted == set(payload)
    audit = payload[REV+'FINAL_AUDIT.json']
    acceptance = payload[REV+'2025-05-31/B2/ACCEPTANCE.json']
    assert audit == readj(repo/'docs/v41r4_final/evidence/restoration/FINAL_AUDIT.json')
    assert acceptance == readj(repo/'docs/v41r4_final/evidence/restoration/2025-05-31/B2/ACCEPTANCE.json')
    assert audit['counts']['total_accepted'] == 124 and not audit['pending']
    keys = {(f'2025-05-{d:02d}', p) for d in range(1, 32) for p in ('B0','B1','B2','B3')}
    for i in (1, 2, 3, 10):
        assert {(r['day'],r['policy']) for r in tables[i]} == keys
    for row in tables[1]:
        assert row['DA_physically_feasible'] == 'TRUE' and int(row['DA_converged_slots']) == 96
        assert all(int(row[f'DA_{k}_violation_count']) == 0 for k in ('voltage','line','tx_current','tx_kVA'))
    for row in tables[2]:
        assert row['Actual_physically_feasible'] == 'TRUE' and int(row['Actual_converged_slots']) == 96
        assert all(int(row[f'Actual_{k}_violation_cells']) == 0 for k in ('voltage','line','tx_current','tx_kVA'))
        assert row['execution_cross_day_state_carried'] == 'FALSE'
    expected_final = dict(rho_max_AC=0.6319676083483373, Vmin_pu=0.9528912500659789,
                          Vmax_pu=1.049570015262741, transformer_phase_current_loading_max=0.9870033465393178,
                          transformer_total_kva_loading_max=0.9999903138843736, convergence_count=96)
    assert all(acceptance['final'][k] == v for k, v in expected_final.items())
    assert acceptance['status'] == 'PASS' and acceptance['full_PQ_fallback']
    assert acceptance['no_DA_optimization'] and acceptance['no_route_search']
    assert all(acceptance['old_identity'][k] == acceptance['new_identity'][k] for k in ('AIDC','route'))
    may31 = next(r for r in tables[1] if (r['day'],r['policy']) == ('2025-05-31','B2'))
    for csvkey, rawkey in [('DA_rho_max','rho_max_AC'),('DA_Vmin_pu','Vmin_pu'),('DA_Vmax_pu','Vmax_pu'),('DA_tx_current_max_pu','transformer_phase_current_loading_max'),('DA_tx_kVA_max_pu','transformer_total_kva_loading_max')]:
        assert float(may31[csvkey]) == acceptance['final'][rawkey]
    assert may31['full_PQ_fallback'] == 'TRUE'
    jobs = {(u['day'],u['policy']): {str(j['job_uid']): j for j in payload[u['accepted_joint']]['decision']['AIDC_decision']} for u in m['unit_source_map']}
    assert sum(len(v) for v in jobs.values()) == len(tables[6])
    flagged, extra = {}, collections.defaultdict(float)
    for row in tables[6]:
        day, policy, uid = row['day'], row['policy'], row['job_uid']
        job, ref = jobs[day,policy][uid], jobs[day,'B0'][uid]
        rt, ot = span(ref['compute_segments'],120), span(job['compute_segments'],120)
        assert float(row['reference_terminal_remaining_slots']) == rt
        assert float(row['optimized_terminal_remaining_slots']) == ot
        assert float(row['terminal_residual_delta_slots']) == ot-rt
        assert float(row['requested_GPU']) == job['requested_GPU']
        assert float(row['optimized_end_slot']) == job['end_slot']-24
        assert row['checkpoint_migrated'] == ('TRUE' if job.get('migration_selected',False) else 'FALSE')
        assert row['terminal_invariant_pass'] == ('FALSE' if ot > rt+1e-9 else 'TRUE')
        if job.get('migration_selected',False):
            assert span(job['compute_segments']) == span(ref['compute_segments'])
        if ot > rt+1e-9:
            assert job['migration_selected']
            assert span(job['compute_segments'],hi=24) == span(ref['compute_segments'],hi=24)
            assert span(ref['compute_segments'],24,120)-span(job['compute_segments'],24,120) == ot-rt
            event = job['migration_events'][0]
            cp, ts, te, re = [event[k] for k in ('checkpoint','transfer_start','transfer_end','restart_end')]
            assert 24 <= cp <= ts < te < re < 120 and re == te+1
            assert job['end_slot']-ref['end_slot'] == re-cp
            value = (ot-rt)*job['requested_GPU']/4
            flagged[day,policy,uid] = value
            extra[day,policy] += value
    assert len(flagged) == 619 and len({k[2] for k in flagged}) == 297 and len(extra) == 60
    assert collections.Counter(k[1] for k in flagged) == {'B1':306,'B3':313}
    denominator = {day: sum(span(j['compute_segments'],24,120)*j['requested_GPU']/4 for j in jobs[day,'B0'].values() if j['AIDC_site'] != 'UNASSIGNED') for day in sorted({k[0] for k in jobs})}
    assert len(tables[9]) == 31 and {r['day'] for r in tables[9]} == set(denominator)
    assert all(int(r['N_days']) == 31 for r in tables[8])
    policies = {}
    for policy, total, pe, sp in [('B1',15897.,.372677,.379829),('B3',16020.5,.109618,.077024)]:
        xs = [extra[r['day'],policy] for r in tables[9]]
        ys = [float(r[f'{policy}_improvement_pct_vs_B0']) for r in tables[9]]
        pearson, spearman = corr(xs,ys), corr(rank(xs),rank(ys))
        assert sum(xs) == total and abs(pearson-pe) < 1e-6 and abs(spearman-sp) < 1e-6
        policies[policy] = dict(records=sum(k[1]==policy for k in flagged), extra_GPUh=sum(xs),
            extra_pct_of_B0_D_day_GPUh=100*sum(xs)/sum(denominator.values()),
            maximum_daily_pct=100*max(extra[d,policy]/denominator[d] for d in denominator),
            P1_percent_improvement_correlation=dict(Pearson=pearson,Spearman=spearman,N=31))
    flagged_deadline = readcsv(deadline/'01_FLAGGED_619_DEADLINE_AUDIT.csv')
    migrations = readcsv(deadline/'02_ALL_MIGRATIONS_DEADLINE_AUDIT.csv')
    summary = readcsv(deadline/'03_DEADLINE_SUMMARY.csv')
    assert {(r['day'],r['policy'],r['job_uid']) for r in flagged_deadline} == set(flagged)
    raw_migrations = {(day,policy,uid) for (day,policy), js in jobs.items() for uid,j in js.items() if j.get('migration_selected',False)}
    assert len(migrations) == 677 and {(r['day'],r['policy'],r['job_uid']) for r in migrations} == raw_migrations
    assert collections.Counter(r['policy'] for r in migrations) == {'B1':333,'B3':344}
    for r in migrations:
        job = jobs[r['day'],r['policy']][r['job_uid']]
        assert json.loads(r['optimized_compute_segments']) == job['compute_segments']
        assert float(r['RW_completion_slot']) == job['RW_completion_slot']
        assert float(r['final_completion_slot']) == job['end_slot']
        assert r['candidate_job_specific_deadline_checked'] == 'FALSE'
        assert all(r[k] == NA for k in ('authoritative_deadline_slot','deadline_source','deadline_slack_slots','deadline_slack_hours','within_deadline'))
        assert float(r['additional_post_horizon_GPUh']) == flagged.get((r['day'],r['policy'],r['job_uid']),0)
    diagnostic = collections.Counter(r['policy'] for r in flagged_deadline if float(r['final_completion_slot']) > float(r['RW_completion_slot']))
    assert diagnostic == {'B1':192,'B3':196}
    assert sum(float(r['final_completion_slot']) > float(r['RW_completion_slot']) for r in migrations) == 412
    for r in summary:
        assert all(r[k] == NA for k in r if k in ('within_deadline','deadline_violations','maximum_violation_h') or 'slack' in k)
    for entry in dm['boundary_audits']:
        boundary = payload[entry['member']]
        assert boundary == entry['body'] and boundary['status'] == 'PASS'
        assert boundary['terminal_residual_constraint_active'] is False and boundary['service_neutrality_constraint_active'] is False
        assert boundary['issue_begin'] == 24 and boundary['issue_end_exclusive'] == 120 and boundary['grid_slots'] == 96
    method_checks = []
    for entry in dm['method_sources']:
        path = repo/entry['path']
        assert sha(path.read_bytes()) == entry['sha256']
        method_checks.append(dict(path=entry['path'],sha256=entry['sha256']))
    for entry in dm['method_source_hash_bindings']:
        assert entry['sha256'] in json.dumps(payload[entry['archive_member']])
    negative = {k: sum(float(r[k]) < 0 for r in tables[9]) for k in tables[9][0] if 'improvement_pct' in k}
    assert any(negative.values())
    nanrows = [r for r in tables[3] if r.get('mean_abs_delta_Q_changed_vehicle_slots_kvar') == 'NaN']
    assert nanrows and all(int(r['changed_Q_vehicle_slots']) == 0 for r in nanrows)
    assert all((r['mean_abs_delta_Q_changed_vehicle_slots_kvar'] == 'NaN') == (int(r['changed_Q_vehicle_slots']) == 0) for r in tables[3])
    ml = dict(source='07_ml_performance.csv',sha256=inventory[7]['sha256'],rows=22,
        review_scope='Static availability/scoping; stored numbers unchanged; no model execution.',
        runtime_population='40,335 matched pending job-day pairs; 6,209 unmatched/unavailable out of 46,544; repeated UIDs across days retained.',
        H4_population='2,511 windows = 31 independent days x 81 windows; raw forecast MAE, actionable reserve shortfalls.',
        traffic_population='72 deduplicated final selected B2/B3 route observations; operational performance only.',
        full_link_validation=NA,metrics=tables[7])
    assert sum(r['value'] == NA for r in tables[7]) == 4
    terminal = dict(classification=CLASS,records=619,unique_uids=297,affected_policy_days=60,
        all_checkpoint_migrated=True,all_677_migrations_total_planned_service_preserved=True,
        all_188036_csv_records_crosschecked_against_archived_segments=True,policies=policies,
        B0_scheduled_D_day_GPUh=sum(denominator.values()),exporter_bug=False,
        causal_contribution=NA,term='migration-induced post-horizon compute-service deferral',
        additional_terminal_invariant_part_of_frozen_migration_method=False,next_day_backlog_propagated=False)
    deadlines = dict(classification='DEADLINE_AUTHORITY_NOT_ESTABLISHED',flagged_records=619,unique_uids=297,
        migrations=dict(B1=333,B3=344,total=677),authoritative_deadline_available=0,
        candidate_job_specific_completion_deadline_checked=False,RW_is_deadline=False,
        RW_semantics='Requested-walltime based reference schedule completion quantity; diagnostic only.',
        diagnostic_completion_gt_RW=dict(flagged_B1=192,flagged_B3=196,flagged_total=388,all_migrations=412),
        within_deadline=NA,deadline_violations=NA,deadline_slack=NA,maximum_deadline_violation=NA,
        scope='Rechecked all 677 stored rows against raw decisions and frozen method source bindings. Prior authority search preserved by manifest hash; not rerun.',
        method_sources_verified=method_checks)
    provenance = []
    for path in [corrected/'MANIFEST.json',corrected/'CSV_REAUDIT_REPORT.md',deadline/'DEADLINE_AUDIT_MANIFEST.json'] + list(deadline.glob('*.csv')) + list(deadline.glob('*.md')):
        data = path.read_bytes()
        protected[path] = sha(data)
        provenance.append(dict(local_path=str(path),bytes=len(data),sha256=sha(data)))
    for part in dm['output_files']:
        assert sha((deadline/part['filename']).read_bytes()) == part['sha256']
    # Bind the retained local reports/manifests to the previously staged catalogs.
    for name in ('CORRECTED_EXPORT_INDEX.json','DEADLINE_AUDIT_INDEX.json'):
        index = readj(repo/'docs/v41r4_final/evidence/posthoc'/name)
        local = index['full_local_manifest']
        assert sha(Path(local['path']).read_bytes()) == local['sha256']
    assert all(sha(p.read_bytes()) == digest for p,digest in protected.items())
    zeros = {k:0 for k in ('Gurobi','DA_optimization','B1_B3_reoptimization','OpenDSS','Actual','Q_search','SUMO','ML','ML_training','ML_inference_regeneration','route_search','checkpoint_domain_regeneration')}
    authority = dict(status='V41R4_FINAL_PAPER_DATA_AUTHORITY_PASS',
        projection_status='PAPER_DATA_PROJECTION_PASS_WITH_COMPUTE_DEFERRAL_LIMITATION',
        audited_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
        audited_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        campaign=dict(days=31,policies=['B0','B1','B2','B3'],policy_days=124,accepted=124,pending=0,status='PASS_124_OF_124'),
        raw_archive=dict(filename=RAW,bytes=before.st_size,sha256=RAW_SHA,local_path=str(archive),read_only=True,mtime_ns_unchanged=True),
        corrected_csv=dict(local_path=str(corrected),files=inventory,total_bytes=86880591,status='PASS_AFTER_METADATA_CORRECTION'),
        metadata_correction=dict(file='00_experiment_authority.csv',field='method_SHA',old_value=NA,new_value=METHOD,other_ten_byte_identical=True),
        terminal_reaudit=dict(records=619,unique_uids=297,B1_records=306,B3_records=313,B1_extra_GPUh=15897.,B3_extra_GPUh=16020.5,classification=CLASS,status='REAL_DEFERRAL_QUANTIFIED'),
        deadline_audit=dict(authoritative_deadline_available=0,deadline_compliance_claimed=False,RW_is_deadline=False,classification='DEADLINE_AUTHORITY_NOT_ESTABLISHED',status='AUTHORITY_NOT_ESTABLISHED_NO_COMPLIANCE_CLAIM'),
        paper_interpretation=dict(workload_class='BEST_EFFORT_LATENCY_TOLERANT_BATCH',service_neutral_claim=False,deadline_claim=False,next_day_backlog_propagated=False,continuous_backlog_status='NOT_EVALUATED_INDEPENDENT_DAILY_EPISODES'),
        May31_B2=dict(final_status='PASS',resolved=True,full_PQ_fallback=True,convergence=96,violations=dict(voltage=0,line=0,transformer_current=0,transformer_kVA=0),metrics=expected_final,AIDC_identity_unchanged=True,route_identity_unchanged=True,DA_optimization_calls=0,route_search_reruns=0),
        reexecution_counts=zeros,local_evidence=provenance,
        verification=dict(archive_members_traversed=files,archive_uncompressed_bytes=expanded,selected_raw_JSON_authorities_verified=len(bound),raw_extraction=False,paired_denominator_days=31,negative_improvement_counts=negative,undefined_Q_mean_rows=len(nanrows),method_source_hash_bindings=len(dm['method_source_hash_bindings']),day_boundary_audits=62,ML_scope_review=True),
        historical_export_status='FAIL_CLOSED under additional terminal invariant; historical evidence unchanged')
    evidence.mkdir(parents=True,exist_ok=True)
    for name, value in [('FINAL_PAPER_DATA_AUTHORITY',authority),('TERMINAL_INTERPRETATION_SUMMARY',terminal),('DEADLINE_AUTHORITY_SUMMARY',deadlines),('ML_METRIC_SCOPE_SUMMARY',ml),('RAW_AUTHORITY_BINDINGS',dict(files=bound))]:
        (evidence/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=authority['status'],raw_authorities=len(bound),terminal=policies,negative_results=negative),indent=2),flush=True)


if __name__ == '__main__':
    main()

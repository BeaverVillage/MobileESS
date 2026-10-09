"""Copy selected Source35 deployment evidence; no scientific imports or producers."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import collections

REPO = Path('D:/MobileESS_v42_autonomous')
ROOT = Path('D:/v42_may_restart_20261010_02')
AUTO = ROOT / 'autonomous'
DEST = REPO / 'docs/v42_autonomous_may_20261010/SOURCE35/DEPLOYMENT'
SELF = Path(__file__).resolve()

def utc():
    return datetime.now(timezone.utc).isoformat()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def identity(raw):
    return {'bytes': len(raw), 'sha256': sha(raw)}

def tree_records(path):
    return {p.relative_to(path).as_posix(): identity(p.read_bytes())
            for p in sorted(path.rglob('*')) if p.is_file()}

preserved = {name: tree_records(DEST.parent/name) for name in ('DIAGNOSIS','PRICE_REVIEW')}
assert not DEST.exists(), 'NEW_DESTINATION_REQUIRED'
DEST.mkdir(parents=True)
provenance = []
copied = {}

def raw_copy(source, relative, kind, expected=None, stable=True):
    source = Path(source)
    captured = utc()
    raw = source.read_bytes()  # One read supplies both copied bytes and receipt.
    record = identity(raw)
    if expected:
        for key in ('bytes','sha256'):
            assert record[key] == expected[key], (source, key)
    target = DEST / relative
    assert target.resolve().is_relative_to(DEST.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as out:
        out.write(raw)
    assert target.read_bytes() == raw
    if stable:
        assert source.read_bytes() == raw, 'SOURCE_BYTES_CHANGED_DURING_COPY'
    provenance.append(dict(source_path=str(source), copied_path=relative,
                           capture_UTC=captured, kind=kind, **record,
                           stable_source_rechecked=stable))
    copied[relative] = raw
    return raw

def generated(name, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    with (DEST/name).open('xb') as out:
        out.write(raw)
    return identity(raw)

expected_prefixes = {
    'V35_VALIDATION_BINDING_TEMPLATE.json':'2475a9d9',
    'V35_SPARSE_IMMUTABLE_FREEZE.json':'60321b4e',
    'V35_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json':'d5768c62',
    'V35_ZERO_START_RETRY_PREPARATION.json':'5a4f6de7',
    'V35_VERIFIED_REPAIR_VALIDATION.json':'01176f37',
    'SOURCE35_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json':'efbf94a6',
    'CODEX_HOURLY_AUTOMATION_VERIFICATION_20261009T234413.json':'c98892ba',
}
for name in (*expected_prefixes, 'V35_ZERO_START_RETRY_DEPLOYMENT.json'):
    raw = raw_copy(AUTO/name, 'producer_receipts/'+name, 'SAVED_ROOT_PRODUCER_RECEIPT')
    if name in expected_prefixes:
        assert sha(raw).startswith(expected_prefixes[name]), (name, sha(raw))

manifest_raw = raw_copy(ROOT/'B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json',
    'producer_receipts/B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json', 'SEALED_DEPLOYMENT_MANIFEST')
assert sha(manifest_raw) == '99259edd8bcadba56155b9e30f3b26208ea84a9e2b35f9f36f2edd801ba05cd4'
manifest = json.loads(manifest_raw)
assert manifest['source_commit'] == '810f98a5da7eb09f61354bbfa67bc3945951f0d7'
assert len(manifest['execution_sources']) == 99
assert manifest['execution_SHA'] == 'a8cb6983fdda381987116936c9a402330111223547abaa64b51408f807ad6a14'

authorization = manifest['reset_authorization']
raw_copy(authorization['path'], 'producer_receipts/USER_ZERO_START_RETRY_AUTHORIZATION.json',
         'IMMUTABLE_USER_FRESH_ZERO_AUTHORIZATION', authorization)
baseline = json.loads(copied['producer_receipts/SOURCE35_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json'])
for key, row in baseline['source32_workers'].items():
    raw_copy(row['ledger_snapshot']['path'], 'continuity_baseline/'+Path(row['ledger_snapshot']['path']).name,
             'SAVED_PRE_ENQUEUE_SOURCE32_RAW_NATIVE_LEDGER', row['ledger_snapshot'])

preparation = json.loads(copied['producer_receipts/V35_ZERO_START_RETRY_PREPARATION.json'])
request_checks = []
for day, slots in sorted(preparation['requests_by_day_and_slot'].items()):
    for slot, receipt in sorted(slots.items()):
        relative = f'sealed_requests/{day}/slot_{slot}/request.json'
        raw = raw_copy(receipt['path'], relative, 'SEALED_SOURCE35_FRESH_REQUEST', receipt)
        request = json.loads(raw)
        assert request['day'] == day and request['worker_slot'] == int(slot)
        assert request['implementation_SHA'] == manifest['execution_SHA']
        assert request['manifest_SHA'] == sha(manifest_raw)
        assert request['restart_from_zero'] is True and request['previous_attempts'] == []
        request_checks.append(dict(day=day, slot=int(slot), copied_path=relative, **identity(raw)))
assert len(request_checks) == 27

helper_names = ('build_v35_validation_template.py', 'freeze_sparse_v35.py',
                'smoke_sparse_v35.py', 'prepare_verified_v35_zero_start_retries.py',
                'capture_source35_pre_enqueue_continuity.py')
for name in helper_names:
    raw_copy(AUTO/name, 'producer_helpers/'+name, 'PRODUCER_HELPER_RAW_BYTES_NOT_EXECUTED_BY_PACKAGER')
for name in ('watch_source35_first_three_native.py', 'PR_BODY_V35.md'):
    raw_copy(AUTO/name, 'selected_operations/'+name, 'SELECTED_SAVED_OPERATIONAL_SOURCE')
raw_copy('D:/v42_source35_independent_review_20261010_01/SOURCE35_OPS_HELPERS_STATIC_READONLY_REVIEW.json',
         'producer_helpers/SOURCE35_OPS_HELPERS_STATIC_READONLY_REVIEW.json',
         'SAVED_STATIC_HELPER_REVIEW_NOT_ACTUAL_DEPLOYMENT_AUDIT')

lease_raw = raw_copy(ROOT/'REPAIR_LEASE.json', 'live_snapshots/REPAIR_LEASE_CAPTURE.json',
                     'LIVE_LEASE_SINGLE_READ_SNAPSHOT', stable=False)
lease = json.loads(lease_raw)
assert lease['token'] == 'ae7e1dc7dabe4431841c30ae011a0289'
assert lease['state'] == 'RELEASED'
queue_start = utc()
queue_raw = raw_copy(ROOT/'RECOVERY_QUEUE.json', 'live_snapshots/RECOVERY_QUEUE_CAPTURE.json',
                     'LIVE_QUEUE_SINGLE_READ_SNAPSHOT_NOT_ENQUEUE_TIME', stable=False)
queue_end = utc()
queue = json.loads(queue_raw)
deployment = json.loads(copied['producer_receipts/V35_ZERO_START_RETRY_DEPLOYMENT.json'])
queue_ids = [x['queue_id'] for x in deployment['queues']]
rows = [x for x in queue['entries'] if x.get('queue_id') in queue_ids]
assert len(rows) == 9 and len(set(x['queue_id'] for x in rows)) == 9
queue_states = collections.Counter(x['verification_status'] for x in rows)
snapshot_observation = dict(
    schema='V42_SOURCE35_DOCS_PACKAGING_OBSERVATION', UTC=utc(), PASS=True,
    verification_scope='Raw-byte preservation, declared receipt/request SHA matching and snapshot labels only.',
    deployment_receipt_UTC=deployment['UTC'], deployment_recorded_READY_count=9,
    deployment_recorded_priority_first_three=1000, deployment_recorded_other_six=100,
    deployment_recorded_initial_Native=0.0, deployment_recorded_budget_seconds=5400,
    current_queue_capture_start_UTC=queue_start, current_queue_capture_end_UTC=queue_end,
    current_queue_snapshot=identity(queue_raw), current_source35_entry_status_counts=dict(queue_states),
    current_source35_entries=[dict(queue_id=x['queue_id'], day=x['date'],
                                  verification_status=x['verification_status']) for x in rows],
    lease_capture=identity(lease_raw), lease_token=lease['token'], lease_state=lease['state'],
    lease_released_UTC=lease['released_UTC'],
    sealed_requests_SHA_and_fresh_fields_rechecked=request_checks,
    parent_reported_independent_deployment_audit_path='D:/v42_source35_deployment_independent_audit_20261010_01',
    independent_actual_deployment_audit_added=False,
    final_root_README_and_inventory_left_for_parent=True,
    ROOT_producer_helpers_executed_by_packager=False,
    Native_optimize_calls=0, real_Native_model_constructions=0,
    live_queue_manifest_worker_or_process_mutations=0, Git_mutations=0,
    actual_Source35_performance_or_date_PASS_claimed=False,
    prior_DIAGNOSIS_and_PRICE_REVIEW_bytes_unchanged=True,
    limitations=[
        'Preparation Native/model-denied PASS records admissions at their producer time; no admission was rerun.',
        'Nine READY entries are recorded by the completed enqueue receipt; the later raw queue snapshot is separately timestamped.',
        'The static helper review is not the pending independent actual deployment audit.',
        'No actual Source35 scientific outcome or scheduled hourly run is inferred from these qualification/configuration records.',
    ])
generated('PACKAGING_OBSERVATION.json', snapshot_observation)

readme = '''# Source35 deployment raw packaging

This initial package preserves the completed Root enqueue receipt dated 2026-10-09T23:43:29.107706+00:00, its sealed Source35 manifest, validation/preparation/freeze/smoke/template records, the prior Source32 worker and Native ledger baseline, all 27 sealed fresh requests, the user zero-start authorization, the five producer helpers, the saved static helper review, and the saved hourly configuration verification.

The completed enqueue producer recorded nine READY repairs: May01–03 priority1000 and May04–09 priority100, each new attempt starting at Native0 with a5400-second budget. The later queue and lease raw copies are single-read live snapshots with their own capture times in PACKAGING_OBSERVATION.json and PROVENANCE_SHA_INDEX.json. They are not represented as earlier enqueue-time observations. Existing historical results and ledgers remain separate from the new requests.

The saved hourly verification records ACTIVE configuration and no actual scheduled run observed. Model/native-denied admissions and335-test qualification are not actual date PASS or measured Source35 performance. No producer helper, admission, Native solve, or model construction was executed for this copying task. No live queue, manifest, worker, process, scientific source or Git state was mutated.

The independent actual deployment audit and the final Root README/inventory are intentionally left for Root to add when that audit completes. This package makes no independent whole-deployment or actual scientific PASS claim. Prior SOURCE35/DIAGNOSIS and PRICE_REVIEW packages were hashed before and after and left unchanged.

PROVENANCE_SHA_INDEX.json binds every raw copy to its exact source path and bytes. PACKAGING_SHA_INVENTORY.json binds this initial package, excluding only itself. Producer JSON, Python, request and ledger bytes were copied without normalization. preserve_deployment_docs.py is this standard-library file-copy script; producer_helpers are preserved source files and were not run by it.
'''
with (DEST/'PACKAGING_README.md').open('xb') as out:
    out.write(readme.encode('utf-8'))
raw_copy(SELF, 'preserve_deployment_docs.py', 'THIS_STANDARD_LIBRARY_DOC_COPY_SCRIPT')
generated('PROVENANCE_SHA_INDEX.json', dict(schema='V42_RAW_BYTE_COPY_PROVENANCE_V1',
    UTC=utc(), PASS=True, records=provenance, copied_raw_file_count=len(provenance)))
for name, before in preserved.items():
    assert tree_records(DEST.parent/name) == before, 'PRIOR_PACKAGE_CHANGED'
inventory_records = tree_records(DEST)
inventory = generated('PACKAGING_SHA_INVENTORY.json', dict(
    schema='V42_INITIAL_SOURCE35_DEPLOYMENT_PACKAGING_INVENTORY_V1', UTC=utc(),
    PASS=True, final_root_inventory_pending=True, files=inventory_records,
    excludes_only='PACKAGING_SHA_INVENTORY.json'))
for relative, expected in inventory_records.items():
    assert identity((DEST/relative).read_bytes()) == expected
print(json.dumps(dict(PASS=True, path=str(DEST), raw_copies=len(provenance),
    file_count=len(inventory_records)+1, total_bytes=sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()),
    inventory=inventory, provenance=identity((DEST/'PROVENANCE_SHA_INDEX.json').read_bytes()),
    current_source35_queue_states=dict(queue_states), previous_packages_unchanged=True,
    actual_independent_deployment_audit_pending=True), indent=2))

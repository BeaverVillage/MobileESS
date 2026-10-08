"""Native=0 admission tests using disposable 62-date input receipts only."""
from pathlib import Path
import shutil
import uuid

import pytest

from v42_may_campaign import common, coordinator, execution
from v42_may_campaign.common import atomic, read, record, sha


def freeze_inputs(root, manifest):
    manifest['inputs'] = {path.relative_to(root).as_posix(): record(path)
                          for path in sorted((root / 'inputs').rglob('*')) if path.is_file()}


def save(root, manifest):
    atomic(root / 'CAMPAIGN_MANIFEST.json', manifest)
    return root / 'CAMPAIGN_MANIFEST.json'


@pytest.fixture
def manifest_fixture():
    base = common.ROOT / 'tmp/v42_may_campaign_manifest_tests'
    base.mkdir(parents=True, exist_ok=True)
    root = base / uuid.uuid4().hex
    root.mkdir()
    manifest = dict(schema='V42_MAY_B1_B2_P1_CAMPAIGN_V1', run_id='FAKE_NATIVE_ZERO_' + root.name,
        axis=[dict(arm=a, day=d) for a, d in common.AXIS], frozen=True,
        policy=dict(Threads=1, wall_seconds=5400, native_seconds=5400, P2_calls=0,
                    failed_date_retries=0, B1_gap=.005, B2_gap=.03,
                    B1_parallel_workers=1, B2_parallel_workers=3),
        sources={name: sha(common.ROOT / name) for name in common.required_source_names()},
        input_folders={}, gates={})
    for arm, day in common.AXIS:
        folder = root / 'inputs' / arm / day
        folder.mkdir(parents=True)
        atomic(folder / 'NATIVE_INPUT.json', dict(arm=arm, day=day, fixture_only=True, Native_calls=0))
        atomic(folder / 'INPUT_IDENTITY.json', dict(PASS=True, arm=arm, day=day, fixture_only=True,
                                                   bundle=record(folder / 'NATIVE_INPUT.json')))
        manifest['input_folders'][arm + '/' + day] = str(folder)
        if arm == 'B2':
            physical = folder / 'PLANNING_PHYSICAL.npz'
            physical.write_bytes(b'FAKE_NATIVE_ZERO_PHYSICAL_INPUT')
            atomic(folder / 'B2_FIXED_AIDC.json', dict(
                identity=dict(PASS=True, arm=arm, day=day, AIDC_optimization_calls=0,
                              B0_B1_schedule_result_reads=0, fixture_only=True), physical=record(physical)))
    freeze_inputs(root, manifest)
    for name in common.REQUIRED_GATES:
        path = root / 'gate_fixtures' / (name + '.json')
        atomic(path, dict(PASS=True, Native_calls=0, fixture_only=True))
        manifest['gates'][name] = dict(status='PASS', **record(path))
    save(root, manifest)
    try:
        yield root, manifest
    finally:
        assert root.resolve().is_relative_to(base.resolve())
        shutil.rmtree(root)


def test_complete_62_file_identity_source_gate_manifest_admits_read_only_scope(manifest_fixture):
    root, manifest = manifest_fixture
    assert common.verify_manifest(root / 'CAMPAIGN_MANIFEST.json') == manifest
    request_path, request = coordinator.new_request(root, manifest, 'B1', common.DAYS[0])
    with execution.worker_scope(request):
        assert execution.authorize(request['day'], 'P1') == request['day']
    assert execution.current() is None


@pytest.mark.parametrize('missing', ['all', 'v42_may_campaign/worker.py', 'v42_m1_anytime/algorithms.py'])
def test_omitted_campaign_or_original_scientific_sources_cannot_disable_sha_gate(manifest_fixture, missing):
    root, manifest = manifest_fixture
    if missing == 'all':
        manifest['sources'] = {}
    else:
        del manifest['sources'][missing]
    with pytest.raises(PermissionError, match='COMPLETE_CAMPAIGN_AND_SCIENTIFIC_SOURCE_SHA'):
        common.verify_manifest(save(root, manifest))


def test_source_sha_drift_is_rejected_without_modifying_scientific_source(manifest_fixture):
    root, manifest = manifest_fixture
    manifest['sources']['v42_may_campaign/worker.py'] = '0' * 64
    with pytest.raises(PermissionError, match='CAMPAIGN_SOURCE_DRIFT'):
        common.verify_manifest(save(root, manifest))


@pytest.mark.parametrize('missing', ['all', 'inputs/B1/2025-05-01/NATIVE_INPUT.json',
                                    'inputs/B2/2025-05-01/PLANNING_PHYSICAL.npz'])
def test_empty_or_omitted_input_file_receipts_cannot_disable_input_sha_gate(manifest_fixture, missing):
    root, manifest = manifest_fixture
    if missing == 'all':
        manifest['inputs'] = {}
    else:
        del manifest['inputs'][missing]
    with pytest.raises(PermissionError, match='INPUT_RECEIPTS|INPUT_FILE_SHA_SET|B2_PHYSICAL_RECEIPT|INPUT_IDENTITY_LINK'):
        common.verify_manifest(save(root, manifest))


def test_duplicate_input_receipts_are_rejected(manifest_fixture):
    root, manifest = manifest_fixture
    manifest['inputs']['duplicate'] = manifest['inputs']['inputs/B1/2025-05-01/NATIVE_INPUT.json']
    with pytest.raises(PermissionError, match='DUPLICATE_FROZEN_INPUT_RECEIPT'):
        common.verify_manifest(save(root, manifest))


def test_new_unfrozen_file_and_modified_input_bytes_are_rejected(manifest_fixture):
    root, manifest = manifest_fixture
    folder = root / 'inputs/B1/2025-05-01'
    extra = folder / 'UNFROZEN.json'
    atomic(extra, dict(fixture_only=True))
    with pytest.raises(PermissionError, match='EXACT_ALL_62_INPUT_FILE_SHA_SET'):
        common.verify_manifest(root / 'CAMPAIGN_MANIFEST.json')
    extra.unlink()
    atomic(folder / 'NATIVE_INPUT.json', dict(arm='B1', day='2025-05-01', TAMPERED=True, fixture_only=True))
    with pytest.raises(PermissionError, match='CAMPAIGN_INPUT_DRIFT'):
        common.verify_manifest(root / 'CAMPAIGN_MANIFEST.json')


def test_b1_folder_cannot_be_used_for_b2_even_when_it_has_frozen_receipts(manifest_fixture):
    root, manifest = manifest_fixture
    manifest['input_folders']['B2/2025-05-01'] = manifest['input_folders']['B1/2025-05-01']
    with pytest.raises(PermissionError, match='EXACT_ARM_DATE_INPUT_FOLDER'):
        common.verify_manifest(save(root, manifest))


def test_refreezing_wrong_day_identity_does_not_admit_cross_date_input(manifest_fixture):
    root, manifest = manifest_fixture
    atomic(root / 'inputs/B2/2025-05-01/INPUT_IDENTITY.json',
           dict(PASS=True, arm='B2', day='2025-05-02', fixture_only=True))
    freeze_inputs(root, manifest)
    with pytest.raises(PermissionError, match='FROZEN_INPUT_ARM_DATE_IDENTITY_DRIFT'):
        common.verify_manifest(save(root, manifest))


def test_b2_fixed_physical_receipt_cannot_reference_another_date(manifest_fixture):
    root, manifest = manifest_fixture
    fixed_path = root / 'inputs/B2/2025-05-01/B2_FIXED_AIDC.json'
    fixed = read(fixed_path)
    fixed['physical'] = record(root / 'inputs/B2/2025-05-02/PLANNING_PHYSICAL.npz')
    atomic(fixed_path, fixed)
    freeze_inputs(root, manifest)
    with pytest.raises(PermissionError, match='FROZEN_B2_PHYSICAL_RECEIPT'):
        common.verify_manifest(save(root, manifest))


def test_native_input_wrong_day_is_denied_even_after_hashes_are_refrozen(manifest_fixture):
    root, manifest = manifest_fixture
    folder = root / 'inputs/B1/2025-05-01'
    native = folder / 'NATIVE_INPUT.json'
    atomic(native, dict(arm='B1', day='2025-05-02', fixture_only=True))
    identity = read(folder / 'INPUT_IDENTITY.json')
    identity['bundle'] = record(native)
    atomic(folder / 'INPUT_IDENTITY.json', identity)
    freeze_inputs(root, manifest)
    with pytest.raises(PermissionError, match='FROZEN_NATIVE_INPUT_DAY_ARM_DRIFT'):
        common.verify_manifest(save(root, manifest))


def test_missing_required_input_file_is_denied_even_if_remaining_inventory_matches(manifest_fixture):
    root, manifest = manifest_fixture
    (root / 'inputs/B1/2025-05-01/NATIVE_INPUT.json').unlink()
    freeze_inputs(root, manifest)
    with pytest.raises(PermissionError, match='REQUIRED_ARM_DATE_INPUT_FILES_MISSING'):
        common.verify_manifest(save(root, manifest))


def test_unfrozen_missing_gate_and_p2_policy_are_denied_before_worker_scope(manifest_fixture):
    root, manifest = manifest_fixture
    request_path, request = coordinator.new_request(root, manifest, 'B1', common.DAYS[0])
    manifest['inputs'] = {}
    save(root, manifest)
    with pytest.raises(PermissionError, match='COMPLETE_FROZEN_INPUT_RECEIPTS'), execution.worker_scope(request):
        pytest.fail('Worker scope must not open before complete frozen inputs')
    assert execution.current() is None
    manifest['frozen'] = False
    with pytest.raises(PermissionError, match='ALL_NEW_CAMPAIGN_GATES_REQUIRED'):
        common.verify_manifest(save(root, manifest))
    manifest['frozen'] = True
    manifest['policy']['P2_calls'] = 1
    with pytest.raises(PermissionError, match='CAMPAIGN_POLICY_DRIFT'):
        common.verify_manifest(save(root, manifest))


def test_read_only_monitor_can_inspect_unfrozen_placeholder_without_opening_worker_scope(manifest_fixture):
    root, manifest = manifest_fixture
    manifest.update(sources={}, inputs={}, frozen=False, gates={})
    assert common.verify_manifest(save(root, manifest), require_preflight=False) == manifest
    with pytest.raises(PermissionError, match='COMPLETE_CAMPAIGN_AND_SCIENTIFIC_SOURCE_SHA'):
        common.verify_manifest(root / 'CAMPAIGN_MANIFEST.json')


@pytest.mark.parametrize('policy,value', [('B1_parallel_workers', 3), ('B2_parallel_workers', 1),
                                          ('B2_parallel_workers', 4), ('Threads', 3)])
def test_exact_parallel_policy_required_before_authorization(manifest_fixture, policy, value):
    root, manifest = manifest_fixture
    manifest['policy'][policy] = value
    with pytest.raises(PermissionError, match='CAMPAIGN_POLICY_DRIFT'):
        common.verify_manifest(save(root, manifest))


def test_parallel_b2_gate_is_mandatory(manifest_fixture):
    root, manifest = manifest_fixture
    assert len(common.REQUIRED_GATES) == 10
    del manifest['gates']['PARALLEL_B2']
    with pytest.raises(PermissionError, match='ALL_NEW_CAMPAIGN_GATES_REQUIRED'):
        common.verify_manifest(save(root, manifest))


@pytest.mark.parametrize('arm,slot', [('B1', 2), ('B1', 3), ('B2', 0), ('B2', 4),
                                     ('B2', True), ('B2', None)])
def test_worker_scoped_parallel_permit_rejects_invalid_slot(manifest_fixture, arm, slot):
    root, manifest = manifest_fixture
    _, request = coordinator.new_request(root, manifest, arm, common.DAYS[0])
    request['worker_slot'] = slot
    with pytest.raises(PermissionError, match='WORKER_SLOT_REQUIRED'), execution.worker_scope(request):
        pytest.fail('Invalid worker slot must not open a scientific permit')
    assert execution.current() is None


def test_b2_third_slot_scoped_permit_stays_p1_and_own_date(manifest_fixture):
    root, manifest = manifest_fixture
    _, request = coordinator.new_request(root, manifest, 'B2', common.DAYS[0])
    request['worker_slot'] = 3
    with execution.worker_scope(request):
        assert execution.current()['worker_slot'] == 3
        assert execution.authorize(request['day'], 'P1') == request['day']
        with pytest.raises(PermissionError, match='P1_ONLY'):
            execution.authorize(request['day'], 'P2')
        with pytest.raises(PermissionError, match='DATE_CONFLICT'):
            execution.authorize(common.DAYS[1], 'P1')
        with pytest.raises(PermissionError, match='AIDC_OPTIMIZATION_FORBIDDEN'):
            execution.authorize(request['day'], 'A1')

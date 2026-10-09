import json
from pathlib import Path
from v42_b2_monitor_v18 import monitor


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


def fixture(tmp_path):
    root=tmp_path
    rows={f'{arm}/2025-05-{n:02d}':dict(arm=arm,day=f'2025-05-{n:02d}',
        status='PASS' if arm=='B1' else 'RUNNING' if n==1 else 'HELD_FOR_CANARY')
        for arm in ('B1','B2') for n in range(1,32)}
    attempt=root/'dates/B2/2025-05-01/attempts/new'
    request=dict(arm='B2',day='2025-05-01',worker_slot=1,started_UTC='2026-10-09T13:00:00+00:00',
        progress=str(attempt/'progress.json'),result=str(attempt/'RESULT.json'),output=str(attempt/'output'),
        attempt_id='new',implementation_SHA='source17')
    write(attempt/'request.json',request)
    write(attempt/'progress.json',dict(worker={},Native_Runtime=3500,Native_Runtime_completed=3400,
        Native_incumbent=.64,Native_BestBd=.31,Native_Gap=.515625,Native_SolCount='UNKNOWN',
        Native_first_incumbent_Runtime=12.12,phase='M_SAME_DAY_P1_INTEGER_SEED',
        # Unsealed progress values must never impersonate independent certificates.
        UB=.64,independent_Global_LB=.63,certified_gap=.015625))
    write(attempt/'NATIVE_RUNTIME_LEDGER.json',dict(measured_Native_Runtime=3400,calls=[],
        inflight=dict(track='M_SEED'),prior_attempt=dict(Native_Runtime=3318.513)))
    write(root/'CHECKPOINT_V17.json',dict(state='CANARY_READY',dates=rows,
        workers={'2025-05-01':dict(request=str(attempt/'request.json'))}))
    write(root/'CONTINUATION_V17_MANIFEST.json',dict(schema='B2_SEED_RECOVERY_V17_20261009',
        run_id='run',execution_SHA='source17',prior_attempts={
        '2025-05-02':dict(Native_Runtime=3285.426),'2025-05-03':dict(Native_Runtime=3316.044)}))
    return root,attempt


def test_native_fields_and_prior_runtime_never_become_certified_bounds(tmp_path):
    root,_=fixture(tmp_path)
    value=monitor.view(root);w=value['workers'][0]
    assert w['UB'] is None and w['independent_Global_LB'] is None
    assert not w['global_gap_display']['available']
    assert w['native_diagnostics']['Native_incumbent']==.64
    assert w['native_diagnostics']['Native_SolCount']=='UNKNOWN'
    assert w['native_diagnostics']['diagnostic_only']
    assert w['reported_native_runtime_seconds']==3500
    assert w['reported_native_remaining_seconds']==1900
    assert w['prior_native_runtime_seconds']==3318.513
    assert value['worker_slots'][1]['Native_Runtime_seconds']==3285.426
    assert value['worker_slots'][2]['native_remaining_seconds']==5400-3316.044
    assert value['B1']['PASS']==31 and len(value['actual_comparison']['rows'])==31
    assert value['source_SHA']=='source17' and not value['canary_PASS']


def test_mismatched_callback_epoch_uses_completed_ledger(tmp_path):
    root,attempt=fixture(tmp_path)
    p=json.loads((attempt/'progress.json').read_text())
    p['Native_Runtime_completed']=3399
    write(attempt/'progress.json',p)
    w=monitor.view(root)['workers'][0]
    assert w['reported_native_runtime_seconds']==3400
    assert w['native_runtime_basis']=='COMPLETED_NATIVE_LEDGER'


def test_full_verified_current_day_start_is_shown_as_ub_only(tmp_path):
    root,attempt=fixture(tmp_path);output=attempt/'output'
    point=output/'point.npz';output.mkdir();point.write_bytes(b'point')
    from v42_pr134_b1.common import sha
    write(output/'SCIENTIFIC_CASE_IDENTITY.json',dict(day='2025-05-01',arm='B2',case_sha='case'))
    write(output/'STATIONARY_DISPATCH_REPLAY.json',dict(PASS=True,case_sha='case',
        exact_Global_UB='4/5',point_path=str(point),point_file_sha256=sha(point),
        strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha='case')))
    w=monitor.view(root)['workers'][0]
    assert w['UB']==.8 and w['independent_Global_LB'] is None
    assert not w['global_gap_display']['available']
    point.write_bytes(b'mutated')
    w=monitor.view(root)['workers'][0]
    assert w['UB'] is None
    assert 'SHA_MISMATCH' in w['bound_status']['stationary_certificate_error']

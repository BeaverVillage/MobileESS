"""Campaign contracts and D-only paths; reuse the verified atomic/PID helpers."""
from pathlib import Path
from contextlib import contextmanager
import os
import msvcrt
import time
import errno
from v42_pr134_b1.common import atomic, table, read, sha, record, digest, now, process, same_process

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime/v42_may_campaign'
DAYS = tuple(f'2025-05-{n:02d}' for n in range(1, 32))
AXIS = tuple((arm, day) for arm in ('B1', 'B2') for day in DAYS)
REQUIRED_GATES = frozenset(('A_STAGE_MAY31', 'M_STAGE_MAY31', 'B2_INDEPENDENT_AIDC',
    'ORDER_AND_FAILURE_ISOLATION', 'WALL_NATIVE_BUDGET', 'ORIGINAL_PHYSICAL_AND_CERTIFICATES',
    'MONITOR', 'INDEPENDENT_PROCESS_PERSISTENCE', 'REGRESSION', 'PARALLEL_B2'))
SCIENTIFIC_SOURCES = frozenset((
    'v42_pr134_b1/common.py', 'v42_pr134_b1/coordinator.py',
    'v42_pr134_b1/native.py', 'v42_pr134_b1/inputs.py', 'v42_pr134_b1/replay.py',
    'v42_a_stage_canary/prepare.py', 'v42_a_stage_canary/phase.py',
    'v42_a_stage_canary/pricing.py', 'v42_a_stage_canary/physical.py',
    'v42_a_stage_acceptance/native.py', 'v42_a_stage_acceptance/physical.py',
    'v42_a_stage_domain_v2/execution.py', 'v42_a_stage_domain_v2/domain.py',
    'v42_a_stage_domain_v2/census.py', 'v42_a_stage_domain_v2/fast_prepare.py',
    'v42_a_stage_domain_v2/fast_backend.py', 'v42_a_stage_early/native.py',
    'v42_a_stage_practical/integer_model.py', 'v42_may12_rescue/contract.py',
    'v42_m1_anytime/algorithms.py', 'v42_m1_anytime/core.py',
    'v42_m1_research/lb.py', 'v42_m1_research/ub.py',
    'v42_m1_research/check_lb.py', 'v42_m1_research/check_ub.py',
    'v42_m1_research/check_joint.py', 'v42_m1_hybrid/final_verify.py',
    'v42_m1_hybrid/blocks.py', 'v42_m1_hybrid/pricing.py',
    'v42_integrated/start.py', 'v42_integrated/matrix.py', 'v42_native/contracts.py',
    'v42_holdout/inputs.py', 'v42_holdout/realization.py',
    'v42_capacity/reference.py', 'v42_final/common.py',
    'v42_regcontrol/authority.py', 'v42_regcontrol/runner.py',
    'v42_thermal/authority.py',
    'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json',
))


def d_path(path):
    p = Path(path).resolve()
    if p.drive.upper() != 'D:':
        raise ValueError('D_DRIVE_WRITES_REQUIRED:' + str(p))
    return p


def environment(root=None):
    """Set process-local temporary storage; workers pass their own attempt."""
    temp = d_path((Path(root) if root else RUNTIME) / 'tmp')
    temp.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(temp), TMP=str(temp), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    import tempfile
    tempfile.tempdir = str(temp)
    return temp


class LockBusy(RuntimeError):
    pass


@contextmanager
def exclusive_lock(path, *, wait=False, check=None):
    path = d_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('a+b')
    acquired = False
    try:
        if path.stat().st_size == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        while not acquired:
            if check is not None:
                check()
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError as error:
                if not wait or error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise LockBusy('LIVE_OS_LOCK:' + str(path)) from error
                # Only the short admission mutex waits. Slot/date locks fail
                # closed immediately and remain owned until worker exit.
                time.sleep(.025)
        yield stream
    finally:
        if acquired:
            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        stream.close()


def worker_slot(request):
    slot = request.get('worker_slot')
    if (type(slot) is not int or request.get('arm') not in ('B1', 'B2')
            or slot not in (1, 2, 3) or request['arm'] == 'B1' and slot != 1):
        raise PermissionError('CAMPAIGN_WORKER_SLOT_REQUIRED')
    return slot


def required_source_names():
    """Campaign ports and known reused scientific authorities must be frozen."""
    package = ROOT / 'v42_may_campaign'
    campaign = {p.relative_to(ROOT).as_posix() for p in package.iterdir()
                if p.is_file() and p.suffix in ('.py', '.html')}
    return SCIENTIFIC_SOURCES | campaign


def _verify_complete_inputs(root, doc):
    expected_keys = {a + '/' + d for a, d in AXIS}
    folders = doc.get('input_folders', {})
    if not isinstance(folders, dict) or set(folders) != expected_keys:
        raise PermissionError('ALL_62_INPUT_IDENTITIES_REQUIRED')
    receipts = doc.get('inputs', {})
    if not isinstance(receipts, dict) or not receipts:
        raise PermissionError('COMPLETE_FROZEN_INPUT_RECEIPTS_REQUIRED')
    frozen = {}
    for key, receipt in receipts.items():
        if not isinstance(receipt, dict) or not receipt.get('path') or not receipt.get('sha256'):
            raise PermissionError('MALFORMED_FROZEN_INPUT_RECEIPT:' + str(key))
        path = Path(receipt['path'])
        if not path.is_absolute():
            raise PermissionError('ABSOLUTE_FROZEN_INPUT_PATH_REQUIRED:' + str(key))
        path = path.resolve()
        if path in frozen:
            raise PermissionError('DUPLICATE_FROZEN_INPUT_RECEIPT:' + str(path))
        frozen[path] = receipt
    actual = set()
    for arm, day in AXIS:
        expected = (root / 'inputs' / arm / day).resolve()
        folder = Path(folders[arm + '/' + day])
        if (not folder.is_absolute() or folder.resolve() != expected
                or not expected.is_relative_to(root) or not expected.is_dir()):
            raise PermissionError('EXACT_ARM_DATE_INPUT_FOLDER_REQUIRED:' + arm + '/' + day)
        for path in expected.rglob('*'):
            if path.is_file():
                resolved = path.resolve()
                if not resolved.is_relative_to(expected):
                    raise PermissionError('INPUT_FILE_ESCAPES_ARM_DATE:' + str(path))
                actual.add(resolved)
        required = {'NATIVE_INPUT.json', 'INPUT_IDENTITY.json'}
        if arm == 'B2':
            required.add('B2_FIXED_AIDC.json')
        if any(not (expected / name).is_file() for name in required):
            raise PermissionError('REQUIRED_ARM_DATE_INPUT_FILES_MISSING:' + arm + '/' + day)
        identity = read(expected / 'INPUT_IDENTITY.json')
        if identity.get('PASS') is not True or identity.get('arm') != arm or identity.get('day') != day:
            raise PermissionError('FROZEN_INPUT_ARM_DATE_IDENTITY_DRIFT:' + arm + '/' + day)
        bundle_path = expected / 'NATIVE_INPUT.json'
        bundle = identity.get('bundle', {})
        linked = Path(bundle.get('path', ''))
        if (not linked.is_absolute() or linked.resolve() != bundle_path
                or bundle_path not in frozen or bundle.get('sha256') != frozen[bundle_path]['sha256']):
            raise PermissionError('FROZEN_NATIVE_INPUT_IDENTITY_LINK_REQUIRED:' + arm + '/' + day)
        native_input = read(bundle_path)
        if native_input.get('day') != day or native_input.get('arm', arm) != arm:
            raise PermissionError('FROZEN_NATIVE_INPUT_DAY_ARM_DRIFT:' + arm + '/' + day)
        if arm == 'B2':
            fixed = read(expected / 'B2_FIXED_AIDC.json')
            identity = fixed.get('identity', {})
            if (identity.get('PASS') is not True or identity.get('arm') != arm or identity.get('day') != day
                    or identity.get('AIDC_optimization_calls') != 0
                    or identity.get('B0_B1_schedule_result_reads') != 0):
                raise PermissionError('FROZEN_B2_FIXED_AIDC_IDENTITY_DRIFT:' + day)
            physical = fixed.get('physical', {})
            physical_path = Path(physical.get('path', ''))
            if (not physical_path.is_absolute() or not physical_path.resolve().is_relative_to(expected)
                    or physical_path.resolve() not in frozen
                    or physical.get('sha256') != frozen[physical_path.resolve()]['sha256']):
                raise PermissionError('FROZEN_B2_PHYSICAL_RECEIPT_REQUIRED:' + day)
    if set(frozen) != actual:
        raise PermissionError('EXACT_ALL_62_INPUT_FILE_SHA_SET_REQUIRED')
    for path, receipt in frozen.items():
        if sha(path) != receipt['sha256']:
            raise PermissionError('CAMPAIGN_INPUT_DRIFT:' + str(path))


def verify_manifest(path, require_preflight=True):
    path = d_path(path)
    doc = read(path)
    if doc.get('schema') != 'V42_MAY_B1_B2_P1_CAMPAIGN_V1' or not doc.get('run_id'):
        raise PermissionError('CAMPAIGN_MANIFEST_REQUIRED')
    if tuple((r['arm'], r['day']) for r in doc.get('axis', [])) != AXIS:
        raise PermissionError('B1_ALL_THEN_B2_AXIS_REQUIRED')
    policy = doc.get('policy', {})
    expected = dict(Threads=1, wall_seconds=5400, native_seconds=5400, P2_calls=0,
                    failed_date_retries=0, B1_gap=.005, B2_gap=.03,
                    B1_parallel_workers=1, B2_parallel_workers=3)
    if any(policy.get(k) != value for k, value in expected.items()):
        raise PermissionError('CAMPAIGN_POLICY_DRIFT')
    sources = doc.get('sources', {})
    if (not isinstance(sources, dict)
            or require_preflight and not required_source_names().issubset(sources)):
        raise PermissionError('COMPLETE_CAMPAIGN_AND_SCIENTIFIC_SOURCE_SHA_REQUIRED')
    for name, expected_sha in sources.items():
        if sha(ROOT / name) != expected_sha:
            raise PermissionError('CAMPAIGN_SOURCE_DRIFT:' + name)
    if require_preflight:
        gates = doc.get('gates', {})
        if doc.get('frozen') is not True or set(gates) != REQUIRED_GATES:
            raise PermissionError('ALL_NEW_CAMPAIGN_GATES_REQUIRED')
        for name, receipt in gates.items():
            if receipt.get('status') != 'PASS' or sha(receipt['path']) != receipt['sha256']:
                raise PermissionError('CAMPAIGN_GATE_NOT_PASS_OR_DRIFT:' + name)
            if read(receipt['path']).get('PASS') is not True:
                raise PermissionError('CAMPAIGN_GATE_RECEIPT_NOT_PASS:' + name)
        _verify_complete_inputs(path.parent, doc)
    return doc

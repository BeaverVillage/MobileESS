"""Immutable precision correction; only the explicitly failed May31 restarts."""
from pathlib import Path
from .common import ROOT, read, sha, digest
from .numerical import PRECISION, DAYS

VERSION = 'B2_FULL_VALIDATION_NAMESPACE_RECOVERY_V11'
BUILD_VERSION = 'B2_BUILD_INPUT_REUSE_V7_20261009'
MANIFEST = 'CONTINUATION_V11_MANIFEST.json'
ATTEMPT = 'mess_build_v11_01'
RETRY_DATES = ()
REQUIRED_VALIDATIONS = frozenset(('LIGHT_REGRESSION', 'NAMESPACE_FINGERPRINT', 'BUILD_REUSE_ROUTE'))


def source_files():
    return {p.relative_to(ROOT).as_posix(): sha(p)
        for folder in ('v42_b2_start_recovery_v11', 'v42_b2_build_optimization')
        for p in sorted((ROOT / folder).iterdir()) if p.is_file() and p.suffix in ('.py', '.html')}


def attempt_path(root, arm, day):
    return Path(root).resolve() / 'dates' / arm / day / 'attempts' / ATTEMPT


def verify_policy(root, *, require_preflight=True):
    from v42_may31_recovery_v10.policy import verify_policy as verify_previous
    root = Path(root).resolve()
    previous = verify_previous(root, require_preflight=require_preflight)
    doc = read(root / MANIFEST)
    if (doc.get('schema') != VERSION or doc.get('run_id') != previous['run_id']
            or doc.get('continuation_version') != VERSION
            or sha(root / 'CONTINUATION_V10_MANIFEST.json') != doc['previous_manifest']['sha256']
            or any(doc[name] != previous[name] for name in ('input_folders', 'scientific_authority', 'axis', 'sources'))
            or doc['implementation']['version'] != BUILD_VERSION
            or doc['implementation']['sources'] != source_files()
            or doc['implementation']['source_SHA'] != digest(source_files())
            or doc.get('attempt_id') != ATTEMPT
            or doc.get('authorized_recovery_dates') != list(RETRY_DATES)
            or doc.get('precision') != PRECISION
            or doc.get('precision_dates') != sorted(DAYS)
            or doc.get('phase_I_presolve') != 0):
        raise PermissionError('V11_PINNED_SOURCE_INPUT_OR_PRECISION_POLICY_DRIFT')
    if sha(doc['base_checkpoint']['path']) != doc['base_checkpoint']['sha256']:
        raise PermissionError('V11_IMMUTABLE_HANDOFF_BOUNDARY_DRIFT')
    boundary = read(doc['base_checkpoint']['path'])['dates']
    inherited = doc.get('inherited_request_receipts', {})
    expected = {'B1/' + day for day in DAYS}
    if (set(inherited) != expected or any(boundary[n]['status'] != 'PASS' for n in expected)):
        raise PermissionError('V11_COMPLETE_INHERITED_B1_SEAL_REQUIRED')
    from .common import record
    for name, receipt in inherited.items():
        if Path(receipt['path']).resolve() != Path(boundary[name]['request']).resolve() or record(receipt['path']) != receipt:
            raise PermissionError('V11_INHERITED_REQUEST_SHA_DRIFT')
    for receipt in doc['prior_failed_validation'].values():
        if record(receipt['path']) != receipt:
            raise PermissionError('V11_PREVIOUS_VALIDATION_FAILURE_RECEIPT_DRIFT')
    if set(doc.get('validation', {})) != REQUIRED_VALIDATIONS:
        raise PermissionError('V11_COMPLETE_VALIDATION_GATES_REQUIRED')
    for receipt in doc['validation'].values():
        if sha(receipt['path']) != receipt['sha256'] or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V11_VALIDATION_GATE_FAILED')
    if sha(doc['retry_authority']['path']) != doc['retry_authority']['sha256']:
        raise PermissionError('V11_EXPLICIT_RETRY_AUTHORITY_DRIFT')
    if doc.get('precision_components') != sorted(('PHASE_I', 'ORIGINAL_P1', 'INTEGER_CONTROL')):
        raise PermissionError('V11_INTEGER_PRECISION_SCOPE_DRIFT')
    return doc


def verify_request(request):
    doc = verify_policy(request['root'])
    if (request.get('policy_version') != VERSION or request.get('algorithm_version') != VERSION
            or request.get('implementation_SHA') != doc['implementation']['source_SHA']
            or request.get('attempt_id') != ATTEMPT):
        raise PermissionError('V11_WORKER_SOURCE_PIN_DRIFT')
    if request.get('preflight_native_zero') is True:
        expected = Path(request['root']).resolve() / 'source_validation_v11' / 'B2' / request['day'] / request['build_mode']
        if (request['arm'] != 'B2' or request['day'] not in ('2025-05-01', '2025-05-23')
                or request['build_mode'] not in ('BASELINE', 'OPTIMIZED')
                or Path(request['result']).resolve().parent != expected):
            raise PermissionError('V11_NATIVE_ZERO_VALIDATION_SCOPE_DRIFT')
    else:
        if Path(request['result']).resolve().parent != attempt_path(request['root'], request['arm'], request['day']):
            raise PermissionError('V11_PRODUCTION_ATTEMPT_PATH_DRIFT')
        original = read(doc['base_checkpoint']['path'])['dates'][request['arm'] + '/' + request['day']]
        if request['arm'] != 'B2':
            raise PermissionError('V11_ONLY_UNSTARTED_B2_PRODUCTION_ALLOWED')
        if original['status'] != 'PENDING' or original.get('attempts', 0) != 0:
            raise PermissionError('V11_COMPLETED_OR_STARTED_DATE_NEVER_REDISPATCHED')
    return doc

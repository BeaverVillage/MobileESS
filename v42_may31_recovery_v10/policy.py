"""Immutable precision correction; only the explicitly failed May31 restarts."""
from pathlib import Path
from .common import ROOT, read, sha, digest
from .numerical import PRECISION, DAYS

VERSION = 'MAY31_INTEGER_PRECISION_RECOVERY_V10'
BUILD_VERSION = 'B2_BUILD_INPUT_REUSE_V7_20261009'
MANIFEST = 'CONTINUATION_V10_MANIFEST.json'
ATTEMPT = 'recovery_v10_01'
RETRY_DATES = ('2025-05-31',)
REQUIRED_VALIDATIONS = frozenset(('LIGHT_REGRESSION', 'MAY31_INTEGER_PRECISION', 'A_SOURCE_PORT'))


def source_files():
    return {p.relative_to(ROOT).as_posix(): sha(p)
        for folder in ('v42_may31_recovery_v10', 'v42_b2_build_optimization')
        for p in sorted((ROOT / folder).iterdir()) if p.is_file() and p.suffix in ('.py', '.html')}


def attempt_path(root, arm, day):
    return Path(root).resolve() / 'dates' / arm / day / 'attempts' / ATTEMPT


def verify_policy(root, *, require_preflight=True):
    from v42_may25_recovery_v9.policy import verify_policy as verify_previous
    root = Path(root).resolve()
    previous = verify_previous(root, require_preflight=require_preflight)
    doc = read(root / MANIFEST)
    if (doc.get('schema') != VERSION or doc.get('run_id') != previous['run_id']
            or doc.get('continuation_version') != VERSION
            or sha(root / 'CONTINUATION_V9_MANIFEST.json') != doc['previous_manifest']['sha256']
            or any(doc[name] != previous[name] for name in ('input_folders', 'scientific_authority', 'axis', 'sources'))
            or doc['implementation']['version'] != BUILD_VERSION
            or doc['implementation']['sources'] != source_files()
            or doc['implementation']['source_SHA'] != digest(source_files())
            or doc.get('attempt_id') != ATTEMPT
            or doc.get('authorized_recovery_dates') != list(RETRY_DATES)
            or doc.get('precision') != PRECISION
            or doc.get('precision_dates') != sorted(DAYS)
            or doc.get('phase_I_presolve') != 0):
        raise PermissionError('V10_PINNED_SOURCE_INPUT_OR_PRECISION_POLICY_DRIFT')
    if sha(doc['base_checkpoint']['path']) != doc['base_checkpoint']['sha256']:
        raise PermissionError('V10_IMMUTABLE_HANDOFF_BOUNDARY_DRIFT')
    if set(doc.get('validation', {})) != REQUIRED_VALIDATIONS:
        raise PermissionError('V10_COMPLETE_VALIDATION_GATES_REQUIRED')
    for receipt in doc['validation'].values():
        if sha(receipt['path']) != receipt['sha256'] or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V10_VALIDATION_GATE_FAILED')
    if sha(doc['retry_authority']['path']) != doc['retry_authority']['sha256']:
        raise PermissionError('V10_EXPLICIT_RETRY_AUTHORITY_DRIFT')
    if doc.get('precision_components') != sorted(('PHASE_I', 'ORIGINAL_P1', 'INTEGER_CONTROL')):
        raise PermissionError('V10_INTEGER_PRECISION_SCOPE_DRIFT')
    return doc


def verify_request(request):
    doc = verify_policy(request['root'])
    if (request.get('policy_version') != VERSION or request.get('algorithm_version') != VERSION
            or request.get('implementation_SHA') != doc['implementation']['source_SHA']
            or request.get('attempt_id') != ATTEMPT):
        raise PermissionError('V10_WORKER_SOURCE_PIN_DRIFT')
    if request.get('preflight_native_zero') is True:
        expected = Path(request['root']).resolve() / 'source_validation_v10' / 'B2' / request['day'] / request['build_mode']
        if (request['arm'] != 'B2' or request['day'] not in ('2025-05-01', '2025-05-23')
                or request['build_mode'] not in ('BASELINE', 'OPTIMIZED')
                or Path(request['result']).resolve().parent != expected):
            raise PermissionError('V10_NATIVE_ZERO_VALIDATION_SCOPE_DRIFT')
    else:
        if Path(request['result']).resolve().parent != attempt_path(request['root'], request['arm'], request['day']):
            raise PermissionError('V10_PRODUCTION_ATTEMPT_PATH_DRIFT')
        original = read(doc['base_checkpoint']['path'])['dates'][request['arm'] + '/' + request['day']]
        if request['arm'] == 'B1' and request['day'] in RETRY_DATES:
            if original.get('attempts') != 1 or original['status'] == 'PASS':
                raise PermissionError('V10_ONLY_EXPLICIT_FAILED_OR_INTERRUPTED_DATES_MAY_RESTART')
        elif original['status'] != 'PENDING' or original.get('attempts', 0) != 0:
            raise PermissionError('V10_COMPLETED_OR_STARTED_DATE_NEVER_REDISPATCHED')
    return doc

"""A new source permit; inherited sources and running attempts stay pinned."""
from pathlib import Path
from .common import ROOT, read, sha, digest

VERSION = 'B2_BUILD_INPUT_REUSE_V7_20261009'
MANIFEST = 'CONTINUATION_V7_MANIFEST.json'
ATTEMPT = 'mess_build_v7_01'
RETRY_DATES = ()
PRECISION = dict(FeasibilityTol=1e-9, OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2)
REQUIRED_VALIDATIONS = frozenset(('LIGHT_REGRESSION', 'B1_SOURCE_DELEGATION', 'B2_BUILD_LIGHT_EQUIVALENCE'))


def source_files():
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for folder in ('v42_may_mess_build_v7', 'v42_b2_build_optimization')
            for p in sorted((ROOT / folder).iterdir()) if p.is_file() and p.suffix in ('.py', '.html')}


def attempt_path(root, arm, day):
    return Path(root).resolve() / 'dates' / arm / day / 'attempts' / ATTEMPT


def verify_policy(root, *, require_preflight=True):
    from v42_may_build_v6.policy import verify_policy as verify_previous
    root = Path(root).resolve()
    previous = verify_previous(root, require_preflight=require_preflight)
    doc = read(root / MANIFEST)
    if (doc.get('schema') != VERSION or doc.get('run_id') != previous['run_id']
            or sha(root / 'CONTINUATION_V6_MANIFEST.json') != doc['previous_manifest']['sha256']
            or doc['input_folders'] != previous['input_folders']
            or doc['scientific_authority'] != previous['scientific_authority']
            or doc['axis'] != previous['axis'] or doc['sources'] != previous['sources']
            or doc['implementation']['version'] != VERSION
            or doc['implementation']['sources'] != source_files()
            or doc['implementation']['source_SHA'] != digest(source_files())
            or doc.get('attempt_id') != ATTEMPT or doc.get('authorized_recovery_dates') != []
            or doc.get('precision') != PRECISION):
        raise PermissionError('V7_PINNED_SOURCE_INPUT_OR_POLICY_DRIFT')
    if sha(doc['base_checkpoint']['path']) != doc['base_checkpoint']['sha256']:
        raise PermissionError('V7_IMMUTABLE_HANDOFF_BOUNDARY_DRIFT')
    if set(doc.get('validation', {})) != REQUIRED_VALIDATIONS:
        raise PermissionError('V7_LIGHT_VALIDATION_GATES_REQUIRED')
    for receipt in doc['validation'].values():
        if sha(receipt['path']) != receipt['sha256'] or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V7_LIGHT_VALIDATION_GATE_FAILED')
    return doc


def verify_request(request):
    doc = verify_policy(request['root'])
    if (request.get('policy_version') != VERSION
            or request.get('implementation_SHA') != doc['implementation']['source_SHA']
            or request.get('algorithm_version') != VERSION or request.get('attempt_id') != ATTEMPT):
        raise PermissionError('V7_WORKER_SOURCE_PIN_DRIFT')
    if request.get('preflight_native_zero') is True:
        expected = Path(request['root']).resolve() / 'source_validation_v7' / 'B2' / request['day'] / request['build_mode']
        if (request['arm'] != 'B2' or request['day'] not in ('2025-05-01', '2025-05-23')
                or request['build_mode'] not in ('BASELINE', 'OPTIMIZED')
                or Path(request['result']).resolve().parent != expected):
            raise PermissionError('V7_NATIVE_ZERO_VALIDATION_SCOPE_DRIFT')
    else:
        if Path(request['result']).resolve().parent != attempt_path(request['root'], request['arm'], request['day']):
            raise PermissionError('V7_PRODUCTION_ATTEMPT_PATH_DRIFT')
        original = read(doc['base_checkpoint']['path'])['dates'][request['arm'] + '/' + request['day']]
        if original['status'] != 'PENDING' or original.get('attempts', 0) != 0:
            raise PermissionError('V7_COMPLETED_OR_STARTED_DATE_NEVER_REDISPATCHED')
    return doc

"""An immutable source boundary; the original V2 manifest is never edited."""
from pathlib import Path
from .common import ROOT, read, sha, digest

VERSION = 'MAY11_MAY19_RECOVERY_V5'
MANIFEST = 'CONTINUATION_V5_MANIFEST.json'
ATTEMPT = 'recovery_v5_01'
RETRY_DATES = ('2025-05-11', '2025-05-19')
PRECISION = dict(FeasibilityTol=1e-9, OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2)
REQUIRED_VALIDATIONS = frozenset(('MAY11_NUMERICAL','MAY19_FROZEN_PHASE_WEIGHTS',
    'FRESH_ORIGINAL_MODELS','ORDER_ISOLATION_MONITOR_REGRESSION','WINDOWS_PROCESS_QUERY',
    'MAY22_RUNTIME','OS_PERSISTENCE','MONITOR_UI'))


def source_files():
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for folder in ('v42_may_recovery_v5', 'v42_may_replay_v3', 'v42_may_phase_v4')
            for p in sorted((ROOT/folder).iterdir()) if p.is_file() and p.suffix in ('.py','.html')}


def attempt_path(root, arm, day):
    return Path(root).resolve()/'dates'/arm/day/'attempts'/ATTEMPT


def verify_policy(root, *, require_preflight=True):
    from v42_may_campaign_native90.common import verify_manifest as verify_base
    root = Path(root).resolve()
    base = verify_base(root/'CAMPAIGN_MANIFEST.json', require_preflight=require_preflight)
    doc = read(root/MANIFEST)
    if (doc.get('schema') != VERSION or doc.get('run_id') != base['run_id']
            or sha(root/'CAMPAIGN_MANIFEST.json') != doc['base_manifest']['sha256']
            or doc['input_folders'] != base['input_folders']
            or doc['scientific_authority'] != base['scientific_authority']
            or doc['axis'] != base['axis'] or doc['implementation']['sources'] != source_files()
            or doc['implementation']['source_SHA'] != digest(source_files())
            or doc['implementation']['version'] != VERSION
            or doc['authorized_recovery_dates'] != list(RETRY_DATES)
            or doc.get('attempt_id') != ATTEMPT or doc['precision'] != PRECISION):
        raise PermissionError('V5_VERSIONED_SOURCE_INPUT_OR_RECOVERY_AUTHORITY_DRIFT')
    if set(doc.get('validation',{})) != REQUIRED_VALIDATIONS:
        raise PermissionError('V5_COMPLETE_VALIDATION_GATES_REQUIRED')
    for receipt in doc['validation'].values():
        if sha(receipt['path']) != receipt['sha256'] or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V5_INDEPENDENT_VALIDATION_GATE_FAILED')
    return doc


def verify_request(request):
    doc = verify_policy(request['root'])
    if (request.get('policy_version') != VERSION
            or request.get('implementation_SHA') != doc['implementation']['source_SHA']
            or request.get('attempt_id') != ATTEMPT
            or Path(request['result']).resolve().parent != attempt_path(request['root'], request['arm'], request['day'])):
        raise PermissionError('V5_WORKER_PIN_OR_ATTEMPT_IDENTITY_DRIFT')
    return doc

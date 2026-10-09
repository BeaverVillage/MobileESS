"""An immutable source boundary; the original V2 manifest is never edited."""
from pathlib import Path
from .common import ROOT, read, sha, digest

VERSION = 'MAY23_BUILD_EFFICIENCY_V6'
MANIFEST = 'CONTINUATION_V6_MANIFEST.json'
ATTEMPT = 'build_v6_01'
RETRY_DATES = ('2025-05-23',)
PRECISION = dict(FeasibilityTol=1e-9, OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2)
REQUIRED_VALIDATIONS = frozenset(('FRESH_ORIGINAL_MODELS', 'REGRESSION', 'OS_PERSISTENCE', 'MONITOR_UI'))


def source_files():
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for folder in ('v42_may_build_v6', 'v42_may_replay_v3', 'v42_may_phase_v4')
            for p in sorted((ROOT/folder).iterdir()) if p.is_file() and p.suffix in ('.py','.html')}


def attempt_path(root, arm, day):
    return Path(root).resolve()/'dates'/arm/day/'attempts'/ATTEMPT


def verify_policy(root, *, require_preflight=True):
    from v42_may_campaign_native90.common import verify_manifest as verify_base
    root = Path(root).resolve()
    base = verify_base(root/'CAMPAIGN_MANIFEST.json', require_preflight=require_preflight)
    from v42_may_recovery_v5.policy import verify_policy as verify_previous
    verify_previous(root, require_preflight=require_preflight)
    doc = read(root/MANIFEST)
    if (doc.get('schema') != VERSION or doc.get('run_id') != base['run_id']
            or sha(root/'CAMPAIGN_MANIFEST.json') != doc['base_manifest']['sha256']
            or sha(root/'CONTINUATION_V5_MANIFEST.json') != doc['previous_manifest']['sha256']
            or doc['input_folders'] != base['input_folders']
            or doc['scientific_authority'] != base['scientific_authority']
            or doc['axis'] != base['axis'] or doc['implementation']['sources'] != source_files()
            or doc['implementation']['source_SHA'] != digest(source_files())
            or doc['implementation']['version'] != VERSION
            or doc['authorized_recovery_dates'] != list(RETRY_DATES)
            or doc.get('attempt_id') != ATTEMPT or doc['precision'] != PRECISION):
        raise PermissionError('V6_VERSIONED_SOURCE_INPUT_OR_RECOVERY_AUTHORITY_DRIFT')
    if set(doc.get('validation',{})) != REQUIRED_VALIDATIONS:
        raise PermissionError('V6_COMPLETE_VALIDATION_GATES_REQUIRED')
    for receipt in doc['validation'].values():
        if sha(receipt['path']) != receipt['sha256'] or read(receipt['path']).get('PASS') is not True:
            raise PermissionError('V6_INDEPENDENT_VALIDATION_GATE_FAILED')
    return doc


def verify_request(request):
    doc = verify_policy(request['root'])
    if (request.get('policy_version') != VERSION
            or request.get('implementation_SHA') != doc['implementation']['source_SHA']
            or request.get('attempt_id') != ATTEMPT
            or Path(request['result']).resolve().parent != attempt_path(request['root'], request['arm'], request['day'])):
        raise PermissionError('V6_WORKER_PIN_OR_ATTEMPT_IDENTITY_DRIFT')
    if request['arm']=='B1' and request['day']<'2025-05-23':
        raise PermissionError('COMPLETED_MAY01_THROUGH_MAY22_NEVER_REDISPATCHED')
    return doc

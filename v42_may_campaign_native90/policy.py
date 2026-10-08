"""Versioned authority for a new run; the superseded run stays immutable."""
from pathlib import Path
from .common import ROOT, read, sha, digest

VERSION = 'NATIVE90_BUILD_REUSE_V2'
EXPECTED = dict(Threads=1, wall_seconds=None, native_seconds=5400, P2_calls=0,
    failed_date_retries=0, B1_gap=.005, B2_gap=.03, B1_parallel_workers=1, B2_parallel_workers=3)

def source_files():
    return {str(p.relative_to(ROOT)).replace('\\','/'):sha(p)
        for folder in ('v42_may_campaign_native90','v42_campaign_monitor')
        for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix in ('.py','.html')}

def verify_policy(root):
    doc=read(Path(root)/'CAMPAIGN_MANIFEST.json')
    if doc.get('schema')!='V42_MAY_B1_B2_NATIVE90_V2' or doc.get('policy')!=EXPECTED:
        raise PermissionError('NATIVE90_POLICY_IDENTITY_DRIFT')
    version=doc['implementation']
    if version['version']!=VERSION or version['sources']!=source_files() or version['source_SHA']!=digest(version['sources']):
        raise PermissionError('VERSIONED_COMPLETE_SOURCE_SHA_DRIFT')
    validation=doc['implementation_validation']
    if sha(validation['path'])!=validation['sha256'] or read(validation['path']).get('PASS') is not True:
        raise PermissionError('VERSIONED_REGRESSION_AND_EQUIVALENCE_GATE_REQUIRED')
    return dict(version=VERSION,source_SHA=version['source_SHA'],**EXPECTED)

def verify_request(request):
    policy=verify_policy(request['root'])
    if request.get('policy_version')!=VERSION or request.get('implementation_SHA')!=policy['source_SHA']:
        raise PermissionError('WORKER_VERSION_PIN_DRIFT')
    return policy

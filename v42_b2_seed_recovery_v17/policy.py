"""New source seal; prior manifests and all prior attempts remain immutable."""
from pathlib import Path
import math
from .common import ROOT, read, record, sha, digest

VERSION = 'B2_SEED_RECOVERY_V17_20261009'
MANIFEST = 'CONTINUATION_V17_MANIFEST.json'
ATTEMPT = 'seed_policy_v17_01'
MODEL_FIELDS = ('original_matrix_sha','original_domain_sha','selected_matrix_sha',
                'selected_domain_sha','bundle_sha','anchor_sha','binary_count')


def source_files():
    folders = ('v42_b2_seed_recovery_v17', 'v42_b2_start_recovery_v13', 'v42_b2_build_authority_v13')
    return {p.relative_to(ROOT).as_posix():sha(p) for folder in folders
            for p in sorted((ROOT/folder).iterdir()) if p.is_file() and p.suffix in ('.py','.html')}


def prior_runtime(receipt, *, root, day):
    p = Path(receipt['ledger']['path']).resolve()
    if not p.is_relative_to(Path(root).resolve()/'dates'/'B2'/day/'attempts'):
        raise PermissionError('PRIOR_LEDGER_DATE_PATH_DRIFT')
    for name in ('ledger','result','request'):
        if record(receipt[name]['path']) != receipt[name]:
            raise PermissionError('PRIOR_ATTEMPT_SHA_DRIFT:'+name)
    ledger, result, request = (read(receipt[n]['path']) for n in ('ledger','result','request'))
    if (request['day'] != day or request['arm'] != 'B2' or result['identity']['day'] != day
            or result['identity']['arm'] != 'B2' or ledger.get('inflight') is not None
            or any(c.get('runtime_unavailable') or not c.get('entered_native') for c in ledger['calls'])):
        raise PermissionError('PRIOR_NATIVE_RUNTIME_QUARANTINE')
    runtime = float(ledger['measured_Native_Runtime'])
    carried = (ledger.get('prior_attempt') or {}).get('Native_Runtime',0.)
    measured = carried + sum(float(c['Native_Runtime']) for c in ledger['calls'])
    if (not math.isfinite(runtime) or not 0 <= runtime <= 5400 or measured != runtime
            or result['Native_Runtime'] != runtime or receipt['Native_Runtime'] != runtime):
        raise PermissionError('PRIOR_CUMULATIVE_NATIVE_SUM_DRIFT')
    return runtime


def verify_manifest(path):
    path = Path(path).resolve(); doc = read(path); root = path.parent
    sources = source_files()
    if (path.name != MANIFEST or doc.get('schema') != VERSION or not doc.get('user_authorized')
            or doc['execution_sources'] != sources or doc['execution_SHA'] != digest(sources)
            or doc['seed_MIPGap'] != .03 or doc['seed_requested_seconds'] != 900
            or doc['native_budget_seconds'] != 5400 or doc['target_gap'] != .03):
        raise PermissionError('V17_SOURCE_OR_POLICY_SEAL_DRIFT')
    for relative, expected in doc['builder_original_sources'].items():
        if sha(ROOT/relative) != expected:
            raise PermissionError('V17_ORIGINAL_SCIENTIFIC_SOURCE_DRIFT:'+relative)
    for name, receipt in doc['prior_attempts'].items():
        prior_runtime(receipt, root=root, day=name)
    for receipt in doc['inherited_B1_results'].values():
        if record(receipt['path']) != receipt:
            raise PermissionError('V17_COMPLETED_B1_RESULT_SHA_DRIFT')
    if record(doc['previous_manifest']['path']) != doc['previous_manifest']:
        raise PermissionError('V17_PRIOR_SOURCE_AUTHORITY_SHA_DRIFT')
    return doc


def verify_request(request):
    doc = verify_manifest(request['manifest'])
    expected = Path(request['root']).resolve()/'dates'/'B2'/request['day']/'attempts'/ATTEMPT
    if (request['arm'] != 'B2' or request['day'] not in doc['input_folders']
            or request['run_id'] != doc['run_id'] or request['manifest_SHA'] != sha(request['manifest'])
            or request['implementation_SHA'] != doc['execution_SHA'] or request['algorithm_version'] != VERSION
            or request['attempt_id'] != ATTEMPT or Path(request['input_folder']).resolve() != Path(doc['input_folders'][request['day']]).resolve()
            or any(request.get(k) != v for k,v in dict(Threads=1,P2_calls=0,native_budget_seconds=5400,
                wall_budget_seconds=None,target_gap=.03).items())
            or any(Path(request[k]).resolve() != expected/name for k,name in
                (('output','output'),('result','RESULT.json'),('progress','progress.json'),('error','error.json')))):
        raise PermissionError('V17_REQUEST_DATE_SOURCE_OR_POLICY_DRIFT')
    return doc

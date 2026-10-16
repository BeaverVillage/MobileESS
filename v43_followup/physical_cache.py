"""Relocate verified source receipts, preserving PR189's cache verifier body.

Only source locations are projected in memory. Original cache bytes, receipts,
scientific input checks, complete-domain hashing and verifier code stay intact.
This adapter cannot run against a live Golden source attempt.
"""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from types import FunctionType
from unittest.mock import patch

import psutil

from v43.common import BASE, ROOT, atomic, git, now, read, record, sha, verify_records

PRODUCERS = ('v42_a_stage_domain_v2/domain.py', 'v42_boundary/generator.py',
             'v42_job_capability.py')
WRITER = 'v42_a_stage_domain_v2/fast_census.py'
VERIFIERS = ('v42_may_campaign_native90/a_cache.py', WRITER,
             'v42_may_campaign_native90/build_reuse.py')
SCHEMA = 'V43_COMPLETED_STATIC_PHYSICAL_CASE_V1'
_mutex = RLock()


def _same_bytes(left, right):
    return all(left[k] == right[k] for k in ('bytes', 'sha256'))


def _base_sources():
    """Pin actual bytes to PR189 Git blobs, independent of checkout paths."""
    import hashlib
    rows = {}
    for relative in dict.fromkeys((*PRODUCERS, *VERIFIERS)):
        blob = git('show', BASE + ':' + relative)
        current = record(ROOT / relative)
        expected = dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
        if not _same_bytes(current, expected):
            raise ValueError('PR189_CACHE_SOURCE_BYTES_DRIFT:' + relative)
        rows[relative] = current
    return rows


def relocated_receipt(raw, *, historical_root, current_root, pinned_sources):
    """Accept only the four exact repository-relative source relocations."""
    old, new = Path(historical_root).resolve(), Path(current_root).resolve()
    projected = deepcopy(raw)
    aliases = []

    def relocate(item, relative):
        original = Path(item['path']).resolve()
        if original != old / relative:
            raise ValueError('CACHE_SOURCE_RELATIVE_PATH_DRIFT:' + relative)
        target = new / relative
        current = record(target)
        if (not _same_bytes(current, item)
                or not _same_bytes(current, pinned_sources[relative])):
            raise ValueError('CACHE_SOURCE_RELOCATION_BYTES_DRIFT:' + relative)
        aliases.append(dict(relative=relative, historical=deepcopy(item), current=current))
        return current

    if len(raw['producer_sources']) != len(PRODUCERS):
        raise ValueError('EXACT_THREE_PHYSICAL_PRODUCERS_REQUIRED')
    projected['producer_sources'] = [relocate(row, relative)
        for row, relative in zip(raw['producer_sources'], PRODUCERS)]
    projected['cache_writer'] = relocate(raw['cache_writer'], WRITER)
    return projected, aliases


def _terminated(start, result, reconciliation):
    if (not result.get('finished_UTC')
            or reconciliation.get('inflight') is not None
            or reconciliation.get('Native_runtime_known') is not True):
        raise ValueError('TERMINATED_RECONCILED_GOLDEN_REQUIRED')
    try:
        process = psutil.Process(start['pid'])
        if process.create_time() == start['process_created'] and process.is_running():
            raise PermissionError('LIVE_GOLDEN_CACHE_ADAPTER_NOT_ADMITTED')
    except psutil.NoSuchProcess:
        pass


def _completed(start, result, reconciliation):
    if (result.get('Gate_A_PASS') is not True
            or result.get('PR189_NUMERICAL_REPRODUCTION') != 'PASS'):
        raise ValueError('COMPLETED_GOLDEN_NUMERICAL_PASS_REQUIRED')
    _terminated(start, result, reconciliation)


def seal_completed_case(request_path, destination, *, domain_only=False):
    """Seal complete local domains; distinguish them from a FULL-model PASS."""
    request = read(request_path)
    attempt, output = Path(request['root']), Path(request['output'])
    paths = {key: attempt / name for key, name in (
        ('start', 'START.json'), ('result', 'RESULT.json'),
        ('reconciliation', 'RECONCILIATION.json'))}
    ( _terminated if domain_only else _completed)(*(read(paths[k]) for k in ('start', 'result', 'reconciliation')))
    if domain_only and read(paths['reconciliation'])['calls'] != 0:
        raise ValueError('DOMAIN_ONLY_RECOVERY_REQUIRES_NATIVE0_RECONCILIATION')
    if attempt.name != 'golden_B1_20250501_attempt002':
        raise ValueError('THIS_ADAPTER_SEALS_GOLDEN002_WITHOUT_A_NEW_GOLDEN')
    prepare_path = output / 'A_PREPARE_RECEIPT.json'
    domain_path = output / 'STATIC/DOMAIN' / request['day'] / 'PHYSICAL_DOMAIN_CACHE.json'
    prepare = read(prepare_path) if prepare_path.exists() else None
    domains = read(domain_path)
    verification = request['_expected_model_verification']
    if (not domain_only and (prepare is None or prepare.get('PASS') is not True
                            or prepare['verification'] != verification)
            or domains.get('PASS') is not True
            or domains['complete_domain_hashes'] != request['_expected_complete_domain_hashes']
            or (domains['jobs'], domains['representatives']) != (1499, 117)
            or (verification['jobs'], verification['classes'], verification['full_STAY'],
                verification['full_migration']) != (1499, 117, 133609, 624473721)
            or domains['serialized_native_variables'] != 0):
        raise ValueError('GOLDEN002_INDEPENDENT_COMPLETE_DOMAIN_PROOF_REQUIRED')
    freeze = read(request['source_freeze'])
    # V43 lifecycle/status IO may have been repaired after the attempt ended.
    # Cache authority is pinned to unchanged PR189 scientific source bytes.
    original_sources = [r for r in freeze['sources']
        if not Path(r['path']).is_relative_to(ROOT / 'v43')]
    verify_records(original_sources + freeze['support'] + freeze['scientific_inputs'])
    sources = _base_sources()
    from v42_may_campaign_native90.common import digest
    payload = dict(schema=SCHEMA, UTC=now(), source_base=BASE,
        day=request['day'], arm=request['arm'], request=record(request_path),
        completed={k: record(p) for k, p in paths.items()},
        source_freeze=record(request['source_freeze']), source_files=sources,
        prepare=record(prepare_path) if prepare else None, domain=record(domain_path),
        scientific_inputs={n: record(Path(request['input_folder']) / n)
            for n in ('NATIVE_INPUT.json', 'WINDOWS.json')},
        expected_model_verification=verification,
        current_model_verification=None if prepare is None else prepare['verification'],
        domain_only=domain_only,
        FULL_model_PASS_claimed=not domain_only,
        complete_domain_hashes=domains['complete_domain_hashes'],
        resources_sha256=domains['resources_sha256'],
        scope='COMPLETE_LOCAL_PHYSICAL_DOMAINS_AND_STATIC_PROOF_ONLY',
        solved_point_imported=False, UB_LB_imported=False, Native_runtime_imported=False)
    payload['proof_sha'] = digest(payload)
    if Path(destination).exists():
        raise FileExistsError('STATIC_CASE_PROOF_NEVER_OVERWRITTEN')
    atomic(destination, payload)
    return record(destination)


def _verified_case(path, request):
    from v42_may_campaign_native90.common import digest
    proof = read(path)
    if (proof.get('schema') != SCHEMA or proof.get('source_base') != BASE
            or proof.get('proof_sha') != digest({k: v for k, v in proof.items() if k != 'proof_sha'})
            or (proof['day'], proof['arm']) != (request['day'], request['arm'])):
        raise ValueError('STATIC_PHYSICAL_CASE_PROOF_SEAL_OR_CASE_DRIFT')
    verify_records(([proof['prepare']] if proof['prepare'] else []) + [proof['domain'], proof['source_freeze'],
                    proof['request'], *proof['completed'].values(), *proof['source_files'].values()])
    (_terminated if proof['domain_only'] else _completed)(*(read(proof['completed'][k]['path']) for k in ('start', 'result', 'reconciliation')))
    original_request = read(proof['request']['path'])
    if (proof['prepare'] is not None and proof['current_model_verification'] != read(proof['prepare']['path'])['verification']
            or proof['complete_domain_hashes'] != read(proof['domain']['path'])['complete_domain_hashes']
            or request.get('_expected_model_verification') != proof['expected_model_verification']
            or request.get('_expected_complete_domain_hashes') != proof['complete_domain_hashes']):
        raise ValueError('STATIC_MATRIX_OR_COMPLETE_DOMAIN_BINDING_DRIFT')
    for name in ('NATIVE_INPUT.json', 'WINDOWS.json'):
        actual = record(Path(request['input_folder']) / name)
        original = record(Path(original_request['input_folder']) / name)
        if not _same_bytes(actual, original) or not _same_bytes(actual, proof['scientific_inputs'][name]):
            raise ValueError('STATIC_CASE_SCIENTIFIC_INPUT_DRIFT:' + name)
    return proof


def load_current_date_physical_cache(request, fresh_data, *, case_proof,
        historical_source_root='D:/MobileESS_V42', check=lambda: None, progress=None,
        original_loader=None):
    """Run unchanged original verifiers with source-only receipt relocation.

    Their full semantic DATA, graph, resources, UID/class, cache byte and
    recalculated complete-domain checks remain mandatory. No native model or
    solver state is read or constructed here.
    """
    from v42_may_campaign_native90 import a_cache
    from v42_a_stage_domain_v2 import fast_census
    check()
    proof = _verified_case(case_proof, request)
    sources = _base_sources()
    if (len(fresh_data[1]) != proof['expected_model_verification']['jobs']
            or len(fresh_data[7]['classes']) != proof['expected_model_verification']['classes']):
        raise ValueError('FRESH_UID_OR_CLASS_POPULATION_DRIFT')
    folder = Path(request['_current_date_physical_cache']) / 'STATIC/DOMAIN' / request['day']
    receipt_path = folder / 'PHYSICAL_DOMAIN_CACHE.json'
    raw_record = record(receipt_path)
    if raw_record != request.get('_physical_cache_identity'):
        raise ValueError('PINNED_ORIGINAL_CACHE_RECEIPT_REQUIRED')
    raw = read(receipt_path)
    if (raw['complete_domain_hashes'] != proof['complete_domain_hashes']
            or raw['resources_sha256'] != proof['resources_sha256']):
        raise ValueError('CACHE_NOT_IDENTICAL_TO_NEW_GOLDEN002_PHYSICAL_CASE')
    projected, aliases = relocated_receipt(raw, historical_root=historical_source_root,
        current_root=ROOT, pinned_sources=sources)
    original_read = a_cache.read

    def routed_read(path):
        if Path(path).resolve() == receipt_path.resolve():
            if record(receipt_path) != raw_record:
                raise ValueError('CACHE_RECEIPT_CHANGED_DURING_VERIFICATION')
            return deepcopy(projected)
        return original_read(path)

    original = original_loader or a_cache.load_current_date_physical_cache
    if (original.__module__ != a_cache.__name__
            or original.__name__ != 'load_current_date_physical_cache'
            or Path(original.__code__.co_filename).resolve() != ROOT / 'v42_may_campaign_native90/a_cache.py'):
        raise ValueError('EXACT_ORIGINAL_CACHE_VERIFIER_FUNCTION_REQUIRED')
    namespace = dict(original.__globals__, read=routed_read)
    loader = FunctionType(original.__code__, namespace, original.__name__, original.__defaults__, original.__closure__)
    with _mutex, patch.object(fast_census, 'read', routed_read):
        domains = loader(request, fresh_data, check=check, progress=progress)
    check()
    if domains is None or set(domains) != set(fresh_data[1]):
        raise ValueError('EXACT_FRESH_UID_DOMAIN_AXIS_REQUIRED')
    full_stay = full_migration = 0
    for members in fresh_data[7]['classes'].values():
        domain = domains[members[0]]
        if any(domains[uid] is not domain for uid in members):
            raise ValueError('EXACT_CLASS_DOMAIN_EXPANSION_REQUIRED')
        full_stay += len(domain.stays)
        full_migration += sum(len(block[-1]) for block in domain.blocks)
    if (full_stay, full_migration) != (proof['expected_model_verification']['full_STAY'], proof['expected_model_verification']['full_migration']):
        raise ValueError('COMPLETE_STAY_OR_MIGRATION_CARDINALITY_DRIFT')
    if record(receipt_path) != raw_record:
        raise ValueError('ORIGINAL_CACHE_RECEIPT_MUTATED')
    verify_records(list(sources.values()))
    output = Path(request['output'])
    atomic(output / 'PATH_INDEPENDENT_PHYSICAL_CACHE_REUSE.json', dict(PASS=True, UTC=now(),
        adapter=record(Path(__file__)), static_case_proof=record(case_proof),
        original_cache_receipt=raw_record, source_relocations=aliases,
        original_verifier_sources={k: sources[k] for k in VERIFIERS},
        original_verifier_code_unchanged=loader.__code__ is original.__code__,
        original_semantic_and_full_domain_checks_executed=True,
        FULL_model_certificate_transferred=False,
        jobs=len(domains), classes=len(fresh_data[7]['classes']),
        full_STAY=full_stay, full_migration=full_migration,
        original_input_and_cache_files_modified=False, Native_calls=0,
        prior_solution_used=False, prior_UB_LB_used=False, prior_Native_runtime_used=False))
    return domains


@contextmanager
def cache_scope(request):
    """V43-only binding; invalid required reuse cannot silently regenerate."""
    proof = request.get('physical_cache_case_proof')
    if proof is None:
        yield
        return
    verify_records([proof])
    from v42_may_campaign_native90 import a_cache
    original = a_cache.load_current_date_physical_cache
    def routed(current_request, fresh_data, check=lambda: None, progress=None):
        try:
            return load_current_date_physical_cache(current_request, fresh_data,
                case_proof=proof['path'], check=check, progress=progress,
                original_loader=original)
        except Exception as error:
            # Original optional cache routing catches ValueError/IOError and
            # recomputes domains. Required, independently verified reuse must
            # fail visibly instead of spending another full build on a bug.
            raise RuntimeError('REQUIRED_VERIFIED_PHYSICAL_CACHE_REUSE_FAILED') from error
    with patch.object(a_cache, 'load_current_date_physical_cache', routed):
        yield

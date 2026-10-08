"""Read-only reuse of this campaign/date's verified physical input cache.

Only complete physical Domain objects are returned. Fresh DATA, graphs,
models, starts, witnesses and optimizer accounting are always constructed in
the new attempt. No historical or other-date result directory is admitted.
"""
import pickle
from dataclasses import asdict
from pathlib import Path
from .common import atomic, read, record, d_path


def _attempt_name(name, day):
    if name == day:
        return True
    prefix = day + '_attempt'
    suffix = name[len(prefix):] if name.startswith(prefix) else ''
    return suffix.isdecimal() and int(suffix) >= 2 and str(int(suffix)) == suffix


def _owned_receipt(receipt, expected):
    path = Path(receipt['path']).resolve()
    if path != Path(expected).resolve() or record(path) != receipt:
        raise ValueError('A_CURRENT_DATE_CACHE_FILE_SHA_OR_PATH_DRIFT:' + str(path))
    return path


def _semantic_data(data):
    """Ignore serialization order/counters; compare every scientific value."""
    from v42_a_stage_domain_v2.census import digest
    from v42_a_stage_domain_v2.domain import graph_content_hash
    if not isinstance(data, tuple) or len(data) != 8:
        raise ValueError('A_CURRENT_DATE_CACHE_DATA_SCHEMA')
    bundle, jobs, bounds, resources, raw, graphs, original_graphs, prep = data
    if set(jobs) != set(bounds) or set(jobs) != set(graphs) or set(jobs) != set(original_graphs):
        raise ValueError('A_CURRENT_DATE_CACHE_JOB_GRAPH_AXIS')
    memo = {}
    def graph_hash(graph):
        key = id(graph)
        if key not in memo:
            memo[key] = graph_content_hash(graph)
        return memo[key]
    return dict(bundle=digest(bundle), jobs=digest({u: asdict(j) for u, j in sorted(jobs.items())}),
        bounds=digest({u: asdict(b) for u, b in sorted(bounds.items())}), resources=digest(asdict(resources)),
        raw=digest(raw), classes=digest(prep['classes']),
        graphs=digest({u: graph_hash(g) for u, g in sorted(graphs.items())}),
        original_graphs=digest({u: graph_hash(g) for u, g in sorted(original_graphs.items())}))


def load_current_date_physical_cache(request, fresh_data, check=lambda: None, progress=None):
    option = request.get('_current_date_physical_cache')
    if option is None:
        return None
    check()
    root, source, output, inputs = (d_path(request[k]) for k in ('root', '_current_date_physical_cache', 'output', 'input_folder'))
    day = request['day']
    authority_root=d_path(request.get('input_authority_root',str(root)))
    parent = authority_root / 'preflight_cases/B1'
    production_output=root/'dates/B1'/day/'output'
    preflight_output=(output.parent==root/'preflight_cases/B1' and _attempt_name(output.name,day))
    if (request.get('arm') != 'B1' or source.parent != parent
            or not preflight_output and output!=production_output
            or source == output or not _attempt_name(source.name, day)
            or inputs != authority_root / 'inputs/B1' / day):
        raise PermissionError('A_CURRENT_CAMPAIGN_SAME_DATE_PREFLIGHT_CACHE_ONLY')
    if fresh_data[0].get('day') != day:
        raise ValueError('A_CURRENT_DATE_CACHE_FRESH_DATA_DAY')
    if progress:
        progress(dict(phase='A_OWN_CURRENT_DATE_PHYSICAL_CACHE_VERIFY', day=day, arm='B1', Native_calls=0))
    # These are the same campaign's causal input generation receipts, created
    # before its prior Native=0 attempt. WINDOWS byte identity is checked here;
    # the Job/Boundary semantics are independently compared below as well.
    input_identity_path = inputs / 'INPUT_IDENTITY.json'
    identity = read(input_identity_path)
    if identity.get('PASS') is not True or identity.get('day') != day or identity.get('arm') != 'B1':
        raise ValueError('A_CURRENT_DATE_CACHE_INPUT_IDENTITY')
    bundle_path = _owned_receipt(identity['bundle'], inputs / 'NATIVE_INPUT.json')
    _owned_receipt(identity['windows'], inputs / 'WINDOWS.json')
    generation_path = authority_root / 'MAY31_INDEPENDENT_INPUT_VERIFICATION.json'
    generation = read(generation_path)
    rows = [row for row in generation['dates'] if row['day'] == day and row['arm'] == 'B1']
    if (generation.get('PASS') is not True or generation.get('Native_calls') != 0
            or len(rows) != 1 or rows[0].get('PASS') is not True
            or Path(generation['input_folders']['B1/' + day]).resolve() != inputs):
        raise ValueError('A_CURRENT_DATE_CACHE_CAUSAL_GENERATION_IDENTITY')
    for name in ('NATIVE_INPUT.json', 'WINDOWS.json'):
        receipts = [r for r in rows[0]['files'] if Path(r['path']).resolve() == inputs / name]
        if len(receipts) != 1:
            raise ValueError('A_CURRENT_DATE_CACHE_GENERATED_INPUT_RECEIPT_REQUIRED:' + name)
        _owned_receipt(receipts[0], inputs / name)
    data_path = source / 'STATIC/DATA/DATA.pkl'
    old_bundle_path = source / 'STATIC/DATA/MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'
    if record(old_bundle_path)['sha256'] != record(bundle_path)['sha256']:
        raise ValueError('A_CURRENT_DATE_CACHE_NATIVE_INPUT_SHA_DRIFT')
    from v42_a_stage_domain_v2 import fast_census as original
    cache_root = source / 'STATIC/DOMAIN'
    receipt_path = cache_root / day / 'PHYSICAL_DOMAIN_CACHE.json'
    receipt = read(receipt_path)
    pinned=request.get('_physical_cache_identity')
    if pinned is not None and record(receipt_path)!=pinned:
        raise ValueError('A_CURRENT_DATE_PINNED_CACHE_RECEIPT_SHA_DRIFT')
    if (receipt.get('PASS') is not True or receipt.get('day') != day
            or receipt.get('schema') != 'FAST_COMPLETE_PHYSICAL_REPRESENTATIVE_CACHE_V1'
            or receipt.get('serialized_native_variables') != 0
            or receipt.get('producer_sources') != original._producer_sources()):
        raise ValueError('A_CURRENT_DATE_CACHE_ORIGINAL_PRODUCER_IDENTITY')
    _owned_receipt(receipt['cache_writer'], Path(original.__file__))
    _owned_receipt(receipt['frozen_DATA'], data_path)
    _owned_receipt(receipt['cache'], cache_root / day / 'PHYSICAL_DOMAIN_CACHE.pkl.gz')
    protected = [receipt['frozen_DATA'], record(old_bundle_path), record(receipt_path), receipt['cache']]
    with data_path.open('rb') as stream:
        old_data = pickle.load(stream)
    check()
    old_semantics, fresh_semantics = _semantic_data(old_data), _semantic_data(fresh_data)
    if old_semantics != fresh_semantics:
        changed = [name for name in old_semantics if old_semantics[name] != fresh_semantics[name]]
        raise ValueError('A_CURRENT_DATE_CACHE_SCIENTIFIC_INPUT_MISMATCH:' + ','.join(changed))
    # Unchanged original helper independently verifies producer sources, DATA
    # SHA, class membership, resources, every representative domain SHA/duration
    # and cache bytes before exposing the physical objects.
    domains = original.load_physical_cache(day, old_data, data_path, cache_root)
    from .build_reuse import domain_hash
    recalculated={}
    for members in fresh_data[7]['classes'].values():
        uid=members[0];domain=domains[uid]
        actual=domain_hash(fresh_data[1][uid],fresh_data[2][uid],domain)
        if actual!=domain.sha or actual!=receipt['complete_domain_hashes'][uid]:
            raise ValueError('A_CURRENT_DATE_CACHE_RECALCULATED_FULL_DOMAIN_SHA_DRIFT:'+uid)
        recalculated[uid]=actual
    expected_hashes=request.get('_expected_complete_domain_hashes')
    if expected_hashes is not None and recalculated!=expected_hashes:
        raise ValueError('A_CURRENT_DATE_INDEPENDENT_COMPLETE_DOMAIN_HASH_DRIFT')
    check()
    if set(domains) != set(fresh_data[1]):
        raise ValueError('A_CURRENT_DATE_CACHE_COMPLETE_DOMAIN_JOB_AXIS')
    for uid, domain in domains.items():
        if domain.cache.r != fresh_data[3] or domain.duration != fresh_data[1][uid].service_slots:
            raise ValueError('A_CURRENT_DATE_CACHE_COMPLETE_DOMAIN_RESOURCE_OR_DURATION')
    if any(record(item['path']) != item for item in protected):
        raise ValueError('A_CURRENT_DATE_CACHE_SOURCE_MUTATION')
    atomic(output / 'CURRENT_DATE_PHYSICAL_CACHE_REUSE.json', dict(PASS=True, day=day, arm='B1',
        scope='SAME_CAMPAIGN_SAME_DATE_PHYSICAL_INPUT_CACHE_ONLY', source_folder=str(source),
        protected_source_files=protected, input_identity=record(input_identity_path),
        input_generation=record(generation_path), inputs={name: record(inputs / name) for name in ('NATIVE_INPUT.json', 'WINDOWS.json')},
        old_semantic_SHA=old_semantics, fresh_semantic_SHA=fresh_semantics,
        original_verifier=record(Path(original.__file__)),
        physical_domain_jobs=len(domains), Native_calls=0, prior_state_used=False,
        recalculated_complete_domain_hashes=recalculated,cache_hit=True,
        prior_native_point_used=False, prior_UB_LB_used=False, prior_native_runtime_used=False,
        fresh_model_required=True, current_model_build_cost_accounted=True))
    return domains

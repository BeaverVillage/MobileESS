"""Transitive input identities, independently reconstructed at every load."""
from pathlib import Path
from copy import deepcopy
from dayahead.paper_analysis.storage import read, write_json, sha
from dayahead.v40a.invariants import digest

REL = Path('dayahead/artifacts/v40h_production_integrity')
CAMPAIGN = Path('dayahead/artifacts/v40h_corrected_may_2025')
SCHEMA = 'V40H_CORRECTED_MAY_EXECUTION_V1'
CASES = ('B0', 'B1', 'B2', 'B3')
DAYS = tuple(f'2025-05-{d:02d}' for d in range(1, 32))


class IntegrityError(ValueError): pass


def require(value, reason):
    if not value: raise IntegrityError(reason)


def file_record(path, *, root=None):
    path = Path(path).resolve(); require(path.is_file(), 'MISSING_AUTHORITY:' + str(path))
    return {'path': str(path), 'relative_path': path.relative_to(Path(root).resolve()).as_posix() if root else path.name,
            'bytes': path.stat().st_size, 'sha256': sha(path)}


def verify_file(record, *, root=None):
    path = Path(record['path']).resolve()
    if root is not None:
        base = Path(root).resolve()
        require(path.is_relative_to(base), 'ARTIFACT_OUTSIDE_CURRENT_NAMESPACE')
        require(path == (base / record['relative_path']).resolve(), 'ARTIFACT_RELATIVE_PATH_MISMATCH')
    require(path.is_file(), 'MISSING_LEAF:' + str(path))
    require(path.stat().st_size == record['bytes'], 'LEAF_SIZE_MISMATCH:' + str(path))
    require(sha(path) == record['sha256'], 'LEAF_SHA_MISMATCH:' + str(path))
    return path


def manifest(paths, root):
    base = Path(root).resolve()
    records = [file_record(p, root=base) for p in sorted(set(map(Path, paths)))]
    require(len({r['relative_path'] for r in records}) == len(records), 'DUPLICATE_MANIFEST_PATH')
    return {'root': str(base), 'files': records, 'manifest_SHA': digest(records)}


def verify_manifest(value):
    require(value['manifest_SHA'] == digest(value['files']), 'MANIFEST_HASH_MISMATCH')
    for record in value['files']: verify_file(record, root=value['root'])
    return value


def bind(kind, inputs, required):
    require(set(required).issubset(inputs), 'MISSING_IDENTITY_ROLES:' + ','.join(sorted(set(required) - set(inputs))))
    require(all(inputs[k] is not None and inputs[k] != '' for k in required), 'EMPTY_IDENTITY_ROLE')
    payload = {'schema': kind, 'inputs': deepcopy(inputs)}
    return {'identity': payload, 'identity_SHA': digest(payload)}


def validate_identity(value, expected):
    require(value['identity_SHA'] == digest(value['identity']), 'IDENTITY_CONTENT_DRIFT')
    require(expected['identity_SHA'] == digest(expected['identity']), 'EXPECTED_IDENTITY_CONTENT_DRIFT')
    require(value['identity_SHA'] == expected['identity_SHA'], 'STALE_DIFFERENT_IDENTITY')
    return value


def verify_bound_files(value):
    """Revalidate all transitive file leaves now, once per validation call."""
    seen = set()
    def walk(node):
        if isinstance(node, dict):
            if {'path', 'bytes', 'sha256'}.issubset(node):
                key = (node['path'], node['bytes'], node['sha256'])
                if key not in seen: verify_file(node); seen.add(key)
            if {'manifest_SHA', 'files'}.issubset(node):
                require(node['manifest_SHA'] == digest(node['files']), 'BOUND_MANIFEST_CONTENT_DRIFT')
            for item in node.values(): walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node: walk(item)
    walk(value)
    return len(seen)


CAMPAIGN_ROLES = ('V40G_method_SHA', 'V40G_source_SHA', 'V40G_config_SHA', 'V40G_git_commit',
    'common_T_DA_SHA', 'common_T_DA_source', 'background_mapper', 'native_load_allocation',
    'electrical_generation', 'daily_electrical_identities', 'AC_anchor', 'voltage_sensitivity',
    'line_current_sensitivity', 'transformer_sensitivity', 'alpha_grid', 'C1', 'AIDC_power',
    'GPU_capacity', 'Rack', 'traffic_forecast', 'road_graph', 'route_generation', 'MESS_mobility',
    'MESS_electrical', 'OpenDSS_mapping_source', 'Fresh_restoration', 'Actual_replay', 'source_manifest',
    'V40H_source_SHA', 'runtime_environment')


def campaign_identity(inputs): return bind(SCHEMA, inputs, CAMPAIGN_ROLES)


def initialize_matrix(identity):
    require(identity['identity']['schema'] == SCHEMA, 'OBSOLETE_CAMPAIGN_FREEZE')
    return {'schema': SCHEMA, 'execution_identity': deepcopy(identity), 'total': 124,
        'rows': [{'day': d, 'case': c, 'status': 'RUN_REQUIRED', 'certificate': None} for d in DAYS for c in CASES],
        'OLD_B0_REUSE_ALLOWED': 'NO', 'OLD_B1_REUSE_ALLOWED': 'NO', 'OLD_B2_REUSE_ALLOWED': 'NO', 'OLD_B3_REUSE_ALLOWED': 'NO'}


def validate_matrix(matrix, expected):
    require(matrix.get('schema') == SCHEMA, 'OBSOLETE_EXECUTION_MATRIX_FORBIDDEN')
    validate_identity(matrix['execution_identity'], expected)
    rows = matrix['rows']
    require(len(rows) == 124 and {(r['day'], r['case']) for r in rows} == {(d, c) for d in DAYS for c in CASES}, 'CORRECTED_MATRIX_124_REQUIRED')
    require(all(r['status'] in ('RUN_REQUIRED', 'COMPLETE_CURRENT_IDENTITY', 'PARTIAL_CURRENT_IDENTITY', 'STALE_DIFFERENT_IDENTITY', 'INVALID') for r in rows), 'LEGACY_REUSE_CERTIFIED_FORBIDDEN')
    return matrix


def immutable_write(path, value):
    path = Path(path)
    if path.exists(): require(read(path) == value, 'PRESERVE_EXISTING_EVIDENCE:' + str(path))
    else: write_json(path, value)
    return file_record(path)

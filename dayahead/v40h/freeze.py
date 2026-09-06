"""Commit-backed scientific freeze and fail-closed corrected campaign input seal."""
from pathlib import Path
import subprocess
import hashlib
from dayahead.paper_analysis.storage import read, write_json, sha
from dayahead.v40a.invariants import digest
from .identity import (REL, CAMPAIGN, DAYS, require, manifest, verify_manifest, file_record,
    campaign_identity, initialize_matrix, immutable_write, verify_bound_files, verify_file)
from .authorities import source_paths
from .policy import configuration


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True, encoding='utf-8').strip()


def verify_preserved(repo):
    preserved = read(Path(repo) / REL / 'PRESERVED_V40G_FINAL.json')
    for path, expected in preserved['files'].items(): require(sha(path) == expected, 'FROZEN_V40G_EVIDENCE_CHANGED:' + path)
    return len(preserved['files'])


def scientific_status(repo):
    repo = Path(repo).resolve(); paths = source_paths(repo)
    names = [p.relative_to(repo).as_posix() for p in paths]
    tracked = set(git(repo, 'ls-files').splitlines())
    missing = sorted(set(names) - tracked)
    changed = set(git(repo, 'diff', '--name-only', 'HEAD').splitlines()) & set(names)
    return {'science_clean': not missing and not changed, 'untracked_scientific_sources': missing,
            'changed_scientific_sources': sorted(changed), 'source_count': len(names)}


def verify_commit_bytes(repo, source):
    names = [r['relative_path'] for r in source['files']]
    data = subprocess.check_output(['git', '-C', str(repo), 'cat-file', '--batch'],
        input=''.join('HEAD:' + name + '\n' for name in names).encode('utf-8'))
    offset = 0
    for record in source['files']:
        end = data.index(b'\n', offset); header = data[offset:end].split()
        require(len(header) == 3 and header[1] == b'blob', 'FROZEN_SOURCE_NOT_IN_COMMIT')
        size = int(header[2]); payload = data[end + 1:end + 1 + size]; offset = end + 2 + size
        require(len(payload) == record['bytes'] and hashlib.sha256(payload).hexdigest() == record['sha256'],
                'GIT_BLOB_BYTES_NOT_FROZEN_WORKTREE:' + record['relative_path'])
    return len(source['files'])


def seal_source(repo):
    repo = Path(repo).resolve(); state = scientific_status(repo)
    require(state['science_clean'], 'SCIENTIFIC_WORKTREE_NOT_CLEAN')
    count = verify_preserved(repo); source = manifest(source_paths(repo), repo)
    verify_commit_bytes(repo, source)
    prior = read(repo / 'dayahead/artifacts/v40g_segment_integration/SOURCE_SEAL.json')
    config = configuration(); method = {'V40G_frozen_segment_method_SHA': prior['method_SHA'],
        'V40G_frozen_segment_config_SHA': prior['config_SHA'], 'V40H_corrections': config,
        'canonical_representation': 'V40G_CANONICAL_COMPUTE_SEGMENTS_V1'}
    value = {'schema': 'V40H_SCIENTIFIC_SOURCE_FREEZE_V1', 'git_commit': git(repo, 'rev-parse', 'HEAD'),
        'source_manifest': source, 'V40G_source_SHA': source['manifest_SHA'], 'V40G_method_SHA': digest(method),
        'V40G_config_SHA': digest(config), 'V40H_source_SHA': manifest((repo / 'dayahead/v40h').glob('*.py'), repo)['manifest_SHA'],
        'method': method, 'configuration': config, 'base_V40G_source_seal': file_record(repo / 'dayahead/artifacts/v40g_segment_integration/SOURCE_SEAL.json'),
        'source_status': state, 'preserved_V40G_files': count,
        'historical_data_artifacts_may_remain_untracked': True, 'production_authorized': False}
    immutable_write(repo / REL / 'FINAL_SCIENTIFIC_SOURCE_FREEZE.json', value)
    return value


def verify_scientific_freeze(repo):
    repo = Path(repo).resolve(); value = read(repo / REL / 'FINAL_SCIENTIFIC_SOURCE_FREEZE.json')
    require(git(repo, 'rev-parse', 'HEAD') == value['git_commit'], 'FROZEN_COMMIT_CHANGED')
    require(scientific_status(repo)['science_clean'], 'SCIENTIFIC_WORKTREE_NOT_CLEAN')
    verify_manifest(value['source_manifest'])
    verify_commit_bytes(repo, value['source_manifest'])
    require(manifest(source_paths(repo), repo)['manifest_SHA'] == value['V40G_source_SHA'], 'SCIENTIFIC_SOURCE_SET_DRIFT')
    require(digest(configuration()) == value['V40G_config_SHA'], 'FROZEN_CONFIGURATION_DRIFT')
    verify_preserved(repo)
    return value


def expected_electrical(repo, day):
    frozen = verify_scientific_freeze(repo)
    inventory = read(Path(repo) / REL / 'CURRENT_TRANSITIVE_INPUT_INVENTORY.json')
    expected = inventory['daily_electrical_identities'][day]
    require(inventory['source_manifest']['manifest_SHA'] == frozen['V40G_source_SHA'], 'INPUT_INVENTORY_SOURCE_NOT_FINAL')
    require(expected['identity']['inputs']['generation_source']['transitive_generation_source_SHA'] == frozen['V40G_source_SHA'], 'ELECTRICAL_EXPECTED_SOURCE_NOT_FINAL')
    verify_bound_files(expected)
    # Re-enumerate roots: adding a component file also invalidates the manifest.
    from .electrical import feeder_manifest
    feeder = expected['identity']['inputs']['feeder_manifest']
    current = feeder_manifest(feeder['consumed_roots'], [r['path'] for r in feeder['masters']])
    require(current['manifest_SHA'] == feeder['manifest_SHA'], 'STALE_ELECTRICAL_FEEDER_SET')
    return expected


def expected_campaign(repo, *, require_outputs=False):
    repo = Path(repo).resolve(); frozen = verify_scientific_freeze(repo)
    inventory = read(repo / REL / 'CURRENT_TRANSITIVE_INPUT_INVENTORY.json'); verify_bound_files(inventory)
    require(inventory['source_manifest']['manifest_SHA'] == frozen['V40G_source_SHA'], 'INPUT_INVENTORY_SOURCE_NOT_FINAL')
    common = read(repo / REL / 'common_inputs/COMMON_INPUT_INDEX.json'); verify_bound_files(common)
    from .electrical import load, OUTPUTS
    outputs = {role: {} for role in OUTPUTS}; missing = []
    for day in DAYS:
        cert = repo / CAMPAIGN / 'electrical' / day / 'GENERATION_CERTIFICATE.json'
        if cert.exists():
            paths = load(cert, lambda d=day: expected_electrical(repo, d))
            for role, path in paths.items(): outputs[role][day] = {'file': file_record(path), 'generation_certificate': file_record(cert)}
        else:
            missing.append(day)
            for role in OUTPUTS: outputs[role][day] = inventory['electrical_generation_outputs'][day]
    if require_outputs: require(not missing, 'ELECTRICAL_GENERATION_REQUIRED:' + ','.join(missing))
    inputs = {k: frozen[k] for k in ('V40G_method_SHA', 'V40G_source_SHA', 'V40G_config_SHA', 'V40H_source_SHA')}
    inputs.update(V40G_git_commit=frozen['git_commit'], common_T_DA_SHA={d: x['COMMON_DA_DURATION_SHA'] for d, x in common.items()},
        common_T_DA_source=common, background_mapper=inventory['daily_electrical_identities'][DAYS[0]]['identity']['inputs']['native_mapper'],
        native_load_allocation=inventory['background'], electrical_generation=inventory['generation_source'],
        daily_electrical_identities=inventory['daily_electrical_identities'], **outputs, alpha_grid=inventory['alpha_grid'],
        C1=inventory['AIDC_power_C1'], AIDC_power=inventory['AIDC_power_C1'], GPU_capacity=inventory['GPU_capacity'], Rack=inventory['Rack'],
        traffic_forecast=inventory['traffic'], road_graph=inventory['road_graph'], route_generation={d: x['route_generation_source'] for d, x in inventory['traffic'].items()},
        MESS_mobility=inventory['MESS_mobility'], MESS_electrical=inventory['MESS_electrical'], OpenDSS_mapping_source=inventory['full_feeder_manifest'],
        Fresh_restoration=inventory['Fresh_restoration'], Actual_replay=inventory['Actual_replay'], source_manifest=frozen['source_manifest'],
        runtime_environment=inventory['runtime_environment'], generation_output_closure='COMPLETE' if not missing else 'GENERATION_REQUIRED',
        missing_electrical_generation_days=missing)
    return campaign_identity(inputs)


def initialize_campaign(repo):
    repo = Path(repo).resolve(); identity = expected_campaign(repo)
    immutable_write(repo / CAMPAIGN / 'CORRECTED_MAY_EXECUTION_FREEZE.json', identity)
    immutable_write(repo / CAMPAIGN / 'CORRECTED_MAY_EXECUTION_MATRIX.json', initialize_matrix(identity))
    immutable_write(repo / CAMPAIGN / 'EXECUTION_AUTHORIZATION.json', {'MAY_31DAY_AUTHORIZED': 'NO', 'FULL_MAY_AUTHORIZED': 'NO',
        'B2_B3_AUTHORIZED': 'NO', 'reason': 'Static hardening only; site blockers remain open; electrical generation and full output seal required.'})
    return identity


def seal_generated_output_revision(repo):
    """After separately authorized generation, seal outputs before any case run.

    Preserve the initial static matrix/freeze. This never changes authorization.
    """
    repo = Path(repo).resolve(); root = repo / CAMPAIGN
    identity = expected_campaign(repo, require_outputs=True)
    path = root / 'CORRECTED_MAY_EXECUTION_MATRIX.json'; previous = read(path)
    require(len(previous['rows']) == 124 and all(r['status'] == 'RUN_REQUIRED' and r['certificate'] is None for r in previous['rows']),
            'OUTPUT_REVISION_REQUIRES_ZERO_STARTED_CASES')
    from .cache import archive_stale
    for target, value in ((root / 'CORRECTED_MAY_EXECUTION_FREEZE.json', identity), (path, initialize_matrix(identity))):
        if read(target) != value:
            archive_stale(target, 'STATIC_INPUT_FREEZE_SUPERSEDED_BY_COMPLETE_GENERATED_OUTPUT_BINDING')
            write_json(target, value)
    return identity

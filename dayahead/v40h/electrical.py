"""Generation-time electrical provenance; file SHA alone never authorizes use."""
from pathlib import Path
import os
import re
from dayahead.paper_analysis.storage import read
from dayahead.v40a.invariants import digest
from .identity import bind, validate_identity, require, manifest, verify_manifest, file_record, verify_file, immutable_write, verify_bound_files

ROLES = ('day', 'generation_source', 'native_mapper', 'native_allocation_authority', 'feeder_manifest',
    'OpenDSS_master', 'PCC_mapping', 'service_PCC_mapping', 'line_ratings', 'transformer_ratings',
    'native_controls', 'alpha_grid', 'demand', 'PV', 'weather', 'background_mapping', 'AIDC_power_C1',
    'AC_anchor_input', 'axes', 'voltage_generation', 'current_generation', 'transformer_generation')
OUTPUTS = ('AC_anchor', 'voltage_sensitivity', 'line_current_sensitivity', 'transformer_sensitivity')
COMMON_PHYSICAL = ('alpha_grid', 'background_mapping', 'feeder_manifest', 'line_ratings', 'transformer_ratings', 'PCC_mapping')


def feeder_manifest(asset_roots, masters):
    """Bind every component under consumed roots and every reachable DSS include.

    A conservative complete directory manifest also covers non-DSS component
    files consumed by the Python feeder builder. Includes escaping a root are
    included explicitly, never silently omitted.
    """
    paths = set(); pending = []
    for root in map(Path, asset_roots):
        require(root.is_dir(), 'FEEDER_ASSET_ROOT_MISSING')
        paths.update(p.resolve() for p in root.rglob('*') if p.is_file())
    pending.extend(Path(p).resolve() for p in masters)
    pending.extend(p for p in paths if p.suffix.lower() == '.dss'); seen = set()
    pattern = re.compile(r'(?im)^\s*(?:redirect|compile)\s+(?:\(([^)]+)\)|"([^"]+)"|\x27([^\x27]+)\x27|([^\s!]+))')
    while pending:
        path = pending.pop()
        if path in seen: continue
        require(path.is_file(), 'DSS_INCLUDE_MISSING:' + str(path)); paths.add(path); seen.add(path)
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        for match in pattern.finditer(text):
            name = next(v for v in match.groups() if v is not None).strip()
            target = (path.parent / name).resolve(); pending.append(target)
    require(bool(paths), 'EMPTY_FEEDER_MANIFEST')
    common = Path(os.path.commonpath([str(p.parent) for p in paths]))
    value = manifest(paths, common)
    value['consumed_roots'] = sorted(str(Path(r).resolve()) for r in asset_roots)
    value['masters'] = [file_record(p) for p in masters]
    return value


def electrical_identity(inputs):
    verify_manifest(inputs['feeder_manifest'])
    return bind('V40H_ELECTRICAL_GENERATION_V1', inputs, ROLES)


def generate(output_certificate, expected_builder, producer):
    """The producer executes only after capturing independently expected inputs."""
    expected = expected_builder(); verify_bound_files(expected)
    require(expected['identity']['schema'] == 'V40H_ELECTRICAL_GENERATION_V1', 'ELECTRICAL_GENERATION_SCHEMA')
    outputs = producer(expected)
    require(set(outputs) == set(OUTPUTS), 'ELECTRICAL_OUTPUT_ROLE_COVERAGE')
    current = expected_builder(); verify_bound_files(current); validate_identity(current, expected)
    certificate = {'schema': 'V40H_ELECTRICAL_CERTIFICATE_V1', 'SOURCE_INPUT_IDENTITY': expected['identity'],
        'SOURCE_INPUT_IDENTITY_SHA': expected['identity_SHA'],
        'OUTPUT_FILE_SHA256': {role: file_record(path) for role, path in outputs.items()},
        'generation_attestation': 'CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER', 'post_hoc_identity_adoption': False}
    immutable_write(output_certificate, certificate)
    return certificate


def load(output_certificate, expected_builder):
    expected = expected_builder(); verify_bound_files(expected); cert = read(output_certificate)
    require(cert.get('schema') == 'V40H_ELECTRICAL_CERTIFICATE_V1' and
            cert.get('generation_attestation') == 'CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER' and
            cert.get('post_hoc_identity_adoption') is False, 'UNATTESTED_ELECTRICAL_GENERATION_FORBIDDEN')
    stored = {'identity': cert['SOURCE_INPUT_IDENTITY'], 'identity_SHA': cert['SOURCE_INPUT_IDENTITY_SHA']}
    try: validate_identity(stored, expected)
    except ValueError as e: raise ValueError('STALE_ELECTRICAL_AUTHORITY=YES; REUSE=FORBIDDEN; ' + str(e)) from e
    require(set(cert['OUTPUT_FILE_SHA256']) == set(OUTPUTS), 'ELECTRICAL_OUTPUT_ROLE_COVERAGE')
    return {role: verify_file(record) for role, record in cert['OUTPUT_FILE_SHA256'].items()}


def namespace_gate(planning, fresh, actual):
    identities = {'Planning': planning['identity']['inputs'], 'Fresh': fresh['identity']['inputs'], 'Actual': actual['identity']['inputs']}
    report = {'status': 'PASS', 'forecast_realized_trajectories_may_differ': ['demand', 'PV', 'weather']}
    for key in COMMON_PHYSICAL:
        values = {label: digest(v[key]) for label, v in identities.items()}
        require(len(set(values.values())) == 1, 'PHYSICAL_AUTHORITY_DIFFERS_ACROSS_NAMESPACES:' + key)
        for label, value in values.items(): report[key + '_SHA_' + label] = value
    for label, v in identities.items():
        report['alpha_grid_' + label] = v['alpha_grid']['value']
        report['feeder_manifest_SHA_' + label] = v['feeder_manifest']['manifest_SHA']
        report['rating_SHA_' + label] = digest({'line': v['line_ratings'], 'transformer': v['transformer_ratings']})
        report['trajectory_role_' + label] = 'REALIZED' if label == 'Actual' else 'D1_FORECAST'
    return report

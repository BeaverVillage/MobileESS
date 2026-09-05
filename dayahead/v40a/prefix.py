"""Exact continuation of a development M1 checkpoint, never a new route search."""
from pathlib import Path
import json
from .context import file_sha
from .invariants import digest


def load_exact_m1(source, repo, day, pcc, context):
    source, repo = Path(source).resolve(), Path(repo).resolve()
    value = json.loads(source.read_text(encoding='utf-8'))
    identity = value['V40A_execution_identity']
    if identity['day'] != day or identity['method'] != 'V40A_M1':
        raise ValueError('M1_CHECKPOINT_DAY_OR_METHOD_MISMATCH')
    if identity['A0_PCC'] != digest(pcc):
        raise ValueError('M1_CHECKPOINT_A0_PCC_MISMATCH')
    if identity['grid'] != [c.coefficient_sha256 for c in context.coefficients]:
        raise ValueError('M1_CHECKPOINT_PLANNING_GRID_MISMATCH')
    if value['V40A_execution_fingerprint'] != digest(identity):
        raise ValueError('M1_CHECKPOINT_IDENTITY_HASH_MISMATCH')
    for relative, sha in identity['source_SHAs'].items():
        if file_sha(repo / relative) != sha:
            raise ValueError('M1_CHECKPOINT_SOURCE_MISMATCH:' + relative)
    if (identity['K'], identity['beam'], identity['seed'], identity['WorkLimit']) != (200, 2, 2, [60,180,300]):
        raise ValueError('M1_CHECKPOINT_SEARCH_SETTINGS_MISMATCH')
    return value, {
        'status': 'PASS', 'source': str(source), 'source_sha256': file_sha(source),
        'A0_PCC_exact': True, 'Planning_coefficients_exact': True,
        'M1_source_exact': True, 'M1_search_settings_exact': True,
        'new_full_route_search_calls_this_continuation': 0,
        'full_route_search_calls_in_represented_pipeline': 1,
        'measured_M1_seconds': value['V40A_wallclock_seconds'],
    }

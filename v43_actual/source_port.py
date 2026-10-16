"""Reproducible, SHA-pinned selective reuse of existing event algorithms.

No Day-Ahead model, D0 initializer, historical solved MESS result or modified
hardware driver is activated. Selected definitions retain their source bodies.
"""
import ast
from pathlib import Path

from v43.common import DOC, PR231, ROOT, atomic, read, record

SOURCE = PR231 / 'v42_integration'
DEST = ROOT / 'v43_actual/vendor'
MANIFEST = DOC / 'GATE_B_SELECTIVE_PORT_MANIFEST.json'

WHOLE = ('actual', 'qos', 'policy', 'reservation_state', 'sensitivity_policy',
         'q90_recourse', 'known_commands', 'initialization', 'initial_state',
         'pr79_reference')
SLICES = {
    'current_ac_admission': (
        'from copy import deepcopy\nfrom datetime import datetime,timezone,timedelta\n'
        'import csv\nimport io\nimport math\nfrom pathlib import Path\nimport zipfile\n'
        'import pandas as pd\nfrom .policy import digest\nfrom v43_actual.io import read,record,checked\n',
        ('AEST','epoch','CausalSeries','_archive_series','CausalObservations')),
    'private_truth': (
        'from pathlib import Path\nimport zipfile\nimport numpy as np\nimport pandas as pd\n'
        'from v43_actual.io import checked, record\n'
        'def require(value, reason):\n    if not value: raise ValueError(reason)\n'
        'def _resolve(receipt):\n    return checked(receipt)\n', ('_truth',)),
    'frozen_unknown': ('from copy import deepcopy\n', ('_migration_capability',)),
    'trajectory_tracking': (
        'from copy import deepcopy\nfrom pathlib import Path\nimport math\nimport json\nimport numpy as np\n'
        'from .actual import _require_public_metadata\nfrom .policy import digest\n'
        'from .reservation_state import union_job_segments\n',
        ('require_tracking_public', 'service_integral', 'TrackingReference')),
    'unified_contract': ('import hashlib\nimport json\n',
                         ('BINDING_FIELDS', 'digest', 'require_bindings')),
    'aidc_sensitivity_runtime': (
        'from copy import deepcopy\nfrom dataclasses import asdict\nfrom time import perf_counter\n'
        'import math\nimport json\nfrom pathlib import Path\nimport hashlib\nimport numpy as np\n'
        'from .actual import _require_public_metadata\n'
        'from .policy import digest, _receipt, migration_guard, ReservationLedger\n'
        'from .reservation_state import union_job_segments\n'
        'from .trajectory_tracking import TrackingReference, service_integral, require_tracking_public\n'
        'from .frozen_unknown import _migration_capability\n'
        'from .unified_contract import require_bindings\nfrom v42_final.workload import ForecastBook\n',
        ('CONTRACT', 'MODE', 'DELAY_SECONDS', 'grid_numeric_fingerprint',
         'conditional_remaining_runtime', 'anonymous_cohort_residual',
         'SignedSensitivityPolicy', 'safe_backfill')),
}


def selected(raw, header, names):
    source = raw.decode('utf-8-sig')
    lines = source.splitlines(keepends=True)
    nodes = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            nodes[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = node
    slices, spans = [], []
    for name in names:
        node = nodes[name]
        start = min([node.lineno] + [x.lineno for x in getattr(node, 'decorator_list', [])])
        slices.append(''.join(lines[start-1:node.end_lineno]))
        spans.append(dict(symbol=name, first_line=start, last_line=node.end_lineno))
    return (header + '\n\n' + '\n\n'.join(slices)).encode('utf8'), spans


def prepare():
    prior = read(MANIFEST) if MANIFEST.exists() else None
    expected = {} if prior is None else {Path(r['port']['path']).stem:r['source'] for r in prior['modules']}
    inventory = {Path(r['path']).stem:r for r in read(DOC/'GATE_B_SELECTIVE_SOURCE_INVENTORY.json')['sources']}
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST/'__init__.py').write_text('"""SHA-pinned existing runtime algorithms; see port manifest."""\n', encoding='utf8')
    rows = []
    for name in WHOLE + tuple(SLICES):
        path = (PR231/'v42_voltage_control/b0_new.py') if name == 'private_truth' else SOURCE/(name+'.py')
        original = record(path)
        pin = expected.get(name, inventory.get(name))
        if pin and any(original[k] != pin[k] for k in ('bytes','sha256')):
            raise ValueError('SELECTIVE_PORT_SOURCE_DRIFT:'+name)
        raw = path.read_bytes()
        if name in WHOLE:
            payload, spans = raw, []
        else:
            payload, spans = selected(raw, *SLICES[name])
        target = DEST/(name+'.py')
        if target.exists() and target.read_bytes() != payload:
            raise ValueError('SELECTIVE_PORT_TARGET_DRIFT:'+name)
        target.write_bytes(payload)
        rows.append(dict(source=original, port=record(target), whole_file_exact_bytes=name in WHOLE,
                         exact_source_definitions=spans))
    manifest = dict(schema='V43_SELECTIVE_ACTUAL_PORT_V1', modules=rows,
        planning_formulation_imported=False, D0_initial_state_imported=False,
        historical_solution_imported=False, added_11_SVR_imported=False,
        initialization_scope='ISSUE_OBSERVED_RUNNING_WITH_EXPLICIT_MISSING_SITE_MODEL_ASSUMPTION',
        Golden003_source_modified=False, Gate_B_PASS=False)
    if prior is not None:
        by_path = {r['port']['path']:r for r in manifest['modules']}
        if any(by_path.get(r['port']['path']) != r for r in prior['modules']):
            raise ValueError('SELECTIVE_PORT_MANIFEST_DRIFT')
    atomic(MANIFEST, manifest)
    return manifest


if __name__ == '__main__':
    prepare()

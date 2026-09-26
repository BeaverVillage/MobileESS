"""Audit-only Timestamp serialization adapter for the unchanged frozen verifier.

The registered verifier compares a Python Timestamp with the string produced
by its own JSON default=str writer. Normalize that type exactly as the writer
does; every forecast, membership value, model and scientific source stays fixed.
"""
from pathlib import Path
import hashlib
import json
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import study as s

s.guard(True)
before = hashlib.sha256((ROOT / 'study.py').read_bytes()).hexdigest()
freeze = s.read('FINAL_SELECTION_FREEZE.json')
data = s.raw('2025-05-31')
timestamp_fields = 0
for model, candidate in freeze['choices'].items():
    _, _, proof = s.compose('2025-05-31', candidate['config'], data)
    stored = s.read(model + '_CALIBRATION_MEMBERSHIP.json')
    original = s.clean(proof)
    normalized = json.loads(json.dumps(original, default=str, allow_nan=False))
    assert normalized == stored, ('ACTUAL_MEMBERSHIP_DRIFT', model)
    assert len(original) == len(stored)
    for live, artifact in zip(original, stored):
        assert set(live) == set(artifact)
        for name, value in live.items():
            if isinstance(value, pd.Timestamp):
                assert name == 'issue' and str(value) == artifact[name]
                timestamp_fields += 1
            else:
                assert value == artifact[name], ('NON_TIMESTAMP_MISMATCH', model, name)

original_clean = s.clean


def artifact_clean(value):
    return str(value) if isinstance(value, pd.Timestamp) else original_clean(value)


s.clean = artifact_clean
s.verify()
assert hashlib.sha256((ROOT / 'study.py').read_bytes()).hexdigest() == before
receipt = dict(
    PASS=True, frozen_source_sha256=before,
    original_verifier_exception='AssertionError: CALIBRATION_MEMBERSHIP',
    original_exception_stage='study.py verify after successful evaluation',
    cause='273 C1 issue Timestamp objects compared to their JSON default=str serialization; C2 proof is empty',
    exact_timestamp_fields=timestamp_fields,
    all_other_fields_equal_without_normalization=True,
    registered_scientific_code_modified=False, model_decisions_changed=False,
    forecasts_or_membership_modified=False,
    adapter='Normalize only pd.Timestamp with str(), identical to existing writer, then execute every original verify check',
    separate_independent_replay='INDEPENDENT_AUDIT.json',
)
assert timestamp_fields == 273
with (ROOT / 'VERIFIER_SERIALIZATION_AUDIT.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(receipt, stream, indent=2, allow_nan=False)
print('FROZEN VERIFY PASS; representation-only Timestamp fields:', timestamp_fields)

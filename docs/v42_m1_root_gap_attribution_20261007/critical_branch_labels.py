"""Attach immutable native branch labels to the already audited line indices.

Reads the archived electrical certificate and its planning NPZ only.  Does
not construct coefficients, invoke the grid builder, or optimize a model.
"""
import csv
import hashlib
import json
import pickle
import sys
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[1]))
SOURCE = Path('C:/Users/kjw39/Documents/Codex/2026-10-03/'
              'single-worker-single-thread-a1-m1/SINGLE_THREAD_LOCAL')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    source_data_SHA = sha(SOURCE/'DATA.pkl')
    with (SOURCE/'DATA.pkl').open('rb') as stream:
        bundle = pickle.load(stream)[0]
    certificate_receipt = bundle['electrical_certificate']
    certificate_path = Path(certificate_receipt['path'])
    assert sha(certificate_path) == certificate_receipt['sha256']
    certificate = json.loads(certificate_path.read_text(encoding='utf-8-sig'))
    planning = certificate['outputs']['planning_coefficients']
    planning_path = Path(planning['path'])
    assert sha(planning_path) == planning['sha256']
    with np.load(planning_path, allow_pickle=False) as archive:
        branch_names = archive['branch_names'].copy()
    assert branch_names.ndim == 1
    audit_path = OUT/'CRITICAL_LINE_TIME_AUDIT.csv'
    with audit_path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames)
        records = list(reader)
    for key in ['branch_name', 'branch_authority_SHA256']:
        if key not in fields:
            fields.append(key)
    mapping = {}
    for record in records:
        line = int(record['line_index'])
        assert 0 <= line < len(branch_names)
        record['branch_name'] = str(branch_names[line])
        record['branch_authority_SHA256'] = planning['sha256']
        mapping[line] = str(branch_names[line])
    with audit_path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields, lineterminator='\n')
        writer.writeheader(); writer.writerows(records)
    assert sha(certificate_path) == certificate_receipt['sha256']
    assert sha(planning_path) == planning['sha256']
    assert sha(SOURCE/'DATA.pkl') == source_data_SHA
    report = dict(PASS=True, optimize_calls=0, grid_build_calls=0,
        source_DATA_SHA256=source_data_SHA,
        branch_axis_source=str(planning_path), planning_SHA256=planning['sha256'],
        certificate_source=str(certificate_path),
        certificate_SHA256=certificate_receipt['sha256'],
        branch_axis_count=len(branch_names), mapped_critical_rows=len(records),
        line_index_to_original_branch_name=mapping,
        original_inputs_unchanged=True,
        native_line_indices_previously_recovered_through_saved_row_axes=True,
        remaining_alias_column_names_not_used_as_target_line_identity=True)
    (OUT/'CRITICAL_BRANCH_AUTHORITY.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('CRITICAL_BRANCH_LABELS_DONE', len(records), mapping, flush=True)


if __name__ == '__main__':
    main()

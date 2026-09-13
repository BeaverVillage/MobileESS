"""Read-only evidence validation and synthetic movement-boundary regression."""
import csv
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    manifest = load(ROOT / 'SOURCE_COPY_MANIFEST.json')
    for row in manifest['files']:
        data = (ROOT / row['path']).read_bytes()
        assert len(data) == row['bytes'], row['path']
        assert hashlib.sha256(data).hexdigest() == row['sha256'], row['path']
    paper = ROOT / 'paper_csv'
    for row in load(paper / 'IEEE8500_PAPER_CSV_MANIFEST.json')['files']:
        assert hashlib.sha256((paper / row['filename']).read_bytes()).hexdigest() == row['sha256']
    with zipfile.ZipFile(paper / 'IEEE8500_PAPER_CSV_UPLOAD.zip') as package:
        assert package.testzip() is None
        assert len(package.namelist()) == 13
        for name in package.namelist():
            assert package.read(name) == (paper / name).read_bytes()
    with (paper / '03_AC_FEASIBILITY_SUMMARY.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 8
    assert len({(r['policy'], r['validation_scope']) for r in rows}) == 8
    assert all(r['overall_ac_feasible'] == 'true' for r in rows)
    b2 = load(ROOT / 'evidence/IEEE8500_B2_actual_availability_gating_20260912_r3/FINAL_ACCEPTANCE.json')
    assert b2['status'] == 'PASS'
    assert b2['summary']['converged_slots'] == b2['summary']['controls_settled_slots'] == 96
    assert b2['executed_P_unchanged_by_QSAFE'] and b2['all_original_frozen_SHA_and_mtime_preserved']
    assert b2['mobility']['departure_shift_count'] == 0
    assert b2['mobility']['previous_unnecessary_ready_based_shifts_removed'] == 4
    assert b2['independent_AC_replay']['status'] == 'PASS'
    gate = load(ROOT / 'evidence/IEEE8500_B2_actual_availability_gating_20260912_r3/IEEE123_REGRESSION_GATE.json')
    assert gate['status'] == 'PASS' and gate['totals']['policy_days'] == 124
    assert gate['totals']['baseline_record_differences'] == gate['totals']['QSAFE_availability_mask_differences'] == 0
    source = ROOT / 'frozen_code/IEEE8500_B2_actual_availability_gating_20260912_r3/availability_gating.py'
    spec = importlib.util.spec_from_file_location('arrival_boundary', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands = [dict(mess_id='M', slot=t, departure_slot=t, origin_service_id=o,
                     destination_service_id=d, route_link_ids=[o+'_'+d], connection_ready_slot=t+2)
                for t, o, d in [(39, 'A', 'B'), (41, 'B', 'C')]]
    for arrival, expected in [(40.5059, 41), (41.2, 42)]:
        def realized(command, departure):
            return dict(command, departure_slot=departure,
                        actual_arrival_slot=arrival if command['slot'] == 39 else departure+0.2,
                        actual_connection_ready_slot=42 if command['slot'] == 39 else departure+1)
        result = module.realize_sequence(commands, {'M': 'A'}, realized)
        assert result[1]['actual_departure_slot'] == expected
    assert not module.command_gate(False, 'B', 'B')
    assert not module.command_gate(True, 'B', 'C')
    assert module.qsafe_eligible(True, 'B', None)
    assert not module.qsafe_eligible(False, 'B', 'B')
    print(json.dumps(dict(status='PASS',copied_files=len(manifest['files']),ac_policy_scopes=len(rows),
                         synthetic_boundary_cases=2,scientific_execution_count=0)))


if __name__ == '__main__':
    main()

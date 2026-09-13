"""Validate review snapshots and small fixtures without reading campaign data."""
import ast
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent / 'paper_export'))
import export_v41r4_final_archive_to_csv as export


def main():
    manifest = json.loads((ROOT / 'docs/v41r4_final/SOURCE_SNAPSHOT.json').read_text(encoding='utf-8-sig'))
    posthoc = json.loads((ROOT / 'docs/v41r4_final/POSTHOC_SOURCE_SNAPSHOT.json').read_text(encoding='utf-8-sig'))
    records = manifest['files'] + posthoc['files']
    assert len({record['path'] for record in records}) == len(records)
    python_count = 0
    for record in records:
        path = ROOT / record['path']
        data = path.read_bytes()
        assert len(data) == record['bytes'], record['path']
        assert hashlib.sha256(data).hexdigest() == record['sha256'], record['path']
        if path.suffix == '.py':
            ast.parse(data, filename=record['path'])
            python_count += 1

    source = export.Source.__new__(export.Source)
    source.errors = []
    with tempfile.TemporaryDirectory(prefix='v41r4_pr_fixture_') as directory:
        root = Path(directory)
        source.root = root
        for path in ('../outside', '/absolute', 'C:\\outside', '\\\\host\\share'):
            try:
                source.path(path)
            except ValueError:
                pass
            else:
                raise AssertionError('Source accepted an external path')
        assert source.path('inside/data.json') == root / 'inside/data.json'

        archive = root / 'unsafe.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            member = tarfile.TarInfo('../escaped.txt')
            member.size = 1
            output.addfile(member, io.BytesIO(b'x'))
        before = archive.read_bytes()
        try:
            export.intake(archive, root / 'cache', root / 'report.json')
        except ValueError as error:
            assert str(error) == 'UNSAFE_ARCHIVE_PATH'
        else:
            raise AssertionError('Intake accepted archive traversal')
        assert not (root / 'escaped.txt').exists()
        assert before == archive.read_bytes()

        reference = dict(job_uid='fixture', requested_GPU=1, AIDC_site='A',
                         start_slot=0, end_slot=188, safe_duration_seconds=188*900,
                         safe_duration_slots=188, compute_segments=[dict(start=0, end=188)],
                         state_at_issue='RUNNING')
        migrated = dict(reference, migration_selected=True, end_slot=190,
                        compute_segments=[dict(start=0, end=26), dict(start=28, end=190)])
        rows = export.project_jobs(source, '2025-05-01', 'B1', [migrated], [reference])
        assert rows[0]['reference_terminal_remaining_slots'] == 68
        assert rows[0]['optimized_terminal_remaining_slots'] == 70
        assert rows[0]['terminal_invariant_pass'] is False
        assert len(source.errors) == 1
        assert source.errors[0]['check'] == 'AIDC_TERMINAL_RESIDUAL_INCREASE'
        source.errors.clear()
        unchanged = export.project_jobs(source, '2025-05-01', 'B0', [reference], [reference])
        assert unchanged[0]['terminal_invariant_pass'] is True and not source.errors

        rows = [dict(day='2025-05-01', value=0.643702807717228, label='결과', valid=True),
                dict(day='2025-05-02', value=export.NA, label='a,b', valid=False)]
        metadata = export.write_csv(root, 'fixture', rows, ['day', 'value', 'label', 'valid'])
        with (root / 'fixture.csv').open(encoding='utf-8-sig', newline='') as handle:
            restored = list(csv.DictReader(handle))
        assert metadata['row_count'] == len(restored) == 2
        assert float(restored[0]['value']) == rows[0]['value']
        assert restored[0]['label'] == '결과' and restored[1]['label'] == 'a,b'
        assert restored[1]['value'] == export.NA
        assert restored[0]['valid'] == 'TRUE' and restored[1]['valid'] == 'FALSE'
        assert metadata['parts'][0]['SHA256'] == hashlib.sha256((root / 'fixture.csv').read_bytes()).hexdigest()

    print(json.dumps(dict(status='PASS', copied_files_verified=len(records),
                          python_sources_parsed=python_count,
                          fixtures=['external_path_rejection', 'archive_traversal_rejection',
                                    'terminal_residual_fail_closed', 'unchanged_terminal_pass',
                                    'CSV_precision_unicode_missing_boolean_roundtrip'],
                          campaign_data_read=False, campaign_reexecuted=False,
                          exporter_terminal_gate='FAIL_CLOSED (unchanged)',
                          independent_projection_classification='VALID_WITH_SCIENTIFIC_TERMINAL_LIMITATION',
                          deadline_compliance='NOT_AVAILABLE'), indent=2))


if __name__ == '__main__':
    main()

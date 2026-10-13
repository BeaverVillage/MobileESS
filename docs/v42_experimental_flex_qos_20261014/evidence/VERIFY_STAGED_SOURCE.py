"""Check that Git's index retains the executed source bytes exactly."""
from pathlib import Path
import gzip, hashlib, io, json, subprocess, tarfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    freeze = json.loads((ROOT / 'audit/SOURCE_FREEZE_C.json').read_text(encoding='utf8'))
    entries = []
    batch = ('\n'.join(':' + row['path'] for row in freeze['files']) + '\n').encode('utf8')
    objects = io.BytesIO(subprocess.check_output(['git', 'cat-file', '--batch'], cwd=ROOT, input=batch))
    for row in freeze['files']:
        path = row['path']
        header = objects.readline().decode('utf8').strip().split()
        assert header[-2] == 'blob', (path, header)
        indexed = objects.read(int(header[-1]))
        assert objects.read(1) == b'\n'
        entries.append(dict(path=path, executed_sha256=row['sha256'],
            indexed_sha256=hashlib.sha256(indexed).hexdigest(),
            LF_normalized_bytes_match=indexed.replace(b'\r\n', b'\n') == (ROOT / path).read_bytes().replace(b'\r\n', b'\n'),
            PASS=hashlib.sha256(indexed).hexdigest() == row['sha256']))
    changed = set(subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--', '*.py'], cwd=ROOT, text=True).splitlines())
    archive = ROOT / 'audit/EXECUTED_SOURCE_BYTES.tar.gz'
    with archive.open('wb') as target, gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as packed:
        with tarfile.open(fileobj=packed, mode='w', format=tarfile.PAX_FORMAT) as bundle:
            for row in freeze['files']:
                data = (ROOT / row['path']).read_bytes()
                assert hashlib.sha256(data).hexdigest() == row['sha256'], 'FROZEN_SOURCE_DRIFT'
                info = tarfile.TarInfo(row['path']); info.size = len(data); info.mode = 0o644
                bundle.addfile(info, io.BytesIO(data))
    with tarfile.open(archive, 'r:gz') as bundle:
        archive_PASS = all(hashlib.sha256(bundle.extractfile(row['path']).read()).hexdigest() == row['sha256'] for row in freeze['files'])
    changed_PASS = all(row['PASS'] for row in entries if row['path'] in changed)
    normalized_PASS = all(row['LF_normalized_bytes_match'] for row in entries)
    receipt = dict(source_sha=freeze['source_sha'], source_files=len(entries),
        git_index_matches_executed_bytes=all(row['PASS'] for row in entries),
        changed_source_index_bytes_exact_PASS=changed_PASS,
        all_index_source_LF_normalized_match_PASS=normalized_PASS,
        unchanged_ancestor_checkout_EOL_differences=sum(not row['PASS'] for row in entries),
        executed_source_lossless_archive=str(archive.relative_to(ROOT)), archive_SHA256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        executed_source_archive_bytes_PASS=archive_PASS,
        scope='CHANGED_SOURCE_INDEX_EXACT;UNCHANGED_ANCESTOR_CHECKOUT_EOL_DISCLOSED;ALL_EXECUTED_BYTES_ARCHIVED_LOSSLESS',
        PASS=changed_PASS and normalized_PASS and archive_PASS, files=entries)
    (ROOT / 'audit/GIT_STAGED_SOURCE_BYTE_VERIFICATION.json').write_text(
        json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    assert receipt['PASS'], 'STAGED_OR_ARCHIVED_SOURCE_MISMATCH'
    print(json.dumps({key: receipt[key] for key in ('source_sha', 'source_files', 'changed_source_index_bytes_exact_PASS',
        'all_index_source_LF_normalized_match_PASS', 'unchanged_ancestor_checkout_EOL_differences', 'executed_source_archive_bytes_PASS', 'PASS')}))

if __name__ == '__main__':
    main()

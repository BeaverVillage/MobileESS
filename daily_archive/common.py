import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time
import zipfile
import io
import threading


BASE = Path(r'D:\MobileESS_V44\runtime\v43_planning_svr12_actual_v1')
DEST = Path(r'C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\IEEE123')
AUDIT = Path(__file__).resolve().parent
REPORT = DEST / 'V44_2025-05-01_14_VERIFICATION.json'
CHUNK = 4 * 1024 * 1024
START = time.monotonic()
last_progress = 0
REPORT_LOCK = threading.RLock()
LOG_LOCK = threading.RLock()
PIN_FILE = AUDIT / 'retained_validation_evidence.json'
PINS = json.loads(PIN_FILE.read_text(encoding='utf-8'))['files'] if PIN_FILE.exists() else []


def retained_for(source):
    root = source.resolve()
    return [r for r in PINS if Path(r['path']).resolve().is_relative_to(root)]


def check_remaining_metadata(source, retained):
    if not retained:
        return not source.exists()
    if not source.is_dir():
        return False
    files, _ = tree_inventory(source)
    expected = {Path(r['path']).relative_to(source).as_posix(): r for r in retained}
    if set(files) != set(expected):
        return False
    return all(digest_file(source / rel) == r['sha256'] and (source / rel).stat().st_size == r['bytes']
               for rel, r in expected.items())


def delete_results_keep_validation(source, files, dirs, retained):
    if not retained:
        shutil.rmtree(source)
        return
    kept = {Path(r['path']).relative_to(source).as_posix() for r in retained}
    if not kept <= set(files):
        raise RuntimeError('Required validation metadata absent from archived source')
    for rel in files:
        if rel not in kept:
            (source / rel).unlink()
    for rel in sorted(dirs, key=lambda x: (len(Path(x).parts), x), reverse=True):
        folder = source / rel
        if any(Path(k).is_relative_to(Path(rel)) for k in kept):
            continue
        folder.rmdir()
    if not check_remaining_metadata(source, retained):
        raise RuntimeError('Unexpected files remain after result deletion')


class StreamingOutput:
    """Buffer sequential ZIP output; ZIP data descriptors avoid per-entry seeks."""
    def __init__(self, path):
        self.file = Path(path).open('xb', buffering=4*1024*1024)
        self.position = 0

    def write(self, value):
        n = self.file.write(value)
        self.position += n
        return n

    def tell(self):
        return self.position

    def seek(self, *args):
        raise io.UnsupportedOperation('sequential ZIP output')

    def flush(self):
        self.file.flush()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.file.close()


def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()


def emit(event, **data):
    record = {'time': now(), 'event': event, **data}
    line = json.dumps(record, ensure_ascii=False)
    with LOG_LOCK:
        print(line, flush=True)
        with (AUDIT / 'progress.jsonl').open('a', encoding='utf-8') as f:
            f.write(line + '\n')


def progress(phase, day, count, total, done_bytes, total_bytes):
    global last_progress
    if time.monotonic() - last_progress >= 10:
        emit('PROGRESS', phase=phase, day=day, files=count, total_files=total,
             GB=round(done_bytes / 1e9, 3), total_GB=round(total_bytes / 1e9, 3))
        last_progress = time.monotonic()


def atomic_json(path, value):
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def signature(p):
    s = p.stat(follow_symlinks=False)
    if s.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise RuntimeError(f'Reparse point is not allowed in source tree: {p}')
    return s.st_size, s.st_mtime_ns


def tree_inventory(root):
    files, dirs = {}, set()
    signature(root)
    stack = [root]
    while stack:
        folder = stack.pop()
        with os.scandir(folder) as entries:
            for entry in entries:
                p = Path(entry.path)
                s = entry.stat(follow_symlinks=False)
                if s.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise RuntimeError(f'Reparse point is not allowed: {p}')
                rel = p.relative_to(root).as_posix()
                if entry.is_dir(follow_symlinks=False):
                    dirs.add(rel)
                    stack.append(p)
                elif entry.is_file(follow_symlinks=False):
                    files[rel] = (s.st_size, s.st_mtime_ns)
                else:
                    raise RuntimeError(f'Unsupported source entry: {p}')
    return files, dirs


def digest_file(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def check_delete_target(source, campaign, day):
    expected_campaign = 'campaign004' if day <= '2025-05-07' else 'campaign005_may08_14'
    assert campaign.name == expected_campaign
    assert campaign.resolve() == (BASE / expected_campaign).resolve()
    assert source.resolve() == (BASE / expected_campaign / day).resolve()
    assert source.name == day and source.parent.resolve() == campaign.resolve()
    assert dt.date(2025, 5, 1) <= dt.date.fromisoformat(day) <= dt.date(2025, 5, 14)
    assert source.resolve().is_relative_to(BASE.resolve())
    signature(source)


def archive_day(day, report):
    campaign = BASE / ('campaign004' if day <= '2025-05-07' else 'campaign005_may08_14')
    source = campaign / day
    archive = DEST / f'V44_IEEE123_{day}.zip'
    partial = archive.with_name(archive.name + '.partial')
    check_delete_target(source, campaign, day)
    if archive.exists():
        raise RuntimeError(f'Refusing to overwrite existing archive: {archive}')
    state = json.loads((campaign / 'CAMPAIGN_STATUS.json').read_text(encoding='utf-8-sig'))
    cases = [x for x in state['cases'] if x['day'] == day]
    if len(cases) != 4 or {x['arm'] for x in cases} != {'B0', 'B1', 'B2', 'B3'}:
        raise RuntimeError(f'Expected four complete cases: {day}')
    if any(x['status'] not in {'COMPLETE', 'PASS'} for x in cases):
        raise RuntimeError(f'Incomplete case on {day}: {cases}')

    emit('INVENTORY_START', day=day, source=str(source))
    tree_files, tree_dirs = tree_inventory(source)
    items = []
    for rel, sig in sorted(tree_files.items()):
        items.append((source / Path(rel), f'{day}/{rel}', sig, True))
    # Include small date-specific reference/request records and campaign metadata.
    support_files = list((campaign / 'B1_A1').glob(day + '*'))
    support_files += list((campaign / 'requests').glob(day + '*'))
    refs = campaign / 'references' / day
    if refs.is_dir():
        ref_files, _ = tree_inventory(refs)
        support_files += [refs / Path(x) for x in ref_files]
    support_files += list(campaign.glob('*.json'))
    for p in sorted(set(support_files)):
        if p.is_file():
            items.append((p, 'campaign_support/' + p.relative_to(campaign).as_posix(), signature(p), False))
    total_bytes = sum(sig[0] for _, _, sig, _ in items)
    day_bytes = sum(sig[0] for _, _, sig, is_result in items if is_result)
    emit('COMPRESS_START', day=day, files=len(items), result_bytes=day_bytes, total_bytes=total_bytes)
    if not partial.exists():
        records, processed = [], 0
        dirs = [f'{day}/'] + [f'{day}/{x}/' for x in sorted(tree_dirs)]
        with StreamingOutput(partial) as output, zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as z:
            for name in dirs:
                z.writestr(name, b'')
            for idx, (p, name, sig, is_result) in enumerate(items, 1):
                if signature(p) != sig:
                    raise RuntimeError(f'Source changed before compression: {p}')
                info = zipfile.ZipInfo.from_file(p, arcname=name)
                info.compress_type = zipfile.ZIP_STORED if p.suffix.lower() in {'.gz', '.zip', '.7z'} else zipfile.ZIP_DEFLATED
                info._compresslevel = 6
                h, size = hashlib.sha256(), 0
                with p.open('rb') as f, z.open(info, 'w', force_zip64=True) as out:
                    while block := f.read(CHUNK):
                        h.update(block)
                        out.write(block)
                        size += len(block)
                        progress('COMPRESS', day, idx - 1, len(items), processed + size, total_bytes)
                if size != sig[0] or signature(p) != sig:
                    raise RuntimeError(f'Source changed during compression: {p}')
                records.append({'path': name, 'bytes': size, 'mtime_ns': sig[1], 'sha256': h.hexdigest()})
                processed += size
                progress('COMPRESS', day, idx, len(items), processed, total_bytes)
            manifest = {'version': 1, 'day': day, 'created': now(), 'source': str(source),
                        'campaign': str(campaign), 'source_result_files': len(tree_files),
                        'source_result_bytes': day_bytes, 'total_uncompressed_bytes': total_bytes,
                        'directories': dirs, 'files': records,
                        'scope': 'All B0-B3 attempts, plus date-specific support and campaign metadata snapshots'}
            z.writestr('_ARCHIVE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False))
        with partial.open('r+b') as f:
            os.fsync(f.fileno())
    else:
        with zipfile.ZipFile(partial, 'r') as z:
            manifest = json.loads(z.read('_ARCHIVE_MANIFEST.json'))
        records, dirs = manifest['files'], manifest['directories']
        expected_records = [(name, sig[0], sig[1]) for _, name, sig, _ in items]
        if [(r['path'], r['bytes'], r['mtime_ns']) for r in records] != expected_records:
            raise RuntimeError('Existing partial archive does not match unchanged source inventory')
        emit('RESUME_COMPLETED_ARCHIVE_VERIFICATION', day=day)
    emit('VERIFY_START', day=day, archive_bytes=partial.stat().st_size, files=len(items))

    processed = 0
    with zipfile.ZipFile(partial, 'r') as z:
        names = z.namelist()
        expected = {name for _, name, _, _ in items} | set(dirs) | {'_ARCHIVE_MANIFEST.json'}
        if len(names) != len(expected) or set(names) != expected:
            raise RuntimeError('Archive entry set differs from source inventory')
        if json.loads(z.read('_ARCHIVE_MANIFEST.json')) != manifest:
            raise RuntimeError('Embedded manifest mismatch')
        for idx, ((p, name, sig, _), record) in enumerate(zip(items, records), 1):
            if signature(p) != sig:
                raise RuntimeError(f'Source changed before verification: {p}')
            source_hash, archive_hash, size = hashlib.sha256(), hashlib.sha256(), 0
            with p.open('rb') as original, z.open(name, 'r') as archived:
                while True:
                    a, b = original.read(CHUNK), archived.read(CHUNK)
                    if a != b:
                        raise RuntimeError(f'Byte comparison mismatch: {p}')
                    if not a:
                        break
                    source_hash.update(a)
                    archive_hash.update(b)
                    size += len(a)
                    progress('VERIFY', day, idx - 1, len(items), processed + size, total_bytes)
            if source_hash.hexdigest() != record['sha256'] or archive_hash.hexdigest() != record['sha256']:
                raise RuntimeError(f'SHA-256 mismatch: {p}')
            if size != sig[0] or signature(p) != sig:
                raise RuntimeError(f'Source changed during verification: {p}')
            processed += size
            progress('VERIFY', day, idx, len(items), processed, total_bytes)

    # Reinventory immediately before deletion to catch newly added or changed files.
    final_files, final_dirs = tree_inventory(source)
    if final_files != tree_files or final_dirs != tree_dirs:
        raise RuntimeError(f'Source tree changed; original retained: {source}')
    os.rename(partial, archive)
    archive_sha = digest_file(archive)
    retained = retained_for(source)
    entry = {'day': day, 'source': str(source), 'archive': str(archive),
             'result_bytes': day_bytes, 'result_files': len(tree_files),
             'archived_total_bytes': total_bytes, 'archived_total_files': len(items),
             'archive_bytes': archive.stat().st_size, 'archive_sha256': archive_sha,
             'verified': now(), 'verification': 'Full byte comparison, per-file SHA-256 and ZIP CRC; source inventory unchanged',
             'original_deleted': False, 'common_support_originals_retained': True,
             'retained_validation_evidence': retained,
             'result_bytes_deleted': day_bytes - sum(r['bytes'] for r in retained),
             'result_files_deleted': len(tree_files) - len(retained),
             'source_directory_removed': not bool(retained)}
    with REPORT_LOCK:
        report['days'].append(entry)
        atomic_json(REPORT, report)
        atomic_json(AUDIT / 'verification_report.json', report)
    emit('VERIFIED', **entry)
    # No shell invocation: validate the exact absolute date directory and remove it natively.
    check_delete_target(source, campaign, day)
    final_files, final_dirs = tree_inventory(source)
    if final_files != tree_files or final_dirs != tree_dirs:
        raise RuntimeError(f'Source changed after archive hash; original retained: {source}')
    emit('DELETE_START', day=day, exact_path=str(source.resolve()))
    delete_results_keep_validation(source, tree_files, tree_dirs, retained)
    if not check_remaining_metadata(source, retained):
        raise RuntimeError(f'Original result deletion check failed: {source}')
    with REPORT_LOCK:
        entry['original_deleted'] = True
        entry['deleted_at'] = now()
        atomic_json(REPORT, report)
        atomic_json(AUDIT / 'verification_report.json', report)
    emit('DAY_COMPLETE', day=day, archive_bytes=entry['archive_bytes'], original_bytes=day_bytes,
         archive_sha256=archive_sha, original_deleted=True)


def main():
    AUDIT.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)
    if REPORT.exists():
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        if report['status'] != 'ERROR' or report['days']:
            raise RuntimeError('Existing report needs manual inspection before resume')
        report['previous_error'] = report.pop('error', None)
        report['status'] = 'RUNNING'
        report['resumed_at'] = now()
    else:
        report = {'started': now(), 'destination': str(DEST), 'status': 'RUNNING', 'days': []}
    atomic_json(REPORT, report)
    emit('RUN_START', destination=str(DEST), free_destination_bytes=shutil.disk_usage(DEST).free)
    try:
        for n in range(1, 15):
            archive_day(f'2025-05-{n:02d}', report)
        report['status'] = 'COMPLETE'
        report['finished'] = now()
        report['total_result_bytes_deleted'] = sum(x['result_bytes'] for x in report['days'])
        report['total_archive_bytes'] = sum(x['archive_bytes'] for x in report['days'])
        report['total_files_verified'] = sum(x['archived_total_files'] for x in report['days'])
        atomic_json(REPORT, report)
        atomic_json(AUDIT / 'verification_report.json', report)
        emit('ALL_COMPLETE', total_archive_bytes=report['total_archive_bytes'],
             total_result_bytes_deleted=report['total_result_bytes_deleted'],
             total_files_verified=report['total_files_verified'], elapsed_seconds=round(time.monotonic()-START,1))
    except BaseException as exc:
        report['status'] = 'ERROR'
        report['error'] = repr(exc)
        report['error_time'] = now()
        atomic_json(REPORT, report)
        atomic_json(AUDIT / 'verification_report.json', report)
        emit('ERROR', error=repr(exc))
        raise


if __name__ == '__main__':
    main()

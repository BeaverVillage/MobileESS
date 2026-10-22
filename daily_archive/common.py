"""Prior daily-export utility functions; no standalone archive/delete entry."""
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

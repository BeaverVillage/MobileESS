"""Windows-safe status publication; independent of scientific controller code."""
from pathlib import Path
import json, os, time, uuid, msvcrt

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + str(os.getpid()) + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    for attempt in range(60):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(min(.05 * (attempt + 1), .5))

def exclusive_supervisor(path):
    handle = Path(path).open('a+b')
    handle.seek(0)
    if Path(path).stat().st_size == 0:
        handle.write(b'0'); handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        raise RuntimeError('SUPERVISOR_ALREADY_RUNNING')
    return handle

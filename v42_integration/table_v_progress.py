"""Best-effort live diagnostics, separate from durable Raw and Native writes.

Only display snapshots may be skipped; evidence and budget writers stay strict.
"""
import json
from pathlib import Path
import sys
import tempfile
from time import sleep, time

from .m_engine import _json_value


def write_progress(path, value):
    """Keep the previous complete snapshot on sharing failure; never abort work.

Unique temporary files also prevent competing display writers from sharing one
`.tmp` name. A short bounded retry handles scanners and legacy readers. Failure
is recorded in an append-only warning stream, falling back to stderr if needed.
Serialization errors remain visible to the caller as programming errors.
"""
    path = Path(path)
    payload = json.dumps(_json_value(value), ensure_ascii=False, allow_nan=False, indent=2) + '\n'
    temporary = None
    error = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf8',
                prefix=path.name + '.', suffix='.tmp', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        for attempt in range(4):
            try:
                temporary.replace(path)
                return True
            except PermissionError:
                if attempt == 3:
                    raise
                sleep(.01 * (attempt + 1))
    except OSError as exc:
        error = exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    warning = dict(schema='TABLE_V_DISPLAY_WRITE_WARNING_V1', path=str(path),
                   epoch_seconds=time(), error=repr(error),
                   previous_snapshot_preserved=True, Raw_or_Native_write=False)
    message = json.dumps(warning, ensure_ascii=False) + '\n'
    try:
        with path.with_name(path.name + '.warnings.jsonl').open('a', encoding='utf8') as stream:
            stream.write(message)
    except OSError:
        try:
            sys.stderr.write(message)
            sys.stderr.flush()
        except OSError:
            pass
    return False

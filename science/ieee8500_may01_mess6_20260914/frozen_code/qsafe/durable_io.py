"""Atomic JSON writes with bounded Windows sharing-violation retries."""
import json, os, time, uuid
from pathlib import Path
from runtime import H, clean

def save(p, value):
    p = Path(p)
    assert p.absolute().is_relative_to(H)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.' + str(os.getpid()) + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(clean(value), indent=2), encoding='utf-8')
    try:
        for attempt in range(101):
            try:
                os.replace(tmp, p)
                break
            except PermissionError:
                if attempt == 100:
                    raise
                time.sleep(.05)
    finally:
        if tmp.exists():
            tmp.unlink()

def state(**kw):
    save(H / 'STATUS.json', dict(unix=time.time(), pid=os.getpid(), **kw))

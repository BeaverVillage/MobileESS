"""Windows-safe atomic persistence; retry sharing violations without changing data."""
from contextlib import contextmanager
from pathlib import Path
import os, tempfile, time

@contextmanager
def atomic(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w+b') as stream:
            yield stream;stream.flush();os.fsync(stream.fileno())
        for attempt in range(101):
            try:os.replace(name,path);break
            except PermissionError:
                if attempt==100:raise
                time.sleep(.05)
    finally:
        if os.path.exists(name):os.unlink(name)

def install():
    from dayahead.paper_analysis import storage
    storage.atomic=atomic


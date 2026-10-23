"""Resolve manifest path aliases only after matching immutable file bytes."""
from pathlib import Path

def canonical_inputs(records,record):
    canonical={}
    for name,expected in records.items():
        actual=record(expected['path'])
        if (actual['sha256']!=expected['sha256'] or actual['bytes']!=expected['bytes']
                or Path(actual['path']).resolve()!=Path(expected['path']).resolve()):
            raise ValueError('INPUT_CONTENT_OR_RESOLVED_PATH_DRIFT:'+name)
        canonical[name]=actual
    return canonical

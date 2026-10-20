"""Same per-call enum validation over every row/column; no validation cache."""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from unittest.mock import patch
import inspect,linecache,textwrap
import numpy as np

def valid_labels(values,allowed):
    if type(values) is np.ndarray and values.ndim==1 and values.dtype.kind=='U' and len(values)>=128:
        valid=values==allowed[0]
        for label in allowed[1:]:valid|=values==label
        return bool(valid.all())
    return not any(value not in allowed for value in values)

def adapted_require(original):
    source=textwrap.dedent(inspect.getsource(original))
    changes=[('any(sense not in ("=", "<", ">") for sense in self.senses)',
              'not _r025a_valid_labels(self.senses,("=", "<", ">"))'),
             ('any(vtype not in ("B", "I", "C") for vtype in self.vtypes)',
              'not _r025a_valid_labels(self.vtypes,("B", "I", "C"))')]
    for old,new in changes:
        if source.count(old)!=1:raise ValueError('R025A_SNAPSHOT_ENUM_VALIDATION_SOURCE_DRIFT')
        source=source.replace(old,new)
    filename=__file__+'.require.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace=dict(original.__globals__,_r025a_valid_labels=valid_labels)
    exec(compile(source,filename,'exec'),namespace)
    return namespace[original.__name__]

@contextmanager
def require_scope():
    from v42_a_stage_domain_v2.lexstage import LinearSnapshot
    original=LinearSnapshot.require;adapted=adapted_require(original)
    with patch.object(LinearSnapshot,'require',adapted):yield

@contextmanager
def install():
    from v44 import worker
    original=worker.a_stage
    @wraps(original)
    def a_stage(request,*args,**kwargs):
        # Original case authority still runs in the unchanged stage owner.
        with require_scope():return original(request,*args,**kwargs)
    with patch.object(worker,'a_stage',a_stage):yield

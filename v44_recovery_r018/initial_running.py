"""Keep all source-observed RUNNING jobs in the existing continuation-only role.

Positive remaining service does not turn an observed running episode into a
new pending command. OriginalKnownWindows and its strict guards stay intact.
"""
from contextlib import contextmanager
import inspect,linecache,textwrap
from unittest.mock import patch


def adapted(function):
    source=textwrap.dedent(inspect.getsource(function))
    old=" and row['service_slots']==0"
    if source.count(old)!=1:raise ValueError('ORIGINAL_EXTERNAL_RUNNING_ROSTER_BOUNDARY_DRIFT')
    source=source.replace(old,'')
    filename='<v44_recovery_r018.initial_running.prepare>'
    linecache.cache[filename]=(len(source),None,source.splitlines(keepends=True),filename)
    namespace=dict(function.__globals__)
    exec(compile(source,filename,'exec'),namespace)
    return namespace[function.__name__]


@contextmanager
def install():
    import v43_actual.case as case
    with patch.object(case,'prepare',adapted(case.prepare)):yield

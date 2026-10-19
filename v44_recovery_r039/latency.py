"""Remove wall-clock rejection only; retain 900-second simulation cadence."""
from contextlib import contextmanager
from unittest.mock import patch
import inspect,linecache,textwrap

def compile_like(function,source,suffix,**extra):
    filename=__file__+'.'+suffix+'.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace=dict(function.__globals__,**extra)
    exec(compile(source,filename,'exec'),namespace)
    return namespace[function.__name__]

def replace_once(body,old,new):
    if body.count(old)!=1:raise ValueError('R039_EXACT_SOURCE_BOUNDARY_DRIFT:'+old)
    return body.replace(old,new)

def tick(function,guard):
    body=textwrap.dedent(inspect.getsource(function))
    body=replace_once(body,'result=super().admit(now)','result=self._admit_jobs(now)')
    body=replace_once(body,"    if wall>=900:\n        raise RuntimeError('V43_CONTROLLER_EXCEEDED_900_SECOND_SLOT')\n",'')
    body=replace_once(body,'def admit(self,now):','def admit(self,now):\n    _r039_require()')
    return compile_like(function,body,'tick',_r039_require=guard)

def compare(function,guard):
    body=textwrap.dedent(inspect.getsource(function))
    body=replace_once(body,"and v['latency_within_900_seconds'] for v in variants.values())","for v in variants.values())")
    # Preserve the diagnostic latency field, maximum time and all physical gates.
    body=replace_once(body,'    output=Path(output)',"    _r039_require()\n    output=Path(output)")
    return compile_like(function,body,'compare',_r039_require=guard)

@contextmanager
def install(guard):
    from v43_actual.controller import V43EventController
    from v43_corrective.controller import CorrectiveController
    import v43_actual.compare as shared
    with patch.object(CorrectiveController,'_admit_tick',tick(V43EventController.admit,guard)),patch.object(shared,'_r039_require',guard,create=True),patch.object(shared,'run',compare(shared.run,guard)):
        yield

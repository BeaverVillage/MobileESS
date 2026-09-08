"""Windows long-path-safe archival of existing MESS search attempts only."""
from fast_prepare import ROOT
from pathlib import Path
import os,inspect

def archive_replace(source,target):
    source=Path(source).resolve();target=Path(target).resolve()
    base=(ROOT/'frozen_artifacts').resolve()
    assert source.is_relative_to(base) and target.is_relative_to(base)
    assert source.parent==target.parent and target.name.startswith(source.stem+'.K')
    prefix=lambda p:'\\\\?\\'+str(p) if os.name=='nt' else str(p)
    assert os.path.isfile(prefix(source)) and not os.path.exists(prefix(target))
    os.replace(prefix(source),prefix(target))

def install():
    from dayahead.v37 import runner
    fn=runner._archive_local_attempt
    if getattr(fn,'_v41_long_paths',False):return
    text=inspect.getsource(fn)
    assert text.count('source.replace(target)')==1
    ns=dict(fn.__globals__,archive_replace=archive_replace)
    exec(compile(text.replace('source.replace(target)','archive_replace(source,target)'),__file__+'::archive','exec'),ns)
    result=ns[fn.__name__];result._v41_long_paths=True
    runner._archive_local_attempt=result

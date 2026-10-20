"""Load only SHA-verified Epoch12 infrastructure; never load its optimizer."""
import importlib.abc
import importlib.util
import sys
from pathlib import Path
from .common import ROOT,DOC,read,sha

REVISION=DOC/'svr11_revision01'
FROZEN=ROOT/'v44/svr11_frozen'


class Epoch12Loader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def __init__(self):
        self.rows={r['relative']:r for r in read(REVISION/'EPOCH12_SOURCE_PIN.json')['sources']}

    def find_spec(self,fullname,path=None,target=None):
        key=fullname.replace('.','/')
        relative=key+'/__init__.py' if key+'/__init__.py' in self.rows else key+'.py'
        if relative not in self.rows or relative=='v42_integrated/contract.py':return None
        answer=importlib.util.spec_from_loader(fullname,self,is_package=relative.endswith('/__init__.py'))
        answer.loader_state=relative;return answer

    def create_module(self,spec):return None

    def exec_module(self,module):
        relative=module.__spec__.loader_state;path=FROZEN/relative;row=self.rows[relative]
        if sha(path)!=row['sha256']:raise PermissionError('EPOCH12_SOURCE_SHA_DRIFT:'+relative)
        module.__file__=str(path)
        if relative.endswith('/__init__.py'):module.__path__=[str(path.parent)]
        exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__)
        module.__epoch12_sha__=row['sha256']


def install():
    if any(isinstance(f,Epoch12Loader) for f in sys.meta_path):return
    loader=Epoch12Loader()
    for relative in loader.rows:
        if relative=='v42_integrated/contract.py':continue
        name=relative.removesuffix('/__init__.py').removesuffix('.py').replace('/','.')
        if name in sys.modules:raise PermissionError('UNPINNED_EPOCH12_MODULE_PRELOADED:'+name)
    sys.meta_path.insert(0,loader)

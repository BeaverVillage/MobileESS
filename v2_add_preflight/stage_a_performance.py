"""Exact serialization and immutable service-boundary validation reuse."""
from contextlib import contextmanager,ExitStack
from contextvars import ContextVar
from unittest.mock import patch
from functools import lru_cache
import ast,inspect,textwrap
import weakref
import numpy as np

ACTIVE=ContextVar('V2_ADD_EXACT_PREPARATION_IO',default=None)

def intern_times(values):
    active=ACTIVE.get()
    if active is None:return tuple(int(t) for t in values)
    values=np.asarray(values);key=(values.dtype.str,values.shape,values.tobytes())
    cache=active['tau_cache']
    if key in cache:
        active['tau_sequences_reused']+=1;active['tau_tuple_elements_avoided']+=len(values)
        return cache[key]
    result=tuple(int(t) for t in values);cache[key]=result;return result

@lru_cache(maxsize=1)
def domain_code():
    from v42_a_stage_domain_v2.domain import physical_domain
    source=textwrap.dedent(inspect.getsource(physical_domain));old='taus = tuple(int(t) for t in ids[good])'
    if source.count(old)!=1:raise ValueError('ORIGINAL_TIME_TUPLE_SOURCE_BOUNDARY_DRIFT')
    source=source.replace(old,'taus = _V2_intern_times(ids[good])')
    filename=__file__+'.domain.generated'
    import linecache
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns={};exec(compile(source,filename,'exec'),ns);return ns['physical_domain'].__code__

@lru_cache(maxsize=2)
def digest_code(kind):
    # The C encoder returns canonical chunks. Hash their identical UTF-8 bytes
    # without joining a second giant string and allocating its full byte copy.
    argument='x' if kind=='common' else 'value'
    data='clean(x)' if kind=='common' else 'value'
    extra='' if kind=='common' else ',default=str,allow_nan=False'
    source=f'''def digest({argument}):
    h=hashlib.sha256()
    encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'){extra})
    for chunk in encoder.iterencode({data},_one_shot=True):h.update(chunk.encode())
    return h.hexdigest()
'''
    filename=__file__+'.'+kind+'_digest.generated'
    import linecache
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns={};exec(compile(source,filename,'exec'),ns);return ns['digest'].__code__

def clean_wrapper(original):
    def clean(value):
        if isinstance(value,np.ndarray) and value.ndim:
            kind=value.dtype.kind
            if kind in 'biuU' or kind=='f' and value.dtype.itemsize<=8 and np.isfinite(value).all():
                return value.tolist()
        return original(value)
    return clean

@lru_cache(maxsize=1)
def constructor():
    from v42_boundary.generator import Domain
    from v42_a_stage_domain_v2.domain import physical_domain
    caller=ast.parse(textwrap.dedent(inspect.getsource(physical_domain))).body[0].body
    if not (len(caller)>=3 and isinstance(caller[-3],ast.Assign) and ast.unparse(caller[-3].targets[0])=='domain'
            and isinstance(caller[-3].value,ast.Call) and ast.unparse(caller[-3].value.func)=='Domain'
            and isinstance(caller[-2],ast.Assign) and ast.unparse(caller[-2].targets[0])=='domain.sha'
            and isinstance(caller[-1],ast.Return) and ast.unparse(caller[-1].value)=='domain'):
        raise ValueError('DOMAIN_HASH_NOT_UNCONDITIONALLY_OVERWRITTEN')
    tree=ast.parse(textwrap.dedent(inspect.getsource(Domain.__init__)));body=tree.body[0].body
    tail=body[-1]
    if not (isinstance(tail,ast.Assign) and len(tail.targets)==1 and ast.unparse(tail.targets[0])=='self.sha'):
        raise ValueError('DOMAIN_DISCARDED_HASH_SOURCE_BOUNDARY_DRIFT')
    body.pop();ast.fix_missing_locations(tree);ns=dict(Domain.__init__.__globals__)
    exec(compile(tree,inspect.getfile(Domain),'exec'),ns);initialize=ns['__init__']
    def allocate(*args):
        # physical_domain has an early empty-domain return before its final
        # authoritative hash assignment. That tiny branch keeps the original
        # constructor and its hash; no skipped initialization may escape.
        if not args[0] and not args[1]:return Domain(*args)
        obj=Domain.__new__(Domain);initialize(obj,*args)
        return obj
    return allocate

def domain_constructor():
    from v42_boundary.generator import Domain
    active=ACTIVE.get()
    if active is None:return Domain
    factory=constructor()
    def make(*args):
        if args[0] or args[1]:active['discarded_domain_hashes_avoided']+=1
        return factory(*args)
    return make

@contextmanager
def scope(root=None):
    import v42_pr134_b1.common as common
    from v42_native.service import NativeServiceBoundary
    original=NativeServiceBoundary.require;checked=weakref.WeakValueDictionary()
    stats=dict(boundary_validation_calls=0,boundary_validation_reuses=0,discarded_domain_hashes_avoided=0,
        tau_cache={},tau_sequences_reused=0,tau_tuple_elements_avoided=0)
    def require(self):
        stats['boundary_validation_calls']+=1
        if checked.get(id(self)) is self:
            stats['boundary_validation_reuses']+=1;return
        original(self);checked[id(self)]=self
    token=ACTIVE.set(stats)
    storage=None
    try:
        # NativeServiceBoundary is frozen; every field is immutable scalars or
        # a tuple of integer starts. Cache only successful validation of the
        # exact object within this stage. Weak values prevent id reuse and do
        # not retain millions of temporary boundaries from membership checks.
        import v42_a_stage_domain_v2.domain as domain
        before_common=common.digest.__code__;before_domain=domain.digest.__code__
        try:
            common.digest.__code__=digest_code('common');domain.digest.__code__=digest_code('domain')
            with ExitStack() as stack:
                stack.enter_context(patch.object(common,'clean',clean_wrapper(common.clean)))
                stack.enter_context(patch.object(NativeServiceBoundary,'require',require))
                if root is not None:
                    import scipy.sparse as sp
                    from .stage_matrix_storage import MatrixFiles
                    storage=MatrixFiles(root);stack.enter_context(patch.object(sp,'save_npz',storage.wrap(sp.save_npz)))
                yield stats
        finally:
            common.digest.__code__=before_common;domain.digest.__code__=before_domain
    finally:
        stats['unique_tau_sequences']=len(stats.pop('tau_cache'));ACTIVE.reset(token)
        if root is not None:
            from pathlib import Path
            from .prestart_execution import atomic
            if Path(root).exists():atomic(Path(root)/'V2_A_PREPARATION_IO_PROFILE.json',dict(stats,
                matrix_storage=storage.report() if storage else None,scientific_FULL_acceptance_not_implied=True))

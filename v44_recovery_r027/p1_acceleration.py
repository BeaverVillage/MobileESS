"""Carry verified feasible starts and exact same-matrix local LP bases."""
import hashlib,inspect,linecache,textwrap
import numpy as np


def structural_key(snapshot):
    h=hashlib.sha256();h.update(repr(snapshot.matrix.shape).encode())
    for a in (snapshot.matrix.indptr,snapshot.matrix.indices,snapshot.matrix.data,
              snapshot.lower,snapshot.upper,snapshot.rhs,snapshot.senses,snapshot.vtypes):
        a=np.asarray(a);h.update(str(a.dtype).encode());h.update(a.tobytes())
    return h.hexdigest()


def compile_p1(function,namespace):
    source=textwrap.dedent(inspect.getsource(function))
    old="    traces=[]\n    while True:"
    assert source.count(old)==1
    source=source.replace(old,"    p1point=certified_zero_point if certified_zero_point is not None else x\n"+old)
    old="        rec,raw=native.solve(s,f,'ORIGINAL_P1')"
    assert source.count(old)==1
    source=source.replace(old,"        native.admit_p1(s,p1point)\n"+old)
    old="        state,_=activate(state,negative,raw['X'],f)"
    assert source.count(old)==1
    # All directions already passed the full native pricing and support proof.
    source=source.replace(old,"        state,p1point=activate(state,negative,raw['X'],f,max_batch=len(negative))")
    filename=__file__+'.phase.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    exec(compile(source,filename,'exec'),namespace)
    return namespace['run']

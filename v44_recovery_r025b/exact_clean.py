from types import FunctionType
from contextlib import contextmanager
import math

_ATOMS={str,int,bool,type(None)}

def cleaner(original):
    def fast(value):
        kind=type(value)
        if kind in _ATOMS:return value
        if kind is float:return value if math.isfinite(value) else str(value)
        if kind is dict:
            return {(key if type(key) is str else str(key)):(item if type(item) in _ATOMS else fast(item)) for key,item in value.items()}
        if kind is list:return [item if type(item) in _ATOMS else fast(item) for item in value]
        return original(value)
    return fast

def dispatch(x):return _r025b_exact_clean_dispatch(x)

@contextmanager
def install():
    import v42_pr134_b1.common as common
    function=common.clean;old=function.__code__;key='_r025b_exact_clean_dispatch'
    assert key not in function.__globals__
    original=FunctionType(old,function.__globals__,function.__name__,function.__defaults__,function.__closure__)
    function.__globals__[key]=cleaner(original);function.__code__=dispatch.__code__
    try:yield
    finally:function.__code__=old;function.__globals__.pop(key,None)

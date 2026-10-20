from contextlib import contextmanager
from types import FunctionType
import os,linecache,inspect

@contextmanager
def install(pool):
    import v43.common as c43
    import v42_pr134_b1.common as c42
    import v44.common as c44
    restored=[]
    try:
        for module,name,fields in [(c43,'record',('path','bytes','sha256')),(c42,'record',('path','sha256','bytes')),
                (c43,'sha',None),(c42,'sha',None),(c44,'sha',None)]:
            function=getattr(module,name);old=function.__code__
            original=FunctionType(old,function.__globals__,function.__name__,function.__defaults__,function.__closure__)
            parameter=list(inspect.signature(function).parameters)
            assert len(parameter)==1 and not function.__code__.co_freevars
            key='_r021_mapped_source_'+name
            assert key not in function.__globals__
            def routed(path,original=original,fields=fields):
                if os.path.normcase(os.fspath(path)) not in pool.files:return original(path)
                row=pool.record(path)
                return row['sha256'] if fields is None else {field:row[field] for field in fields}
            function.__globals__[key]=routed
            source=f'def {name}({parameter[0]}):\n    return {key}({parameter[0]})\n'
            filename=__file__+'.'+module.__name__+'.'+name+'.generated'
            linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
            ns={};exec(compile(source,filename,'exec'),ns)
            function.__code__=ns[name].__code__;restored.append((function,old,key))
        yield
    finally:
        for function,old,key in reversed(restored):function.__code__=old;function.__globals__.pop(key,None)

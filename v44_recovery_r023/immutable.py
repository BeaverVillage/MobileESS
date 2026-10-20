"""Read-only JSON graphs: history evidence can be shared without deep copies."""

def _deny(*args,**kwargs):
    raise TypeError('IMMUTABLE_PREFIX_EVIDENCE')


class FrozenDict(dict):
    __slots__=()
    __setitem__=__delitem__=clear=pop=popitem=setdefault=update=__ior__=_deny
    def __deepcopy__(self,memo):memo[id(self)]=self;return self
    def __copy__(self):return self
    def __reduce_ex__(self,protocol):return freeze,(dict(self),)


class FrozenList(list):
    __slots__=()
    __setitem__=__delitem__=append=clear=extend=insert=pop=remove=reverse=sort=__iadd__=__imul__=_deny
    def __deepcopy__(self,memo):memo[id(self)]=self;return self
    def __copy__(self):return self
    def __reduce_ex__(self,protocol):return freeze,(list(self),)


_ATOMIC={str,int,float,bool,bytes,type(None),complex}


def freeze(value,memo=None):
    kind=type(value)
    if kind in _ATOMIC or kind in (FrozenDict,FrozenList):return value
    if memo is None:memo={}
    if id(value) in memo:return memo[id(value)]
    if kind is dict:
        result=FrozenDict();memo[id(value)]=result
        for key,item in value.items():
            if type(key) is not str:raise TypeError('PREFIX_STRING_KEYS_REQUIRED')
            dict.__setitem__(result,key,freeze(item,memo))
        return result
    if kind is list:
        result=FrozenList();memo[id(value)]=result
        for item in value:list.append(result,freeze(item,memo))
        return result
    raise TypeError('PREFIX_PLAIN_GRAPH_REQUIRED:'+kind.__name__)

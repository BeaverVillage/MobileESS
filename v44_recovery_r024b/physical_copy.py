"""Lossless independent graph copies; avoid atomic-leaf deepcopy dispatch."""
from copy import deepcopy

_ATOMIC={str,int,float,bool,bytes,type(None),complex}


def clone_physical(value, memo=None):
    """Preserve cycles/aliases and delegate all non-plain data to deepcopy.

    Only exact built-in dict/list containers are specialized. Mutable arrays,
    subclasses, tuples, custom protocols and unusual keys retain Python's
    original deepcopy implementation and share the same graph memo.
    """
    kind=type(value)
    if kind in _ATOMIC:return value
    if memo is None:memo={}
    identity=id(value)
    if identity in memo:return memo[identity]
    if kind is dict:
        result={};memo[identity]=result
        for key,item in value.items():
            copied_key=key if type(key) in _ATOMIC else deepcopy(key,memo)
            result[copied_key]=item if type(item) in _ATOMIC else clone_physical(item,memo)
        return result
    if kind is list:
        result=value.copy();memo[identity]=result
        for index,item in enumerate(result):
            if type(item) not in _ATOMIC:result[index]=clone_physical(item,memo)
        return result
    return deepcopy(value,memo)

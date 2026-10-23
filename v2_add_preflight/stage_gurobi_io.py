"""ASCII filesystem aliases for Gurobi's native Windows file IO only.

The workspace resolves through a Korean OneDrive path. Its existing D: alias
is byte-identical; Python receipts keep their canonical paths. No model data,
parameter value other than file paths, or source solver method is replaced.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from .stage_common import ROOT


def ascii_path(value):
    if not value:return value
    original=str(value)
    if original.isascii():return original
    alias=Path('D:/ChatGPT/Mobile ESS 2')
    resolved=Path(value).resolve();base=ROOT.parent.resolve()
    if not alias.exists() or alias.resolve()!=base or not resolved.is_relative_to(base):
        raise PermissionError('VERIFIED_OWN_ASCII_GUROBI_IO_ALIAS_REQUIRED')
    target=alias/resolved.relative_to(base)
    if not str(target).isascii():raise ValueError('NON_ASCII_GUROBI_LEAF_NAME')
    return str(target)


class Parameters:
    def __init__(self,value):object.__setattr__(self,'_value',value)
    def __getattr__(self,key):return getattr(self._value,key)
    def __setattr__(self,key,value):
        setattr(self._value,key,ascii_path(value) if key in ('LogFile','NodefileDir','ResultFile') else value)


@contextmanager
def scope():
    import gurobipy as gp
    original=gp.Model
    class Model(original):
        def __getattribute__(self,name):
            value=super().__getattribute__(name)
            return Parameters(value) if name=='Params' else value
        def setParam(self,name,value):
            return super().setParam(name,ascii_path(value) if name in ('LogFile','NodefileDir','ResultFile') else value)
        def write(self,path):return super().write(ascii_path(path))
    with patch.object(gp,'Model',Model):yield

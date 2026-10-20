"""Per-probe immutable native-class names; all object property values read live."""
from weakref import WeakKeyDictionary
import inspect,linecache,textwrap
from contextlib import contextmanager
from unittest.mock import patch

class ClassPropertySchema:
    def __init__(self):self.engines=WeakKeyDictionary();self.reads=0;self.hits=0
    def names(self,engine,obj):
        props=engine.Properties;lib=props._lib
        index=int(lib.Obj_GetClassIdx(obj));props._check_for_error()
        count=int(lib.Obj_GetNumProperties(obj));props._check_for_error()
        entries=self.engines.setdefault(engine,{})
        if index in entries:
            old_count,names=entries[index]
            if old_count!=count:raise ValueError('R026F1_NATIVE_CLASS_SCHEMA_PROPERTY_COUNT_DRIFT')
            self.hits+=1;return names
        names=tuple(engine.CktElement.AllPropertyNames())
        if count!=len(names):raise ValueError('R026F1_NATIVE_CLASS_SCHEMA_PROPERTY_COUNT_DRIFT')
        entries[index]=(count,names);self.reads+=1;return names


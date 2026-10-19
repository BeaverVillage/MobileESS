"""Object schema only, no property values; native classes are immutable."""
from weakref import WeakKeyDictionary
import inspect,linecache,textwrap


class PropertySchema:
    """Per-probe weak engine/object metadata, checked by live class/count.

    Property names are a native class definition, not mutable equipment data.
    The first read of each object retains its exact live names/order; every
    later read checks that object's live native class and property count.
    The native context is never held by this cache. Values are never stored.
    """
    def __init__(self):
        self.engines=WeakKeyDictionary();self.reads=0;self.hits=0
    def names(self,engine,obj):
        props=engine.Properties;lib=props._lib
        index=int(lib.Obj_GetClassIdx(obj));props._check_for_error()
        count=int(lib.Obj_GetNumProperties(obj));props._check_for_error()
        key=int(props._api_util.ffi.cast('uintptr_t',obj))
        entries=self.engines.setdefault(engine,{})
        if key in entries:
            old_index,old_count,names=entries[key]
            if (old_index,old_count)!=(index,count):raise ValueError('R019_NATIVE_OBJECT_SCHEMA_DRIFT')
            self.hits+=1;return names
        names=tuple(engine.CktElement.AllPropertyNames())
        if count!=len(names):raise ValueError('R019_NATIVE_PROPERTY_COUNT_AXIS_DRIFT')
        entries[key]=(index,count,names);self.reads+=1
        return names


def named_property(engine,name):
    """Same public getter C calls, without a failing int(property_name)."""
    props=engine.Properties
    if not hasattr(props,'_lib'):return props.Value(name)
    props._lib.DSSProperty_Set_Name(name.encode(props._api_util.codec))
    return props._get_string(props._check_for_error(props._lib.DSSProperty_Get_Val()))


def equipment_reader(function):
    source=textwrap.dedent(inspect.getsource(function))
    old='engine.Properties.Value(k)'
    if source.count(old)!=1 or "('NormAmps','EmergAmps','NormHkVA','EmergHkVA','Xhl','%noloadloss')" not in source:
        raise ValueError('R019_EXACT_EQUIPMENT_SIX_READ_BOUNDARY_DRIFT')
    source=source.replace(old,'_r019_named_property(engine,k)')
    filename=__file__+'.equipment.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    ns=dict(function.__globals__,_r019_named_property=named_property)
    exec(compile(source,filename,'exec'),ns);return ns[function.__name__]

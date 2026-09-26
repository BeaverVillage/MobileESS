"""Extension-only normalization of a zero-column relocation audit table."""
from pathlib import Path
import types
import pandas as pd


def normalize_audit_table(original):
    def table(path,frame):
        # Parquet has no integer labels to preserve when there are no columns.
        # Keep the original strict readback check and all nonempty tables intact.
        if Path(path).name=='PRESTART_RELOCATION_CANDIDATES.parquet' and frame.shape==(0,0):
            frame=frame.copy()
            frame.columns=pd.Index([],dtype='object')
        return original(path,frame)
    return table


def install():
    from dayahead.v41r1 import migration_audit
    original=migration_audit.persist
    namespace=dict(original.__globals__)
    namespace['table']=normalize_audit_table(namespace['table'])
    migration_audit.persist=types.FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)

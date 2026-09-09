"""Canonical column index for a truly empty migration audit table."""
import pandas as pd
from dayahead.v41.persistence import table as original_table

def table(path,frame):
    if frame.shape==(0,0):
        frame=frame.copy();frame.columns=pd.Index([],dtype=object)
    return original_table(path,frame)

def install():
    from dayahead.v41r1 import migration_audit
    migration_audit.persist.__globals__['table']=table
    migration_audit.table=table

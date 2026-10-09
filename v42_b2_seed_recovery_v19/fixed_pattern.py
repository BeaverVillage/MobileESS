"""Repair terminal occupancy in auxiliary candidates; original model is frozen."""
import numpy as np
from v42_b2_seed_recovery_v18.initialization import values_for as old_values_for

def values_for(case,paths,charge):
    ids,values=old_values_for(case,paths,charge)
    terminal={}
    for unit,path in paths.items():
        if not path:raise ValueError('EMPTY_ORIGINAL_ROUTE_PATH')
        final=case.graph[2][path[-1]]
        if final[3]!=96:raise ValueError('PATH_DOES_NOT_REACH_ORIGINAL_TERMINAL_SLOT')
        terminal[unit]=final[2]
    for k,j in enumerate(ids):
        name=str(case.d['names'][j])
        if name.startswith('node_activity['):
            unit,site,slot=name[14:-1].split(',')
            if int(slot)==96:values[k]=float(site==terminal[unit])
    fixed=dict(zip(map(int,ids),map(float,values)))
    for i,name in enumerate(map(str,case.d['row_names'])):
        if name.split('[',1)[0]!='terminal_location':continue
        a,b=case.A.indptr[i:i+2];columns=case.A.indices[a:b]
        if not all(int(j) in fixed for j in columns):raise ValueError('TERMINAL_ROW_NOT_FIXED_BY_CANDIDATE')
        actual=sum(float(w)*fixed[int(j)] for j,w in zip(columns,case.A.data[a:b]))
        if actual!=float(case.d['rhs'][i]):raise ValueError('CANDIDATE_ORIGINAL_TERMINAL_LOCATION_RESIDUAL')
    return ids,values

"""Repair terminal occupancy in auxiliary candidates; original model is frozen."""
import numpy as np

def integer_representatives(case):
    # C3A represents many FULL binary arcs by continuous route-flow columns.
    # Fixing only C3A VType!='C' leaves those original integer decisions loose.
    names=np.asarray(case.d['names'],dtype=str)
    return np.flatnonzero((case.d['types']!='C')|np.char.startswith(names,'route_flow['))

def discrete_stationary(case):
    ids=integer_representatives(case);values=[]
    for j in ids:
        name=str(case.d['names'][j]);family=name.split('[',1)[0]
        axis=name.split('[',1)[1][:-1].split(',');unit=axis[0]
        if family in ('arc','route_flow'):
            arc=case.graph[2][int(axis[1])]
            value=float(arc[-1] is None and arc[0]==case.graph[1][unit])
        elif family=='node_activity':value=float(axis[1]==case.graph[1][unit])
        elif family=='charge_mode':value=0.
        else:raise ValueError('UNKNOWN_ORIGINAL_INTEGER_REPRESENTATIVE:'+name)
        values.append(value)
    return ids,np.asarray(values,dtype=float)

def values_for(case,paths,charge):
    terminal={};connected=set();chosen={unit:set(path) for unit,path in paths.items()}
    for unit,path in paths.items():
        if not path:raise ValueError('EMPTY_ORIGINAL_ROUTE_PATH')
        site,time=case.graph[1][unit],0
        for k in path:
            arc=case.graph[2][k]
            if arc[0]!=site or arc[1]!=time or not time<arc[3]<=96:raise ValueError('ORIGINAL_PATH_FLOW_OR_ETA')
            if arc[-1] is None:connected.add((unit,arc[0],arc[1]))
            else:arc[-1].validate(96)
            site,time=arc[2],arc[3]
        final=case.graph[2][path[-1]]
        if final[3]!=96:raise ValueError('PATH_DOES_NOT_REACH_ORIGINAL_TERMINAL_SLOT')
        terminal[unit]=final[2]
        connected.add((unit,final[2],96))
    ids=integer_representatives(case);values=[]
    for j in ids:
        name=str(case.d['names'][j]);family=name.split('[',1)[0]
        axis=name.split('[',1)[1][:-1].split(',');unit=axis[0]
        if family in ('arc','route_flow'):value=float(int(axis[1]) in chosen[unit])
        elif family=='node_activity':value=float((unit,axis[1],int(axis[2])) in connected)
        elif family=='charge_mode':value=float(charge(unit,int(axis[1])))
        else:raise ValueError('UNKNOWN_ORIGINAL_INTEGER_REPRESENTATIVE:'+name)
        values.append(value)
    values=np.asarray(values,dtype=float)
    fixed=dict(zip(map(int,ids),map(float,values)))
    for i,name in enumerate(map(str,case.d['row_names'])):
        if name.split('[',1)[0]!='terminal_location':continue
        a,b=case.A.indptr[i:i+2];columns=case.A.indices[a:b]
        if not all(int(j) in fixed for j in columns):raise ValueError('TERMINAL_ROW_NOT_FIXED_BY_CANDIDATE')
        actual=sum(float(w)*fixed[int(j)] for j,w in zip(columns,case.A.data[a:b]))
        if actual!=float(case.d['rhs'][i]):raise ValueError('CANDIDATE_ORIGINAL_TERMINAL_LOCATION_RESIDUAL')
    return ids,values

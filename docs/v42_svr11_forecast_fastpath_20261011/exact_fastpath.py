"""Detached input schedules and one terminal read per element; no solved state."""
import numpy as np

def forecast_setter_schedule(native,totals,background,plan,adapter,load_names,generator_names,pf_tan):
    result=[]
    for slot in range(96):
        rows=[]
        for row in native.loads:
            name=str(row['load_name']);p,q=totals[slot][name.lower()]
            rows.append(('native',name,p,q))
        for row in adapter['pv_generators']:
            bus=str(row['bus']).lower();phase='ABC'[int(row['phase'])-1]
            rows.append(('generator',str(row['generator_name']),background.pv_generation_kw_96[slot].get((bus,phase),0.0),0.0))
        for index in range(1,13):
            value=float(plan[slot][index-1]);rows.append(('load',f'IDC_IDC{index:02d}',value,value*pf_tan))
        for name in generator_names:
            if str(name).lower().startswith('mess_dis_'):rows.append(('generator',str(name),0.0,0.0))
        for name in load_names:
            if str(name).lower().startswith('mess_chg_'):rows.append(('load',str(name),0.0,0.0))
        result.append(tuple(rows))
    return tuple(result)

def apply_schedule(engine,rows):
    from dayahead.v28r2.opendss_mapping import _set_load
    from dayahead import run_v16_3_voltage_candidate as original
    for kind,name,p,q in rows:
        if kind=='native':_set_load(engine,name,p,q)
        elif kind=='generator':original._set_generator(engine,name,p,q)
        elif kind=='load':original._set_load(engine,name,p,q)
        else:raise ValueError('SVR11_FORECAST_SETTER_KIND_DRIFT')

def terminal_layout(engine,branches):
    groups={}
    for position,b in enumerate(branches):
        group=groups.setdefault(b.branch_id,[])
        engine.Circuit.SetActiveElement(b.branch_id)
        if str(engine.CktElement.Name()).lower()!=b.branch_id.lower():raise ValueError('SVR11_TERMINAL_ELEMENT_NOT_FOUND')
        conductors=int(engine.CktElement.NumConductors())
        buses=[str(value).split('.',1)[0].lower() for value in engine.CktElement.BusNames()]
        terminal=buses.index(b.parent_bus.lower());nodes=list(map(int,engine.CktElement.NodeOrder()))
        wanted='ABC'.index(b.phase)+1
        index=next(terminal*conductors+i for i in range(conductors) if nodes[terminal*conductors+i]==wanted)
        group.append((position,index))
    return tuple((name,tuple(group)) for name,group in groups.items())

def terminal_values(engine,layout,size):
    values=np.empty((size,3))
    for name,indices in layout:
        engine.Circuit.SetActiveElement(name)
        powers=list(map(float,engine.CktElement.Powers()));currents=list(map(float,engine.CktElement.CurrentsMagAng()))
        for position,index in indices:values[position]=(powers[2*index],powers[2*index+1],currents[2*index])
    return values

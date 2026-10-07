"""Complete the C1/weather/rack/grid portion of the non-nesting inventory."""
import numpy as np,pandas as pd
from .common import *

def walk_refs(v):
    out=[]
    if isinstance(v,dict):
        if 'path' in v and 'sha256' in v:out.append(v)
        for x in v.values():out.extend(walk_refs(x))
    elif isinstance(v,list):
        for x in v:out.extend(walk_refs(x))
    return out

def run(day):
    import v42_temporal.native as temporal
    b=read(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json');d='DAY_'+day.replace('-','')
    base=ROOT/'docs/v42_may_b0_zero_margin_holdout';p=read(base/'INPUT/BUNDLE'/d/'PLANNING_INPUT_BUNDLE.json')
    c1=pd.read_csv(base/'INPUT/BUNDLE'/d/'C1_PLANNING_COEFFICIENTS.csv');power0=read(base/'INPUT/BUNDLE'/d/'POWER_AUTHORITY.json')
    cert,power,idle,swing=temporal.load_power(b)
    discrepancies=[]
    for row in c1.itertuples():
        x=power[row.aidc_id,int(row.slot)]
        for field in ('slope','intercept_kw'):
            if getattr(row,field)!=getattr(x,field):discrepancies.append(dict(site=row.aidc_id,slot=int(row.slot),field=field,B0=getattr(row,field),B1=getattr(x,field)))
    racks={s:sorted(set(r['compatibility_GPU_limit'] for r in b['racks'] if r['aidc_id']==s)) for s in b['capacities']}
    rk0={s:sorted(set(r)) for s,r in p['rack_compatibility'].items()}
    name='B0_TO_B1_NESTING_AUDIT_'+label(day)+'.json';facts=read(OUT/name)
    facts.update(rack_compatibility_equal=racks==rk0,C1_endpoint_coefficients_exact_equal=not discrepancies,
        C1_coefficient_mismatches=discrepancies,C1_idle_equal=idle==power0['current_IT_idle_kW_per_installed_GPU'],
        C1_swing_equal=swing==power0['current_IT_swing_kW_per_active_GPU'],
        B0_C1=record(base/'INPUT/BUNDLE'/d/'C1_PLANNING_COEFFICIENTS.csv'),
        B0_power=record(base/'INPUT/BUNDLE'/d/'POWER_AUTHORITY.json'),B1_electrical_certificate=b['electrical_certificate'],
        B0_voltage=p['primary_voltage'],B1_voltage=dict(lower_pu=.95,upper_pu=1.05),
        B0_network_authority=p['network_authority'],B1_electrical_input_refs=walk_refs(cert['input_identity']),
        B0_background_refs=walk_refs(read(base/'INPUT/BUNDLE'/d/'SOURCE_PROVENANCE.json')),
        C1_grid_embedding_proven=False,
        electrical_comparison_scope='C1 numeric coefficients/idle/swing/racks exact; native B1 affine grid and B0 FreshAC are different mathematical representations. Non-nesting already follows from required job start/site counterexamples.')
    write(name,facts);write(label(day)+'_B0_TO_B1_NESTING.json',facts)
    print(day,'C1 mismatches',len(discrepancies),'rack match',racks==rk0,flush=True)
if __name__=='__main__':
    for day in DAYS:run(day)

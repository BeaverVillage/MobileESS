"""Diagnose the saved optimal BASE point without changing or rounding it."""
from collections import Counter,defaultdict
from pathlib import Path
import json,sys
import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'docs/v42_b2_root_lp_tightening/base'


def run():
    cert=json.loads((BASE/'INDEPENDENT_CERTIFICATE.json').read_text(encoding='utf-8'))
    assert cert['PASS'] and cert['solver_status']==2
    with np.load(BASE/'LP_DATA.npz') as z:d={k:z[k] for k in z.files}
    with np.load(BASE/'LP_POINT.npz') as z:x=z['x']
    A=sparse.load_npz(BASE/'LP_A.npz').tocsr()
    table=defaultdict(lambda:dict(C=0.,D=0.,Q=0.,SOC=None,mode=None,fractional_locations=0,location_mass=0.))
    summary=Counter();examples=defaultdict(list);station=defaultdict(lambda:dict(C=0.,D=0.))
    for col,name in enumerate(d['names']):
        name=str(name)
        if '[' not in name:continue
        family,args=name.split('[',1);parts=args.rstrip(']').split(',');value=float(x[col]);unit=parts[0]
        fractional=abs(value-round(value))>1e-8
        if family in ('node_activity','charge_mode','route_flow'):
            summary[family+'_fractional']+=int(fractional)
            summary[family+'_active']+=int(abs(value)>1e-8)
            if fractional and len(examples[family])<20:examples[family].append(dict(column=col,name=name,value=value))
        if family in ('Pch','Pdis','Q','node_activity'):
            slot=int(parts[-1]);row=table[unit,slot]
            if family=='Pch':row['C']+=value;station[unit,parts[1],slot]['C']+=value
            elif family=='Pdis':row['D']+=value;station[unit,parts[1],slot]['D']+=value
            elif family=='Q':row['Q']+=value
            else:row['fractional_locations']+=int(fractional);row['location_mass']+=value
        elif family=='SOC':table[unit,int(parts[-1])]['SOC']=value
        elif family=='charge_mode':table[unit,int(parts[-1])]['mode']=value
    # Initial/terminal aliases are literal Source18r endpoint constants.
    for unit in ('MESS01','MESS02','MESS03','MESS04'):
        table[unit,0]['SOC']=760.;table[unit,96]['SOC']=760.
    energy=[]
    for index,name in enumerate(d['row_names']):
        name=str(name)
        if name.split('[',1)[0]!='energy_balance':continue
        row=A.getrow(index);flow_terms=[];travel=0.
        soc=[(str(d['names'][col]),float(coef)) for col,coef in zip(row.indices,row.data)
             if str(d['names'][col]).startswith('SOC[')]
        assert soc and all(abs(coef)==1 for _,coef in soc)
        unit=soc[0][0].split('[',1)[1].split(',')[0]
        before=[int(s.split(',')[-1].rstrip(']')) for s,c in soc if c==-1]
        after=[int(s.split(',')[-1].rstrip(']')) for s,c in soc if c==1]
        slot=before[0] if before else after[0]-1
        assert 0<=slot<96 and (not after or after[0]==slot+1)
        for col,coef in zip(row.indices,row.data):
            if str(d['names'][col]).startswith('route_flow['):
                travel+=float(coef*x[col]);flow_terms.append(dict(column=int(col),energy_coefficient=float(coef),flow=float(x[col])))
        residual=float((row@x-d['rhs'][index]).item())
        table[unit,slot]['retained_travel_energy_debit']=travel
        energy.append(dict(unit=unit,slot=slot,row=index,residual=residual,retained_travel_energy_debit=travel,
                           active_travel_terms=sum(abs(t['flow'])>1e-8 for t in flow_terms),
                           fractional_travel_terms=sum(abs(t['flow']-round(t['flow']))>1e-8 for t in flow_terms)))
    slots=[dict(unit=u,slot=t,**values,simultaneous_C_D=values['C']>1e-8 and values['D']>1e-8)
           for (u,t),values in sorted(table.items())]
    same_station=[dict(unit=u,location=s,slot=t,**v) for (u,s,t),v in station.items() if v['C']>1e-8 and v['D']>1e-8]
    value=dict(PASS=True,point_unchanged=True,point_kind='verified numerical OPTIMAL BASE LP',
               LP_ObjVal=cert['ObjVal'],LP_exact_weak_duality_bound=cert['LP_lower_bound'],
               fractional_counts=dict(summary),fractional_examples=dict(examples),
               vehicle_slot_simultaneous_C_D=sum(row['simultaneous_C_D'] for row in slots),
               same_station_simultaneous_C_D=len(same_station),same_station_examples=same_station[:30],
               energy_balance_maximum_residual=max(abs(row['residual']) for row in energy),
               vehicle_slot_diagnostics=slots,energy_balance=energy,
               original_SOC_endpoint_constants_source='Inherited exact Source18r endpoint alias proof: 760 kWh',
               location_scope='Counts and location_mass use retained node_activity columns only; removed static node aliases are not replayed here. This census does not prove transit occupancy. Complete original transit, travel and SOC replay is recorded separately in SOC_BASE_FRACTIONAL_DIAGNOSTICS.json.',
               travel_scope='Travel coefficients are retained literal energy-row route_flow terms. Removed constant aliases are incorporated in the actual row RHS; complete Original debit is independently available in SOC exact candidate replay.',
               FULL_UB_or_Actual_PASS_claim=False)
    output=BASE.parent/'BASE_FRACTIONAL_DIAGNOSTICS.json'
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:value[k] for k in ('PASS','fractional_counts','vehicle_slot_simultaneous_C_D','same_station_simultaneous_C_D','energy_balance_maximum_residual')}))


if __name__=='__main__':run()

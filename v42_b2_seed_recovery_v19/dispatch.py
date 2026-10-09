"""Export the unchanged FULL witness after the independent FULL gate."""
import numpy as np
from v42_m1_research.check_ub import vector_sha
from .common import atomic,record

def export(case,point,strict):
    if strict.get('PASS') is not True:raise ValueError('FULL_CERTIFICATE_REQUIRED_FOR_DISPATCH_EXPORT')
    full=case.lift(point)
    np.savez_compressed(case.output/'BENCHMARK_FULL_RAW_POINT.npz',point=full)
    vehicles={u:dict(Pch_kW=[0.]*96,Pdis_kW=[0.]*96,P_kW=[0.]*96,Q_kvar=[0.]*96,
        SOC_kWh=[None]*97,charge_mode=[None]*96,location=['TRANSIT']*96,routes=[]) for u in case.graph[1]}
    for name,value in zip(map(str,case.original_d['names']),full):
        family=name.split('[',1)[0]
        if family not in ('Pch','Pdis','Q','SOC','charge_mode','arc'):continue
        axis=name.split('[',1)[1][:-1].split(',');unit=axis[0];v=vehicles[unit];value=float(value)
        if family in ('Pch','Pdis','Q'):
            key={'Pch':'Pch_kW','Pdis':'Pdis_kW','Q':'Q_kvar'}[family];v[key][int(axis[-1])]+=value
        elif family=='SOC':v['SOC_kWh'][int(axis[-1])]=value
        elif family=='charge_mode':v['charge_mode'][int(axis[-1])]=value
        elif value==1.:
            arc=case.graph[2][int(axis[1])]
            if arc[-1] is None:v['location'][arc[1]]=arc[0]
            else:
                route=arc[-1]
                v['routes'].append(dict(arc_index=int(axis[1]),source=arc[0],depart_slot=arc[1],
                    destination=arc[2],connect_slot=arc[3],route_id=route.route_id,
                    energy_kWh=route.energy_kwh,ETA_authority_SHA=route.authority_sha256))
    for v in vehicles.values():
        v['P_kW']=[dis-charge for dis,charge in zip(v['Pdis_kW'],v['Pch_kW'])]
        v['routes'].sort(key=lambda r:r['depart_slot'])
    atomic(case.output/'INITIAL_POINT_DISPATCH.json',dict(case_SHA=case.case_sha,
        selected_point_SHA=vector_sha(point),FULL_point_SHA=vector_sha(full),original_FULL_replay_PASS=True,
        FULL_raw_point=record(case.output/'BENCHMARK_FULL_RAW_POINT.npz'),UB=strict['Global_UB'],
        units=dict(P='kW',Q='kvar',SOC='kWh',slot_minutes=15),vehicles=vehicles,
        clipping=False,rounding=False,repairs=False))

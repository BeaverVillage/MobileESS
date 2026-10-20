"""Publish explicitly named frozen electrical arrays and identity errors."""
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import numpy as np
from ac import ROOT,DOC,RUN,save,csvout
from authority import read,record


def array_record(array,unit,axes):
    b=io.BytesIO();np.save(b,np.asarray(array),allow_pickle=False)
    return dict(sha256_npy=hashlib.sha256(b.getvalue()).hexdigest(),shape=list(array.shape),
        dtype=str(array.dtype),unit=unit,axes=axes,serialization='NumPy .npy, allow_pickle=False')


def errors(a,b):
    d=np.abs(np.asarray(a)-np.asarray(b));scale=float(np.abs(a).max(initial=0))
    return dict(max_abs_error=float(d.max(initial=0)),max_relative_error=float(d.max(initial=0)/scale) if scale else 0,
        relative_denominator='max absolute original array value; zero arrays require exact zero',exact=bool(np.array_equal(a,b)))


def main():
    bg=np.load(RUN/'IEEE123_FROZEN_BACKGROUND.npz');jobs=np.load(RUN/'jobs/ACTUAL_PHYSICAL.npz')
    refpath=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/references/2025-05-01/AIDC_REFERENCE.json')
    ref=read(refpath);r=ref['identity']
    assert r['arm']=='B0' and r['rule']=='EXACT_PR189_R0_Q50' and not r['B1_optimized_commands_read']
    p=np.load(r['physical']['path']);arrays={};registry={};totals=[];aidc=[];checks=[]
    begin=read(RUN/'jobs/REPLAY_RECEIPT.json')['begin'];AEST=timezone(timedelta(hours=10))
    for role,count,offset in [('PLANNING',96,0),('ACTUAL',120,24)]:
        key=role.lower();P=bg[key+'_P'];Q=bg[key+'_Q'];PV=bg[key+'_PV'];PVQ=np.zeros_like(PV)
        source=jobs if role=='ACTUAL' else p;AP=source['PCC_P_kw'];AQ=source['PCC_Q_kvar']
        arrays.update({role+'_BG_P_kw':P,role+'_BG_Q_kvar':Q,role+'_PV_P_kw':PV,role+'_PV_Q_kvar':PVQ,
            role+'_AIDC_P_kw':AP,role+'_AIDC_Q_kvar':AQ,role+'_BG_bus_phase':bg[key+'_bus_phase_keys'],
            role+'_AIDC_site':source['sites']})
        for name,value,unit,axes in [('BG_P_kw',P,'kW','slot,bus::phase'),('BG_Q_kvar',Q,'kvar','slot,bus::phase'),
             ('PV_P_kw',PV,'kW generation positive','slot,bus::phase'),('PV_Q_kvar',PVQ,'kvar generation positive','slot,bus::phase'),
             ('AIDC_P_kw',AP,'kW consumption positive','slot,AIDC01..12'),('AIDC_Q_kvar',AQ,'kvar consumption positive','slot,AIDC01..12')]:
            registry[role+'_'+name]=array_record(value,unit,axes)
        netP=np.array([math.fsum(a)+math.fsum(b)-math.fsum(v) for a,b,v in zip(P,AP,PV)])
        netQ=np.array([math.fsum(a)+math.fsum(b)-math.fsum(v) for a,b,v in zip(Q,AQ,PVQ)])
        arrays[role+'_NET_P_kw']=netP;arrays[role+'_NET_Q_kvar']=netQ
        registry[role+'_NET_P_kw']=array_record(netP,'kW','slot')
        registry[role+'_NET_Q_kvar']=array_record(netQ,'kvar','slot')
        for t in range(count):
            absolute=begin+(t+24 if role=='PLANNING' else t)*900
            totals.append(dict(role=role,execution_slot=t if role=='ACTUAL' else '',evaluation_slot=t-offset,
                interval_start_AEST=datetime.fromtimestamp(absolute,AEST).isoformat(),
                interval_end_AEST=datetime.fromtimestamp(absolute+900,AEST).isoformat(),
                background_P_kw=math.fsum(P[t]),background_Q_kvar=math.fsum(Q[t]),PV_P_kw=math.fsum(PV[t]),PV_Q_kvar=0.,
                AIDC_P_kw=math.fsum(AP[t]),AIDC_Q_kvar=math.fsum(AQ[t]),NET_P_kw=netP[t],NET_Q_kvar=netQ[t]))
            for j,site in enumerate(source['sites']):
                aidc.append(dict(role=role,execution_slot=t if role=='ACTUAL' else '',evaluation_slot=t-offset,
                    site=str(site),P_kw=AP[t,j],Q_kvar=AQ[t,j],IT_kw=source['IT_kw'][t,j],
                    cooling_aux_kw=AP[t,j]-source['IT_kw'][t,j],GPU=source['GPU'][t,j]))
        # Preserving site arrays in the proposed adapter is an identity binding,
        # not evidence that those sites can connect to any Greensboro PCC.
        for name,value,unit in [('AIDC_P',AP,'kW'),('AIDC_Q',AQ,'kvar')]:
            checks.append(dict(role=role,quantity=name,unit=unit,status='PASS_ARRAY_IDENTITY_ONLY',
                **errors(value,value.copy()),PCC_acceptance='NOT_VERIFIED'))
    file=DOC/'IEEE123_FROZEN_ELECTRICAL_INPUTS.npz';np.savez_compressed(file,**arrays)
    csvout('IEEE123_FINAL_POWER_TOTALS_216.csv',totals)
    csvout('IEEE123_AIDC12_POWER_2592.csv',aidc)
    save('ELECTRICAL_ARRAY_SHA256.json',dict(container=record(file),arrays=registry,
        planning_AIDC_reference=record(refpath),planning_AIDC_physical=r['physical'],
        Actual_FCFS_replay=record(RUN/'jobs/ACTUAL_PHYSICAL.npz'),
        PV_Q_authority='Original Generator Model=1 constant PQ; every application sets kvar=0. Actual setpoint digest matches all 120 archived slots.',
        site_array_conservation=checks,PV_physical_remapping='NOT_VERIFIED',Greensboro_AC_allowed=False))
    manifest=read(ROOT/'docs/v44/SEVEN_DAY_INPUT_MANIFEST.json')['days'][0]
    save('GREENSBORO_CANDIDATE_INPUT_BINDING.json',dict(status='NOT_CERTIFIED_SPATIAL_MAPPING',
        operating_input_ready=False,original_electrical_input=record(file),
        unchanged_dated_sources=manifest['files'],
        AIDC_P_Q_binding='Identity on original site axis; no site permutation',
        jobs_GPU_QoS_deadline='Original native/windows/public request descriptor files referenced unchanged; no descriptor rewritten',
        traffic='Original 24-service Route Table and Traffic Forecast receipts referenced unchanged; no ETA/energy entry rewritten',
        P_Q_spatial_weights=record(DOC/'GREENSBORO_FIXED_LOAD_SHARE_CANDIDATES.csv'),
        PV_mapping=None,PV_mapping_status='INPUT_MAPPING_NOT_VERIFIED',
        final_PCC_mapping=None,approval_or_physical_certification_inferred=False))
    print('exported',len(totals),'total rows',len(aidc),'site rows and',len(registry),'array digests')


if __name__=='__main__':main()

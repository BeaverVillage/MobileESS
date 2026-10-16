"""Dated V44 R0 anchor feeding the exact Epoch12 Forecast generator."""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import argparse
import numpy as np
from .common import ROOT,DOC,RUNTIME,read,record,atomic,verify,digest,now,NotReady
from .config import DAYS,axis
from .svr11_vendor import REVISION
from .svr11_hardware import HARDWARE,scope,prepare,source_identity

INPUTS=RUNTIME/'svr11_revision01/inputs'
MODELS=RUNTIME/'svr11_revision01/models'


def base_day(day):
    if day not in DAYS:raise ValueError('V44_SEVEN_DAYS_ONLY')
    return next(r for r in read(DOC/'SEVEN_DAY_INPUT_MANIFEST.json')['days'] if r['day']==day)


def prepare_inputs(day):
    row=base_day(day);folder=INPUTS/day;folder.mkdir(parents=True,exist_ok=True)
    receipts={}
    for label,name in [('native','NATIVE_INPUT.json'),('windows','WINDOWS.json'),('planning_input','PLANNING_INPUT_BUNDLE.json'),
            ('power_authority','POWER_AUTHORITY.json'),('provenance','SOURCE_PROVENANCE.json')]:
        original=row['files'][label];verify([original]);target=folder/name
        # NATIVE_INPUT is the V44 revision's explicit binding output. Original
        # Raw and its native input remain immutable and SHA-recorded separately.
        if not target.exists():target.write_bytes(Path(original['path']).read_bytes())
        elif name!='NATIVE_INPUT.json' and target.read_bytes()!=Path(original['path']).read_bytes():
            raise ValueError('SVR11_DATED_INPUT_DRIFT:'+name)
        receipts[name]=original
    atomic(folder/'ORIGINAL_INPUT_RECEIPTS.json',dict(day=day,axis=axis(day),sources=receipts,
        hardware=record(HARDWARE/'HARDWARE.json'),Actual_input_copied=False,Actual_input_reads=0))
    return folder


def planning_anchor(day,input_folder,output):
    from v43_arms.reference import project
    from v42_temporal.native import load_power
    from v42_integrated.contract import physical_authority
    output=Path(output);output.mkdir(parents=True,exist_ok=True);native=read(Path(input_folder)/'NATIVE_INPUT.json')
    sites,caps,known,anon,selected,x,carry,cons=project(native)
    with physical_authority():_,power,idle,swing=load_power(native)
    gpu=known+anon;it=idle*caps+swing*gpu
    pcc=np.array([[power[s,t].slope*it[t,j]+power[s,t].intercept_kw for j,s in enumerate(sites)] for t in range(96)])
    arrays=dict(sites=np.array(sites),capacities=caps,known_gpu=known,cc4_served_gpu=anon,GPU=gpu,IT_kw=it,
        PCC_P_kw=pcc,PCC_Q_kvar=pcc*np.tan(np.arccos(.95)))
    np.savez_compressed(output/'PLANNING_PHYSICAL.npz',**arrays)
    atomic(output/'B0_NEW_PLANNING_GENERATION.json',dict(schema='V44_EXACT_PR189_R0_FORECAST_ANCHOR',
        day=day,conservation=cons,input=record(Path(input_folder)/'ORIGINAL_INPUT_RECEIPTS.json'),
        physical=record(output/'PLANNING_PHYSICAL.npz'),Actual_inputs_read=0,Native_calls=0))
    return dict(arrays=arrays)


def generate(day,*,progress=lambda r:None):
    if day not in DAYS:raise ValueError('V44_SEVEN_DAYS_ONLY')
    row=base_day(day)
    if row['status']!='INPUT_READY':raise NotReady('SVR11_DATED_SOURCE_INPUT_NOT_READY:'+day)
    h=read(HARDWARE/'HARDWARE.json')
    if h['source_SHA']!=source_identity():raise ValueError('SVR11_HARDWARE_PREPARATION_SOURCE_DRIFT')
    folder=prepare_inputs(day);out=MODELS/day
    with scope() as authority:
        from v42_svr11 import model
        from v42_voltage_control import b0_new
        from v42_may_campaign_native90.preflight import native_zero
        def report(r):
            atomic(MODELS/(day+'_LIVE.json'),dict(r,day=day,UTC=now(),source_SHA=authority['execution_SHA']))
            progress(r)
        with native_zero() as denied,patch.object(b0_new,'build_planning',planning_anchor):
            certificate=model.generate(day,folder,out,report)
            if denied:raise PermissionError('SVR11_FORECAST_GUROBI_CALL_FORBIDDEN')
        cert=read(certificate['path'])
        if cert['scenario_SHA']!=h['scenario_SHA'] or not cert['model_regenerated'] or cert['Actual_inputs_read']!=0:
            raise ValueError('SVR11_NEW_FORECAST_CERTIFICATE_REQUIRED')
        native=read(folder/'NATIVE_INPUT.json')
        native.update(electrical_certificate=certificate,grid_outputs=cert['outputs'],
            V44_SVR11=dict(hardware=record(HARDWARE/'HARDWARE.json'),scenario=h['scenario'],
                source_SHA=authority['execution_SHA'],model_version=cert['model_version'],revision='V44_SVR11_REVISION01'))
        atomic(folder/'NATIVE_INPUT.json',native)
        proof=dict(PASS=True,day=day,source_SHA=authority['execution_SHA'],hardware=record(HARDWARE/'HARDWARE.json'),
            model=certificate,input=record(folder/'NATIVE_INPUT.json'),windows=record(folder/'WINDOWS.json'),
            original=record(folder/'ORIGINAL_INPUT_RECEIPTS.json'),
            fresh_topology_and_153_transformer_phase_rows=True,Actual_inputs_read=0,tap_optimization_variables=0,
            old_Golden003_or_B2_point_reused=False,nonlinear_safety='NOT_CERTIFIED_BY_LOCAL_RESPONSE')
        atomic(folder/'SVR11_INPUT_READY.json',proof);return proof


def main():
    p=argparse.ArgumentParser();p.add_argument('--day',required=True);a=p.parse_args()
    from .locks import coordinator
    # Forecast probes own the same external resource lease as real workers.
    with coordinator(RUNTIME/'svr11_revision01/FORECAST_LEASE'):
        result=generate(a.day,progress=lambda r:print(r,flush=True))
    print(dict(PASS=result['PASS'],day=a.day,certificate=result['model']),flush=True)


if __name__=='__main__':main()

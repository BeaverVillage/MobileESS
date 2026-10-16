"""Original PR189 R0 site/start reference with its current frozen Q50 view.

The native bundle, not inherited requested/Q90 service fields, determines
service. No FCFS regeneration, optimized B1 command or private event is read.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from v43.common import ROOT,DOC,read,record,verify_records,atomic
from v42_native.contracts import digest


def project(native):
    from v42_final.native import canonical_jobs
    from v42_capacity.queue import allocate,conservation
    verify_records([native['reference']])
    old={r['job_uid']:r for r in read(native['reference']['path'])}
    if set(old)!={r['job_uid'] for r in native['known_population']}:
        raise ValueError('ORIGINAL_R0_ROSTER_REQUIRED')
    sites=sorted(native['capacities']);caps=np.array([native['capacities'][s] for s in sites])
    known=np.zeros((96,12));selected={}
    for job in canonical_jobs(native):
        r=old[job['job_id']]
        if r['AIDC_site']!=job['site'] or r['start_slot']!=job['reference_start']:
            raise ValueError('PR189_R0_SITE_START_DRIFT')
        if not job['nominal_slots']:continue
        site=job['site'];start=job['reference_start'];end=job['nominal_end']
        known[max(0,start-24):max(0,min(96,end-24)),sites.index(site)]+=job['GPU_gang']
        selected[job['job_id']]=dict(start=start,initial_site=site,segments=[[site,start,end]],
            checkpoint=-1,physical_checkpoint_seconds=-1,destination='',transfer_start=-1,
            transfer_end=-1,restart_end=-1,wan=[])
    kernel=pd.read_csv(ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv',float_precision='round_trip').kappa.to_numpy()
    from v42_final.workload import profile
    replay=profile(native['C0_Q50'],kernel)
    full=np.asarray(native['unknown_nominal_GPU'],float)
    if replay.shape!=full.shape or not np.allclose(replay,full,rtol=0,atol=1e-9):
        raise ValueError('ORIGINAL_CC4_PROFILE_CHANGED')
    anon,_,backlog=allocate(known,full[:96],caps)
    # Label the existing forward-backlog allocator's work by original hour.
    # FIFO labeling is accounting only: aggregate served GPU is unchanged.
    x={};pending=np.zeros(24)
    for t in range(96):
        for h,mass in enumerate(native['C0_Q50']):
            lag=t-4*h
            if 0<=lag<len(kernel):pending[h]+=4*mass*kernel[lag]
        remaining=float(anon[t].sum())
        for h in range(24):
            take=min(remaining,max(0.,pending[h]));remaining-=take;pending[h]-=take
            if take:x[str((h,t))]=take/4
        if remaining>1e-7:raise ValueError('CC4_BASELINE_HOUR_LABELING_MASS_DRIFT')
    carry={str(h):float(mass-sum(v for key,v in x.items() if key.startswith('('+str(h)+',')))
        for h,mass in enumerate(native['C0_Q50'])}
    conservation_receipt=conservation(sum(native['C0_Q50']),anon,backlog[-1],float(full[96:].sum()/4))
    conservation_receipt.update(kernel_roundtrip_replay_max_abs_GPU=float(abs(replay-full).max()),
        physical_forecast_profile='LITERAL_FROZEN_NATIVE_INPUT_NO_REPLACEMENT',
        replay_tolerance_only_not_model_feasibility_tolerance=1e-9,
        maximum_capacity_backlog_GPU=float(backlog.max()),terminal_capacity_backlog_GPU=float(backlog[-1]))
    return sites,caps,known,anon,selected,x,carry,conservation_receipt


def freeze(output):
    from v43_actual.case import accepted
    from v42_temporal.native import load_power
    from v42_integrated.contract import physical_authority
    output=Path(output)
    if output.exists():raise ValueError('NEW_B0_REFERENCE_OUTPUT_REQUIRED')
    output.mkdir(parents=True)
    cert,original_freeze,native,windows,_=accepted()
    sites,caps,known,anon,selected,x,carry,cons=project(native)
    with physical_authority():_,power,idle,swing=load_power(native)
    gpu=known+anon;it=idle*caps+swing*gpu
    pcc=np.array([[power[s,t].slope*it[t,j]+power[s,t].intercept_kw for j,s in enumerate(sites)] for t in range(96)])
    arrays=dict(sites=np.array(sites),capacities=caps,known_gpu=known,cc4_served_gpu=anon,
        GPU=gpu,IT_kw=it,PCC_P_kw=pcc,PCC_Q_kvar=pcc*np.tan(np.arccos(.95)))
    np.savez_compressed(output/'PLANNING_PHYSICAL.npz',**arrays)
    source=[record(ROOT/p) for p in ('v43_arms/reference.py','v42_final/native.py',
        'v42_capacity/queue.py','v42_final/workload.py','v42_temporal/native.py')]
    identity=dict(schema='V43_PR189_R0_Q50_REFERENCE_V1',day='2025-05-01',arm='B0',stage='REFERENCE',
        parent_case_sha=original_freeze['scientific_input']['NATIVE_INPUT.json']['sha256'],
        reference=native['reference'],input=original_freeze['scientific_input']['NATIVE_INPUT.json'],
        windows=original_freeze['scientific_input']['WINDOWS.json'],source=source,
        Known_UID=1649,selected_nominal_UID=len(selected),external_initial_RUNNING=44,
        rule='EXACT_PR189_R0_SITE_START_WITH_CANONICAL_CURRENT_Q50_SERVICE',
        CC4_rule='ORIGINAL_FIXED_EXECUTION_KERNEL_GRID_BLIND_CAPACITY_ALLOCATION',
        physical=record(output/'PLANNING_PHYSICAL.npz'),conservation=cons,
        AIDC_optimization_calls=0,MESS_optimization_calls=0,old_requested_service_imported=False,
        B1_optimized_commands_read=False,Source_initial44='MODEL_ASSUMED_IN_ACTUAL_ONLY',
        FULL_optimization_certificate='NOT_APPLICABLE_REFERENCE',FORECAST_CAUSAL_AVAILABILITY='NOT_CERTIFIED')
    aidc=dict(selected_jobs=selected,CC4_service=x,CC4_carryout=carry,
        AIDC_P_by_site={s:pcc[:,j].tolist() for j,s in enumerate(sites)},
        AIDC_Q_by_site={s:arrays['PCC_Q_kvar'][:,j].tolist() for j,s in enumerate(sites)})
    identity['aidc_anchor']=digest(aidc)
    atomic(output/'AIDC_REFERENCE.json',dict(identity=identity,**aidc))
    atomic(DOC/'V43_B0_REFERENCE_AUDIT.json',dict(status='REFERENCE_FROZEN_PLANNING_AC_NOT_YET_CERTIFIED',
        frozen_reference=record(output/'AIDC_REFERENCE.json'),**identity,
        alternate_FCFS_cache_rejected='Different R0 sites/start authority; not the original PR189 common reference'))
    return dict(bundle=native,planning=arrays,identity=identity)


def load(output):
    from v43_actual.case import accepted
    doc=read(Path(output)/'AIDC_REFERENCE.json');identity=doc['identity']
    verify_records(identity['source']+[identity['input'],identity['windows'],identity['reference'],identity['physical']])
    with np.load(identity['physical']['path'],allow_pickle=False) as z:arrays={k:z[k].copy() for k in z.files}
    return dict(bundle=accepted()[2],planning=arrays,identity=identity)

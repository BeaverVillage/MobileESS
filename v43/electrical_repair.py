"""Isolated GFS00Z electrical case using unchanged original AC generators."""
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import FunctionType
import argparse
import hashlib
import inspect
import os
import shutil
import sys
import traceback
from .common import *

SOURCE=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance').resolve()
WEATHER=RUNS.parent/'inputs/weather/2025-05-01_GFS00Z'
CASE=RUNS.parent/'cases/2025-05-01_GFS00Z_attempt001'
DAY='2025-05-01'
CUTOFF=datetime.fromisoformat('2025-04-30T08:00:00+00:00')

def original_inputs():
    folder=Path(read(DOC/'GOLDEN_REQUEST.json')['input_folder'])
    b=read(folder/'NATIVE_INPUT.json')
    verify_records([b['electrical_certificate']])
    c=read(b['electrical_certificate']['path'])
    return b,c

def verify_weather():
    m=read(WEATHER/'REPAIR_SOURCE_MANIFEST.json')
    if len(m['records'])!=150:raise ValueError('ALL_150_FORECAST_MESSAGES_REQUIRED')
    verify_records([m['weather']]+[x['file'] for x in m['records']]+[x['idx'] for x in m['records']])
    axis={(x['lead_hours'],x['variable']) for x in m['records']}
    expected={(lead,var) for lead in range(14,39) for var in ('TMP','DPT','RH','PRES','UGRD','VGRD')}
    if axis!=expected:raise ValueError('GFS_REPAIR_COMPLETE_LEAD_VARIABLE_AXIS_REQUIRED')
    for x in m['records']:
        if parsedate_to_datetime(x['Last_Modified'])>CUTOFF or not x['available_before_cutoff']:
            raise ValueError('GFS_RELEASE_AFTER_CUTOFF')
    return m

def prepare():
    import numpy as np
    import pandas as pd
    sys.path.insert(0,str(SOURCE))
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v36.contracts import PF_TAN,SOURCE_DATA_REPOSITORY
    from dayahead.v28r2.source_cache import day_root
    if CASE.exists():raise PermissionError('NEW_ELECTRICAL_CASE_REQUIRED')
    m=verify_weather();bundle,old=original_inputs();i=old['input_identity']['identity']['inputs']
    CASE.mkdir(parents=True);inputs=CASE/'inputs';inputs.mkdir()
    original_anchor=i['AC_anchor_input']['source'];verify_records([original_anchor])
    with np.load(original_anchor['path']) as z:
        oldgpu=z['gpu'].copy();oldit=z['it'].copy()
    sites=sorted(bundle['capacities']);caps=[bundle['capacities'][s] for s in sites]
    if oldgpu.shape!=(96,12) or oldgpu.dtype.kind not in 'iu':raise ValueError('ORIGINAL_WHOLE_GPU_ANCHOR_AXIS')
    it=np.array([[float(site_it_power_kw(caps[j],int(oldgpu[t,j]))) for j in range(12)] for t in range(96)])
    if not np.array_equal(it,oldit):raise ValueError('ORIGINAL_GPU_IT_ANCHOR_NOT_REPRODUCED')
    weather=pd.read_parquet(m['weather']['path'])
    model=SOURCE/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json'
    params=load_c1(model)
    pcc=np.array([exact_c1_pcc_kw(it[t],float(w.t_wb_c),float(w.rh_pct),params) for t,w in enumerate(weather.itertuples())])
    if pcc.shape!=(96,12) or not np.isfinite(pcc).all():raise ValueError('FINITE_NEW_PCC_ANCHOR_REQUIRED')
    np.savez_compressed(inputs/'V41R2_B0_IT_PCC.npz',gpu=oldgpu,it=it,pcc=pcc,qcc=pcc*PF_TAN)
    forecast=day_root(SOURCE_DATA_REPOSITORY,DAY)/'aemo_forecast.json'
    shutil.copyfile(forecast,inputs/'aemo_forecast.json')
    shutil.copyfile(m['weather']['path'],inputs/'gfs_d1_weather.parquet')
    copied=[]
    for rel in ('dayahead/v40e/mapping.py','dayahead/v28r2/electrical_context.py',
                'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json'):
        p=CASE/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/rel,p);copied.append(record(p))
    values={k:deepcopy(i[k]) for k in ('day','alpha_grid','axes','OpenDSS_master','PCC_mapping','service_PCC_mapping',
        'demand','PV','feeder_manifest','line_ratings','transformer_ratings','native_controls','background_mapping','AIDC_power_C1') if k in i}
    values.update(weather=record(inputs/'gfs_d1_weather.parquet'),
        AC_anchor_input=dict(role='V43_CAUSAL_WEATHER_NEW_PCC_ORIGINAL_GPU_IT',source=record(inputs/'V41R2_B0_IT_PCC.npz')),
        voltage_generation=dict(frozen_April_joint_authority=deepcopy(i['voltage_generation']['frozen_April_joint_authority'])),
        V43_causal_source_manifest=record(WEATHER/'REPAIR_SOURCE_MANIFEST.json'),
        V43_AEMO_forecast=record(inputs/'aemo_forecast.json'),V43_original_unchanged_known_inputs=record(Path(read(DOC/'GOLDEN_REQUEST.json')['input_folder'])/'NATIVE_INPUT.json'))
    atomic(inputs/'CURRENT_PHYSICAL_INPUTS.json',values)
    result=dict(status='PREPARED_NATIVE0_NOT_ELECTRICAL_CERTIFIED',Native_calls=0,UTC=now(),
        original_input=record(Path(read(DOC/'GOLDEN_REQUEST.json')['input_folder'])/'NATIVE_INPUT.json'),
        original_anchor=original_anchor,weather_manifest=record(WEATHER/'REPAIR_SOURCE_MANIFEST.json'),
        GPU_IT_bit_exact_reproduced=True,GPU_IT_weather_independent=True,new_anchor=record(inputs/'V41R2_B0_IT_PCC.npz'),
        C1=record(model),inputs=record(inputs/'CURRENT_PHYSICAL_INPUTS.json'),copied_support=copied,
        source=[record(SOURCE/'dayahead/v41r2/prepare.py'),record(SOURCE/'dayahead/v39a/power.py')],
        source_cases_differ=True,old_electrical_arrays_used=False,old_UB_LB_transferred=False)
    atomic(CASE/'PREPARE_NATIVE0.json',result);print('ELECTRICAL_CASE_PREPARED',CASE,flush=True)

@contextmanager
def routed_sources():
    """Only process-local path/authority routing, no generator-body edits."""
    sys.path.insert(0,str(SOURCE))
    from dayahead.v28r2 import source_cache
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.v41r2 import authority as r2
    from dayahead.v41r3 import authority as r3
    from dayahead.v40e import electrical as engine
    from dayahead import run_v16_3_voltage_candidate as voltage,run_v16_3_correction as current
    saved=(source_cache.day_root,r2.ROOT,r2.OUT,r2.DAY,r3.scale_background,voltage._compile,current._compile)
    original_day=source_cache.day_root
    def day_root(repo,day):
        if Path(repo).resolve()==SOURCE_DATA_REPOSITORY.resolve() and day==DAY:return CASE/'inputs'
        return original_day(repo,day)
    source_cache.day_root=day_root;r2.ROOT=CASE;r2.OUT=CASE/'inputs';r2.DAY=DAY
    # Exactly the original V41R4 final-authority adapter: its only literal
    # change is the already-approved frozen alpha assertion 1.6 -> 1.15.
    src=inspect.getsource(saved[4]);needle="authority['selected_alpha_BG']==1.6"
    if src.count(needle)!=1:raise ValueError('ORIGINAL_BACKGROUND_ADAPTER_SHAPE_DRIFT')
    namespace=dict(saved[4].__globals__,OUT=SOURCE/'frozen_artifacts/v41r4_may/audit',
        SCALE=SOURCE/'frozen_artifacts/v41r4_may/audit'/DAY)
    exec(compile(src.replace(needle,"authority['selected_alpha_BG']==1.15"),__file__+'::v41r4_alpha_binding','exec'),namespace)
    r3.scale_background=namespace['scale_background']
    def isolated(original,label):
        def compile(*args,**kwargs):
            previous=Path.cwd()
            try:
                odd,adapter=original(*args,**kwargs)
                path=CASE/'generation/OPENDSS_SANDBOX'/label;path.mkdir(parents=True,exist_ok=True)
                odd.Basic.DataPath(str(path))
                if Path(odd.Basic.DataPath()).resolve()!=path.resolve():raise ValueError('AC_DATA_PATH_ISOLATION_FAILED')
                return odd,adapter
            finally:os.chdir(previous)
        return compile
    voltage._compile=isolated(saved[5],'voltage');current._compile=isolated(saved[6],'current')
    try:yield
    finally:
        source_cache.day_root,r2.ROOT,r2.OUT,r2.DAY,r3.scale_background,voltage._compile,current._compile=saved

def source_freeze():
    sources=[record(p) for p in sorted((SOURCE/'dayahead').rglob('*.py'))]
    sources += [record(Path(__file__)),record(ROOT/'v43/common.py')]
    original=read(CASE/'PREPARE_NATIVE0.json')
    values=read(CASE/'inputs/CURRENT_PHYSICAL_INPUTS.json')
    return dict(schema='V43_INDEPENDENT_ELECTRICAL_SOURCE_FREEZE_V1',UTC=now(),Native_calls=0,
        source_commit=git('rev-parse','HEAD').decode().strip(),sources=sources,prepared=record(CASE/'PREPARE_NATIVE0.json'),
        new_case_inputs=record(CASE/'inputs/CURRENT_PHYSICAL_INPUTS.json'),
        weather=record(CASE/'inputs/gfs_d1_weather.parquet'),anchor=record(CASE/'inputs/V41R2_B0_IT_PCC.npz'),
        dependency_routing='V43_PROCESS_LOCAL_PATHS_AND_ORIGINAL_V41R4_ALPHA_ASSERTION_ONLY',
        unchanged_original_AIDC_math=True,original_AIDC_native_policy_unchanged=True,
        new_weather_is_new_case=True,historical_bounds_transferred=False)

def generate():
    sys.path.insert(0,str(SOURCE))
    from v42_may_campaign.common import exclusive_lock
    from v43.golden import no_heavy_peer
    from v42_may_campaign_native90.preflight import native_zero
    from dayahead.v40i.electrical import generate_outputs
    from dayahead.v40h.identity import bind,verify_bound_files
    from dayahead.v41.mapper_audit import observe
    from dayahead.v41.electrical import verify_generation_proof
    from dayahead.v39d.evaluate import _load_capacity
    prepared=read(CASE/'PREPARE_NATIVE0.json');verify_weather()
    for x in (prepared['new_anchor'],prepared['inputs'],prepared['weather_manifest']):verify_records([x])
    run=CASE/'generation'
    if run.exists():raise PermissionError('FRESH_AC_GENERATION_ATTEMPT_REQUIRED')
    with ExitStack() as owned:
        no_heavy_peer()
        for p in (Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock'):
            owned.enter_context(exclusive_lock(p))
        freeze=source_freeze();atomic(run/'SOURCE_FREEZE.json',freeze)
        values=read(CASE/'inputs/CURRENT_PHYSICAL_INPUTS.json')
        values['V43_generation_source_freeze']=record(run/'SOURCE_FREEZE.json')
        verify_bound_files(values)
        identity=bind('V43_ELECTRICAL_GENERATION_V1',values,tuple(values))
        atomic(run/'PRE_GENERATION_IDENTITY.json',identity);captured=now()
        atomic(run/'START.json',dict(pid=os.getpid(),UTC=captured,Native_calls=0,source=record(run/'SOURCE_FREEZE.json')))
        with native_zero() as attempted,routed_sources(),observe(run/'mapper_audit',DAY,'Planning_GENERATION'):
            capacity,_=_load_capacity(CASE)
            if capacity.site_capacity!=original_inputs()[0]['capacities']:raise ValueError('ORIGINAL_780_CAPACITY_NOT_RETAINED')
            outputs,proof=generate_outputs(CASE,DAY,run,identity)
        if attempted:raise ValueError('NATIVE_OPTIMIZE_FORBIDDEN_DURING_AC_GENERATION')
        finished=now();verify_records(freeze['sources']);verify_bound_files(values)
        certificate=dict(schema='V41_ELECTRICAL_CERTIFICATE_V1',V43_case=True,
            generation_attestation='CAPTURED_BEFORE_PRODUCER_AND_RECHECKED_AFTER',
            pre_generation_identity_completed_at=captured,generation_started_at=captured,
            generation_finished_at=finished,post_generation_verification_completed_at=now(),
            input_identity=identity,outputs={k:record(p) for k,p in outputs.items()},proof=proof,
            mapper_audit=record(run/'mapper_audit/MAPPER_AUDIT.json'),
            generation_start_receipt=record(run/'START.json'),source_freeze=record(run/'SOURCE_FREEZE.json'),
            Native_calls=0,prior_certificate_or_bound_reused=False)
        verify_generation_proof(certificate)
        if read(certificate['mapper_audit']['path'])['status']!='PASS':raise ValueError('ORIGINAL_MAPPING_AUDIT_FAILED')
        atomic(run/'V43_ELECTRICAL_CERTIFICATE.json',certificate)
        atomic(CASE/'RESULT.json',dict(status='FRESH_AC_COEFFICIENT_GENERATION_COMPLETE_NOT_GOLDEN_PASS',
            Native_calls=0,certificate=record(run/'V43_ELECTRICAL_CERTIFICATE.json'),proof=proof))
        print('ELECTRICAL_REGENERATION_COMPLETE',run,flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','generate'));a=p.parse_args()
    try:
        if a.action=='prepare':prepare()
        else:generate()
    except BaseException as e:
        atomic(CASE/(a.action.upper()+'_ERROR.json'),dict(error=repr(e),traceback=traceback.format_exc(),UTC=now(),Native_calls=0))
        raise

if __name__=='__main__':main()

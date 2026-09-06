"""D-1-only context materialization without the legacy outcome namespaces."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import FunctionType, SimpleNamespace
import hashlib
import json
import os
import numpy as np
import pandas as pd


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def load_planning_context(repo, day):
    from dayahead.v28r2.electrical_context import source_root, portable_background_paths
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    from dayahead import grid_background_v16_2 as bg
    from dayahead.v37r3.voltage_authority import joint_repaired_coefficients
    from dayahead.v28r2.c1_affine import load_c1, exact_c1_pcc_kw
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v39d.evaluate import _load_capacity
    repo=Path(repo).resolve();source=source_root(SOURCE_DATA_REPOSITORY)
    if not day.startswith(('2025-04-','2025-05-')):raise ValueError('UNAUTHORIZED_DEVELOPMENT_OR_EVALUATION_DAY')
    if day.startswith('2025-04-'):
        cache=SOURCE_DATA_REPOSITORY/'frozen_artifacts/v28r2_april_full_month_preflight'/day/'dayahead/electrical_cache/data'
    else:cache=repo/'dayahead/cache/v37_may_locked_final/electrical'/day/'data'
    vp=cache/f'D1_AC_ANCHOR_SENSITIVITY_{day}.npz'
    ip=cache/f'D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz'
    fp=day_root(SOURCE_DATA_REPOSITORY,day)/'aemo_forecast.json'
    wp=day_root(SOURCE_DATA_REPOSITORY,day)/'gfs_d1_weather.parquet'
    forecast=json.loads(fp.read_text(encoding='utf-8'));weather=pd.read_parquet(wp)
    cutoff=(datetime.fromisoformat(day)-timedelta(hours=6)).isoformat(timespec='minutes')
    if not str(forecast['cutoff_fixed_aest']).startswith(cutoff):raise ValueError('D1_FORECAST_CAUSALITY')
    hashes={str(p):file_sha(p) for p in (vp,ip,fp,wp)}
    paths=portable_background_paths(SOURCE_DATA_REPOSITORY,source)
    def verify_numeric_inputs(p):
        records={}
        for name,expected in bg.EXPECTED_SHA256.items():
            if name=='pv_reference':
                records[name]={'sha256':expected,'status':'FROZEN_PROVENANCE_ONLY_NOT_OPENED'};continue
            path=getattr(p,name);observed=file_sha(path)
            if observed!=expected:raise ValueError('BACKGROUND_AUTHORITY_DRIFT:'+name)
            hashes[str(path)]=observed;records[name]={'path':str(path),'sha256':observed,'status':'PASS'}
        return records
    ns=dict(bg.build_authority_background_binding.__globals__);ns['_verify_sources']=verify_numeric_inputs
    build=FunctionType(bg.build_authority_background_binding.__code__,ns)
    background=build(timestamps_fixed_aest=forecast['timestamps_96'],demand_mw_96=forecast['demand_mw_96'],rooftop_pv_mw_96=forecast['pv_mw_96'],paths=paths)
    voltage=np.load(vp,allow_pickle=False);current=np.load(ip,allow_pickle=False)
    previous=Path.cwd()
    try:
        anchor=np.asarray(voltage['anchor_control'])
        if anchor.shape!=(96,60) or np.count_nonzero(anchor[:,12:]):raise ValueError('PLANNING_ANCHOR_AXIS')
        pcc=SOURCE_DATA_REPOSITORY/'dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss'
        hashes[str(pcc)]=file_sha(pcc)
        binding=build_full_grid_binding(assets=source/'opendss_assets',contract=source/'power_v70_p4f_contract',
            demand_mw_96=forecast['demand_mw_96'],rooftop_pv_mw_96=forecast['pv_mw_96'],aidc_plan_kw_96x12=anchor[:,:12],pcc_asset=pcc,background_binding=background)
        electrical=SimpleNamespace(legacy_context=(None,forecast,background,binding,vp,None),voltage=voltage,current=current,voltage_path=vp)
        coefficients=joint_repaired_coefficients(repo,electrical)
    except BaseException:
        voltage.close();current.close();raise
    finally:os.chdir(previous)
    capacity,_=_load_capacity(repo)
    c1path=repo/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json'
    hashes[str(c1path)]=file_sha(c1path);c1=load_c1(c1path)
    tables={}
    for site,cap in capacity.site_capacity.items():
        it=np.asarray([float(site_it_power_kw(cap,g)) for g in range(cap+1)])
        tables[site]=np.asarray([exact_c1_pcc_kw(it,float(r.t_wb_c),float(r.rh_pct),c1) for r in weather.itertuples(index=False)])
    return SimpleNamespace(electrical=electrical,coefficients=coefficients,nodes=list(map(str,voltage['node_names'])),
                           capacity=capacity,tables=tables,input_shas=hashes,day=day,
                           provenance={'D1_cutoff':cutoff,'Actual_reads':0,'Fresh_reads':0,'candidate_AC_solves':0})

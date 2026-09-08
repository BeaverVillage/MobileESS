"""Frozen materialized inputs only; no training, prediction or optimization."""
from pathlib import Path
from dataclasses import replace
import numpy as np
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,record
OLD=ROOT.parent/'MobileESS_v41r2_780gpu_capacity_rebase'
OLD_RUN=OLD/'frozen_artifacts/v41r2_780'
OUT=ROOT/'dayahead/artifacts/v41r3_fast_power_scale_freeze'
SCALE=ROOT/'dayahead/artifacts/v41r3_scale_rebalance'
DAY='2025-05-04'

def scale_background(background,stage):
    authority=read(OUT/'V41R3_BACKGROUND_SCALE_AUTHORITY.json')
    assert authority['status']=='FROZEN' and authority['selected_alpha_BG']==1.6
    assert not background.evidence.get('V41R3_scaled',False),'BACKGROUND_DOUBLE_SCALING'
    alpha=authority['selected_alpha_BG']
    with np.load(SCALE/'inputs'/f'ORIGINAL_{stage}_BACKGROUND.npz') as z:
        keys=[tuple(k.split('::')) for k in z['bus_phase_keys']]
        for name,field in [('gross_P_kw','gross_p_kw_96'),('gross_Q_kvar','gross_q_kvar_96'),('PV_P_kw','pv_generation_kw_96')]:
            values=np.asarray([[row.get(k,0.) for k in keys] for row in getattr(background,field)])
            assert np.array_equal(values,z[name]),'FROZEN_BACKGROUND_SOURCE_DRIFT:'+stage+name
    p=tuple({k:alpha*v for k,v in row.items()} for row in background.gross_p_kw_96)
    q=tuple({k:alpha*v for k,v in row.items()} for row in background.gross_q_kvar_96)
    net=tuple({k:row.get(k,0.)-pv.get(k,0.) for k in set(row)|set(pv)} for row,pv in zip(p,background.pv_generation_kw_96))
    return replace(background,gross_p_kw_96=p,gross_q_kvar_96=q,net_p_kw_96=net,
        evidence=dict(background.evidence,V41R3_scaled=True,alpha_BG=alpha,scale_authority=record(OUT/'V41R3_BACKGROUND_SCALE_AUTHORITY.json')))

def snapshot(day):
    from dayahead.v41.data import RUNTIME
    from dayahead.v41.reserve import validate_snapshot
    from dayahead.v41r2.authority import capacity
    assert day==DAY,'FULL_MAY_HOLD'
    path=RUNTIME/'inputs'/day/f'V41_ML_SNAPSHOT_{day}.json'
    original=OLD_RUN/'inputs'/day/path.name
    assert record(path)['sha256']==record(original)['sha256'],'FROZEN_ML_SNAPSHOT_DRIFT'
    value=read(path);validate_snapshot(value,capacity()[0])
    assert np.all(np.asarray(value['H4_CAP_PHYS'])==3120)
    seal=read(path.parent/'ML_SNAPSHOT_RECEIPT.json')
    assert seal['snapshot']==record(path)
    return path,seal

def pre_solve(day,snapshot_path,capacity):
    from dayahead.v41.persistence import verify_table
    from dayahead.v41.reserve import validate_snapshot
    path=Path(snapshot_path);snapshot(day)
    validate_snapshot(read(path),capacity)
    audit=read(path.parent/'PRE_SOLVE_PERSISTENCE_AUDIT.json')
    assert audit['status']=='PASS' and audit['snapshot']==record(path)
    for entry in audit['tables'].values():verify_table(entry)
    return audit

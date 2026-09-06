from __future__ import annotations
import numpy as np, pandas as pd


def _hour_bin(hour,bins):
    for i in range(len(bins)-1):
        if bins[i]<=hour<bins[i+1]: return f"{bins[i]:02d}-{bins[i+1]:02d}"
    return f"{bins[-2]:02d}-{bins[-1]:02d}"

def _prepare_library(mark,timezone,bins):
    m=mark.copy(); m["timestamp_utc"]=pd.to_datetime(m.timestamp_utc,utc=True)
    local=m.timestamp_utc.dt.tz_convert(timezone); m["weekend"]=(local.dt.dayofweek>=5).astype(int); m["hour_bin"]=[_hour_bin(int(h),bins) for h in local.dt.hour]
    return m

def generate_for_origin(hazard_row,mark,origin,n_scenarios,cfg,seed=None):
    rng=np.random.default_rng(int(seed if seed is not None else cfg["scenarios"]["random_seed"])); bins=list(map(int,cfg["scenarios"]["representative_hour_bins"])); tz=cfg["analysis"]["local_timezone"]
    ts=pd.Timestamp(origin); ts=ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC"); local=ts.tz_convert(tz); weekend=int(local.dayofweek>=5); hb=_hour_bin(local.hour,bins)
    lib=_prepare_library(mark,tz,bins); sub=lib[(lib.weekend==weekend)&(lib.hour_bin==hb)]
    if len(sub)<int(cfg["scenarios"]["minimum_positive_marks_per_stratum"]): sub=lib[lib.weekend==weekend]
    if sub.empty: sub=lib
    value_col="gpu_hours_per_job" if "gpu_hours_per_job" in sub else ("gpu_hours" if "gpu_hours" in sub else ("flexible_gpu_hours" if "flexible_gpu_hours" in sub else "mark_gpu_hours"))
    site_col="idc_id" if "idc_id" in sub else "origin_idc_id"
    lam=np.array([float(hazard_row[f"lambda_step_{k:02d}"]) for k in range(1,int(cfg["analysis"]["trajectory_steps"])+1)])
    rows=[]
    vals=sub[value_col].to_numpy(float); sites=sub[site_col].astype(str).to_numpy(); weights=sub.sampling_weight.to_numpy(float) if "sampling_weight" in sub else np.ones(len(sub),dtype=float); weights=np.maximum(weights,0); weights=weights/weights.sum()
    for s in range(n_scenarios):
        counts=rng.poisson(lam)
        for step,c in enumerate(counts,1):
            if c:
                idx=rng.choice(len(sub),size=int(c),replace=True,p=weights); vv=vals[idx]; ss=sites[idx]
                alloc=pd.DataFrame({"idc_id":ss,"gpu_hours":vv}).groupby("idc_id").gpu_hours.sum(); text=";".join(f"{k}:{v:.6f}" for k,v in alloc.items()); total=float(vv.sum())
            else: text=""; total=0.0
            rows.append({"origin_timestamp_utc":ts,"origin_hour_bin":hb,"origin_weekend":weekend,"scenario_id":s,"horizon_step":step,"event_count":int(c),"flexible_gpu_hours":total,"idc_allocations":text})
    return pd.DataFrame(rows)

def representative(hazard,mark,cfg):
    bins=list(map(int,cfg["scenarios"]["representative_hour_bins"])); hz=hazard.copy(); hz["timestamp_utc"]=pd.to_datetime(hz.timestamp_utc,utc=True); local=hz.timestamp_utc.dt.tz_convert(cfg["analysis"]["local_timezone"]); hz["weekend"]=(local.dt.dayofweek>=5).astype(int); hz["hour_bin"]=[_hour_bin(int(h),bins) for h in local.dt.hour]
    rows=[]
    for (weekend,hb),g in hz.groupby(["weekend","hour_bin"]):
        row=g.iloc[len(g)//2]
        rows.append(generate_for_origin(row,mark,row.timestamp_utc,int(cfg["scenarios"]["representative_scenarios_per_stratum"]),cfg,seed=int(cfg["scenarios"]["random_seed"])+len(rows)))
    return pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()

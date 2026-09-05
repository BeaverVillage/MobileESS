"""Date-generic V39G grid loader; no production or V39G files are modified."""
from dataclasses import fields
from datetime import datetime,timedelta
import os
import json
from pathlib import Path
from types import FunctionType,SimpleNamespace
import numpy as np
import pandas as pd
from dayahead.tools.v39g_shadow_grid import sha,load_coefficients,inequalities,evaluate

def prepare_grid(repo,out,day):
    from dayahead.v28r2.electrical_context import source_root,portable_background_paths
    from dayahead.v28r2.source_cache import day_root
    from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
    from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
    from dayahead import grid_background_v16_2 as bg
    from dayahead.v37r3.voltage_authority import joint_repaired_coefficients
    from dayahead.v28r2.electrical_subproblem import SlotCoefficients
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v39d.evaluate import _load_capacity
    repo,out=repo.resolve(),out.resolve()
    source=source_root(SOURCE_DATA_REPOSITORY)
    cache=repo/f"dayahead/cache/v37_may_locked_final/electrical/{day}/data"
    vp=cache/f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz";ip=cache/f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz"
    forecast_path=day_root(SOURCE_DATA_REPOSITORY,day)/"aemo_forecast.json"
    weather_path=day_root(SOURCE_DATA_REPOSITORY,day)/"gfs_d1_weather.parquet"
    forecast=json.loads(forecast_path.read_text(encoding="utf-8"));weather=pd.read_parquet(weather_path)
    cutoff=(datetime.fromisoformat(day)-timedelta(hours=6)).isoformat(timespec="minutes")
    assert str(forecast["cutoff_fixed_aest"]).startswith(cutoff)
    source_hashes={str(p):sha(p) for p in (vp,ip,forecast_path,weather_path)}
    paths=portable_background_paths(SOURCE_DATA_REPOSITORY,source)
    def verify_numeric_inputs(p):
        records={}
        for name,expected in bg.EXPECTED_SHA256.items():
            if name=="pv_reference":
                records[name]={"sha256":expected,"status":"FROZEN_PROVENANCE_ONLY_NOT_OPENED"};continue
            path=getattr(p,name);actual=sha(path)
            if actual!=expected:raise RuntimeError(f"BACKGROUND_AUTHORITY_SHA:{name}")
            source_hashes[str(path)]=actual;records[name]={"path":str(path),"sha256":actual,"status":"PASS"}
        return records
    ns=dict(bg.build_authority_background_binding.__globals__);ns["_verify_sources"]=verify_numeric_inputs
    build_bg=FunctionType(bg.build_authority_background_binding.__code__,ns)
    background=build_bg(timestamps_fixed_aest=forecast["timestamps_96"],demand_mw_96=forecast["demand_mw_96"],rooftop_pv_mw_96=forecast["pv_mw_96"],paths=paths)
    old=Path.cwd();voltage=np.load(vp,allow_pickle=False);current=np.load(ip,allow_pickle=False)
    try:
        anchor=np.asarray(voltage["anchor_control"])
        assert anchor.shape==(96,60) and not np.count_nonzero(anchor[:,12:])
        pcc=SOURCE_DATA_REPOSITORY/"dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss";source_hashes[str(pcc)]=sha(pcc)
        binding=build_full_grid_binding(assets=source/"opendss_assets",contract=source/"power_v70_p4f_contract",
            demand_mw_96=forecast["demand_mw_96"],rooftop_pv_mw_96=forecast["pv_mw_96"],aidc_plan_kw_96x12=anchor[:,:12],pcc_asset=pcc,background_binding=background)
        electrical=SimpleNamespace(legacy_context=(None,forecast,background,binding,vp,None),voltage=voltage,current=current,voltage_path=vp)
        cs=joint_repaired_coefficients(repo,electrical)
        data={f.name:np.asarray([getattr(c,f.name) for c in cs]) for f in fields(SlotCoefficients) if f.name!="transformer_ratings"}
        data["transformer_ratings"]=np.asarray([[np.nan if r is None else r for r in c.transformer_ratings] for c in cs])
        data["node_names"]=np.asarray(voltage["node_names"]);data["anchor_v_squared"]=np.asarray(voltage["anchor_v_squared"])
        # Original filenames are retained ONLY inside each V39H day's isolated
        # cache to reuse the frozen V39G load_coefficients implementation.
        np.savez_compressed(out/"V39G_FROZEN_GRID_COEFFICIENTS.npz",**data)
        topology=dict(binding.topology_evidence)
        for parent in (source/"opendss_assets",source/"power_v70_p4f_contract"):
            for p in parent.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".dss",".csv",".json"):source_hashes[str(p)]=sha(p)
    finally:voltage.close();current.close();os.chdir(old)
    capacity,_=_load_capacity(repo);c1path=repo/"dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
    source_hashes[str(c1path)]=sha(c1path);c1=load_c1(c1path);tables={}
    for site,cap in capacity.site_capacity.items():
        it=np.asarray([float(site_it_power_kw(cap,g)) for g in range(cap+1)])
        tables[site]=np.asarray([exact_c1_pcc_kw(it,float(r.t_wb_c),float(r.rh_pct),c1) for r in weather.itertuples(index=False)])
    np.savez_compressed(out/"V39G_C1_INTEGER_TABLES.npz",**tables)
    return {"day":day,"D1_cutoff":cutoff,"source_SHA256":source_hashes,"topology":topology,
        "candidate_OpenDSS_solves":0,"Actual_reads":0,"Fresh_calls":0,"raw_annual_PV_measurement_archive_opened":False,
        "coefficient_sha256_by_slot":[c.coefficient_sha256 for c in cs],"C1_exact_integer_tables":True}

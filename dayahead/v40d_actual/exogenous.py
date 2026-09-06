"""Post-freeze readers using the already audited actual-data alignment rules."""
from pathlib import Path
import pandas as pd
import numpy as np
from dayahead.paper_analysis.storage import read, sha
from .contracts import ReplayError


def load(repo, day):
    from dayahead.tools.audit_v40d_actual_replay import archive_rows, AEST
    root = Path(repo)/"dayahead/artifacts/v40d_actual_realized_replay"
    aemo = read(root/"V40D_AEMO_COMPLETENESS.json")
    start = pd.Timestamp(day, tz=AEST)
    end = start+pd.Timedelta(days=1)
    values = {}
    for kind, ts, col in (("demand","SETTLEMENTDATE","TOTALDEMAND"),("pv","INTERVAL_DATETIME","POWER")):
        authority = aemo[kind]["source"]
        if sha(authority["path"]) != authority["sha256"]:
            raise ReplayError("ACTUAL_AEMO_AUTHORITY_DRIFT")
        records = [r for r in archive_rows(Path(authority["path"])) if r.get("REGIONID")=="VIC1" and ts in r and (kind!="pv" or r.get("TYPE")=="MEASUREMENT")]
        f = pd.DataFrame(records)
        time = pd.to_datetime(f[ts],format="%Y/%m/%d %H:%M:%S").dt.tz_localize(AEST)
        s = pd.Series(pd.to_numeric(f[col]).to_numpy(), index=time)
        axis = pd.date_range(start+pd.Timedelta(minutes=15 if kind=="demand" else 30),end,freq="15min" if kind=="demand" else "30min")
        selected = s[(s.index>start)&(s.index<=end)]
        if selected.index.duplicated().any():
            raise ReplayError("ACTUAL_AEMO_DUPLICATE_INTERVAL")
        v = selected.reindex(axis).to_numpy(float)
        values[kind] = v if kind=="demand" else np.repeat(v,2)
        if values[kind].shape != (96,) or not np.isfinite(values[kind]).all():
            raise ReplayError("ACTUAL_AEMO_INCOMPLETE")
    weather_ref = read(root/"V40D_WEATHER_COMPLETENESS.json")["derived"]
    if sha(weather_ref["path"]) != weather_ref["sha256"]:
        raise ReplayError("ACTUAL_OBSERVED_WEATHER_DRIFT")
    f = pd.read_parquet(weather_ref["path"])
    f.index = pd.DatetimeIndex(f.ts).tz_convert(AEST)
    numeric = f.drop(columns="ts").select_dtypes(include="number")
    target = pd.date_range(start,periods=96,freq="15min")
    weather = numeric.reindex(numeric.index.union(target)).sort_index().interpolate(method="time").reindex(target)
    if not np.isfinite(weather[["t_wb_c","rh_pct"]].to_numpy()).all():
        raise ReplayError("ACTUAL_WEATHER_INCOMPLETE")
    return {"demand_mw": values["demand"], "pv_mw": values["pv"], "weather": weather,
        "timestamps": [t.isoformat() for t in target], "authority": {"demand": aemo["demand"]["source"],
        "pv": aemo["pv"]["source"], "weather": weather_ref}, "role": "ACTUAL_ONLY_AFTER_FROZEN_DECISION_VERIFICATION"}

"""Same-time measured altimeter fallback; no temporal fill or stale-age relaxation."""
from pathlib import Path
from copy import deepcopy
import math,importlib.util
import numpy as np
from v44.common import read,record,verify,atomic,now
from v44_recovery_r029.weather import loader as original_loader

HOME=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign005_may08_14/OPERATIONS/R049_MAY23_WEATHER')
SUPPLEMENT=HOME/'SAME_TIME_OBSERVATIONS.json'
RAW=Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터/NOAANCEI Global Hourly/4384652.csv')
BASE=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v24t_thermal_aware_aidc')
PSYCH=Path(__file__).with_name('psychrometrics.py')
TARGETS=('2025-05-22T15:00:00+00:00','2025-05-22T16:00:00+00:00')
FORMULA_URL='https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.altimeter_to_station_pressure.html'


def station_pressure_hpa(altimeter,elevation):
    """Smithsonian 1951 altimeter inversion, standard atmosphere, hPa/metres.

    The same equation/constants are documented and implemented by MetPy 1.7.1.
    A derived station pressure is labelled derived, never a direct observation.
    """
    if not all(math.isfinite(float(x)) for x in (altimeter,elevation)) or not 800<=altimeter<=1100 or not 0<=elevation<=3000:
        raise ValueError('R049_FINITE_PHYSICAL_ALTIMETER_AND_ELEVATION_REQUIRED')
    n=287.04749097718457*.0065/9.80665
    return (altimeter**n-1013.25**n*.0065*elevation/288.)**(1./n)+.3


def psychrometrics():
    spec=importlib.util.spec_from_file_location('r049_original_psychrometrics',PSYCH)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def build():
    import pandas as pd
    from datetime import datetime
    HOME.mkdir(exist_ok=True);assert not SUPPLEMENT.exists()
    meta=read(BASE/'V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json');raw_record=record(RAW)
    assert raw_record['sha256']==meta['sha256'] and meta['station_id']=='94866099999' and meta['elevation_m']==132.28
    raw=pd.read_csv(RAW,low_memory=False);raw['timestamp']=pd.to_datetime(raw['DATE'],utc=True)
    parquet=BASE/'V24T_MELBOURNE_ACTUAL_WEATHER_HOURLY.parquet';original=record(parquet);frame=pd.read_parquet(parquet)
    psycho=psychrometrics();finite=frame[['t_db_c','rh_pct','pressure_pa','t_wb_c']].notna().all(axis=1)
    replay=psycho.wet_bulb_temperature_c(frame.loc[finite,'t_db_c'],frame.loc[finite,'rh_pct'],frame.loc[finite,'pressure_pa'])
    error=float(np.max(abs(replay-frame.loc[finite,'t_wb_c'].to_numpy())))
    assert error==0.,'ORIGINAL_PSYCHROMETRIC_SOURCE_NOT_BYTE_EQUIVALENT'
    rows=[];details=[]
    for iso in TARGETS:
        timestamp=pd.Timestamp(iso);matches=raw[raw.timestamp==timestamp];old=frame[frame.ts==timestamp].iloc[0]
        assert not np.isfinite(old['t_wb_c']) and not np.isfinite(old['pressure_pa'])
        accepted=[]
        for index,r in matches.iterrows():
            ma=str(r['MA1']).split(',');tmp=str(r['TMP']).split(',');dew=str(r['DEW']).split(',')
            if str(r['STATION'])!='94866099999' or float(r['ELEVATION'])!=132.28:raise ValueError('R049_WRONG_STATION')
            if len(ma)!=4 or ma[0]=='99999' or ma[1] not in '0145' or tmp[1] not in '0145' or dew[1] not in '0145':continue
            t=float(tmp[0])/10;td=float(dew[0])/10;alt=float(ma[0])/10
            accepted.append((int(index),t,td,alt,str(r['REPORT_TYPE']),str(r.get('REM',''))))
        assert accepted and len({r[1:4] for r in accepted})==1,'R049_MISSING_OR_CONFLICTING_SOURCE'
        index,t,td,alt,kind,remark=accepted[0]
        assert (t,td,alt)==(float(old.t_db_c),float(old.t_dew_c),float(old.altimeter_hpa))
        rh=float(psycho.relative_humidity_from_dewpoint(t,td));assert abs(rh-float(old.rh_pct))<1e-12
        pressure=station_pressure_hpa(alt,132.28);wet=float(psycho.wet_bulb_temperature_c(t,rh,pressure*100))
        assert td<=wet<=t and math.isfinite(wet)
        rows.append(dict(observed_seconds=timestamp.timestamp(),available_seconds=timestamp.timestamp(),
            values=dict(t_wb_c=wet,rh_pct=rh),source=raw_record,source_row=index,
            pressure_source='DERIVED_FROM_MEASURED_MA1_ALTIMETER_AND_SOURCE_STATION_ELEVATION',
            derived_station_pressure_hpa=pressure,station_pressure_directly_observed=False,
            measured_altimeter_hpa=alt,station_elevation_m=132.28,source_timestamp=iso,
            temporal_interpolation=False,future_observations_read=False))
        details.append(dict(timestamp=iso,raw_row=index,matching_raw_rows=[r[0] for r in accepted],report_type=kind,
            original_MA1=str(matches.loc[index,'MA1']),original_TMP=str(matches.loc[index,'TMP']),original_DEW=str(matches.loc[index,'DEW']),
            original_METAR=remark,pressure_hpa=pressure,rh_pct=rh,wet_bulb_c=wet,dry_bulb_c=t,dewpoint_c=td))
    result=dict(PASS=True,UTC=now(),day='2025-05-23',rows=rows,details=details,
        sources=[raw_record,original,record(BASE/'V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json'),record(PSYCH)],
        original_finite_wet_bulb_replay_count=int(finite.sum()),original_finite_replay_max_abs_error=error,
        station_pressure_assumption='Standard-atmosphere altimeter inversion; derived value, not a direct station-pressure observation',
        formula_reference=FORMULA_URL,original_parquet_modified=False,max_staleness_seconds=7200,Native_calls=0)
    atomic(SUPPLEMENT,result);assert record(parquet)==original;return result


def loader(output=None):
    base=original_loader(output)
    def load(*,begin,end,bundle):
        obs=base(begin=begin,end=end,bundle=bundle)
        if Path(bundle).name!='DAY_20250523':return obs
        supplement=read(SUPPLEMENT);verify(supplement['sources']);assert supplement['PASS']
        from v43_actual.vendor.current_ac_admission import CausalSeries,CausalObservations
        rows=deepcopy(list(obs.weather._CausalSeries__rows));before={r['observed_seconds'] for r in rows}
        for row in supplement['rows']:
            assert row['observed_seconds'] not in before and row['observed_seconds']==row['available_seconds']
            rows.append(deepcopy(row))
        weather=CausalSeries(rows,name='weather');assert weather.max_staleness_seconds==7200
        return CausalObservations(obs.demand,obs.pv,weather,sources=obs.sources+[record(SUPPLEMENT)])
    return load

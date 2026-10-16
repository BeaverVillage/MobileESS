"""Recover cutoff-admissible GFS bytes, retaining the original decoder/C1 inputs.

This is an input repair only. It does not certify an electrical case, run an
optimizer, modify PR189, or promote a new weather file into an old certificate.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request,urlopen
import hashlib
import sys
from .common import RUNS,DOC,atomic,record,now,read

SOURCE=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
OUT=RUNS.parent/'inputs/weather/2025-05-01_GFS00Z'
CUTOFF=datetime.fromisoformat('2025-04-30T08:00:00+00:00')
INIT=datetime.fromisoformat('2025-04-30T00:00:00+00:00')

def require_available(headers,cutoff=CUTOFF):
    stamp=headers.get('Last-Modified')
    if not stamp or parsedate_to_datetime(stamp)>cutoff:
        raise ValueError('GFS_OBJECT_NOT_AVAILABLE_BY_CUTOFF')
    if not headers.get('ETag'):raise ValueError('GFS_OBJECT_ETAG_REQUIRED')
    return stamp

def run():
    import numpy as np
    import pandas as pd
    sys.path.append('D:/MobileESS_V43/dependencies')
    sys.path.insert(0,str(SOURCE))
    from dayahead.thermal.gfs_idx import parse_idx,select_messages
    from dayahead.thermal.contracts import GFS_VARIABLES
    from dayahead.thermal.gfs_decode import decode_nearest
    from dayahead.thermal.psychrometrics import relative_humidity_from_dewpoint,wet_bulb_temperature_c
    if (OUT/'REPAIR_SOURCE_MANIFEST.json').exists():raise PermissionError('WEATHER_REPAIR_ALREADY_COMPLETE_VERIFY_BEFORE_REUSE')
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[];records=[]
    source_files=[record(SOURCE/'dayahead/thermal'/n) for n in ('gfs_idx.py','gfs_decode.py','psychrometrics.py','contracts.py')]
    atomic(OUT/'START.json',dict(UTC=now(),Native_calls=0,initialization_UTC=INIT.isoformat(),cutoff_UTC=CUTOFF.isoformat(),sources=source_files))
    for lead in range(14,39):
        url=f'https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20250430/00/atmos/gfs.t00z.pgrb2.0p25.f{lead:03d}'
        with urlopen(Request(url,method='HEAD'),timeout=40) as response:head=dict(response.headers.items())
        require_available(head)
        with urlopen(url+'.idx',timeout=40) as response:idx=response.read()
        folder=OUT/f'f{lead:03d}';folder.mkdir(exist_ok=True)
        (folder/'index.idx').write_bytes(idx)
        messages=select_messages(parse_idx(idx.decode(),int(head['Content-Length'])),GFS_VARIABLES)
        decoded={}
        for variable in GFS_VARIABLES:
            message=messages[variable];path=folder/(variable+'.grib2');receipt=folder/(variable+'.json')
            if path.exists() and receipt.exists():
                prior=read(receipt)
                if prior['object_ETag']!=head['ETag'] or prior['file']!=record(path):raise ValueError('RESUMED_GFS_BYTES_DRIFT')
                content=path.read_bytes();item=prior
            else:
                with urlopen(Request(url,headers={'Range':message.range_header,'Accept-Encoding':'identity'}),timeout=90) as response:
                    if response.status!=206:raise ValueError('GFS_RANGE_RESPONSE_REQUIRED')
                    content=response.read();returned=dict(response.headers.items())
                if len(content)!=message.byte_count or returned.get('ETag')!=head['ETag']:
                    raise ValueError('GFS_RANGE_SIZE_OR_ETAG_DRIFT')
                if returned.get('Content-Range') != f'bytes {message.start}-{message.end}/{head["Content-Length"]}':
                    raise ValueError('GFS_EXACT_CONTENT_RANGE_REQUIRED')
                require_available(returned)
                path.write_bytes(content)
                item=dict(variable=variable,lead_hours=lead,initialization_UTC=INIT.isoformat(),url=url,
                    byte_range=message.range_header,object_ETag=head['ETag'],Last_Modified=head['Last-Modified'],
                    available_before_cutoff=True,file=record(path),idx=record(folder/'index.idx'),full_GRIB_download=False)
                atomic(receipt,item)
            value=decode_nearest(content,-37.6655,144.8321)
            decoded[variable]=value;records.append(item)
        rows.append(dict(initialization_utc=pd.Timestamp(INIT),lead_hours=lead,
            valid_time_utc=pd.Timestamp(INIT)+pd.Timedelta(hours=lead),
            t_db_c=decoded['TMP']['value']-273.15,t_dew_c=decoded['DPT']['value']-273.15,
            rh_pct_raw=decoded['RH']['value'],pressure_pa=decoded['PRES']['value'],
            u10_mps=decoded['UGRD']['value'],v10_mps=decoded['VGRD']['value'],
            grid_latitude=decoded['TMP']['grid_latitude'],grid_longitude=decoded['TMP']['grid_longitude'],
            distance_km=decoded['TMP']['distance_km']))
        atomic(OUT/'PROGRESS.json',dict(UTC=now(),lead_complete=lead,leads_required=25,records=len(records),Native_calls=0))
        print('GFS00Z',lead,'complete',flush=True)
    hourly=pd.DataFrame(rows).sort_values('valid_time_utc')
    hourly['rh_pct']=relative_humidity_from_dewpoint(hourly['t_db_c'],hourly['t_dew_c'])
    hourly['wind_speed_mps']=np.hypot(hourly['u10_mps'],hourly['v10_mps'])
    hourly['t_wb_c']=wet_bulb_temperature_c(hourly['t_db_c'],hourly['rh_pct'],hourly['pressure_pa'])
    index=pd.DatetimeIndex(hourly['valid_time_utc']).tz_convert('Etc/GMT-10');hourly.index=index
    target=pd.date_range('2025-05-01',periods=96,freq='15min',tz='Etc/GMT-10')
    forcing=hourly.drop(columns=['initialization_utc','valid_time_utc']).reindex(index.union(target)).sort_index().interpolate(method='time').reindex(target)
    forcing.insert(0,'ts_fixed_aest',target)
    if len(forcing)!=96 or forcing.isna().any().any():raise ValueError('GFS_REPAIR_FINITE_96_AXIS_REQUIRED')
    path=OUT/'gfs_d1_weather.parquet';forcing.to_parquet(path,index=False)
    manifest=dict(status='SOURCE_BYTES_RECOVERED_ELECTRICAL_CASE_NOT_GENERATED',UTC=now(),Native_calls=0,
        day='2025-05-01',initialization_UTC=INIT.isoformat(),cutoff_UTC=CUTOFF.isoformat(),
        records=records,weather=record(path),decoder_sources=source_files,record_count=len(records),
        every_used_object_preexisting_by_cutoff=True,full_GRIB_downloads=0,old_input_bytes_changed=False,
        old_electrical_certificate_reused_for_repaired_weather=False,original_case_UB_LB_transferred=False,
        next_step='Regenerate C1/B0 anchor and original electrical sensitivities under independent V43 source/case freeze; preserve PR189 AIDC math and policy.')
    atomic(OUT/'REPAIR_SOURCE_MANIFEST.json',manifest)
    atomic(DOC/'CAUSAL_WEATHER_REPAIR_SOURCE.json',dict(manifest=record(OUT/'REPAIR_SOURCE_MANIFEST.json'),
        status=manifest['status'],weather=manifest['weather'],Native_calls=0))
    print('SOURCE_RECOVERY_COMPLETE',path,flush=True)

if __name__=='__main__':run()

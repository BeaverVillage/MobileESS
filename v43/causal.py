"""Native=0 independent checks against the original PR189 input loaders."""
from datetime import datetime, timedelta, timezone
import pandas as pd
from .common import *

def check(request,output):
    from v42_pr134_b1.native import bind
    from v42_integrated.contract import physical_authority
    from v42_may_campaign_native90.bindings import check_a_cells,check_coefficients,check_forecast
    from v42_may_campaign_native90.preflight import native_zero
    folder=Path(request['input_folder']); output=Path(output); output.mkdir(parents=True,exist_ok=False)
    b=read(folder/'NATIVE_INPUT.json');operations=read(folder/'OPERATIONS.json')
    identity=read(folder/'INPUT_IDENTITY.json')
    verify_records([identity[k] for k in ('bundle','windows','operations')])
    issue=datetime.fromisoformat(b['issue_time'])
    midnight=datetime.fromisoformat(b['day']).replace(tzinfo=timezone(timedelta(hours=10)))
    assert issue==midnight-timedelta(hours=6)
    for r in b['known_population']:
        assert r['known_at_issue'] and datetime.fromisoformat(r['submit_time'])<=issue
    aemo=operations['forecast_inputs']['AEMO']
    assert datetime.fromisoformat(aemo['cutoff_fixed_aest'])==issue
    assert datetime.fromisoformat(aemo['demand_issue'])<=issue
    assert datetime.fromisoformat(aemo['pv_issue'])<=issue
    verify_records([b['electrical_certificate']])
    with native_zero() as attempts,physical_authority():
        data,_,coeff,*_=bind(b,folder,output)
        cells=check_a_cells(b,read(folder/'WINDOWS.json'),data.load_native())
        certificate=read(b['electrical_certificate']['path'])
        electrical=check_coefficients(b['day'],certificate,coeff)
        forecast=check_forecast(b,operations,ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv')
    assert not attempts
    weather=certificate['input_identity']['identity']['inputs']['weather']
    path=Path(weather['path'])
    if not path.exists():
        recovery=read(ROOT/'docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json')['recovered']
        choices=[r['resolved'] for r in recovery if r['original']==str(path)]
        assert choices and all(r['sha256']==weather['sha256'] for r in choices)
        path=Path(choices[0]['path'])
    assert sha(path)==weather['sha256']
    frame=pd.read_parquet(path)
    meta=dict(columns=list(frame.columns),attrs=frame.attrs,source=record(path))
    # Forecast arrays and byte identity are proven here. Their original GFS
    # publication evidence is recorded separately; absence never becomes PASS.
    result=dict(PASS=True,Native_calls=0,known=cells,electrical=electrical,forecast=forecast,
        AEMO_issue_before_cutoff=True,weather=meta,weather_publication_cutoff='PENDING_SOURCE_METADATA_AUDIT',
        complete_causal_certification=False,output_role='ORIGINAL_INPUT_LOADER_VERIFICATION')
    atomic(output/'CAUSAL_INPUT_AUDIT.json',result)
    return result

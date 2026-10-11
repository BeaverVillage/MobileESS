"""Read-only all-31-day issue/roster/provenance audit without Native calls."""
from pathlib import Path
from datetime import datetime
import sys,json
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from tools import b1_only_v4 as b

def audit():
    root=b.DEFAULT_ROOT;m=b.verify_only(root);rows=[];checked={}
    def check(ref):
        if ref['path'] not in checked:checked[ref['path']]=b.record(ref['path'])
        actual=checked[ref['path']]
        assert Path(ref['path']).resolve()==Path(actual['path']).resolve()
        assert all(actual[k]==v for k,v in ref.items() if k in ('bytes','sha256'))
    for day in b.DAYS:
        raw=root/'raw'/day;n=b.read(raw/'NATIVE_INPUT_TEMPLATE_B1.json');p=b.read(raw/'PLANNING_INPUT_BUNDLE.json')
        ops=b.read(raw/'OPERATIONS_TEMPLATE_B1.json');prov=b.read(raw/'SOURCE_PROVENANCE.json')
        assert n['day']==p['day']==day and p['future_actual_arrival_IDs_present'] is False
        assert p['primary_voltage_band_pu']==[.95,1.05]
        cutoff=datetime.fromisoformat(p['issue_time']);assert datetime.fromisoformat(n['issue_time'])==cutoff
        forecast=ops['forecast_inputs']['AEMO']
        assert forecast==p['forecast_inputs']['AEMO']
        assert datetime.fromisoformat(forecast['cutoff_fixed_aest'])==cutoff
        assert all(datetime.fromisoformat(forecast[k])<=cutoff for k in ('demand_issue','pv_issue'))
        assert len(forecast['timestamps_96'])==len(forecast['demand_mw_96'])==len(forecast['pv_mw_96'])==96
        for job in n['known_population']:
            assert job['known_at_issue'] is True and datetime.fromisoformat(job['issue_time'])==cutoff
            assert datetime.fromisoformat(job['submit_time'])<=cutoff
            assert job['state'] in ('RUNNING','PENDING')
            assert not {'actual_runtime','end_time','actual_remaining','voltage','line_loading'} & job.keys()
        assert prov['Actual_observations_loaded'] is False and prov['Actual_voltage_read'] is False
        assert not {'end_time','actual_runtime','actual_remaining'} & set(prov['snapshot_columns'])
        check(prov['snapshot'])
        for name in ('aemo_forecast.json','gfs_d1_weather.parquet'):check(prov['daily_sources'][name])
        rows.append(dict(day=day,PASS=True,cutoff=cutoff.isoformat(),known_job_count=len(n['known_population']),
            Forecast=b.record(raw/'PLANNING_INPUT_BUNDLE.json'),known_jobs=b.record(raw/'NATIVE_INPUT_TEMPLATE_B1.json'),
            physical_Gpu_Rack_WAN_Runtime_authority=b.digest({k:n.get(k) for k in ('capacities','racks','WAN','C0_binding','C0_Q50','C0_Q90','CC4_reserve_GPU','runtime_reserve_gamma','runtime_survival_kernel','runtime_provider')})))
    receipt=dict(PASS=True,days=rows,causal_issue_and_no_future_actual_ids=True,
        external_forecast_and_snapshot_sources=list(checked.values()),Native_calls=0,inputs_modified=0,source_SHA=m['execution_SHA'],UTC=b.now())
    b.atomic(root/'ALL31_CAUSAL_INPUT_AUDIT.json',receipt)
    print(json.dumps(dict(PASS=True,days=len(rows),external_sources=len(checked),Native_calls=0)))

if __name__=='__main__':audit()

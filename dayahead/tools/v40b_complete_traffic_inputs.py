"""Materialize previously unvisited days through the unchanged D-1 traffic authority."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from concurrent.futures import ProcessPoolExecutor,as_completed

def one(day):
    from dayahead.v35.execution import daily_traffic_authority
    from dayahead.v35.contracts import PHASE_MAY
    from dayahead.v37.runner import ADMISSION
    cache=REPO/'dayahead/cache/v37_may_locked_final/traffic'
    bundle,graph,route,files=daily_traffic_authority(REPO,cache,PHASE_MAY,day,ADMISSION)
    assert bundle.causality_pass and not bundle.future_actual_read_count and bundle.max_input_timestamp<=bundle.issue_time
    return {'day':day,'status':'PASS','forecast_SHA':bundle.canonical_sha256,'route_SHA':route.canonical_sha256,
       'model_SHA':bundle.model_sha,'issue_time':bundle.issue_time.isoformat(),'max_input_timestamp':bundle.max_input_timestamp.isoformat(),'files':list(files)}

def main():
    missing=[d for d in DAYS if not (REPO/'dayahead/cache/v37_may_locked_final/traffic/shared/traffic'/d/'ROUTE_TABLE.json.gz').exists()]
    rows=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,d) for d in missing]):
            row=future.result();rows.append(row);print(row['day'],'D1_TRAFFIC_PASS',flush=True)
            write(ROOT/'V40B_ADDITIONAL_D1_TRAFFIC_INPUTS.json',{'status':'PASS' if len(rows)==len(missing) else 'RUNNING',
              'method_changed':False,'result_based_tuning':False,'reason':'Original stopped campaign had not visited May20-31; build only missing D-1 inputs with frozen traffic model',
              'rows':rows,'original_copy_manifest_modified':False})

if __name__=='__main__':main()

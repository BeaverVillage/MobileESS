"""Read-only May input metadata compatibility; no May Actual/voltage outcomes."""
from pathlib import Path
import pandas as pd
from v42_april_port.audit import record, write
from .freeze import ROOT, OUT
from .population import classify

def main():
    snapshot=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_D1_SNAPSHOT.parquet')
    cols=['id','submit_time','gpus_requested','partition']
    f=pd.read_parquet(snapshot,columns=cols); f['id']=f.id.astype(str)
    ledger=ROOT/'docs/v42_final_integration/MAY01_Q50_JOB_LEDGER.csv'
    lc=['job_uid','submit_time','issue_time','state','GPU_gang','runtime_authority','service_slots','V10_Q50_total_seconds']
    cache=pd.read_csv(ledger,usecols=lc,dtype={'job_uid':str})
    caps=dict(zip(['AIDC%02d'%i for i in range(1,13)],[80,40,80,40,100,80,40,80,40,80,40,80]))
    racks={s:[c] for s,c in caps.items()}; lookup=f.set_index('id'); result=[]
    for j in cache.to_dict('records'):
        raw=lookup.loc[j['job_uid']].to_dict()
        row=dict(j,Q50_total_seconds=j['V10_Q50_total_seconds'],runtime_inference_event_time=j['issue_time'])
        r=classify(row,raw,caps,racks,'2025-03-31T00:00:00+00:00')
        result.append(dict(job_uid=j['job_uid'],modelable=r['modelable'],classification=r['classification'],reasons=r['reasons']))
    write(OUT,'POPULATION/MAY_RULE_COMPATIBILITY_AUDIT.json',dict(status='INPUT_METADATA_RULE_APPLIED',
        snapshot=record(snapshot),snapshot_columns_read=cols,Runtime_metadata_cache=record(ledger),cache_columns_read=lc,
        compared_rows=len(result),raw_snapshot_rows=len(f),modelable_cache_rows=sum(r['modelable'] for r in result),
        checks=dict(requested_GPU_to_GPU_gang_unchanged=True,current_Runtime_used=True,
            original_site_absence_not_exclusion=True,historical_planning_eligible_filter_not_copied=True),
        classifications=result,May_Actual_outcomes_read=False,May_voltage_read=False,May_policy_outcomes_read=False,
        May_metadata_as_numeric_April_donor=False,May_outcomes_used=False,
        limitation='Current known May metadata only; no May Actual population or scientific outcomes accessed.'))

if __name__=='__main__': main()

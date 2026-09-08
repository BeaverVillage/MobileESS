"""Read-back audit of the uniform prospective Q90 baseline for every May day."""
from pathlib import Path
import json,time
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json,digest
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.reserve import require


def audit_available():
    from dayahead.v41.snapshot import capacity_authority
    from dayahead.v41.common import build
    from dayahead.v41.persistence import table,verify_table
    from dayahead.v41.scientific_archive import scalar_frame
    from dayahead.v41r1.migration_baseline import CONTRACT
    cap=capacity_authority()[0];progress=read(RUNTIME/'BASELINE_PREPARATION_PROGRESS.json')
    rows=[]
    for n in range(1,32):
        day=f'2025-05-{n:02}'
        if progress['days'].get(day,{}).get('status')!='PASS':
            rows.append(dict(day=day,status='WAITING_FOR_CAUSAL_SNAPSHOT'));continue
        folder=RUNTIME/'inputs'/day;path=folder/f'V41_ML_SNAPSHOT_{day}.json'
        try:
            jobs,seal=build(day,path,cap)
            baseline=read(folder/'common_q90_v3/Q90_BASELINE_MATERIALIZATION.json')
            tables={name:table(folder/'common_q90_v3'/(name+'.parquet'),scalar_frame(baseline[key]))
                for name,key in (('BASELINE_JOBS','rows'),('BASELINE_OCCUPANCY_EVENTS','occupancy_events'))}
            for value in tables.values():verify_table(value)
            require(read(seal['files']['COMMON_B0_REFERENCE_JOBS.json']['path'])==json.loads(json.dumps(jobs)),
                'BASELINE_JOB_READBACK_MISMATCH')
            old=folder/'common/COMMON_B0_REFERENCE_JOBS.json'
            identical=old.exists() and record(old)['sha256']==seal['files']['COMMON_B0_REFERENCE_JOBS.json']['sha256']
            events=verify_table(tables['BASELINE_OCCUPANCY_EVENTS'])
            require((events.GPU<=events.capacity).all() and (events.GPU>=0).all(),'INDEPENDENT_BASELINE_RESOURCE_BOUND')
            rows.append(dict(day=day,status='PASS',changed_start_jobs=baseline['changed_start_jobs'],
                changed_job_ids=[r['job_id'] for r in baseline['rows'] if r['start_delay_slots']],
                changed_pre_D00_starts=sum(r['start_delay_slots']>0 and r['old_start_issue_slot']<24 for r in baseline['rows']),
                shifted_beyond_D24=sum(r['old_start_issue_slot']<120<=r['new_start_issue_slot'] for r in baseline['rows']),
                unadmitted_Q90_overlap_jobs=sum(r['unadmitted_Q90_interval_overlaps_Day_D'] for r in baseline['rows']),
                unadmitted_Q90_overlap_full_backlog_GPUh=sum(r['unadmitted_backlog_GPUh'] for r in baseline['rows'] if r['unadmitted_Q90_interval_overlaps_Day_D']),
                GPU_feasibility='PASS',rack_feasibility='PASS',site_changes=0,admission_changes=0,
                grid_reads=0,Actual_reads=0,snapshot=record(path),common=record(folder/'common_q90_v3/COMMON_INPUT_RECEIPT.json'),
                common_reference_SHA=seal['files']['COMMON_B0_REFERENCE_JOBS.json']['sha256'],
                common_service_SHA=seal['COMMON_DA_DURATION_SHA'],previous_common_byte_identical=identical,
                tables=tables,policies=['B0','B1','B2','B3'],rule_source=seal['baseline_source']))
        except Exception as error:
            rows.append(dict(day=day,status='FAIL',error=repr(error)))
    passed=[r for r in rows if r['status']=='PASS'];failed=[r for r in rows if r['status']=='FAIL']
    result=dict(status='PASS' if len(passed)==31 else 'FAIL' if failed else 'IN_PROGRESS',contract=CONTRACT,
        target_days=31,verified_days=len(passed),failed_days=len(failed),
        affected_days=sum(r['changed_start_jobs']>0 for r in passed),
        changed_job_day_starts=sum(r['changed_start_jobs'] for r in passed),
        changed_unique_job_ids=len({uid for r in passed for uid in r['changed_job_ids']}),days=rows,
        algorithm_sources=[record(ROOT/p) for p in ('dayahead/v41r1/migration_baseline.py','dayahead/v41/common.py',
            'dayahead/v41r1/migration.py','dayahead/v41r1/migration_admission.py','dayahead/v40g_segments/canonical.py',
            'dayahead/v37/aidc_materializer.py','dayahead/v39d/actual.py')],
        superseded_failure=dict(classification='OLD_B0_REFERENCE_INCOMPATIBLE_WITH_FINAL_Q90_RUNTIME',
            evidence=record(OUT/'MAY03_COMMON_REFERENCE_FAILURE_AUDIT.json')),
        B1_B3_reference_identity='Single common file and service SHA per day; B2 reuses B0, B3 reuses accepted B1; no policy-specific baseline',
        entire_campaign_must_wait_for_31_day_PASS=True)
    write_json(OUT/'Q90_BASELINE_31_DAY_AUDIT.json',result)
    print({k:result[k] for k in ('status','verified_days','failed_days','affected_days','changed_job_day_starts')},flush=True)
    return result


if __name__=='__main__':audit_available()

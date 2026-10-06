"""Recover wall measurements with their limitations; do not infer native intervals."""
from v42_m_stage.common import *
import csv
import time

def run():
    with (OUT/'DW_CONTINUATION_RESOURCE_LEDGER.csv').open(encoding='utf8') as f:resources=list(csv.DictReader(f))
    origin=float(resources[0]['perf'])-float(resources[0]['elapsed'])
    cp=read(OUT/'DW_CHECKPOINT_LATEST.json');r=read(OUT/'DW_CONTINUATION_FINAL_RESULT.json')
    r['build_seconds']=None
    r['initial_pool_audit_restore_wall']=read(OUT/'DW_INITIAL_POOL_AUDIT.json')['wall']
    r['initial_prepare_before_first_optimize_wall']=min(a for a,b in cp['optimize_intervals'])-origin
    r['initial_prepare_measurement']='Resource monitor perf-elapsed epoch through first native interval; includes preparation, restored pool and audit; sampling epoch approximation'
    r['elapsed_including_build_audit']=time.perf_counter()-origin
    r['elapsed_measurement']='Continuous root development through report recovery in same perf_counter epoch; includes failure diagnosis and closeout; not production runtime'
    r['historical_PR149_native']=read(OUT/'ROOT1604_RESUME_AUTHORITY.json')['historical_PR149_native']
    r['historical_PR152_native']=read(OUT/'ROOT1604_RESUME_AUTHORITY.json')['historical_PR152_native']
    write('DW_CONTINUATION_FINAL_RESULT.json',r)
    write('ROOT_MEASUREMENT_LIMITATIONS.json',dict(build_only_not_durably_preserved=True,
        initial_prepare_wall=r['initial_prepare_before_first_optimize_wall'],
        measured_root_and_closeout_wall=r['elapsed_including_build_audit'],
        missing_last_RMP_interval_endpoints=True,durable_native_debit_used=True,
        full_native_interval_independent_reconstruction=False,fresh_production_runtime_claimed=False))

if __name__=='__main__':run()

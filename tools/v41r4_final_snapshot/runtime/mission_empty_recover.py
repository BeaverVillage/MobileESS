"""Recover pre-optimization empty migration-table serialization failures."""
import time,shutil
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from v41r4_loop_runtime import MAY_RUN,MAY_OUT,BASE_RUN,BASE_OUT

def main(day):
    phase=MAY_OUT/day/'PHASE_B0_DA.json';base_phase=BASE_OUT/day/'PHASE_B0_DA.json'
    failure=read(phase)
    assert 'DataFrame.columns are different' in failure['error'] and 'inferred_type' in failure['error']
    da=BASE_RUN/day/'B0/dayahead'
    assert not (da/'FROZEN_JOINT_DECISION.json').exists() and not (da/'DAYAHEAD_RECEIPT.json').exists()
    assert not any((MAY_RUN/day/p/'actual/ACTUAL_BOUNDARY_RECEIPT.json').exists() for p in ('B0','B1','B2','B3'))
    saved=MAY_OUT/'mission/EMPTY_TABLE_FAILED_EVIDENCE'/day;saved.mkdir(parents=True,exist_ok=False)
    moves=[(da,saved/'dayahead'),(base_phase,saved/'BASE_PHASE_B0_DA.json'),(phase,saved/'PHASE_B0_DA.json')]
    for src,dst in moves:
        assert src.resolve().is_relative_to(BASE_RUN.resolve()) and dst.resolve().is_relative_to(saved.resolve())
    for src,dst in moves:src.rename(dst)
    shutil.copy2(saved/'PHASE_B0_DA.json',MAY_OUT/'mission'/f'PRESERVED_PHASE_{day}_B0_DA_EMPTY_TABLE_FAILURE.json')
    write_json(saved/'REPAIR.json',dict(status='PRESERVED_FOR_RETRY',reason='Empty (0,0) DataFrame RangeIndex does not roundtrip through Parquet; canonical empty object columns',
        helper=record(ROOT/'mission_empty_table.py'),numerical_values_changed=0,previous_optimization_started=False,at=time.time()))
    from mission_cut_worker import main as worker
    worker(day,'B0_DA')
    assert read(phase)['status']=='PASS'
    write_json(saved/'RECOVERY.json',dict(status='PASS',phase=record(phase),at=time.time()))
if __name__=='__main__':
    import sys
    main(sys.argv[1])

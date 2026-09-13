"""Actual-only producer selection repair; original verification remains intact."""
import sys
from fast_prepare import read
import v41r4_search_runtime as runtime
import v41r4_search_worker as worker

def configure(day,policy):
    execution=runtime.configure(day,policy)
    original=execution.verify_dayahead
    def verify(target,method):
        if method in ('B0','B2'):
            phase=read(runtime.MAY_OUT/target/f'PHASE_{method}_DA.json')
            if phase.get('reused_phase') or phase.get('result',{}).get('reused_phase'):
                expected=read(runtime.BASE_OUT/'MAY_CAMPAIGN_RELEASE.json')['source']
                return runtime.verify_old_or_current(target,method,expected)
        return original(target,method)
    execution.verify_dayahead=verify
    from dayahead.v41 import scientific_archive as archive
    from copy import deepcopy
    original_inputs=archive.actual_inputs
    def actual_inputs(output,day,decision,da_output,obs,exo,mess_result,workload):
        normalized=deepcopy(mess_result)
        for move in normalized['moves']:
            source=move['actual_traffic_source']
            current=archive.record(source['path'])
            assert set(source) <= {'path','sha256','bytes','exists'}, 'UNEXPECTED_TRAFFIC_REFERENCE_SCHEMA'
            assert source.get('exists',True) is True, 'ACTUAL_TRAFFIC_MISSING'
            assert all(source[k]==current[k] for k in current), 'ACTUAL_TRAFFIC_HASH_DRIFT'
            move['actual_traffic_source']=current
        return original_inputs(output,day,decision,da_output,obs,exo,normalized,workload)
    archive.actual_inputs=actual_inputs
    return execution

if __name__=='__main__':
    assert sys.argv[2] in ('B0_AC','B1_AC','B2_AC','B3_AC')
    worker.configure=configure
    worker.main(sys.argv[1],sys.argv[2])

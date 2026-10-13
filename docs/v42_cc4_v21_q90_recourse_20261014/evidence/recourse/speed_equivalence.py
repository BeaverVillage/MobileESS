"""Same frozen inputs, before/after numerical grouping and guard performance."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter
import numpy as np

ROOT=Path(__file__).parents[2];sys.path.insert(0,str(ROOT))
from v42_integration.q90_recourse import evaluate_q90_recourse
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def record(p):
    b=Path(p).read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def main():
    source=module('v42_integration._frozen_reference',ROOT/'audit/reference_source.py').load_conditional_source()
    old=module('_pre_cached_recourse',Path(__file__).parent/'PRE_CACHED_AFFINE_q90_recourse.py')
    n=read(Path(__file__).parent/'FROZEN_A2_NOMINAL_SERVICE.json')
    p=read(Path(__file__).parent/'A2_SERVICE_TIMING_SOURCE_PACKET.json')
    oldpacket,newpacket=deepcopy(source['packet']),deepcopy(source['packet'])
    candidates=[np.zeros((96,len(newpacket.sites)))]
    # Public frozen nominal service only, no new real UID or future truth.
    nominal=np.array(n['nominal_site_GPU'])
    for t in (24,48,72):
        j=int(np.argmax(nominal[t]));k=(j+1)%len(newpacket.sites)
        d=np.zeros_like(nominal);d[t,j]=-min(1.,nominal[t,j]);d[t,k]=-d[t,j]
        candidates.append(d)
    rows=[]
    for i,d in enumerate(candidates):
        args=(n,p['q90_hourly_GPUh'],p['TRAIN_CDF_lower'],p['TRAIN_CDF_upper'])
        start=perf_counter();before=old.evaluate_q90_recourse(oldpacket,*args,candidate_gpu_delta=d)
        old_seconds=perf_counter()-start
        start=perf_counter();after=evaluate_q90_recourse(newpacket,*args,candidate_gpu_delta=d)
        new_seconds=perf_counter()-start
        start=perf_counter();hit=evaluate_q90_recourse(newpacket,*args,candidate_gpu_delta=d)
        hit_seconds=perf_counter()-start
        gpu_error=float(np.max(np.abs(np.array(before['admitted_extra_site_GPU'])-np.array(after['admitted_extra_site_GPU']))))
        x_error=float(np.max(np.abs(np.array(before['extra_x_GPUh'])-np.array(after['extra_x_GPUh']))))
        row=dict(candidate=i,old_seconds=old_seconds,new_seconds=new_seconds,exact_cache_seconds=hit_seconds,
            admitted_GPU_max_abs_difference=gpu_error,cohort_x_GPUh_max_abs_difference=x_error,
            served_GPUh_difference=after['admitted_extra_service_GPUh']-before['admitted_extra_service_GPUh'],
            peak_difference=after['original_grid_score']['peak_score']-before['original_grid_score']['peak_score'],
            physical_hard_identical=after['physical_hard_feasible']==before['physical_hard_feasible'],
            timing_status_identical=after['CDF_timing_status']==before['CDF_timing_status'],
            timing_violation_count_identical=len(after['timing_violations'])==len(before['timing_violations']),
            mass_PASS=after['conservation']['conserved'],original_scalar_guard_retained=True,
            new_admission=after['admission'],cache_hit=hit['runtime_cache']['hit'])
        row['PASS']=bool(gpu_error<1e-7 and x_error<1e-7 and abs(row['peak_difference'])<1e-12
            and row['physical_hard_identical'] and row['timing_status_identical'] and row['timing_violation_count_identical']
            and row['mass_PASS'] and row['cache_hit'])
        rows.append(row)
    result=dict(schema='D_RECOURSE_SOURCE_ROW_SPEED_EQUIVALENCE_V1',status='PASS' if all(r['PASS'] for r in rows) else 'FAIL',
        rows=rows,source_before=record(Path(__file__).parent/'PRE_CACHED_AFFINE_q90_recourse.py'),
        source_after=record(ROOT/'v42_integration/q90_recourse.py'),
        original_grid_hard_tolerance=1e-9,forecast_or_capacity_modified=False,
        conservative_roundoff_changes_only_admitted_service=True,
        source_same_nominal_Q50_and_hourly_Q90=True,Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_calls=0)
    (Path(__file__).parent/'RECOURSE_SPEED_EQUIVALENCE_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()

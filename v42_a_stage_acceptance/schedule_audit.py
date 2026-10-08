"""No-native independent objective reconstruction from original job schedule."""
import sys,gzip,pickle
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import read,record,atomic
from .policy import OUT,OLD

def run(day):
    f=OUT/day;freeze=read(f/'FROZEN_A1.json');selected=freeze['selected_jobs']
    if day=='2025-05-19':
        build=read(OLD/'LEX_FULL_BUILD_VERIFICATION.json')
        with gzip.open(build['state']['path'],'rb') as stream:data=pickle.load(stream)['state']['data']
    else:
        build=read(f/'INITIAL_VERIFICATION.json')
        with gzip.open(build['state']['path'],'rb') as stream:data=pickle.load(stream)['data']
    jobs=data[1]
    if set(jobs)!=set(selected):raise ValueError('ORIGINAL_JOB_POPULATION_CHANGED')
    metrics=dict(migration_count=sum(o['checkpoint']>=0 for o in selected.values()),
        shift_magnitude=sum(abs(o['start']-jobs[uid].reference_start) for uid,o in selected.items()),
        prestart_relocation=sum(o['initial_site']!=jobs[uid].reference_site for uid,o in selected.items()))
    residuals={k:abs(float(Fraction(freeze['exact_objective_values'][k]))-v) for k,v in metrics.items()}
    phys=read(freeze['physical']['path']);rho=phys['physical']['P1_rho']
    passed=phys['PASS'] and max(residuals.values(),default=0)<=1e-5 and rho==freeze['objective_values']['rho']
    if not passed:raise ValueError('INDEPENDENT_ORIGINAL_SCHEDULE_OBJECTIVES_MISMATCH')
    receipt=dict(PASS=True,day=day,original_jobs=len(jobs),schedule_integer_objectives=metrics,
        rho_from_original_physical_replay=rho,raw_affine_objectives=freeze['exact_objective_values'],
        affine_vs_schedule_residual=residuals,inherited_integer_tolerance=1e-5,
        points_rounded_or_clipped=False,original_jobs_and_reference_values_used=True,
        frozen_A1=record(f/'FROZEN_A1.json'),source=record(__file__),native_optimization_calls=0)
    atomic(f/'INDEPENDENT_ORIGINAL_SCHEDULE_OBJECTIVES.json',receipt)
    print('SCHEDULE_OBJECTIVE_AUDIT_PASS',day,metrics,flush=True)
    return receipt
if __name__=='__main__':run(sys.argv[1])

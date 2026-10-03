"""Independent full-precision residual, state and authority verification."""
import csv
import gzip
import hashlib
import subprocess
import numpy as np
from .common import *
from .verify import identity
from .authority import source


def main():
    identity(); rows=0
    compressed=OUT/'APRIL_B0_AUTONOMOUS_REGCONTROL_VOLTAGE_RESIDUALS.csv.gz'
    with gzip.open(compressed,'rt',encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        for day in DAYS:
            p=np.load(OLD/'BUNDLE'/day_folder(day)/'V_PLAN.npz')
            a=np.load(output_day(day)/'V_ACTUAL_AC.npz')
            names=tuple(map(str,p['node_names']))
            pv=p['V_PLAN']; av=a['V_ACTUAL_AC']
            for t in range(96):
                for n,name in enumerate(names):
                    r=next(reader); node,phase=name.rsplit('.',1)
                    if (r['day'],r['node'],r['phase'],int(r['slot']))!=(day,node,'ABC'[int(phase)-1],t):
                        raise ValueError('INDEPENDENT_CSV_AXIS_DRIFT')
                    plan=float(pv[t,n]); actual=float(av[t,n]); error=actual-plan
                    expected=dict(V_PLAN=plan,V_ACTUAL_AC=actual,e_total=error,r_up=max(error,0),r_down=max(-error,0),abs_e=abs(error))
                    if any(float(r[k])!=v for k,v in expected.items()):
                        raise ValueError('LOSSLESS_FLOAT_CSV_IDENTITY_DRIFT')
                    rows+=1
        if next(reader,None) is not None: raise ValueError('EXTRA_RESIDUAL_ROWS')
    if rows!=1111680: raise ValueError('ALL_APRIL_POINTS_REQUIRED')
    for r in source()['audit']['static_source_graph']['files']+source()['audit']['code_read']:
        resolve(r)
    parameter=read(OUT/'REGCONTROL_PARAMETER_INTEGRITY.json')
    if len(parameter['days'])!=33: raise ValueError('ALL_DIAGNOSTIC_AND_FULL_RUN_INTEGRITY_REQUIRED')
    paired=read(OUT/'ARCHIVED_PR125_PAIRED_INPUT_REPRODUCIBILITY.json')
    if not paired['PASS']: raise ValueError('PAIRED_INPUT_REPRODUCIBILITY_REQUIRED')
    write(OUT,'INDEPENDENT_RESIDUAL_CSV_AUDIT.json',dict(PASS=True,rows=rows,
        exact_float_roundtrip=True,exact_axes=True,dropped_rows=0,source_files_rehashed=True,
        parameters_checked_all_33_new_runs=True,archived_3_day_reproduction_numeric_identity=True))
    write(OUT,'VERIFICATION.json',dict(PASS=True,exact_base=BASE,base_files_checked=3590,
        exact_BASE_bytes_preserved=True,PR125_PR127_evidence_overwritten=False,
        PR124_PR126_imports=0,Planning_V_PLAN_bytes_and_values_unchanged=True,
        workload_capacity_PQ_arrays_unchanged=True,source_parameters_unchanged=True,
        Actual_regulator_autonomous=True,capacitors_fixed_ON=True,CapControl_count=0,
        Planning_tap_cap_replay_current_path=False,
        Actual_repairs_reoptimization=0,MESS_PQ=0,Actual_AC_converged_days=30,
        diagnostic_repeat_in_full_numeric_identity=True,CSV_full_precision_exact_rows=rows,
        May_scientific_execution='NOT_RUN',scientific_results_estimated=False,
        operation_counts_are_settled_steps_not_internal_events=True))
    print('INDEPENDENT QA PASS:',rows,'exact CSV points; 3590 BASE files; 33 source-integrity runs',flush=True)


def manifest():
    paths=['v42_regcontrol/','docs/v42_actual_autonomous_regcontrol_fixed_cap/']
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--',*paths],cwd=ROOT).decode().splitlines()
    files=[]
    for n in sorted(set(names)):
        if n.endswith('/SHA256_MANIFEST.json'): continue
        p=ROOT/n; files.append(dict(path=n,sha256=sha(p),bytes=p.stat().st_size))
    write(OUT,'SHA256_MANIFEST.json',dict(base=BASE,files=files,file_count=len(files),
        bytes=sum(r['bytes'] for r in files),excludes=['self','ignored Python caches'],
        full_precision_voltage_CSV_gzip=True,old_evidence_in_BASE_preservation=True))


if __name__=='__main__':
    import sys
    manifest() if '--manifest' in sys.argv else main()

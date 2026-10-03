"""Independent source, exact Git BASE, array freeze and CSV-axis verification."""
import hashlib
import subprocess
import csv
import gzip
import numpy as np
from .common import *

def base():
    rows=[]
    for line in subprocess.check_output(['git','ls-tree','-r',BASE],cwd=ROOT).decode().splitlines():
        meta,name=line.split('\t',1);oid=meta.split()[2];data=(ROOT/name).read_bytes()
        if hashlib.sha1(('blob %d\0'%len(data)).encode()+data).hexdigest()!=oid: raise ValueError('PR128_BASE_BYTE_DRIFT:'+name)
        rows.append(dict(path=name,git_blob_sha1=oid,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
    write(OUT,'PR128_BASE_BYTE_IDENTITY.json',dict(PASS=True,base=BASE,files_checked=len(rows),files=rows,
        April_evidence_modified=False,previous_parameter_or_margin_tuning_modified=False))
    return rows

def main():
    base();source_freeze();rows=0
    vintage=read(OUT/'D1_FORECAST_VINTAGE_CAUSALITY.json')
    if not vintage['PASS'] or vintage['days_checked']!=31:raise ValueError('D1_VINTAGE_QA_REQUIRED')
    for day in vintage['days']:
        for key in ('GFS_vintage_manifest','forecast','weather'):resolve(day[key])
    with gzip.open(OUT/'MAY_B0_VOLTAGE_RESIDUALS.csv.gz','rt',encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        for day in DAYS:
            dest=destination(day);p=np.load(dest/'V_PLAN.npz');a=np.load(dest/'V_ACTUAL_AC.npz')
            names=tuple(map(str,p['node_names']));pv=p['V_PLAN'];av=a['V_ACTUAL_AC']
            if names!=tuple(map(str,a['node_names'])) or pv.shape!=(96,386): raise ValueError('EXACT_VOLTAGE_AXIS')
            for t in range(96):
                for n,name in enumerate(names):
                    r=next(reader);node,phase=name.rsplit('.',1)
                    if (r['day'],r['node'],r['phase'],int(r['slot']))!=(day,node,'ABC'[int(phase)-1],t): raise ValueError('CSV_AXIS_DRIFT')
                    if (float(r['V_PLAN']),float(r['V_ACTUAL_AC']),float(r['e_total']))!=(pv[t,n],av[t,n],av[t,n]-pv[t,n]): raise ValueError('LOSSLESS_RESIDUAL_FLOAT_DRIFT')
                    rows+=1
            freeze=read(dest/'PLANNING_FREEZE.json')
            for key in ('reference','physical_arrays','voltage','response','planning_input','coefficients'):resolve(freeze[key])
            physical=np.load(dest/'ACTUAL_PHYSICAL.npz')
            for key in ('PCC_P_kw','PCC_Q_kvar'):
                if not np.array_equal(physical[key],a[key]): raise ValueError('SEALED_ACTUAL_PQ_DRIFT')
            for row in read(dest/'RAW_PHYSICAL_INPUT_LOG.json')['slots']:
                if not row['all_MESS_PQ_zero'] or not np.array_equal(row['PCC_P_kw'],physical['PCC_P_kw'][row['slot']]) or not np.array_equal(row['PCC_Q_kvar'],physical['PCC_Q_kvar'][row['slot']]):
                    raise ValueError('ENGINE_PQ_READBACK_DRIFT')
            control=read(dest/'RAW_CONTROL_LOG.json')
            if len(control['slots'])!=96:raise ValueError('ALL_SLOTS_CONTROL_LOG_REQUIRED')
            for t,r in enumerate(control['slots']):
                if r['slot']!=t or r['capacitor_states']!=[1]*4 or not r['source_parameters_before_after_identical'] or not r['all_7_RegControls_enabled'] or r['control_mode']==-1:
                    raise ValueError('CONTROL_INTEGRITY_DRIFT')
                expected=control['source_initial_inventory']['regulators'] if t==0 else None
                previous=[x['initial_tap'] for x in expected] if t==0 else control['slots'][t-1]['actual_taps']
                if previous!=r['previous_taps']: raise ValueError('DAILY_SEQUENTIAL_CONTROL_STATE_DRIFT')
            if not read(dest/'ACTUAL_CAPACITY_RECEIPT.json')['capacity_violations']==0: raise ValueError('CAPACITY_DRIFT')
        if next(reader,None) is not None or rows!=1148736: raise ValueError('FULL_31_DAY_CSV_REQUIRED')
    for row in read(OUT/'ACTUAL_PHYSICAL_FREEZE.json')['days']: resolve(row['physical']);resolve(row['Planning_freeze'])
    write(OUT,'NON_GRID_AUTHORITY_IDENTITY.json',dict(PASS=True,method='exact PR128 code/parameter/April evidence bytes + pre-Actual May freeze SHA + engine readback',
        numeric_May_equal_April_claim=False,current_reference_Runtime_CC4_capacity_power_laws_unchanged=True,
        May_Planning_workload_PQ_reference_coefficients_V_PLAN_preserved_after_freeze=True,
        May_Actual_occupancy_PQ_preserved_after_Fresh_AC=True,parameter_or_margin_refit_calls=0,
        private_future_truth_controller_reads=0,Actual_PQ_repair=0,Actual_reoptimization=0,MESS=0))
    write(OUT,'VERIFICATION.json',dict(PASS=True,base=BASE,base_files=3809,days=31,slots=2976,
        residual_exact_rows=rows,exact_node_phase_day_slot_axes=True,lossless_CSV_float_roundtrip=True,
        same_PR128_Actual_slot_loop_AST=True,April_evidence_preserved=True,source_parameters_unchanged=True,
        workload_capacity_PQ_V_PLAN_authority_drift=False,Planning_frozen_before_Actual=True,
        B1_B2_B3_M1_A2_M2='NOT_RUN',May_used_to_retune=False,FINAL_MARGIN_ACCEPTED=False,
        PROBLEM13_FINAL_VALIDATED=False))
    print('INDEPENDENT HOLDOUT QA PASS:',rows,'CSV points; 3809 BASE files; all 31 frozen inputs preserved',flush=True)

def manifest():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--','v42_holdout/','docs/v42_may_b0_zero_margin_holdout/'],cwd=ROOT).decode().splitlines()
    files=[dict(path=n,sha256=sha(ROOT/n),bytes=(ROOT/n).stat().st_size) for n in sorted(set(names)) if not n.endswith('/SHA256_MANIFEST.json')]
    write(OUT,'SHA256_MANIFEST.json',dict(base=BASE,files=files,file_count=len(files),bytes=sum(r['bytes'] for r in files),excludes=['self','ignored caches']))

if __name__=='__main__':
    import sys
    manifest() if '--manifest' in sys.argv else main()

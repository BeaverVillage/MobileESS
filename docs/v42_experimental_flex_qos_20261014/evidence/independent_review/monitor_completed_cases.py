"""Read finished experiment receipts; no replay, optimizer or AC invocation."""
from datetime import datetime,timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).parents[2]
OUT=ROOT/'audit/control/FINAL_FLEX_COMPARISON'
REPORT=Path(__file__).parent/'C_COMPLETED_CASE_VALIDATION.json'


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def spec_module(path):
    spec=importlib.util.spec_from_file_location('_reporting_only_flex_summary',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def physical_arrays(folder,result,receipt,capacity_packet):
    path=folder/'ACTUAL_PHYSICAL_ARRAYS.npz';details={}
    with np.load(path,allow_pickle=False) as archive:
        required={'occupancy_GPU','compute_occupancy_GPU','physical_IT_kw','physical_PCC_P_kw','physical_PCC_Q_kvar'}
        required_present=required.issubset(archive.files)
        for name in archive.files:
            source=(result.get('physical') or {}).get(name.removeprefix('physical_')) if name.startswith('physical_') else result.get(name)
            stored=np.asarray(archive[name]);decoded=np.asarray(source) if source is not None else None
            numeric=decoded is not None and stored.shape==decoded.shape and np.array_equal(stored,decoded)
            projected=bool(numeric and stored.tobytes(order='C')==np.asarray(decoded,dtype=stored.dtype).tobytes(order='C'))
            details[name]=dict(shape=list(stored.shape),NPZ_dtype=stored.dtype.str,
                JSON_numeric_exact_PASS=bool(numeric),byte_exact_after_JSON_projection_to_NPZ_dtype_PASS=projected)
        occupation=np.asarray(archive['occupancy_GPU']);compute=np.asarray(archive['compute_occupancy_GPU'])
        caps=capacity_packet['capacities_by_site'];sites=result['sites']
        resource_axis=sites==capacity_packet['resource_sites']
        shape=occupation.shape==compute.shape==(receipt['slots'],len(sites))
        capacities=np.array([caps[s] for s in sites],float)
        occupation_GPUh=float(occupation.sum()/4);compute_GPUh=float(compute.sum()/4)
        occupation_error=occupation_GPUh-result['receipt']['actual_occupation_GPUh']
        compute_error=compute_GPUh-result['receipt']['actual_compute_GPUh']
        result=dict(path=str(path),sha256=sha(path),arrays=details,
            JSON_has_no_dtype_metadata=True,byte_comparison_scope='C_ORDER_BYTES_AFTER_JSON_VALUES_PROJECTED_TO_STORED_NPZ_DTYPE',
            capacity_source_path=str(ROOT/'audit/cc4_service/A2_SERVICE_TIMING_SOURCE_PACKET.json'),
            capacity_source_sha=sha(ROOT/'audit/cc4_service/A2_SERVICE_TIMING_SOURCE_PACKET.json'),
            capacities_by_site=caps,capacity_total_GPU=float(capacities.sum()),
            required_original_physical_arrays_present_PASS=required_present,
            resource_site_axis_PASS=resource_axis,Full96_shapes_PASS=shape,
            compute_nonnegative_PASS=bool(np.min(compute)>=-1e-9),
            occupation_nonnegative_PASS=bool(np.min(occupation)>=-1e-9),
            compute_not_above_occupation_PASS=bool(np.max(compute-occupation)<=1e-9),
            occupation_per_site_capacity_PASS=bool(np.max(occupation-capacities[None,:])<=1e-9),
            max_occupation_by_site=dict(zip(sites,occupation.max(axis=0).tolist())),
            original_slot_hours=.25,slot_seconds=(receipt['end_seconds']-receipt['begin_seconds'])/receipt['slots'],
            occupation_GPUh_from_NPZ=occupation_GPUh,compute_GPUh_from_NPZ=compute_GPUh,
            occupation_receipt_error_GPUh=occupation_error,compute_receipt_error_GPUh=compute_error,
            occupation_receipt_exact_PASS=occupation_error==0,compute_receipt_exact_PASS=compute_error==0,
            numeric_guard=1e-9,actual_grid_or_AC_certificate=False)
        result['PASS']=all(d['JSON_numeric_exact_PASS'] and d['byte_exact_after_JSON_projection_to_NPZ_dtype_PASS'] for d in details.values()) and all(
            result[k] for k in ('required_original_physical_arrays_present_PASS','resource_site_axis_PASS','Full96_shapes_PASS','compute_nonnegative_PASS','occupation_nonnegative_PASS',
                'compute_not_above_occupation_PASS','occupation_per_site_capacity_PASS')) and abs(occupation_error)<=1e-9 and abs(compute_error)<=1e-9 and result['slot_seconds']==900
        return result


def main():
    manifest=read(OUT/'CASE_MANIFEST.json')
    previous=read(REPORT) if REPORT.is_file() else dict(cases=[])
    prior={r['name']:r for r in previous['cases']}
    summarize=spec_module(ROOT/'audit/SUMMARIZE_FLEX_COMPARISON.py').summarize
    summary_sha=sha(ROOT/'audit/SUMMARIZE_FLEX_COMPARISON.py')
    monitor_sha=sha(__file__)
    capacity_packet=read(ROOT/'audit/cc4_service/A2_SERVICE_TIMING_SOURCE_PACKET.json')
    rows=[];new=[]
    for case in manifest['cases']:
        name='_'.join(case[k] for k in ('scenario','participation','algorithm'))
        folder=OUT/name;rp=folder/'EXECUTION_RECEIPT.json'
        if not rp.is_file():continue
        receipt_sha=sha(rp)
        if (name in prior and prior[name]['execution_receipt_sha']==receipt_sha
                and prior[name].get('summary_script_sha')==summary_sha):
            if prior[name].get('monitor_script_sha')==monitor_sha:
                rows.append(prior[name]);continue
        r=read(rp);program=read(folder/'FROZEN_CONDITIONAL_POLICY_PROGRAM.json')
        result_path=folder/'CONDITIONAL_ACTUAL_RESULT.json.gz'
        result_sha=sha(result_path)
        with gzip.open(result_path,'rt',encoding='utf-8') as stream:d=json.load(stream)
        cc4=d['cc4_depletion_ledger'];actual=d['receipt']
        score_audit=d.get('experimental_candidate_audit',[])
        selected_mass=[e['selected_Q90_mass'] for e in score_audit if e.get('selected_Q90_mass')]
        arrays=physical_arrays(folder,d,r,capacity_packet)
        checks=dict(case_sha=case['case_sha']==r['case_sha']==d['conditional_case']['case_sha']==program['bindings']['case_sha'],
            source_sha=manifest['source_sha']==r['source_freeze_sha']==d['conditional_case']['source_freeze_sha']==program['bindings']['science_sha'],
            frozen_program_sha=program['policy_sha']==r['policy_sha']==d['conditional_case']['policy_sha'],
            result_file_sha=result_sha==r['result_sha256'],Full96=r['Full96'] is True and r['slots']==96,
            source_bytes_after=r['source_bytes_PASS_after'] is True,
            capacity_zero=actual['capacity_violations']==0,dropped_zero=actual['dropped_jobs']==0,
            private_duration_zero=actual['future_duration_controller_reads']==0,
            private_completion_zero=actual['future_completion_controller_reads']==0,
            CC4_once=all(row['depletion_count']==1 for row in cc4),
            CC4_UID_unique=len(cc4)==len({row['uid'] for row in cc4}),
            retrospective_service_mass=r['retrospective_service_audit']['PASS'] is True,
            selected_Q90_mass=all(m.get('conservation_PASS') is True for m in selected_mass),
            selected_Q90_physical=all(e['selected_Q90_risk']['hard_feasible'] is True for e in score_audit if e.get('selected_Q90_risk')),
            intentional_budget=all(row['total_intentional_burden_seconds']<=row['budget_seconds']+1e-7 for row in d['qos_ledger']),
            actual_power_recomputed=actual['actual_power_recomputed'] is True and actual['planning_power_copied'] is False,
            Native_zero=r['Native_Optimize_calls']==0 and actual['optimizer_calls']==0 and actual['actual_global_reoptimization']==0,
            Fresh_AC_NOT_RUN=r['Fresh_AC_status']=='NOT_RUN',JSON_NPZ_physical_arrays=arrays['PASS'])
        summary=summarize(d,r)
        row=dict(name=name,checks=checks,PASS=all(checks.values()),execution_receipt_sha=receipt_sha,summary_script_sha=summary_sha,
            monitor_script_sha=monitor_sha,physical_array_validation=arrays,
            result_file_sha=result_sha,source_sha=r['source_freeze_sha'],case_sha=r['case_sha'],
            program_sha=r['policy_sha'],CC4_depletion_UIDs=len(cc4),selected_Q90_mass_records=len(selected_mass),summary=summary)
        rows.append(row);new.append(dict(name=name,PASS=row['PASS'],failed_checks=[k for k,v in checks.items() if not v],
            completed_jobs=actual['completed_jobs'],carryout_jobs=actual['carryout_jobs'],
            executed_START_NOW=summary['executed_START_NOW'],executed_DELAY=summary['executed_DELAY'],
            executed_PREPLACE=summary['executed_PREPLACE'],executed_MIGRATE=summary['executed_MIGRATE'],
            engine_wall_seconds=r['wall_seconds'],writer_wall_seconds=r['writer_inclusive_wall_seconds']))
        del d
    report=dict(schema='READ_ONLY_COMPLETED_C_CASE_VALIDATION_V1',updated_utc=datetime.now(timezone.utc).isoformat(),
        source_sha=manifest['source_sha'],expected_cases=len(manifest['cases']),completed_cases=len(rows),
        complete=len(rows)==len(manifest['cases']),all_completed_PASS=all(r['PASS'] for r in rows),cases=rows,
        Native_Optimize_calls_by_monitor=0,Actual_replays_by_monitor=0,Fresh_AC_calls_by_monitor=0,
        private_realization_reaudit_by_monitor=False,retrospective_service_receipt_checked=True,
        actual_electrical_performance_certificate=False,Source_or_production_edits=0)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(completed=len(rows),expected=len(manifest['cases']),all_PASS=report['all_completed_PASS'],
        new=new,report=str(REPORT)),ensure_ascii=False))


if __name__=='__main__':main()

"""Native0 immutable-source nominal and extra-only recourse audit."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import sys
from time import perf_counter

os.environ['PYTHONDONTWRITEBYTECODE']='1'
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT))
from v42_integration.q90_recourse import load_nominal_service,evaluate_q90_recourse


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(name,value):
    p=Path(__file__).parent/name
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return str(p)
def receipt(p):
    p=Path(p);b=p.read_bytes()
    return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))


def main():
    begin=perf_counter()
    p=Path('D:/v42_experimental_flex_qos_20261014/audit/cc4_service/A2_SERVICE_TIMING_SOURCE_PACKET.json')
    packet=read(p)
    for r in packet['source_receipts']:
        current=receipt(r['path'])
        if current['sha256']!=r['sha256']:raise ValueError('SOURCE_RECEIPT_BYTE_DRIFT:'+r['path'])
    # Copy only audited public source vectors/decisions, never private Actual.
    write('A2_SERVICE_TIMING_SOURCE_PACKET.json',packet)
    spec=importlib.util.spec_from_file_location('v42_integration._frozen_reference',ROOT/'audit/reference_source.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    loaded=module.load_conditional_source()
    a=dict(model_id=packet['model_id'],prediction_sha=packet['prediction_sha'],
        kernel_sha=packet['kernel_sha'],timing_envelope_sha=packet['TRAIN_envelope']['sha256'],
        q50_hourly_GPUh=packet['q50_hourly_GPUh'],q90_hourly_GPUh=packet['q90_hourly_GPUh'],
        future_Actual_or_UID_inputs_used=False,forecast_modifications=0,
        source_receipts=packet['source_receipts'])
    nominal=load_nominal_service(loaded['aidc'],packet['q50_hourly_GPUh'],
        packet['TRAIN_CDF_lower'],packet['TRAIN_CDF_upper'],source_authority=a)
    write('FROZEN_A2_NOMINAL_SERVICE.json',nominal)
    before=perf_counter()
    r=evaluate_q90_recourse(loaded['packet'],nominal,packet['q90_hourly_GPUh'],
        packet['TRAIN_CDF_lower'],packet['TRAIN_CDF_upper'],source_authority=a)
    elapsed=perf_counter()-before
    write('A2_REFERENCE_Q90_EXTRA_RECOURSE.json',r)
    summary=dict(schema='D_SOURCE_ONLY_NOMINAL_AND_RECOURSE_REPLAY_V1',
        status='PASS' if r['conservation']['conserved'] and r['physical_hard_feasible'] else 'FAIL',
        source_packet=receipt(p),source_module=receipt(ROOT/'v42_integration/q90_recourse.py'),
        frozen_A2_aidc_anchor=loaded['aidc']['aidc_anchor'],nominal_replay=nominal['replay'],
        original_A2_nominal_served_GPUh=sum(sum(x) for x in nominal['x_GPUh']),
        original_A2_nominal_carryout_GPUh=sum(nominal['carryout_GPUh_by_hour']),
        old_A2_reserve_target_served_GPUh=sum(packet['CC4_reserve_service'].values()),
        old_A2_achieved_CC4_reserve_GPUh=sum(sum(v) for v in packet['achieved_CC4_reserve_site_GPU'].values())/4,
        original_A2_reserve_target_is_executable_capacity_certificate=False,
        recourse_mass=r['mass'],risk_total_unfinished_GPUh=r['risk_total_unfinished_GPUh'],
        physical_hard_feasible=r['physical_hard_feasible'],CDF_timing_status=r['CDF_timing_status'],
        CDF_lower_max_deficit_GPUh=r['CDF_lower_max_deficit_GPUh'],
        CDF_timing_violation_count=len(r['timing_violations']),
        peak_line_loading=r['original_grid_score']['peak_score'],
        grid_admission=r['admission'],recourse_seconds=elapsed,total_loader_audit_seconds=perf_counter()-begin,
        Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_calls=0,models_created=0,
        shared_solver_budget_debit=0,job_QoS_certified=False,whole_gang_schedulability_certified=False,
        physical_scope='ORIGINAL_SIGNED_AFFINE_PLANNING_ROWS;NO_NEW_AC_EXECUTION',
        future_UID_or_actual_completion_inputs_used=False,
        nominal_schedule_changed=False,forecast_scaled_or_clipped=False,
        kernel_reference_not_fixed_service=True,B2_B3_campaign_HOLD=True,May31_started=False)
    write('SOURCE_RECOURSE_NATIVE0_AUDIT.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()

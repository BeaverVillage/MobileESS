"""Package the bounded D component evidence, never run an optimizer/Actual."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from test_v42_q90_recourse import inputs,run
from v42_integration.q90_recourse import POLICY_ID


def read(name):return json.loads((Path(__file__).parent/name).read_text(encoding='utf-8'))
def write(name,value):
    (Path(__file__).parent/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def record(path):
    p=Path(path);b=p.read_bytes()
    return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))


def main():
    source=read('A2_SERVICE_TIMING_SOURCE_PACKET.json')
    nominal=read('FROZEN_A2_NOMINAL_SERVICE.json')
    r=read('A2_REFERENCE_Q90_EXTRA_RECOURSE.json')
    replay=read('SOURCE_RECOURSE_NATIVE0_AUDIT.json')
    write('A_STAGE_SERVICE_TIMING_REUSE_AUDIT.json',dict(status='PASS',
        original_A2_aidc_anchor=nominal['aidc_anchor'],nominal_service_sha=nominal['nominal_service_sha'],
        nominal_replay=nominal['replay'],original_source_function='v42_temporal.service.bind_service',
        original_nominal_x_carry_reused=True,nominal_service_rescheduled=False,
        kernel_fixed_schedule_imposed=False,original_reserve_achieved_GPUh=0.,
        original_reserve_target_served_GPUh=sum(source['CC4_reserve_service'].values()),
        reserve_target_is_physical_capacity_certificate=False,
        source_receipts=source['source_receipts'],Native_Optimize_calls=0,Fresh_AC_calls=0))
    write('Q90_QUEUE_AWARE_RECOURSE_POLICY.json',dict(policy_id=POLICY_ID,
        scientific_boundary='NEW_Q90_DEMAND_RECOURSE_ON_EXACT_PR224;NOT_PR224_BUG_REIMPLEMENTATION',
        primary='ORIGINAL_A2_Q50_ALL_REMAINING_SLOT_MAX_LINE_LOADING',
        risk='Q90_MINUS_Q50_AGGREGATE_CDF_CAPACITY_AND_SIGNED_GRID_ADMISSION',
        comparison='Q50_HARD_AND_ORIGINAL_JOB_RIGHTS_FIRST;Q90_QUEUE_RISK_TIEBREAK',
        service_rule='CDF_REQUIRED_FIRST_THEN_ORIGINAL_HOUR_FIFO;FIXED_SORTED_SITE_PRIORITY',
        hard_rows=['original voltage squared band','signed16face corrected line current',
                   'all original transformer current','all original transformer16facekVA','unchanged siteGPUcapacity'],
        unmet_lower_status='TIMING_INFEASIBLE;NOT_NORMAL_COMPLETE;NOT_JOB_QOS_CERTIFIED',
        extra_work_deleted=False,extra_forecast_scaled_or_clipped=False,
        kernel_reference_frozen=True,kernel_is_fixed_execution_schedule=False,
        nominal_x_site_carry_unchanged=True,whole_gang_schedulability_certified=False,
        Actual_executed=False,Fresh_AC_executed=False,Native_Optimize_calls=0,
        source_module=record(ROOT/'v42_integration/q90_recourse.py'),
        source_packet=record(Path(__file__).parent/'A2_SERVICE_TIMING_SOURCE_PACKET.json')))
    write('Q90_WORK_MASS_CONSERVATION.json',dict(status='PASS',
        extra_mass=r['mass'],full_Q90_mass=r['full_Q90_mass'],per_cohort=r['conservation'],
        nominal_carryout_GPUh=r['nominal_carryout_GPUh'],extra_carryout_GPUh=r['extra_carryout_GPUh'],
        risk_total_unfinished_GPUh=r['risk_total_unfinished_GPUh'],
        terminal_pending_GPUh=r['terminal_pending_GPUh'],
        backlog_GPUh_by_slot=r['backlog_GPUh_by_slot'],queue_area_GPUh_hours=r['queue_area_GPUh_hours'],
        service_delay=r['service_delay'],CDF_timing_status=r['CDF_timing_status'],
        timing_violation_count=len(r['timing_violations']),
        CDF_lower_max_deficit_GPUh=r['CDF_lower_max_deficit_GPUh'],
        physical_hard_feasible=r['physical_hard_feasible'],
        maximum_line_loading=r['original_grid_score']['peak_score'],
        nominal_carry_and_extra_carry_disjoint=True,Actual_executed=False))
    values=inputs(destination_slope=0.);values[0].capacities={'A':1.,'B':201.}
    small=run(values,extra=500.)
    write('Q90_500GPUH_200GPU_CAPACITY_FIXTURE.json',dict(schema='NAMED_AGGREGATE_FIXTURE',
        status='PASS',extra_hour0_arrival_GPUh=500.,additional_site_B_capacity_GPU=200.,
        additional_first_hour_served_GPUh=sum(sum(x) for x in small['admitted_extra_site_GPU'][:4])/4,
        backlog_after_first_hour_GPUh=small['backlog_GPUh_by_slot'][3],
        subsequently_served_GPUh=sum(sum(x) for x in small['admitted_extra_site_GPU'][4:])/4,
        backlog_after_slot9_GPUh=small['backlog_GPUh_by_slot'][9],
        carryout_GPUh=small['extra_carryout_GPUh'],mass=small['mass'],
        physical_hard_feasible=small['physical_hard_feasible'],Native_Optimize_calls=0,
        source_scope='SYNTHETIC_SIGNED_GRID_FIXTURE;NOT_MAY_RUN'))
    write('COMPONENT_SOURCE_MANIFEST.json',dict(source_records=[record(ROOT/'v42_integration/q90_recourse.py'),
        record(ROOT/'tests/test_v42_q90_recourse.py'),record(Path(__file__).parent/'source_replay.py'),
        record(Path(__file__).parent/'A2_SERVICE_TIMING_SOURCE_PACKET.json')],
        tests=21,focused_tests_status='PASS',source_native0_audit=replay,
        Original_Actual_Full96_reexecuted=False,Original_Fresh_AC_reexecuted=False,
        shared_solver_budget_debit=0))
    print('Wrote5 component evidence artifacts; Native/Actual/AC0')


if __name__=='__main__':main()

"""Report exact input gates; unavailable scientific measurements remain null."""
from collections import Counter
import csv
from v42_april_port.audit import read, write, table, record
from .freeze import ROOT, OUT
from .execution import execution_guard

def main():
    population=read(OUT/'POPULATION/APRIL_MODELABILITY_SUMMARY.json')
    reference=read(OUT/'REFERENCE/V42_COMMON_REFERENCE_AUTHORITY.json')
    power=read(OUT/'BUNDLE/APRIL_POWER_CONSTRUCTION_GATE.json')
    try: execution_guard(reference['audits'])
    except ValueError as e: guard_reason=str(e)
    else: guard_reason=None
    with (OUT/'REFERENCE/V42_COMMON_REFERENCE_SCHEDULE.csv').open(encoding='utf8') as f:
        blocked=[r for r in csv.DictReader(f) if r['status']=='BLOCKED']
    witnesses=[]
    from v42_april_b0_v2.reference import build_reference
    for day in sorted({r['day'] for r in blocked}):
        p=read(OUT/'BUNDLE'/('DAY_'+day.replace('-',''))/'PLANNING_INPUT_BUNDLE.json')
        rr,_=build_reference(p['known_population'],p['capacities'],p['rack_compatibility'],issue_time=p['issue_time'])
        hard=[r for r in rr if r.get('q50_expired_hard_occupancy') and r['reference_site']=='AIDC05']
        witnesses.append(dict(day=day,pending_job='8504781',GPU_gang=96,only_compatible_site='AIDC05',site_capacity=100,
            permanently_reserved_by_expired_running_GPU=sum(r['GPU_gang'] for r in hard),
            hard_occupancy_jobs=[dict(job_uid=r['job_uid'],GPU_gang=r['GPU_gang'],service_slots=r['service_slots'],
                runtime_authority=r['runtime_authority'],source_member=r['source_member'],source_row=r['source_row']) for r in hard],
            current_reference_causal_release_missing=True,Actual_completion_not_consulted=True))
    write(OUT,'REFERENCE/CAUSAL_RELEASE_BLOCKERS.json',dict(blocked_rows=blocked,witnesses=witnesses,
        modelable_jobs_dropped=False,site_rule_changed_after_preflight=False,historical_service_fallback=False))
    gates=[]
    for r in power['days']:
        folder='DAY_'+r['day'].replace('-','')
        gate=dict(day=r['day'],J_PHYSICAL_GPU_COMPLETE=True,physical_source_fields_complete=True,
            current_Runtime_bound=True,CC4_date_bound=True,current_C1_date_bound=True,
            reference_ready=r['known_reference_ready'],fixed_CC4_nominal_capacity_feasible=not r['infeasible_slots'],
            full_workload_power_constructible=r['fixed_known_plus_CC4_power_constructible'],
            April_Planning_grid_numeric_coefficients_generated=False,Actual_physical_occupancy_generated=False,
            executable_bundle_complete=False,B0_executed=False)
        gates.append(gate)
        for filename in ('PLANNING_INPUT_BUNDLE.json','ACTUAL_INPUT_BUNDLE.json'):
            b=read(OUT/'BUNDLE'/folder/filename)
            b['current_power_authority']=record(OUT/'BUNDLE'/folder/'POWER_AUTHORITY.json')
            b['input_gate_PASS']=False
            b['status']='SOURCE_FIELDS_COMPLETE_PHYSICAL_EXECUTION_GATE_FAILED'
            b['execution_gate']=gate
            write(OUT,'BUNDLE/'+folder+'/'+filename,b)
        write(OUT,'B0/'+folder+'/EXECUTION_STATUS.json',dict(day=r['day'],status='NOT_RUN',
            blockers=[x for x,v in [('REFERENCE_CAUSAL_RELEASE_UNAVAILABLE',r['known_reference_ready']),
                 ('FIXED_CC4_PLUS_KNOWN_CAPACITY_INFEASIBLE',not r['infeasible_slots'])] if not v],
            all_30_complete_bundles_required=True,operational_DA_AC_gate=False,
            optimizer_calls=0,OpenDSS_calls=0,Actual_P_Q_repair_calls=0,Actual_schedule_repair_calls=0,
            served_jobs=None,served_GPUh=None,AIDC_IT_energy_kWh=None,AIDC_PCC_energy_kWh=None,
            V_PLAN=None,V_DA_AC=None,V_DDAY_AC=None,physical_pass=None))
    table(OUT,'BUNDLE/APRIL_DAY_INPUT_GATE.csv',gates,list(gates[0]))
    manifest=read(OUT/'BUNDLE/APRIL_INPUT_MANIFEST.json')
    for r in manifest['days']:
        folder='DAY_'+r['day'].replace('-','')
        r['planning']=record(OUT/'BUNDLE'/folder/'PLANNING_INPUT_BUNDLE.json')
        r['actual']=record(OUT/'BUNDLE'/folder/'ACTUAL_INPUT_BUNDLE.json')
    manifest.update(current_CC4_date_bound_days=30,current_C1_date_bound_days=30,
        reference_preflight_complete_days=reference['preflight_ready_days'],
        fixed_known_plus_CC4_capacity_compatible_days=power['fixed_profile_constructible_days'],
        full_executable_complete_days=0,complete_power_grid_actual_execution_bundles=False)
    write(OUT,'BUNDLE/APRIL_INPUT_MANIFEST.json',manifest)
    table(OUT,'CALIBRATION/APRIL_B0_RESIDUALS.csv',[],['day','node','phase','slot','V_PLAN','V_DA_AC','V_DDAY_AC','e_model','e_forecast','e_total','r_up','r_down'])
    for stem in ('POINTWISE_QUANTILES','DAY_WORST_QUANTILES'):
        table(OUT,'CALIBRATION/'+stem+'.csv',[dict(q=q,delta_up=None,delta_down=None,status='NOT_MEASURED') for q in (.9,.95,.975,.99)],
              ['q','delta_up','delta_down','status'])
    write(OUT,'CALIBRATION/CURRENT_005_COVERAGE.json',dict(status='NOT_MEASURED',delta_current=.005,
        upper_pointwise_coverage=None,lower_pointwise_coverage=None,day_coverage=None,
        exceedance_dates=None,maximum_exceedance=None,node=None,phase=None,slot=None))
    write(OUT,'CALIBRATION/CANDIDATE_BANDS.json',dict(status='NOT_MEASURED',primary_band=[.95,1.05],
        lower_formula='0.95 + delta_down_q',upper_formula='1.05 - delta_up_q',
        candidates=[dict(q=q,lower=None,upper=None) for q in (.9,.95,.975,.99)],FINAL_MARGIN_ACCEPTED=False))
    flags=dict(AIDC_PRESENT=True,AIDC_WORKLOAD_PRESENT=True,ML_RUNTIME_USED=True,
        Runtime_cache_reused=True,COMMON_CC4_DATE_BOUND=True,CC4_FORECAST_INTERFACE_USED=True,
        B0_ML_configuration_ON=True,B0_execution_ML_used=None,AIDC_FLEX_OPTIMIZATION=False,MESS_ACTIVE=False,
        P_MESS=0,Q_MESS=0,movement=0,MESS_optimization_calls=0,B0_executed_days=0,
        B1='NOT_RUN',B2='NOT_RUN',B3='NOT_RUN',May='NOT_RUN',M1_Benders='NOT_RUN',
        OFFLINE_CALIBRATION_DIAGNOSTIC_ONLY=True,operational_DA_AC_stage=False,
        Actual_global_reoptimization=0,Actual_P_repair=0,Actual_Q_repair=0,Actual_schedule_repair=0,
        MAY_USED_FOR_MARGIN_CALIBRATION=False,May_outcomes_used=False,FINAL_MARGIN_ACCEPTED=False)
    write(OUT,'FINAL_FLAGS.json',flags)
    verdict=dict(status='STOP_CURRENT_PHYSICAL_CONSTRUCTION_GATE',population=population,
        physical_input_fields_complete_days=30,executable_complete_days=0,
        CC4_date_bound_days=30,current_C1_date_bound_days=30,
        reference_ready_days=reference['preflight_ready_days'],reference_blocked_events=len(blocked),
        CC4_nominal_capacity_infeasible_days=sum(bool(r['infeasible_slots']) for r in power['days']),
        current_fixed_profile_power_constructible_days=power['fixed_profile_constructible_days'],
        B0_executed_days=0,physical_pass_days=None,voltage_measurements=None,
        Q95_delta_up=None,Q95_delta_down=None,Q99_delta_up=None,Q99_delta_down=None,
        AIDC_IT_energy_kWh=None,AIDC_PCC_energy_kWh=None,guard_reason=guard_reason,
        stop_reasons=['Two days require unavailable causal completion to generate the frozen PR121 reference.',
                      '15 days cannot allocate the unmodified current CC4 nominal profile plus the fixed known reference within 780 GPU.'],
        raw_unmodelable_presence_is_STOP_reason=False,J_PHYSICAL_changed_after_preflight=False,
        J_FLEX_rule_frozen=True,J_FLEX_executable_population_frozen=False,
        FINAL_MARGIN_ACCEPTED=False,May_outcomes_used=False)
    write(OUT,'FINAL_VERDICT.json',verdict)
    next_text='''# Required current authority changes before physical execution

The old missing-GPU NO-DROP gate is superseded. All modelable source fields are
complete on 30 days; unmodelable raw rows are retained separately, never imputed.

1. PR121 reference: pending UID 8504781 needs 96 GPUs and only fits AIDC05.
   On April 17/18, Q50-expired RUNNING jobs retain that site's physical capacity
   indefinitely without a causal completion receipt. Four later April 18 pending
   rows are retained behind it under strict FCFS. Do not use future Actual end times,
   revise the frozen placement after results, split the gang, drop or resize jobs.
   A reviewed common placement/release authority is needed to resolve this conflict.
2. Current CC4 date binding exists on all 30 days, but nominal execution-lag occupancy
   plus the known fixed reference exceeds 780 GPU on 15 days (maximum 1527.7423).
   A common, causal, grid-independent forecast/service capacity binding is needed;
   it must conserve full GPUh/tails and explicitly define any permitted queueing.
   This task did not silently introduce aggregate retiming, clipping or an anonymous
   LP job schedule. The per-slot capacity lower bounds do not depend on site ordering.
3. After resolving these common input authorities, certify J_FLEX complete options,
   generate date-specific current Planning grid coefficients and Actual causal
   occupancy, freeze common schedules, and run all April B0 diagnostics. Retain the
   0.95–1.05 primary Planning band and no Actual P/Q/schedule/route repair.

No old baseline recovery or extra raw GPU archaeology is required. No coverage
percentage gate is proposed. GPUh coverage remains not identifiable from source.
'''
    (OUT/'NEXT_MODIFICATIONS.md').write_text(next_text,encoding='utf8',newline='\n')
    review=f'''# April current V42 modelable population 및 B0 input gate

PR122 exact head를 보존하고 physical population rule을 결과 조회 전에 freeze했다.
Raw unique {population['raw_unique_jobs']:,}, modelable {population['modelable_unique_jobs']:,},
unmodelable {population['unmodelable_unique_jobs']:,}; modelable fraction {population['modelable_job_fraction']:.8%}.
GPU request 누락을 숫자로 채우지 않았으며 모든 제외 event를 ledger에 보존했다.
GPUh coverage는 NOT_IDENTIFIABLE_FROM_SOURCE이다.

30일 current Runtime source fields / April CC4 date binding / April weather C1 계수는 준비했다.
이는 실행 가능한 Planning/Actual physical bundle 30개가 완성되었다는 뜻이 아니다.
Reference preflight는 28/30일 통과했다. 4/17·4/18의 pending 96-GPU job 8504781에
필요한 AIDC05의 hard RUNNING release가 causal하게 알려지지 않았다. 이 job 및
FCFS 후속 4개 row를 J_PHYSICAL에서 제거하지 않았다.
15일은 known frozen reference + current CC4 nominal occupancy가 780 GPU를 초과한다.
고정 profile로 power를 구성 가능한 날짜는 14/30이다. 개별 날짜를 골라 실행하지 않았다.

J_PHYSICAL 및 J_FLEX rule은 frozen이며, J_FLEX 실행 가능 domain의 완성은 미확인이다.
May known input metadata 1,649행에 동일 modelability rule을 read-only 적용했다.
May Actual/voltage/policy outcome을 읽거나 April numerical donor로 사용하지 않았다.

B0 실행 0일, fully executable bundle 0/30. AIDC energy, 세 voltage, physical pass,
Q95/Q99, ±0.005 coverage 및 candidate band는 미측정(null)이다. Runtime/CC4 ML은
input layer에서 ON이며, B0 실행을 했다고 주장하지 않는다. B1/B2/B3/May/M1 NOT_RUN.
FINAL_MARGIN_ACCEPTED=false. 중단 원인은 raw unmodelable row 존재가 아니라
현재 공통 fixed schedule/CC4의 capacity 및 causal release authority이다.

회귀 tests는 기존 sealed fixtures를 읽는 baseline suite를 상속한다. 이는 새 April
construction이 May scientific outcome을 donor로 사용한 것과 구분된다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(review,encoding='utf8',newline='\n')

if __name__=='__main__': main()

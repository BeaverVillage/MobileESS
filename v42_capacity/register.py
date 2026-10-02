from datetime import datetime, timezone
from .common import *

def main():
    if not (OUT/'EXACT_BASE_AUTHORITY_REAUDIT.json').exists(): raise ValueError('READ_REQUIRED_BASE_AUTHORITY_FIRST')
    if (OUT/'PREREGISTRATION.json').exists(): raise ValueError('ALREADY_FROZEN')
    write(OUT,'PREREGISTRATION.json',dict(base=BASE,frozen_at=datetime.now(timezone.utc).isoformat(),
        days=['2025-04-%02d'%d for d in range(1,31)],capacity_total_GPU=780,
        primary_voltage_band_pu=[.95,1.05],primary_residual='V_ACTUAL_AC - V_PLAN',
        voltage_representation='magnitude pu; sqrt nonnegative surrogate squared voltage before residual',
        quantiles=[.9,.95,.975,.99],quantile_method='higher',mass_tolerance_absolute_GPUh=1e-9,
        mass_tolerance_relative=1e-12,Planning_reference='PR121 FCFS/site order with nominal Q50 release and separate current observed placement',
        CC4_reference_profile_unchanged=True,CC4_queue='forward backlog; ascending AIDC first spare; no advance or clipping',
        Actual_queue='submit_time/job_uid strict FCFS; no backfill; re-admit at submit/completion release/900-second boundaries',
        Actual_truth='source realized end-start duration hidden in environment; pending simulated start + duration; running source completion',
        missing_or_invalid_realized_duration='FAIL_CLOSED; no walltime/Q50/zero synthetic fill',
        Actual_zero_duration='only exact source observed start=end, not missing-start cancellation promoted to service duration',
        release='ceil(causal completion / 900)*900',Runtime_reserve_gamma=2.423057443558147,
        Runtime_reserve_kernel_unchanged=True,reserve_KPI_only=True,
        reserve_achievement='site-local Runtime first; CC4 spread from remaining headroom, ascending site',
        reserve_is_electrical_load=False,AIDC_PRESENT=True,AIDC_WORKLOAD_PRESENT=True,
        ML_RUNTIME_USED=True,CC4_used=True,AIDC_FLEX_OPTIMIZATION=False,MESS_ACTIVE=False,
        Actual_PQ_repair=False,Actual_global_reoptimization=False,Actual_grid_aware_schedule_repair=False,
        Actual_capacity_admission_queue=True,B1_RUN=False,B2_RUN=False,B3_RUN=False,May_RUN=False,
        M1_RUN=False,A2_RUN=False,M2_RUN=False,PR124_imported=False,
        FINAL_MARGIN_ACCEPTED=False,PROBLEM13_FINAL_VALIDATED=False))
    text='''# Scientific contract

CC4 is not a four-hour model. It supplies 24 hourly Q50/Q90 future-arrival
lifetime GPUh values. Its frozen execution-lag kernel and ML predictions stay
unchanged. Only capacity-caused forward admission backlog is added, with full
GPUh and original kernel-tail conservation. No workload advance or drop.

Planning RUNNING nominal remaining is max(Q50_total - elapsed, 0). Expired Q50
retains observed physical placement at the issue instant, but no infinite nominal
future reservation. Statistical overrun exposure uses the existing signed Q50
completion origin, gamma and frozen survival kernel. Reserve is a headroom KPI,
not realized IT/PCC load and not a new scientific objective.

Actual retains physical RUNNING until causal completion/release. Submitted jobs
wait under deterministic strict FCFS and first capacity-feasible ascending AIDC
placement, without backfill. Queue waiting is physical admission, not optimized
timeshift, migration, grid-aware relocation or P/Q/schedule voltage repair.
Realized service duration is private environment truth; controller/job views
cannot receive future end/runtime. Pending completion is simulated admission
plus uniquely source-backed realized duration, following the audited current
May-lineage counterfactual execution primitive. Missing actual duration stops the
campaign; requested walltime, Q50 and invented zero cannot replace it.

Primary voltage evidence is Planning surrogate magnitude pu versus D-Day Fresh
OpenDSS magnitude pu. Compare exactly aligned day/node/phase/slot axes after
sqrt conversion where the surrogate stores voltage squared. Primary band is
0.95–1.05 pu. No operational Day-Ahead AC stage or required DA diagnostic.
Empirical quantiles use the fixed higher method. Violating days remain present.
FINAL_MARGIN_ACCEPTED=false and PROBLEM13_FINAL_VALIDATED=false. B1/B2/B3,
May scientific runs, M1/A2/M2 and PR124 imports remain off.
'''
    (OUT/'SCIENTIFIC_CONTRACT.md').write_text(text,encoding='utf8',newline='\n')
    (OUT/'.gitattributes').write_text('* -text whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol\n',encoding='utf8')

if __name__=='__main__': main()

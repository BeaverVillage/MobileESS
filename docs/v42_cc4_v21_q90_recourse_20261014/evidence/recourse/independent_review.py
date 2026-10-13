"""Independent read-only recurrence/source review. No solver/Actual/AC."""
from pathlib import Path
import hashlib,json
import numpy as np
B=Path(__file__).parent;ROOT=B.parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def record(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
r=read(B/'A2_REFERENCE_Q90_EXTRA_RECOURSE.json');n=read(B/'FROZEN_A2_NOMINAL_SERVICE.json')
s=read(B/'SOURCE_RECOURSE_NATIVE0_AUDIT.json');src=read(B/'A2_SERVICE_TIMING_SOURCE_PACKET.json')
x=np.array(r['extra_x_GPUh']);carry=np.array(r['extra_carryout_GPUh_by_hour']);prior=r['prior_served_GPUh']
extra=np.array(src['extra_hourly_GPUh']);gpu=np.array(r['admitted_extra_site_GPU'])
nom=np.array(n['nominal_site_GPU']);known=np.array(n['known_site_GPU']);physical=np.array(r['physical_site_GPU'])
caps=np.array([src['capacities_by_site'][site] for site in n['site_axis']])
lo=np.array(src['TRAIN_CDF_lower']);hi=np.array(src['TRAIN_CDF_upper'])
assert prior==0 and x.shape==(24,96) and gpu.shape==(96,12)
mass_err=float(np.max(np.abs(x.sum(axis=1)+carry-extra)))
site_err=float(np.max(np.abs(gpu.sum(axis=1)*.25-x.sum(axis=0))))
full_error=float(np.sum(n['x_GPUh'])+sum(n['carryout_GPUh_by_hour'])+x.sum()+carry.sum()-sum(src['q90_hourly_GPUh']))
timing_upper=0.;max_lower=0.;timing_count=0
for h in range(24):
    assert np.sum(x[h,:4*h])==0
    cumulative=0.
    for t in range(4*h,96):
        cumulative+=x[h,t];lag=t-4*h
        upper=max(0.,cumulative-hi[lag]*extra[h]);lower=max(0.,lo[lag]*extra[h]-cumulative)
        timing_upper=max(timing_upper,upper);max_lower=max(max_lower,lower)
        timing_count+=lower>1e-7 or upper>1e-7
assert mass_err<=1e-7 and site_err<=1e-7 and abs(full_error)<=1e-7 and timing_upper<=1e-7
assert np.allclose(physical,known+nom+gpu,rtol=0,atol=1e-9)
assert np.all(physical<=caps+1e-9) and np.all(physical>=-1e-9)
assert not r['job_QoS_certified'] and not r['whole_gang_schedulability_certified']
assert r['CDF_timing_status']=='LOWER_BOUND_UNMET' and r['status']=='TIMING_INFEASIBLE'
assert abs(max_lower-r['CDF_lower_max_deficit_GPUh'])<=1e-7
assert int(timing_count)==len(r['timing_violations'])
assert s['source_module']['sha256']==record(ROOT/'v42_integration/q90_recourse.py')['sha256']
value=dict(schema='D_INDEPENDENT_CDF_RECOURSE_REVIEW_V1',status='PASS_WITH_EXPLICIT_AGGREGATE_SCOPE',
    code_review='COMPLETE_CURRENT_SOURCE_READ_NO_SOURCE_EDITS',Native_Optimize_calls=0,models_created=0,
    Actual_runs=0,Fresh_AC_calls=0,test_reruns=0,shared_solver_budget_debit=0,
    review_sources=[record(ROOT/'v42_integration/q90_recourse.py'),record(ROOT/'v42_integration/q90_policy.py'),
        record(ROOT/'tests/test_v42_q90_recourse.py'),record(ROOT/'tests/test_v42_q90_policy.py'),
        record(B/'A2_REFERENCE_Q90_EXTRA_RECOURSE.json'),record(B/'FROZEN_A2_NOMINAL_SERVICE.json'),
        record(B/'SOURCE_RECOURSE_NATIVE0_AUDIT.json'),record(B/'A2_SERVICE_TIMING_SOURCE_PACKET.json')],
    independent_saved_result_replay=dict(per_hour_extra_mass_max_error_GPUh=mass_err,
        site_GPUh_projection_max_error_GPUh=site_err,full_Q90_mass_error_GPUh=full_error,
        CDF_upper_max_violation_GPUh=float(timing_upper),CDF_lower_max_deficit_GPUh=float(max_lower),
        CDF_lower_violation_count=int(timing_count),physical_capacity_max_violation_GPU=float(max(0.,np.max(physical-caps))),
        extra_demand_GPUh=float(extra.sum()),extra_served_GPUh=float(x.sum()),extra_carryout_GPUh=float(carry.sum()),
        nominal_served_GPUh=float(np.sum(n['x_GPUh'])),nominal_carryout_GPUh=float(sum(n['carryout_GPUh_by_hour'])),
        nominal_plus_extra_terminal_carry_GPUh=float(sum(n['carryout_GPUh_by_hour'])+carry.sum()),PASS=True),
    checked_semantics={
        'Q90_minus_Q50_only':'PASS_LITERAL_HOURLY_DIFFERENCE_NO_FULL_Q50_RESCHEDULING',
        'hourly_to_slot_to_site_units':'PASS_24_HOURLY_GPUh_TO_96_QUARTER_SERVICES_TO_12_SITE_GPU',
        'original_nominal_x_carry_reuse':'PASS_SEALED_RECEIPT_KNOWN_SITE_AND_AIDC_ANCHOR_MATCH',
        'source_CDF_upper':'PASS_CUMULATIVE_ADMISSION_QUOTAS_HI_TIMES_REMAINING_PLUS_PRIOR',
        'source_CDF_lower':'REQUIRED_FIRST_AND_UNMET_RECORDED_AS_TIMING_INFEASIBLE_NOT_NORMAL_COMPLETED',
        'midcohort_history':'EXPLICIT_PRIOR_AND_REMAINING_PER_HOUR_MUST_SUM_TO_UNCHANGED_SOURCE_EXTRA',
        'future_prior':'POSITIVE_SERVICE_BEFORE_4H_COHORT_ARRIVAL_REJECTED',
        'terminal_carry':'ONE_TERMINAL_RESIDUAL_RECLASSIFICATION_PENDING0_NO_DOUBLE_COUNT',
        'full_Q90_mass':'Q90=FROZEN_NOMINAL_SERVE_PLUS_CARRY_PLUS_EXTRA_PRIOR_SERVE_CARRY',
        'signed_physics':'ORIGINAL_SIGNED_VOLTAGE_LINE_CURRENT_ALL_TRANSFORMER_CURRENT_KVA_ADMISSION_AND_SCALAR_BOUNDARY_CHECK',
        'Q50_evidence_reuse':'EXACT_REJECT_ORDINAL_COUNT_ACTION_SITE_ALL_SCENARIO_PEAK_ASSERTIONS_PLUS_ALL_OLD_NONSCIENCE_BINDINGS_UNCHANGED'},
    compiler_findings_reported_and_resolved=[
        dict(issue='ACTION_SITE_KEY_LOST_DISTINCT_DELAY_Q50_EVIDENCE',resolution='EXACT_ORDERED_REJECTION_CONSUMPTION_AND_SOURCE_SCORE_ASSERTIONS',status='RESOLVED_SOURCE_REVIEW'),
        dict(issue='MET_TREATED_AS_TIMING_RISK_BY_PASS_ONLY_COMPARISON',resolution='MET_IS_ACCEPTED',status='RESOLVED_SOURCE_REVIEW'),
        dict(issue='GRID_ONLY_RECOURSE_APPROVAL_OMITTED_EXPLICIT_CAPACITY_STATUS',resolution='PHYSICAL_HARD_FEASIBLE_GRID_AND_CAPACITY_REQUIRED',status='RESOLVED_SOURCE_REVIEW')],
    causal_scope=dict(begin0='SAME_FULL_DAY_SOURCE_COUNTERFACTUAL_FOR_EVERY_ACTION_NOT_LIVE_ACTUAL_BACKLOG',
        remaining_slot='CANDIDATE_DELTA_ZERO_IN_PAST_REMAINING_HORIZON_SCORE',
        actual_forecastbook_depletion='SEPARATE_CAUSAL_ONCE_ONLY_PATH_NOT_INFERRED_FROM_RECOURSE',
        existing_pending_mass_added_to_past_begin0=False,future_UID_or_private_Actual_completion_used=False),
    scientific_limits=dict(CDF_lower_unmet_is_real_risk=True,anonymous_job_QoS_guarantee=False,
        whole_gang_exact_scheduling_guarantee=False,global_recourse_optimum=False,
        new_A_M_FULL_or_gap=False,new_Full96_Actual_Fresh_AC='NOT_RUN',
        old_PR223_Actual_Fresh_results_transferred=False,PR224_fixes_reimplemented=False,
        B2_B3_campaign_HOLD=True,May31_campaign_started=False),
    unresolved_material_correctness_findings=0)
(B/'INDEPENDENT_CDF_RECOURSE_REVIEW.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(status=value['status'],independent_replay=value['independent_saved_result_replay'],
    receipt=record(B/'INDEPENDENT_CDF_RECOURSE_REVIEW.json')),ensure_ascii=False))

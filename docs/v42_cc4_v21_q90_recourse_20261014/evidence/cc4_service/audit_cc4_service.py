"""Read-only D audit: original hourly service binding, no model/solver creation."""
from pathlib import Path
import ast,csv,hashlib,json,subprocess,sys,time
import numpy as np
ROOT=Path(__file__).parents[2];sys.path.insert(0,str(ROOT))
from v42_integration.cc4_policy_inputs import load_frozen_cc4
from v42_integration.production_case import TIMING,KERNEL,RESOURCE_DISTRIBUTION_FIELDS
from v42_integration.a_engine import digest
from v42_final.workload import ForecastBook,profile
from v42_temporal.service import validate_envelope
OUT=Path(__file__).parent
BASE=Path('D:/v42_integration_validation_20261013/DDAY_V5_B3_FINAL_ATTEMPT01/B3')
DOC=Path('D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout')
V5=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/SOURCE_FREEZE_DDAY_GRID_V5.json')
SOURCE_AUDIT=Path('D:/v42_integration_validation_20261013/CC4_POLICY_SOURCE_AUDIT')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def record(p):
    p=Path(p);return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
def symbols(p,names):
    p=Path(p);tree=ast.parse(p.read_text(encoding='utf-8-sig'))
    return dict(record(p),symbols={n.name:n.lineno for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names})
started=time.perf_counter()
cc4=load_frozen_cc4(DOC/'MAY_CC4_BINDING.json',DOC/'CC4/DAY_20250501.json',kernel_path=KERNEL,
    runtime_integrity_path=ROOT/'v42_final/runtime_bundle/INTEGRITY.json',
    planning_bundle_path='D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
with TIMING.open(encoding='utf-8-sig',newline='') as f:env=list(csv.DictReader(f))
lo=np.array([float(r['Q10']) for r in env]);hi=np.array([float(r['Q90']) for r in env]);validate_envelope(lo,hi)
assert [int(r['lag_slot']) for r in env]==list(range(len(env)))
a=read(BASE/'A2/A_RESULT.json');plan=read(BASE/'PLANNING_FREEZE.json');freeze=read(V5)
assert a['FULL_feasible'] and a['FULL_max_residual']<=1e-5 and a['aidc_anchor']==plan['aidc_anchor']
assert digest({k:a[k] for k in RESOURCE_DISTRIBUTION_FIELDS})==a['resource_distribution_sha']
sites=tuple(a['resource_sites']);assert len(sites)==12
bundle=read('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01/NATIVE_INPUT_TEMPLATE_B1.json')
caps=np.array([bundle['capacities'][s] for s in sites]);assert caps.sum()==780
arrays={key:np.array([a[key][s] for s in sites],float).T for key in
    ('nominal_site_GPU','reserve_site_GPU','known_site_GPU','achieved_CC4_reserve_site_GPU','achieved_runtime_reserve_site_GPU')}
assert all(v.shape==(96,12) and np.isfinite(v).all() for v in arrays.values())
from datetime import datetime
day=datetime.fromisoformat(bundle['day']+'T00:00:00+10:00').timestamp()
issue=datetime.fromisoformat(bundle['issue_time']).timestamp()
book=ForecastBook(tuple(cc4['q50_hourly_GPUh']),tuple(cc4['q90_hourly_GPUh']),day)
depletion=[book.row(h,issue) for h in range(24)]
assert issue==day-21600 and not any(r['cohort_closed'] for r in depletion)
cohorts=[];scenario_summary={};x_all={}
for label,xkey,carrykey,work,sitekey in (
    ('Q50_NOMINAL','CC4_service','CC4_carryout',np.array(cc4['q50_hourly_GPUh']),'nominal_site_GPU'),
    ('Q90_MINUS_Q50_TARGET','CC4_reserve_service','CC4_reserve_carryout',
     np.array(cc4['q90_hourly_GPUh'])-cc4['q50_hourly_GPUh'],'reserve_site_GPU')):
    x=np.zeros((24,96));nonnegative=True;axes=True
    for k,v in a[xkey].items():
        h,t=ast.literal_eval(k);assert type(h) is int and type(t) is int
        axes &= 0<=h<24 and 4*h<=t<96 and t-4*h<len(lo)
        x[h,t]=v;nonnegative &= v>=-1e-9
    carry=np.array([a[carrykey].get(str(h),0.) for h in range(24)])
    mass=np.sum(x,axis=1)+carry
    errors=np.abs(mass-work)
    cdf_errors=[]
    for h in range(24):
        cumulative=0.;lower_error=upper_error=0.
        for t in range(4*h,96):
            cumulative+=x[h,t];lag=t-4*h
            lower_error=max(lower_error,lo[lag]*work[h]-cumulative)
            upper_error=max(upper_error,cumulative-hi[lag]*work[h])
        cdf_errors.append(max(lower_error,upper_error))
        cohorts.append(dict(scenario=label,hour=h,arrival_slot=4*h,work_GPUh=float(work[h]),
            served_GPUh=float(x[h].sum()),carryout_GPUh=float(carry[h]),mass_error_GPUh=float(errors[h]),
            maximum_CDF_lower_violation_GPUh=float(lower_error),maximum_CDF_upper_violation_GPUh=float(upper_error),
            CDF_PASS=bool(max(lower_error,upper_error)<=1e-7),
            GPUh_to_GPU_conversion='4 * x[h,t] for 0.25h slot',served_before_GPUh=0.))
    conversion=np.sum(x,axis=0)*4
    site_error=float(np.max(np.abs(arrays[sitekey].sum(axis=1)-conversion)))
    assert nonnegative and axes and errors.max()<=1e-7 and max(cdf_errors)<=1e-7 and site_error<=1e-7
    scenario_summary[label]=dict(hours=24,slots=96,sites=12,x_variables=len(a[xkey]),
        full_work_GPUh=float(work.sum()),served_within96_GPUh=float(x.sum()),carryout_GPUh=float(carry.sum()),
        maximum_per_hour_mass_error_GPUh=float(errors.max()),maximum_CDF_violation_GPUh=float(max(cdf_errors)),
        maximum_site_partition_error_GPU=float(site_error),mass_PASS=True,CDF_PASS=True,site_partition_PASS=True)
    x_all[label]=x
nominal=arrays['known_site_GPU']+arrays['nominal_site_GPU']
physical=nominal+arrays['achieved_CC4_reserve_site_GPU']+arrays['achieved_runtime_reserve_site_GPU']
capacity_error=float(np.max(physical-caps));assert capacity_error<=1e-7
target_fixed=nominal+arrays['reserve_site_GPU']
target_over=float(np.max(target_fixed-caps))
source_functions=[symbols(ROOT/'v42_temporal/service.py',{'bind_service','bind_forecast','validate_envelope'}),
    symbols(ROOT/'v42_temporal/native.py',{'grid_binding'}),
    symbols(ROOT/'v42_final/workload.py',{'ForecastBook','profile','row','submit'}),
    symbols(ROOT/'v42_final/reserve.py',{'bind_headroom'}),
    symbols(ROOT/'v42_integration/a_engine.py',{'PlanningGridContext','bind','optimize_aidc'}),
    symbols(ROOT/'v42_integration/cc4_policy_inputs.py',{'load_frozen_cc4','validate_optimized_reserve'}),
    symbols(ROOT/'v42_integration/sensitivity_policy.py',{'_scenarios','compile_sensitivity_policy','evaluate'})]
pr129_path='docs/v42_may_b0_zero_margin_holdout/MAY_CC4_BINDING.json'
pr129_raw=subprocess.check_output(['git','show','97ef9cc9b655d93a42b0b43d593aac01b951c6f3:'+pr129_path],cwd=ROOT)
pr129_binding=json.loads(pr129_raw.decode('utf-8-sig'))
assert pr129_binding['interface']['prediction']['sha256']==cc4['prediction_sha']
lineage=[]
for number,head in [(64,'99a1d9d87eb1b6dd76ce41b734af8104099f992f'),
                    (74,'bae7916c759e1c845bb87a8ee0dff761b5db7f7a'),
                    (129,'97ef9cc9b655d93a42b0b43d593aac01b951c6f3')]:
    path='docs/cc4_v21_causal_refit_hurdle/predictions/LGBM_weighted_c1_s20260924.npz'
    if number==129:
        # PR129 contains the immutable external NPZ descriptor, not a duplicate
        # prediction blob in its branch. Its selected row is verified above.
        lineage.append(dict(PR=129,head=head,git_path=pr129_path,
            source='EXACT_BINDING_GIT_BLOB_EXTERNAL_PREDICTION_BYTES_RECHECKED',
            binding_blob_sha256=hashlib.sha256(pr129_raw).hexdigest(),
            prediction_sha256=pr129_binding['interface']['prediction']['sha256'],
            same_as_current_prediction=True,prediction_stored_inside_PR129=False,
            external_prediction=pr129_binding['interface']['prediction'],
            url=f'https://github.com/BeaverVillage/MobileESS/blob/{head}/{pr129_path}'))
        continue
    try:
        raw=subprocess.check_output(['git','show',head+':'+path],cwd=ROOT,stderr=subprocess.PIPE)
        scope='EXACT_LOCAL_GIT_COMMIT_BLOB'
    except subprocess.CalledProcessError:
        descriptor=json.loads(subprocess.check_output(['gh','api','repos/BeaverVillage/MobileESS/contents/'+path+'?ref='+head],cwd=ROOT,text=True,encoding='utf-8'))
        import base64
        raw=base64.b64decode(descriptor['content']);scope='EXACT_GITHUB_COMMIT_BLOB'
    sha=hashlib.sha256(raw).hexdigest();assert sha==cc4['prediction_sha']
    lineage.append(dict(PR=number,head=head,git_path=path,source=scope,prediction_sha256=sha,bytes=len(raw),
        same_as_current_prediction=True,url=f'https://github.com/BeaverVillage/MobileESS/blob/{head}/{path}'))
receipts=[*cc4['source_receipts'],record(TIMING),record(TIMING.parent/'CC4_SERVICE_TIMING_ENVELOPE_AUDIT.json'),
    record(BASE/'A2/A_RESULT.json'),record(BASE/'PLANNING_FREEZE.json'),record(V5),record(SOURCE_AUDIT/'PR64_PR74_SOURCE_AUDIT.json')]
common=dict(schema='CC4_ORIGINAL_SERVICE_SOURCE_AUDIT_D_V1',status='PASS_ORIGINAL_BINDING_REUSED',
    Native_Optimize_calls=0,models_created=0,Actual_runs=0,Fresh_AC_calls=0,ML_fit_calls=0,
    forecast_scaling_or_clipping_calls=0,shared_solver_budget_debit=0,new_A_M_FULL_claim=False,
    B2_B3_campaign_HOLD=True,May31_campaign_started=False,
    original_A2_source_science_sha=freeze['source_sha'],original_A2_case_sha=a['case_sha'],
    original_A2_aidc_anchor=a['aidc_anchor'],source_receipts=receipts,source_functions=source_functions)
write('A2_SERVICE_TIMING_SOURCE_PACKET.json',dict(**common,model_id=cc4['model_id'],
    prediction_sha=cc4['prediction_sha'],prediction_row_sha=cc4['original_selected_row_sha'],kernel_sha=cc4['kernel_sha'],
    q50_hourly_GPUh=cc4['q50_hourly_GPUh'],q90_hourly_GPUh=cc4['q90_hourly_GPUh'],
    extra_hourly_GPUh=(np.array(cc4['q90_hourly_GPUh'])-cc4['q50_hourly_GPUh']).tolist(),
    TRAIN_CDF_lower=lo.tolist(),TRAIN_CDF_upper=hi.tolist(),TRAIN_envelope=record(TIMING),
    kernel_reference=cc4['kernel'],kernel_is_fixed_execution_schedule=False,
    resource_sites=sites,capacities_by_site=bundle['capacities'],
    **{k:a[k] for k in ('CC4_service','CC4_carryout','CC4_reserve_service','CC4_reserve_carryout',
        'nominal_site_GPU','reserve_site_GPU','known_site_GPU','achieved_CC4_reserve_site_GPU','achieved_runtime_reserve_site_GPU')},
    resource_distribution_sha=a['resource_distribution_sha'],recourse_rule='FROZEN_Q50_ALLOCATION_PLUS_Q90_MINUS_Q50_EXTRA_WORK',
    recourse_must_not_reschedule_full_Q50=True,carry_must_not_be_double_counted=True))
write('CC4_V21_HOURLY_TARGET_CONTRACT.json',dict(**common,
    model_id=cc4['model_id'],prediction_sha=cc4['prediction_sha'],prediction_row_index=cc4['prediction_index'],
    prediction_row_sha=cc4['original_selected_row_sha'],prediction_array_shape=[443,24,2],PR_lineage=lineage,
    PR129_binding=dict(head='97ef9cc9b655d93a42b0b43d593aac01b951c6f3',path=pr129_path,
        binding_blob_sha256=hashlib.sha256(pr129_raw).hexdigest(),prediction_sha=pr129_binding['interface']['prediction']['sha256']),
    target_definition='W_Qq[h] = marginal Qq of lifetime GPUh of jobs arriving during hour h, h=0..23',
    hourly_Q50_GPUh=cc4['q50_hourly_GPUh'],hourly_Q90_GPUh=cc4['q90_hourly_GPUh'],
    sum_hourly_Q50_GPUh=float(np.sum(cc4['q50_hourly_GPUh'])),sum_hourly_Q90_GPUh=float(np.sum(cc4['q90_hourly_GPUh'])),
    sum_of_hourly_marginal_Q90_is_daily_total_Q90=False,target_is_instantaneous_GPU=False,
    target_is_remaining_GPU_capacity=False,forecast_hours=24,forecast_resolution_seconds=3600,
    optimizer_slots=96,optimizer_resolution_seconds=900,optimizer_sites=12,
    event30_is_separate_control_event_rule=True,
    PR64_DeepAR_research_selection_promoted=False,PR74_hybrid_replaced_frozen_LGBM=False))
write('CC4_24H_96SLOT_BINDING_AUDIT.json',dict(**common,PASS=True,
    day_begin_seconds=day,issue_seconds=issue,native_slot_offset=24,native_day_slots=[24,120],scenario_summary=scenario_summary,
    per_hour_cohorts=cohorts,capacity_bound=dict(expression='Known + anonymous nominal + achieved CC4 + achieved runtime <= site capacity',
        total_GPU_capacity=780,maximum_original_capacity_violation_GPU=max(0,capacity_error),PASS=True),
    forecast_book_issue_rows=depletion,served_before_for_original_preaday_issue=0,
    formula='sum_t x[h,t] + carryout[h] = remaining W[h]; GPU[t] = 4*sum_h x[h,t]; sum_s GPU[s,t] = GPU[t]',
    mid_replan_formula='served_before + sum_future x + carry = served_before + remaining W; historical service remains in CDF total',
    no_future_UID_or_private_actual_truth_accessed=True))
fixed_reference=profile(cc4['q50_hourly_GPUh'],cc4['kernel'])
write('A_STAGE_SERVICE_TIMING_REUSE_AUDIT.json',dict(**common,PASS=True,
    model_defect_found=False,already_implemented_service_and_carry_preserved=True,
    reuse_chain=['literal LGBM NPZ row412 -> C0_Q50/C0_Q90','PlanningGridContext.bind -> ForecastBook -> bind_forecast',
        'bind_service -> per-hour CDF-constrained GPUh x + carryout','anonymous/arrival_target 12-site partition',
        'bind_headroom -> achieved reserves + original shortfall','C1/grid electricity uses Known+anonymous nominal only'],
    CDF_envelope=dict(source=record(TIMING),rows=len(lo),first_lag=0,last_lag=len(lo)-1,
        cumulative_lower='TRAIN Q10',cumulative_upper='TRAIN Q90',kernel='reference/deviation only, never fixed x'),
    nominal_service_differs_from_fixed_kernel_reference=dict(maximum_GPU_absolute_delta=float(np.max(np.abs(arrays['nominal_site_GPU'].sum(axis=1)-fixed_reference[:96]))),
        slot_equality_required=False,both_full_mass_conserved=True),
    A2_P1='rho maximum original line loading',A2_P2_calls=a['P2_calls'],P1_modified=False,
    achieved_CC4_reserve_GPUh=float(arrays['achieved_CC4_reserve_site_GPU'].sum()*.25),
    achieved_runtime_reserve_GPUh=float(arrays['achieved_runtime_reserve_site_GPU'].sum()*.25),
    CC4_shortfall_GPU_slots=a['CC4_reserve_shortfall_GPU_slots'],runtime_shortfall_GPU_slots=a['runtime_reserve_shortfall_GPU_slots'],
    target_reserve_is_capacity_backed_achieved_reserve=False,target_reserve_is_electrical_load=False,
    fixed_Q90_target_as_occupancy_peak_site_excess_GPU=target_over,
    original_FULL_feasible=a['FULL_feasible'],original_FULL_max_residual=a['FULL_max_residual'],
    control_mismatch=dict(scope='sensitivity_policy._scenarios/compile_sensitivity_policy',
        condition='all(v.hard_feasible for v in evaluation.values()) after adding optimized reserve target as scenario_gpu',
        reason='target is future demand allocation with soft achieved-reserve shortfall, not capacity-backed execution occupancy',
        minimal_new_policy_boundary='keep A2 nominal x/siteGPU/carry; recourse only hourly Q90−Q50 under original service envelope and residual physical capacity',
        PR224_zero_delay_and_past_capacity_fixes='ALREADY_COMPLETED_NOT_REIMPLEMENTED'),
    source_packet=record(OUT/'A2_SERVICE_TIMING_SOURCE_PACKET.json'),elapsed_seconds=time.perf_counter()-started))
(OUT/'Q50_Q90_DEMAND_VS_OCCUPANCY_KO.md').write_text(f'''# CC4 시간별 수요와 A-stage 서비스 배분 — D Native0 감사\n\n원래 CC4 바인딩은 PASS다. 동결 모델은 `LGBM_weighted_c1_s20260924`이며 PR64·74·129의 동일 NPZ SHA `{cc4['prediction_sha']}`를 원본 Commit blob으로 확인했다. PR64의 별도 DeepAR 연구 선택은 현 V42 생산 입력으로 승격되지 않았다. 예측은 24개 시간 각각에 도착할 작업의 lifetime GPUh Q50/Q90이다. 24개 주변 Q90 합계 {sum(cc4['q90_hourly_GPUh']):.6f} GPUh는 하루 총수요의 Q90 분위수가 아니다.\n\n원본 `bind_service`의 x[h,t]는 hour h의 익명 수요 중 slot t에서 처리할 GPUh다. `sum x + carryout = remaining W`를 보존하고 `GPU[t] = 4*sum_h x[h,t]`로 15분 평균 GPU를 계산한다. 12개 사이트 분배 합은 이 값과 같다. 원래 pre-day issue에서는 served_before=0이며 중간 재계획에서는 이미 처리된 서비스가 누적 CDF와 전체 수요의 양쪽에 보존된다.\n\nA2의 Q50 수요·서비스·이월은 각각 {scenario_summary['Q50_NOMINAL']['full_work_GPUh']:.6f}·{scenario_summary['Q50_NOMINAL']['served_within96_GPUh']:.6f}·{scenario_summary['Q50_NOMINAL']['carryout_GPUh']:.6f} GPUh다. Q90−Q50 target의 수요·서비스 시점 목표·이월은 {scenario_summary['Q90_MINUS_Q50_TARGET']['full_work_GPUh']:.6f}·{scenario_summary['Q90_MINUS_Q50_TARGET']['served_within96_GPUh']:.6f}·{scenario_summary['Q90_MINUS_Q50_TARGET']['carryout_GPUh']:.6f} GPUh다. 모든 24개 hour의 질량과 원래 TRAIN Q10/Q90 누적 서비스 범위를 재검증했다. TRAIN kernel은 참조 시점 및 deviation 기준이며 실제 x를 고정하지 않는다.\n\n물리 capacity 식은 Known+Q50 익명 nominal+달성된 CC4 reserve+달성된 runtime reserve≤site capacity다. 저장된 A2 FULL은 유지되며 최대 capacity 위반은 {max(0,capacity_error):.3g} GPU다. 원본 A-stage의 achieved reserve와 target 사이 shortfall은 허용된 모델 항이다. P1은 원래 최대 선로부하율이고 이번 감사는 목적함수를 변경하지 않았다. P2 호출은 {a['P2_calls']}회였다. reserve target을 실제 달성 reserve 또는 전기 부하로 부르면 안 된다.\n\n제어표의 불일치는 target reserve를 고정 Q90 실행 부하로 더하고 모든 scenario의 hard-feasible을 요구한 경계에 있다. A-stage의 서비스·carry 모델이 없어서 생긴 결함이 아니다. 새 D recourse는 저장된 A2 Q50 x·site GPU·carry를 고정하고 Q90−Q50 추가 GPUh만 원래 서비스 범위와 잔여 용량에서 처리한다. 미처리 GPUh는 시점별 backlog와 horizon 종료 carry로 한 번만 계상해야 한다. service carry와 QoS 준수는 별도 판정이며 익명 집계 recourse는 Job별 whole-gang 최적해 증명이 아니다.\n\n이 감사는 Source 및 저장된 A2 산출물을 읽은 Native0 검증이다. 새 모델 생성·Optimize·Actual·Fresh AC·fit·calibration은 0회이며 과거 PR223 Full96/Fresh 증거를 새 정책의 결과로 이전하지 않는다. PR224 수정은 완료된 기존 경계로 유지한다. 새로운 Q90 제어 정책과 E1/E2 계약은 별도 과학 정책이며 새 Full96/Fresh AC는 NOT_RUN이다. B2/B3 및 31일 캠페인 HOLD를 유지한다.\n''',encoding='utf-8')
write('CC4_SERVICE_AUDIT_MANIFEST.json',dict(status='PASS_NATIVE0_ORIGINAL_MODEL_REUSE_AUDIT',
    artifacts=[record(OUT/n) for n in ['CC4_V21_HOURLY_TARGET_CONTRACT.json','CC4_24H_96SLOT_BINDING_AUDIT.json',
        'A_STAGE_SERVICE_TIMING_REUSE_AUDIT.json','Q50_Q90_DEMAND_VS_OCCUPANCY_KO.md','A2_SERVICE_TIMING_SOURCE_PACKET.json']],
    script=record(__file__),Native_Optimize_calls=0,Actual_runs=0,Fresh_AC_calls=0,
    elapsed_seconds=time.perf_counter()-started))
print(json.dumps(dict(status='PASS',scenario_summary=scenario_summary,capacity_error_GPU=capacity_error,
    source_packet=str(OUT/'A2_SERVICE_TIMING_SOURCE_PACKET.json'),elapsed_seconds=time.perf_counter()-started),ensure_ascii=False))

"""Write a HOLD checkpoint after read-only forensics. Does not freeze or generate electrical inputs."""
from pathlib import Path
from datetime import datetime,timezone
import json
import xml.etree.ElementTree as ET
import pandas as pd
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v40h.identity import file_record,manifest,verify_file
from dayahead.v40i.closeout import protected_diff
from dayahead.v40i.electrical import generation_release,git
from dayahead.v40i.dominance import actual_outcome

repo=Path.cwd();root=repo/'dayahead/artifacts/v40i_authority_electrical_closure';dual=root/'dual_forensic';pending=root/'pending_runtime_forensic'
at=datetime.now(timezone.utc).isoformat()
runtime=read(dual/'V40I_H100_COMPLETED_POINT_MODEL_METRICS.json');reactive=read(dual/'V40I_AIDC_REACTIVE_AUTHORITY_FINAL.json')
support=read(dual/'V40I_H100_TRAINING_SUPPORT_FINAL.json');sensitivity=read(dual/'V40I_AIDC_PQ_SENSITIVITY_FORENSIC.json')
penetration=read(pending/'V40I_AIDC_CONTROLLABLE_PENETRATION.json')['cases']['B1']
chain=[
 ('TRAINING POPULATION → POINT PREDICTION','H100 87,319 rows; FAILED 54,057 versus COMPLETED 28,394; source MoE XGBoost reg:absoluteerror',
  'V40I_H100_STATUS_RUNTIME_DISTRIBUTION.json / V40I_H100_FEATURE_VISIBILITY_AUDIT.json','Population mix HIGH; fitted-tree cause NOT PROVEN','Final model/encoder state discarded; FAILED effect PLAUSIBLE_NOT_PROVEN.'),
 ('POINT PREDICTION → POOLED q','Existing completed calibration N=2,562, mean error +7,064s, underprediction64.13%; frozen pooled positive-residual q90=5,576.44921875s',
  'V40I_H100_COMPLETED_POINT_MODEL_METRICS.json','HIGH for saved predictions','Rolling calibration evidence is not an independent final fitted-state holdout.'),
 ('POOLED q → SAFE DURATION','min(requested,max(point+q,900)); ceil to900s. +29 jobs have effective22,500s',
  'V40I_H100_COMPLETED_DIAGNOSTIC_RESIDUAL_QUANTILES.json / ../pending_runtime_forensic/V40I_PENDING_RUNTIME_PREDICTOR_LINEAGE.json','HIGH','No conditional coverage guarantee; diagnostic q not applied.'),
 ('SAFE DURATION → PLANNED OCCUPANCY','Frozen DA service/start/site yields downstream B0 223, B1 182 GPU at slot73',
  '../may01_actual_forensic/DA_VS_ACTUAL_JOB_COMPARISON.parquet','HIGH in modeled domain','D-1 closed cohort excludes later arrivals.'),
 ('PLANNED OCCUPANCY → B1 SITE/TIME DECISION','Saved 539 site changes and461 start changes; primary bound matches optimum; hierarchy preserved',
  '../../v40g_joint_aidc/V40G_MAY01_FINAL_REPORT.json','HIGH historical Planning','No fresh V40I optimization; not a future execution authorization.'),
 ('B1 DECISION + ACTUAL RUNTIME → ACTUAL OCCUPANCY','29 one-GPU jobs run28,577–43,227s; frozen dispatcher with segment migration/conservation',
  'V40I_MAY01_29JOB_H100_TAIL_POSITION.csv / ../may01_actual_forensic/B1_CRITICAL_ACTIVE_UID_SET.json','HIGH for frozen replay','Timing derived from original start/end; physical execution-site authority is separate and not promoted.'),
 ('ACTUAL OCCUPANCY → DOWNSTREAM LOAD','B0 171, B1 173; temporal−2 + spatial9 + interaction−4 + migration−1 = +2 GPU',
  '../pending_runtime_forensic/V40I_SLOT73_FROZEN_DECISION_DECOMPOSITION.json','HIGH exact UID reconciliation','Factorial intermediate dispatch is causal diagnostic, not a certified feasible new policy.'),
 ('DOWNSTREAM GPU → P PROFILE','CENTER incremental GPU power plus C1 PCC model; downstream delta≈1.09545kW',
  '../pending_runtime_forensic/V40I_AIDC_CONTROLLABLE_PENETRATION.json','HIGH within frozen power model','Synthetic power mapping, not independent per-job measured PCC.'),
 ('P PROFILE → Q/P REPRESENTATION','Q=P*tan(acos(.95)), both cases and all namespaces',
  'V40I_AIDC_REACTIVE_MODEL_LINEAGE.json','HIGH code/setpoint identity; physical fidelity OPEN','PCC_Q/readback is derived; no independent facility time-varying Q authority.'),
 ('P/Q REPRESENTATION → FEEDER P/Q FLOW','Frozen IEEE123 model, native mapping, background/PV, regulators/capacitors; existing AC results',
  'V40I_AIDC_PCC_Q_AUTHORITY_AUDIT.json','HIGH simulated lineage','Flow Q is a network response conditioned on prescribed AIDC Q; no measured Q validation.'),
 ('FEEDER P/Q FLOW → PHASE-A CURRENT','Fixed-PF directional gradient predicts+0.14891585A; saved+0.14624173A; mismatch1.8286%',
  'V40I_AIDC_PQ_SENSITIVITY_FORENSIC.json','HIGH saved numbers; approximate differential','AIDC pure P/Q derivatives unavailable; separate-PCC MESS proxies cannot certify AIDC Q partials.'),
 ('PHASE-A CURRENT → rho','Fixed418A rating; Actual B1 rho0.5895856573 versus B0 0.5892357967',
  '../../v40g_joint_aidc/V40G_MAY01_FINAL_REPORT.json','HIGH saved electrical result','Actual outcome sign is scientific result, not an integrity-failure gate.')]
causal=['# V40I 최종 causal chain','',
 '학습 population과 fitted tree의 직접 인과 효과, workload occupancy 역전, 전기 모델 fidelity를 분리한다. 아래 HIGH는 지정한 frozen/simulated scope의 신뢰도다. 물리 현장 측정의 의미로 확장하지 않는다.','',
 '| 연결 | Evidence | Authority artifact | Confidence | Unresolved gap |','|---|---|---|---|---|',
 *['| '+' | '.join(r)+' |' for r in chain],'',
 'Actual timing과 execution-site authority는 별개다. 122 case 중 50개는 timing으로 legitimate pre-day completion을 입증했으나 actual site를 승인한 case는 0개, 72개는 unresolved다. May-01의 historical synthetic replay forensic은 이 72개 production blocker를 해제하지 않는다.','',
 'Runtime/site occupancy 역전은 재현됐다. 고정 PF에 연결된 P/Q 전류 변화도 저장 결과와 근접한다. 다만 이것을 Q를 고정한 순수 P 효과 또는 PF=0.95 현실성 검증으로 바꾸지 않는다.','']
for name in ['V40I_FINAL_CAUSAL_CHAIN.md','V40I_DA_TO_GRID_CAUSAL_CHAIN_AUDIT.md']:(dual/name).write_text('\n'.join(causal),encoding='utf-8')
matrix=[
 ('A Subgroup upper-bound calibration','Pooled q is only67.02 percentile for COMPLETED H100 residual; conditional coverage fails','Independent temporal calibration/test splits; request-family support','Tail coverage matched to causal subgroup','High if May q/coverage guides selection','Medium','Pre-May submission features, end/start, GPU, separate calibration/test','May excluded from fitting/tuning; May01 no longer blind'),
 ('B Point predictor redesign','COMPLETED point error +7,064s, under64.13%; identity visible; multimodal mixtures','Persisted final encoder/tree audit, outcome semantics, conditional/request drift support','Reduce point misfit without using future status','High if May features or model selected for May reversal','Medium/High','Pre-May causal features plus outcomes for labels only; FAILED retained/audited per predeclared target','May01 diagnostic only; use genuinely unseen blocks for confirmation'),
 ('C Robust runtime envelope/reserve','Large positive-residual tail and joint occupancy risk','Predeclared uncertainty set and service/headroom validation','Scheduling protection when runtime uncertainty remains','High if reserve calibrated from May critical slot','High','Pre-May job/feeder joint backtests and untouched stress/test blocks','May not used to size envelope'),
 ('D Hybrid point + conditional bound + reserve','Point misfit, conditional q failure and multiple regimes coexist','All A–C evidence and ablations under one causal protocol','Assess combined forecast/coverage/scheduling tradeoff','High if three components tuned to May outcome','High','Time-separated pre-May train/calibration/validation; locked comparison metrics','Recommended research direction only, no fitted/selected replacement'),
 ('E Retain fixed PF0.95 baseline','Current lineage reproducible; no independent AIDC Q/control authority','Physical PF fidelity remains OPEN; weak Q impact is not proven','Preserve comparability and disclose assumption','Low if PF unchanged','Low','Independent P/Q data needed before any physical accuracy claim','Current frozen baseline retained, not validated by circular PF reconstruction'),
 ('F Exogenous time/load-dependent PF','Possible fidelity question; currently no qualifying measurements','Site/time-aligned independent P/Q or device telemetry and pre-May forecast validation','Represent Q variability without granting control','High if PF chosen to improve May current','Medium','Pre-May signed P/Q with cadence/site/cause; no fixed-PF-derived labels','Future held-out evaluation required; current implementation not authorized'),
 ('G Controllable Q','No qualifying AIDC capability authority found','UPS/STATCOM asset identity, ratedkVA, Qrange, P-Q curve, response/control interval','Only if physically available VAR operation is demonstrated','High if invented capability improves May','High','Equipment contract plus pre-May operating telemetry','NOT AUTHORIZED; MESS/native capacitors not transferable authority')]
method=['# V40I 다음 revision 의사결정','',
 '**권고 연구 방향: HYBRID_PREDICTION_AND_ROBUST_SCHEDULING.** COMPLETED subgroup point misfit를 먼저 조사하고, causal subgroup upper bound와 robust envelope/reserve의 추가 효과를 독립 pre-May 시간 블록에서 비교한다. 구현·fit·q선정·정책 변경은 하지 않았다.','',
 '| 후보 | Supporting evidence | Missing authority | Expected benefit | Leakage risk | Complexity | Required pre-May data | May evaluation boundary |','|---|---|---|---|---|---|---|---|',
 *['| '+' | '.join(r)+' |' for r in matrix],'',
 'COMPLETED/FAILED는 retrospective stratification label이다. Production feature로 넣거나 FAILED를 제거한 모델을 이번 단계에서 학습하지 않는다. 기존 q와 diagnostic subgroup q의 차이는 설명값이며 새 q를 선정한 것이 아니다.','',
 'Runtime 범위의 historical support는 충분하지만 같은 9-feature 조합은 학습에 0개였다. 같은 8-feature 조합 1,501개는 모두48h 요청으로 May12h 요청과 다르다. 이 문제는 final tree state 없이 FAILED 혼합의 직접 효과로 단정할 수 없다.','',
 'Reactive level0 고정 PF는 현재 재현 baseline으로 유지한다. Level1은 독립 time/load-dependent P/Q authority, level2는 추가 장비 P-Q capability/control authority가 필요하다. Q sensitivity가 작다고 입증된 것은 아니며 exact AIDC pure-Q gradient도 없다. 현재 Q control authorization=NO.','',
 'May-01은 이미 원인 분석과 연구 질문 형성에 사용했다. 새 revision에 대해 untouched/blind confirmatory test라고 주장하지 않는다. 모든 May label의 fitting/calibration/parameter selection 사용은 금지하고, 이후 확인 실험은 실제로 아직 보지 않은 사전 고정 evaluation을 사용해야 한다.','',
 '현재 상태: 31-day electrical regeneration HOLD; B0/B1/B2/B3/AIDC/MESS optimization NO; retraining NO; q/PF/Q-control 변경 NO; full-May execution NO. 이 문서는 실행 승인이 아니다.','']
for name in ['V40I_NEXT_REVISION_METHOD_DECISION.md','V40I_NEXT_METHOD_DECISION_MATRIX.md']:(dual/name).write_text('\n'.join(method),encoding='utf-8')

# Recheck all requested file families and deterministic reconciliations.
required_dual=['V40I_H100_STANDBY_POINT_VS_SAFETY_FORENSIC.csv','V40I_H100_STANDBY_POINT_MODEL_METRICS.json',
 'V40I_H100_STANDBY_REQUIRED_MARGIN_DIAGNOSTIC.json','V40I_H100_STANDBY_RUNTIME_DISTRIBUTION.json',
 'V40I_PENDING_RUNTIME_FEATURE_AUDIT.json','V40I_H100_TRAINING_SUPPORT_AUDIT.json','V40I_H100_CALIBRATION_SUPPORT_AUDIT.json',
 'V40I_H100_MAY01_TAIL_POSITION_AUDIT.json','V40I_H100_RUNTIME_ROOT_CAUSE_FINAL.md',
 'V40I_AIDC_REACTIVE_MODEL_LINEAGE.json','V40I_AIDC_PCC_Q_AUTHORITY_AUDIT.json','V40I_AIDC_TIME_VARYING_PF_FORENSIC.json',
 'V40I_AIDC_REACTIVE_CONTROL_CAPABILITY_AUDIT.json','V40I_AIDC_PQ_SENSITIVITY_FORENSIC.json','V40I_DA_TO_GRID_CAUSAL_CHAIN_AUDIT.md',
 'V40I_NEXT_METHOD_DECISION_MATRIX.md','V40I_H100_STATUS_RUNTIME_DISTRIBUTION.json','V40I_H100_COMPLETED_POINT_MODEL_METRICS.json',
 'V40I_H100_COMPLETED_DIAGNOSTIC_RESIDUAL_QUANTILES.json','V40I_H100_FEATURE_VISIBILITY_AUDIT.json',
 'V40I_H100_TRAINING_SUPPORT_FINAL.json','V40I_MAY01_29JOB_H100_TAIL_POSITION.csv','V40I_AIDC_REACTIVE_MODEL_FINAL_AUDIT.md',
 'V40I_AIDC_REACTIVE_AUTHORITY_FINAL.json','V40I_CONTROLLABLE_PENETRATION_FINAL.json','V40I_FINAL_CAUSAL_CHAIN.md','V40I_NEXT_REVISION_METHOD_DECISION.md']
required_dual=sorted(set(required_dual+['V40I_H100_COMPLETED_WALLTIME_REGIME_AUDIT.json','V40I_H100_WALLTIME_CONDITIONAL_SUPPORT.json',
 'V40I_MAY01_29JOB_CONDITIONAL_SUPPORT.csv','V40I_H100_SUPPORT_CONDITIONED_ERROR.json','V40I_H100_POINT_VS_Q_FINAL.json',
 'V40I_H100_RUNTIME_DISTRIBUTION_FINAL.json','V40I_RUNTIME_ROOT_CAUSE_FINAL.md','V40I_AIDC_REACTIVE_LINEAGE_FINAL.json',
 'V40I_AIDC_Q_AUTHORITY_FINAL.json','V40I_FIXED_PF_DIRECTIONAL_SENSITIVITY_FINAL.json','V40I_FINAL_CAUSAL_CLASSIFICATION.json',
 'V40I_FINAL_FORENSIC_REVIEW.md','V40I_NEXT_REVISION_DECISION.md']))
for name in required_dual:assert (dual/name).is_file() and (dual/name).stat().st_size
sums={}
for label,expected in [('RUNTIME_UNDERPREDICTION',29),('RUNTIME_OVERPREDICTION',-3),('ADMISSION_DELAY',-3)]:
 f=pd.read_csv(pending/('V40I_MAY01_SLOT73_PENDING_'+label+'.csv'));sums[label]=int(f.slot73_GPU_contribution.sum());assert sums[label]==expected
factor=pd.read_csv(pending/'V40I_SLOT73_ALL_UID_FACTORIAL_LEDGER.csv')
factor_sums={k:int(factor[k].sum()) for k in ['temporal','spatial','interaction','migration','total']}
assert factor_sums=={'temporal':-2,'spatial':9,'interaction':-4,'migration':-1,'total':2} and len(factor)==1649
assert pd.read_csv(pending/'V40I_MAY01_SLOT73_SPATIAL_EFFECT_LEDGER.csv').delta_downstream_GPU.sum()==9
assert len(pd.read_csv(dual/'V40I_MAY01_29JOB_H100_TAIL_POSITION.csv'))==29
assert abs(penetration['critical_slot73']['CONTROLLABLE_FEEDER_PENETRATION']-.008947578561407063)<1e-14
verified=0
for path in [pending/'V40I_ADDITIONAL_FORENSIC_INPUT_HASHES.json',dual/'V40I_H100_INPUT_HASHES.json',dual/'V40I_REACTIVE_INPUT_HASHES.json',dual/'V40I_COMPLETED_INPUT_HASHES.json',dual/'V40I_CONDITIONAL_INPUT_HASHES.json']:
 evidence=read(path);assert evidence['post_read_hashes_identical']
 for record in evidence['pre_read_records']:verify_file(record);verified+=1
protected=protected_diff(repo);assert protected['status']=='PASS' and protected['protected_file_count']==1779

xml=root/'V40I_FINAL_CLOSURE_REGRESSIONS.xml';suites=ET.parse(xml).getroot().findall('testsuite')
counts={k:sum(int(s.attrib[k]) for s in suites) for k in ['tests','failures','errors','skipped']}
assert counts=={'tests':186,'failures':0,'errors':0,'skipped':0},counts
sources=list((repo/'dayahead/v40i').glob('*.py'))+list((repo/'tests/dayahead').glob('test_v40i_*.py'))
oldreport=root/'V40I_PRE_GENERATION_TEST_REPORT.json';oldcopy=root/'V40I_TEST_REPORT_166_HISTORICAL_BEFORE_FORENSIC.json'
if not oldcopy.exists():oldcopy.write_bytes(oldreport.read_bytes())
previous182=root/'V40I_TEST_REPORT_182_BEFORE_CONDITIONAL.json'
if read(oldreport)['tests']==182 and not previous182.exists():previous182.write_bytes(oldreport.read_bytes())
legacy=read(root/'V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.json')
assert legacy['total']==64 and legacy['reproduced_on_pre_I_source']==64 and legacy['V40I_failures']==0
report={'revision':'V40I','captured_at':at,'status':'PASS','scope':'V40H106 + all V40I80; user-approved166 baseline plus20 additional integrity/forensic regressions',
 'baseline_V40H':106,'new_V40I':80,**counts,'test_result':file_record(xml),
 'test_log':file_record(root/'V40I_FINAL_CLOSURE_REGRESSIONS.log'),'V40I_tested_source_manifest':manifest(sources,repo),
 'broader_repository_status':'FAIL_PREEXISTING_CLASSIFIED','broader_repository_failures':55,'broader_repository_errors':9,
 'broader_repository_failure_classification':file_record(root/'V40I_FULL_REPOSITORY_FAILURE_CLASSIFICATION.json'),
 'generation_scope_clarification_status':'ANSWERED; LATEST_USER_HOLD_ACTIVE_NO_GENERATION',
 'generation_authorized':False,'source_input_freeze_created_by_this_report':False}
write_json(oldreport,report)
hold=read(root/'V40I_ADDITIONAL_FORENSIC_GENERATION_HOLD.json');assert hold['status']=='HOLD'
write_json(root/'V40I_LATEST_FORENSIC_EXECUTION_HOLD.json',{'at':at,'status':'HOLD','latest_request':'27bdafa5-4fad-4ffd-875d-910ceacd193b/pasted-text.txt',
 '31_DAY_ELECTRICAL_REGENERATION':'HOLD','B0_B1_REOPTIMIZATION':'NO','B2_B3_EXECUTION':'NO','FULL_MAY_EXECUTION':'NO',
 'MODEL_RETRAINING':'NO','CALIBRATION_CHANGE':'NO','PF_CHANGE':'NO','Q_CONTROL_CHANGE':'NO',
 'release_after_forensic_automatic':False,'existing_generator_enforced_hold':file_record(root/'V40I_ADDITIONAL_FORENSIC_GENERATION_HOLD.json')})
try:generation_release(repo)
except ValueError as ex:assert 'HOLD' in str(ex);hold_reason=str(ex)
else:raise AssertionError('Generation hold did not reject release')
closure=read(root/'V40I_122_CASE_AUTHORITY_CLOSURE.json')
assert [closure[k] for k in ['TOTAL','LEGITIMATE_PRE_DAY_COMPLETE','ACTUAL_EXECUTION_AUTHORIZED','AUTHORITY_MISSING']]==[122,50,0,72]
authorization={'revision':'V40I','complete_execution_identity':'INCOMPLETE_HOLD','B2_B3_AUTHORIZED':'NO','FULL_MAY_AUTHORIZED':'NO',
 'MAY_31DAY_AUTHORIZED':'NO','FRESH_B0_B1_ACTUAL_EXECUTION_AUTHORIZED':'NO','production_runs_executed':dict.fromkeys(['B0','B1','B2','B3'],0),
 'reason':'72 unresolved actual execution-site authority cases; zero certified V40I electrical days; latest explicit user HOLD.'}
write_json(root/'V40I_EXECUTION_AUTHORIZATION.json',authorization)
gate={'gate':'B0_B1_PLANNING_STRUCTURAL_DOMINANCE','status':'IMPLEMENTED_STATIC_TESTED_NOT_EXECUTED','implemented':True,
 'hard_gate':True,'production_B0_B1_run_executed':False,'requires_separate_future_authorization':True,
 'source':file_record(repo/'dayahead/v40i/dominance.py'),'tests':file_record(repo/'tests/dayahead/test_v40i_dominance.py'),
 'required_condition':'Common D1/service/residual/terminal/electrical/objective identity; include B0 candidate and directly certify feasibility in B1 Planning, J_B1 <= J_B0+tolerance, primary bound certificate, no lower-level primary degradation.',
 'unsupported_constraint_kinds':'FAIL_CLOSED','historical_V40G_May01_Planning_certificate':'PASS; not a fresh V40I execution'}
write_json(root/'B0_B1_PLANNING_STRUCTURAL_DOMINANCE.json',gate)
write_json(root/'B0_B1_ACTUAL_REPLAY_IDENTITY.json',{'gate':'B0_B1_ACTUAL_REPLAY_IDENTITY','status':'NOT_RUN',
 'implemented':True,'hard_gate':True,'Actual_outcome_sign_required':False,'fresh_production_run_executed':False,
 'source':file_record(repo/'dayahead/v40i/dominance.py'),'reason':'Future separately authorized frozen-policy replay only; timing and site authority separate.'})
historical_path=repo/'dayahead/artifacts/v40g_joint_aidc/V40G_MAY01_FINAL_REPORT.json';historical=read(historical_path)
actual=[]
for case in ['B0','B1']:
 r=historical['critical_metrics']['Actual_'+case];actual.append({**r,'current':r['critical_current_A'],'voltage':{'min':r['Vmin'],'max':r['Vmax']},'loading':r['rho']})
write_json(root/'B0_B1_ACTUAL_OUTCOME.json',{'scope':'UNCHANGED_HISTORICAL_V40G_MAY01_NOT_FRESH_V40I','source':file_record(historical_path),**actual_outcome(*actual)})
initial=read(root/'V40I_INITIAL_GENERATION_CHRONOLOGY_AUDIT.json');first=next(r for r in initial['runs'] if '2025-05-01' in r['run'])
freeze=read(root/'V40I_GENERATOR_SOURCE_FREEZE.json')
chronology={'generator_source_commit':initial['initial_generator_commit'],'source_commit_at':initial['source_commit_at'],
 'generation_started_at':first['generation_started_at'],'generation_HEAD':first['generation_HEAD'],
 'admission_at_not_generation_entry':first['run_admitted_at'],
 'pre_generation_source_freeze_filesystem_written_at':initial['freeze_written_at_filesystem'],
 'pre_generation_complete_input_manifest_created_at':None,
 'pre_generation_source_hashes':freeze['source_manifest'],'pre_generation_input_hashes':first['pre_generation_input_hashes'],
 'post_generation_source_input_hashes':first['post_generation_source_input_hashes'],
 'pre_generation_identity_completed_before_start':False,
 'ordering_supported':'source commit -> source-only freeze -> run admission; complete pre identity/exact generator entry not durably proven',
 'classification':'HISTORICAL_UNTRUSTED_GENERATION','original_evidence_preserved':True,'certified_output':False,
 'fresh_regeneration':'NOT_STARTED_LATEST_USER_HOLD','input_source_posthash_cannot_be_retroactively_proven_from_current_hash':True}
write_json(root/'V40I_GENERATION_SEVEN_FIELD_STATUS.json',chronology)
qa={'status':'PASS','at':at,'required_dual_unique_files':len(required_dual),'required_files':[file_record(dual/n) for n in required_dual],
 'UID_GPU_reconciliation':sums,'factorial':factor_sums,'verified_input_records':verified,'protected_files':1779,'regressions':counts,
 'current_generator_hold_verified':hold_reason,'new_production_optimization_runs':0,'new_electrical_generation':0,
 'scientific_source_changes':0,'model_q_PF_changes':0,'authority_case_counts':{k:closure[k] for k in ['TOTAL','LEGITIMATE_PRE_DAY_COMPLETE','ACTUAL_EXECUTION_AUTHORIZED','AUTHORITY_MISSING']}}
write_json(root/'V40I_FORENSIC_FINAL_QA.json',qa)
status={'at':at,'revision':'V40I','status':'FORENSICS_COMPLETE; AUTHORITY_UNRESOLVED; ELECTRICAL_HOLD',
 'forensic_SOURCE_HEAD_before_checkpoint_commit':git(repo,'rev-parse','HEAD'),'not_a_generation_source_freeze':True,
 'authority_counts':qa['authority_case_counts'],'regressions':counts,'broader_preexisting_failures':64,
 'broader_failure_classification_counts':legacy['classification_counts'],'certified_V40I_electrical_days':0,
 'scientific_protected_files_unchanged':1779,'runtime_method_direction':'HYBRID_PREDICTOR_CALIBRATION_ROBUST_RESEARCH_ONLY',
 'Actual_non_dominance_integrity_failure':False,'actual_execution_site_authority_not_inferred_from_timing':True,
 'reactive_fidelity':'OPEN_NO_INDEPENDENT_AIDC_Q_AUTHORITY','new_authorized_optimization_or_generation':False,
 'superseded_reporting':['Basic May01 report conditional regeneration-permitted field is superseded by explicit HOLD.',
   '177 tests were PASS before dual-source additions; final scope now186 PASS.',
   'H100 ALL28.38/28.17 rates are distinct from COMPLETED32.98/32.67 rates and pooled10% uncapped-q rate.',
   'Coupled P/fixed-PF-Q sensitivity must not be labeled pure-P partial.'],
 'reports':{'runtime':str(dual/'V40I_RUNTIME_ROOT_CAUSE_FINAL.md'),'reactive':str(dual/'V40I_AIDC_REACTIVE_MODEL_FINAL_AUDIT.md'),
   'causal':str(dual/'V40I_FINAL_CAUSAL_CHAIN.md'),'method':str(dual/'V40I_NEXT_REVISION_DECISION.md'),'final':str(dual/'V40I_FINAL_FORENSIC_REVIEW.md')},
 'current_authorization':authorization}
write_json(root/'V40I_CURRENT_PREREQUISITE_STATUS.json',status)
p=penetration['critical_slot73'];day=penetration['whole_day'];m=runtime['layers']['point']
text=['# V40I 현재 prerequisite / forensic 상태','',
 '추가 workload·H100 COMPLETED/FAILED·reactive forensic은 완료했다. Production prerequisite는 완료되지 않았다. 31-day electrical regeneration은 HOLD, certified V40I days=0이다.','',
 'Authority122: legitimate pre-day complete50, actual execution authorized0, authority missing72. Timing만으로 site를 승인하지 않았다. 필수 regression186/186 PASS(V40H106+V40I80). 전체 저장소55 failures+9 errors는 변경 전에도 재현된64건으로 분류했으며 전체 저장소 PASS로 주장하지 않는다.','',
 f"COMPLETED H100 N=2,562; point underprediction{m['underprediction_rate']:.4%}, mean signed error+{m['signed_mean_error_seconds']:.3f}s. Pooled q의 conditional coverage 실패와 point misfit가 함께 있다. FAILED mixture의 직접 tree causal effect는 PLAUSIBLE_NOT_PROVEN이다.",'',
 f"B1 slot73: feeder{p['feeder_gross_load_kW']:.6f}kW, AIDC{p['total_AIDC_PCC_kW']:.6f}kW, controllable{p['B1_controllable_load_kW']:.6f}kW, fixed{p['fixed_noncontrollable_AIDC_PCC_kW']:.6f}kW. AIDC/feeder{p['AIDC_PENETRATION']:.4%}, controllable/AIDC{p['FLEXIBLE_AIDC_SHARE']:.4%}, controllable/feeder{p['CONTROLLABLE_FEEDER_PENETRATION']:.4%}. Whole-day energy ratios:{day['AIDC_PENETRATION']:.4%}/{day['FLEXIBLE_AIDC_SHARE']:.4%}/{day['CONTROLLABLE_FEEDER_PENETRATION']:.4%}.",'',
 'AIDC는 fixed PF0.95이고 Q는 시간가변 P에서 파생된다. 독립 facility Q/PF authority와 AIDC Q-control capability는 확인되지 않았다. Fixed-PF fidelity는 OPEN. 현재 Actual outcome 부호는 integrity failure가 아니다.','',
 'UID reconciliation:+29−3−3; frozen-decision decomposition−2+9−4−1=+2 PASS. 보호 대상1,779파일 unchanged. 신규 scientific optimization/retraining/calibration/PF/Q-control/electrical regeneration/B2/B3/full-May 실행 모두 NO.','',
 '상세 보고서: [Runtime](dual_forensic/V40I_H100_RUNTIME_ROOT_CAUSE_FINAL.md), [Reactive](dual_forensic/V40I_AIDC_REACTIVE_MODEL_FINAL_AUDIT.md), [Causal chain](dual_forensic/V40I_FINAL_CAUSAL_CHAIN.md), [Next revision](dual_forensic/V40I_NEXT_REVISION_METHOD_DECISION.md).','']
(root/'V40I_CURRENT_PREREQUISITE_STATUS.md').write_text('\n'.join(text),encoding='utf-8')
print(json.dumps({'QA':qa['status'],'tests':counts['tests'],'authority_missing':72,'electrical':'HOLD','protected_unchanged':1779},ensure_ascii=False))

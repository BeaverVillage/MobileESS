from pathlib import Path
import os,json,hashlib,subprocess,ast
import sys
sys.path.insert(0,'C:/v42_dw_multicolumn_microbenchmark')
os.environ['V42_DW_CLEAN_REVALIDATION']='1'
from v42_dw_harvest.common import ROOT,OUT,OLD,BASE,read,write,sha,table
import gurobipy as gp
native_attempts=[]
def forbidden(*a,**k):
 native_attempts.append('optimize');raise AssertionError('POSTBENCHMARK_NATIVE_OPTIMIZE_FORBIDDEN')
gp.Model.optimize=forbidden
from v42_dw_harvest.finalize import verify_leg
from v42_dw_harvest.prepare import preserved
PAIR=read(OUT/'CONTINUOUS_PAIR_TERMINAL.json')
SOURCE=read(OUT/'SOURCE_FREEZE.json')
assert all(sha(ROOT/p)==h for p,h in SOURCE['files'].items())
assert SOURCE['preregistration_SHA']==sha(OUT/'CLEAN_PREREGISTRATION.json')
assert preserved()==12919
assert read(OUT/'A_STAGE_TERMINAL_BARRIER.json')['PASS']
assert PAIR['continuous_wall_seconds']<=600
assert PAIR['foreign_process_control_calls']==0
assert read(OUT/'MULTICOLUMN_LIGHTWEIGHT_TESTS.json')['PASS']
a,b=verify_leg('BASELINE'),verify_leg('CHALLENGER')
assert all(a[k]==b[k] for k in ['pool_SHA','checkpoint_SHA','true_dual_SHA','search_dual_SHA','starting_columns','U_before'])
for r in [a,b]:
 assert r['metric_wall_includes_freeze_admission_build_audit_cleanup']
 assert r['efficiency']==r['upper_improvement']/r['total_wall_seconds']
 assert r['settings']['Threads']==1
 assert r['Discovery_rounds']==r['RMP_calls']==1 and r['pricing_calls']==4
 assert r['Certification_calls']==r['authoritative_continuation_calls']==r['Branch_and_Price_calls']==0
 assert not r['scientific_certificate_merge']
assert a['total_wall_seconds']+b['total_wall_seconds']<=PAIR['continuous_wall_seconds']
scientific=read(OUT/'MULTICOLUMN_SCIENTIFIC_EQUIVALENCE.json')['PASS']
guards=sum(len(r['resource']['guard_failures']) for r in [a,b])
confirmed=[]
for mode in ['baseline','challenger']:
 state=read(OUT/mode/'PROCESS_OPTIMIZE_STATE.json')
 for event in state['events']:
  for p in event['confirmed_foreign_native']:
   assert p['PID_identity_rechecked'] and p['live_call_proofs'] and p['optimize_state']=='IN_NATIVE_CALL_OR_ITS_CALLBACK'
   assert all(q['sample_pid']==p['pid'] for q in p['live_call_proofs'])
   confirmed.append(dict(mode=mode,PID=p['pid'],create_time=p['create_time'],state=p['optimize_state'],proofs=p['live_call_proofs']))
valid=PAIR['PASS'] and not PAIR['hard_deadline_control'] and all(r['status']=='AUDITED_BENCHMARK' and r['U_after'] is not None and r['original_primal_audit']['PASS'] for r in [a,b])
ratio=b['efficiency']/a['efficiency'] if a['efficiency']>0 else None
threshold=ratio is not None and ratio>=1.2
full_wall_arithmetic_gate=bool(scientific and valid and guards==0 and threshold)
core_a=a['upper_improvement']/a['core_wall_seconds']
core_b=b['upper_improvement']/b['core_wall_seconds']
core_ratio=core_b/core_a if core_a>0 else None
# Keep the registered metric and its outcome intact. The old PR153 timer
# excluded preflight hash checks/cleanup. The new inclusive denominator is
# not comparable to that intended Discovery/RMP metric; do not adopt from it.
scope_validity=False
selected=False
status='MICROBENCHMARK_INCONCLUSIVE'
method=dict(PASS=False,classification='TIMING_SCOPE_CONTAMINATION',
 full_wall_arithmetic_gate_PASS=full_wall_arithmetic_gate,
 registered_metric_not_replaced=True,original_PR153_pipeline_scope_ratio=core_ratio,
 original_PR153_pipeline_scope_improvement_percent=(core_ratio-1)*100,
 original_PR153_pipeline_efficiency_baseline=core_a,original_PR153_pipeline_efficiency_challenger=core_b,
 outside_original_pipeline_seconds_baseline=a['total_wall_seconds']-a['core_wall_seconds'],
 outside_original_pipeline_seconds_challenger=b['total_wall_seconds']-b['core_wall_seconds'],
 reason='Inclusive leg wall added repository hash/admission/cleanup outside the original PR153 Discovery/RMP timer. That overhead was 83.3s versus 7.5s. Full-wall 56.9% improvement cannot establish a comparable 20% algorithm advantage; the original pipeline diagnostic improved only 1.20%. No posthoc substitution as preregistered evidence, no adoption and no rerun.',
 causal_uniqueness_not_claimed=True,authoritative_native_calls=0,additional_native_calls=0)
write(OUT/'TIMING_SCOPE_INDEPENDENT_AUDIT.json',method)
comparison=dict(status=status,MULTICOLUMN_SELECTED=selected,scientific_equivalence=scientific,invalid_admitted_columns=0,guard_interruptions=guards,minimum_efficiency_ratio=1.2,efficiency_ratio=ratio,efficiency_improvement_percent=(ratio-1)*100 if ratio is not None else None,
 full_wall_arithmetic_gate_PASS=full_wall_arithmetic_gate,performance_measurement_validity_PASS=scope_validity,
 original_PR153_pipeline_scope_efficiency_ratio=core_ratio,methodology=method,
 continuous_wall_seconds=PAIR['continuous_wall_seconds'],continuous_wall_cap_seconds=600,baseline=a,challenger=b,confirmed_foreign_native_during_pair=confirmed,authoritative_root_columns=1604,authoritative_root_interval=read(OLD/'DW_CONTINUATION_FINAL_RESULT.json')['final_interval'],authoritative_continuation_calls=0,Certification_calls=0,Branch_and_Price_calls=0,May_production_calls=[0,0,0],single_pair_statistical_superiority_not_claimed=True,replay_calls=0,automatic_extension=False)
write(OUT/'MULTICOLUMN_AB_COMPARISON.json',comparison)
harvest=[];resource=[]
import csv
for mode in ['BASELINE','CHALLENGER']:
 leg=OUT/mode.lower()
 for m in range(4):
  receipt=read(leg/f'live/pricing_receipts/PRICE_{m+1:04d}.json')
  for c in receipt['candidates']:
   harvest.append(dict(mode=mode,MESS=receipt['MESS'],trajectory_SHA=c['column_SHA'],source=c['source'],valid_negative=c['valid_negative'],selected=c['selected'],true_RC=c['rc_inc'],search_RC=c['manual_search_rc'],physical_PASS=c['physical']['PASS'],original_local_PASS=c['full_original_local']['PASS']))
 with (leg/'RESOURCE_LEDGER.csv').open(encoding='utf8',newline='') as f:
  resource += [dict(mode=mode,**r) for r in csv.DictReader(f)]
table(OUT/'COLUMN_HARVEST_LEDGER.csv',harvest);table(OUT/'RESOURCE_LEDGER.csv',resource)
assert not native_attempts
verification=dict(PASS=True,performance_measurement_validity_PASS=False,performance_selection_status=status,lightweight_tests=21,scientific_equivalence=scientific,original_tracked_files_preserved=12919,original_terminal_hash_bindings=2033,read_only_columns_each=1604,same_checkpoint_duals=True,invalid_admitted_columns=0,admitted_columns=a['retained_new_columns']+b['retained_new_columns'],guard_interruptions=guards,confirmed_foreign_native_during_pair=len(confirmed),PID_optimize_state_proof_semantics_PASS=True,continuous_wall_seconds=PAIR['continuous_wall_seconds'],continuous_wall_cap_seconds=600,pricing_calls=8,RMP_calls=2,Threads=1,post_benchmark_optimize_calls=0,authoritative_continuation_calls=0,Certification_calls=0,Branch_and_Price_calls=0,foreign_process_control_calls=0,source_freeze_PASS=True,independent_saved_point_full_original_matrix_audits_PASS=True,pre_native_commit=read(OUT/'CONTINUOUS_PAIR_START.json')['pre_native_commit'])
write(OUT/'VERIFICATION.json',verification)
flags=dict(MULTICOLUMN_SELECTED=selected,status=status,efficiency_ratio=ratio,original_PR153_pipeline_scope_efficiency_ratio=core_ratio,PERFORMANCE_MEASUREMENT_VALIDITY_PASS=False,FULL_WALL_ARITHMETIC_GATE_PASS=full_wall_arithmetic_gate,minimum_efficiency_ratio=1.2,guard_interruptions=guards,SCIENTIFIC_EQUIVALENCE_PASS=scientific,INVALID_ADMITTED_COLUMNS=0,PR152_AUTHORITY_PRESERVED=True,AUTHORITATIVE_ROOT_CONTINUATION_NOT_RUN=True,BRANCH_AND_PRICE_NOT_RUN=True,AUTHORITATIVE_CONTINUATION_CALLS=0,CERTIFICATION_CALLS=0,BRANCH_AND_PRICE_CALLS=0,MAY_PRODUCTION_CALLS=[0,0,0],CONTINUOUS_WALL_SECONDS=PAIR['continuous_wall_seconds'],CONTINUOUS_WALL_CAP_SECONDS=600,Threads=1,NO_REPLAY=True,STOP_AFTER_PAIR=True)
write(OUT/'FINAL_FLAGS.json',flags)
history=ROOT/'docs/v42_m1_dw_multicolumn_microbenchmark'
for name in ['FINAL_FLAGS.json','FINAL_REVIEW_KO.md','VERIFICATION.json']:
 original=subprocess.check_output(['git','show','3d33133e0c4177cb417ee3f03a85cde21f2b43a0:docs/v42_m1_dw_multicolumn_microbenchmark/'+name],cwd=ROOT)
 (OUT/('PR153_PRIOR_'+name)).write_bytes(original)
write(history/'FINAL_FLAGS.json',dict(flags,LATEST_REVALIDATION='clean_revalidation/MULTICOLUMN_AB_COMPARISON.json',prior_guard_interrupted_pair_parent='3d33133e0c4177cb417ee3f03a85cde21f2b43a0'))
write(history/'VERIFICATION.json',dict(verification,LATEST_REVALIDATION='clean_revalidation/VERIFICATION.json'))
lines=[f'Clean PR153 재검증: **{status} / MULTICOLUMN_SELECTED={str(selected).lower()}**.',
 f'PR152 exact head `{BASE}`, immutable1,604-column checkpoint. 각 leg 정확히1Discovery(4 pricing)+1RMP; Threads=1. Alpha=.1/physics/domain/true-dual authority/Certification unchanged.',
 f'A-stage 전용 supervisor/worker 모두 종료 후 시작. 총 continuous pair wall **{PAIR["continuous_wall_seconds"]:.3f}/600s**, clock reset/extension/replay0. Full leg wall includes source-hash checks, resource admission, model builds, candidate/matrix audits and cleanup.',
 '| Metric | Baseline | Challenger |','|---|---:|---:|',
 f'| 새 retained columns | {a["retained_new_columns"]} | {b["retained_new_columns"]} |',
 f'| 끝 pool | {a["ending_columns"]} | {b["ending_columns"]} |',
 f'| Pricing native sum / batch wall (s) | {a["pricing_native_sum_seconds"]:.3f} / {a["pricing_wall_seconds"]:.3f} | {b["pricing_native_sum_seconds"]:.3f} / {b["pricing_wall_seconds"]:.3f} |',
 f'| RMP native (s) | {a["RMP_native_seconds"]:.3f} | {b["RMP_native_seconds"]:.3f} |',
 f'| Full leg wall (s) | {a["total_wall_seconds"]:.3f} | {b["total_wall_seconds"]:.3f} |',
 f'| Audited upper before | {a["U_before"]} | {b["U_before"]} |',
 f'| Audited upper after | {a["U_after"]} | {b["U_after"]} |',
 f'| Audited upper decrease | {a["upper_improvement"]:.12g} | {b["upper_improvement"]:.12g} |',
 f'| Upper decrease / full wall-second | {a["efficiency"]:.12g} | {b["efficiency"]:.12g} |',
 f'| Retained / pricing native minute | {a["retained_per_pricing_native_minute"]:.3f} | {b["retained_per_pricing_native_minute"]:.3f} |',
 f'| Sampled peak RSS GiB | {a["resource"]["sampled_peak_tree_RSS_GiB"]:.3f} | {b["resource"]["sampled_peak_tree_RSS_GiB"]:.3f} |',
 f'| Min available RAM GiB | {a["resource"]["min_available_RAM_GiB"]:.3f} | {b["resource"]["min_available_RAM_GiB"]:.3f} |',
 f'| Max commit % | {a["resource"]["max_commit_percent"]:.3f} | {b["resource"]["max_commit_percent"]:.3f} |',
 f'| Guard interruptions | {len(a["resource"]["guard_failures"])} | {len(b["resource"]["guard_failures"])} |',
 f'Full-wall arithmetic: scientific equivalence PASS; invalid admission=0; guard interruption={guards}; registered full-wall ratio={ratio:.6f}, improvement={(ratio-1)*100:.3f}%. 산술 gate는 통과했지만 timing scope validity FAIL로 selected=false다.',
 f'Timing audit: 기존 PR153 Discovery→RMP timer 구간은 Baseline {a["core_wall_seconds"]:.3f}s / Challenger {b["core_wall_seconds"]:.3f}s; efficiency {core_a:.12g} / {core_b:.12g}, ratio {core_ratio:.6f} (+{(core_ratio-1)*100:.3f}%). 기존 구간 밖 source-hash/admission/cleanup overhead가 83.329s / 7.470s로 달랐다. 포함 범위를 불필요하게 넓힌 측정 때문에 full-wall20%를 신뢰할 만한 알고리즘 개선으로 해석할 수 없다. Registered 값은 보존하며 core diagnostic을 사전 등록 primary로 사후 대체하지 않는다. 성능 선택 결과 INCONCLUSIVE, false 유지, 추가 native 재실행0. 통계적 또는 causal uniqueness를 주장하지 않는다.',
 'Guard는 PID/create_time/native mapping/live source call site를 함께 확인하는 nonblocking observation으로 변경했다. Import/reservation/mock/unobservable 상태만으로 WAIT_RESOURCE 하지 않는다. 샘플 관측의 미관측 구간까지 실제 foreign optimize 부재를 보증하지 않는다.',
 'Lightweight fixtures21/21 PASS; independent original full matrix saved-point audit PASS; inherited12,919 tracked files와 terminal2,033 hash bindings 보존. source freeze PASS. Post-benchmark optimize is monkeypatch-forbidden and attempted calls0.',
 f'Harvested candidates/MESS: Baseline {[m["candidates_encountered"] for m in a["independent_candidate_metrics"]]}, Challenger {[m["candidates_encountered"] for m in b["independent_candidate_metrics"]]}.',
 f'Validated negative/MESS: Baseline {[m["validated_negative_columns"] for m in a["independent_candidate_metrics"]]}, Challenger {[m["validated_negative_columns"] for m in b["independent_candidate_metrics"]]}.',
 f'Duplicate/projection/dominance recount: Baseline {a["independent_candidate_metrics"]}; Challenger {b["independent_candidate_metrics"]}. Batch quota rejection은 duplicate로 계산하지 않았다.',
 'Benchmark 출력은 read-only 개발 snapshot에만 기록했다. Authoritative continuation / Certification / B&P=0; May production0/0/0; 다른 Lane kill/terminate/edit0. PR152의 certified interval/materiality/CG convergence는 그대로다.',
 '이 pair 뒤 STOP. 장시간 root-CG나 추가 native 검증은 실행하지 않았다. PR153 publication/local-remote SHA/clean evidence는 별도 publication receipt와 최종 응답에 기록한다.',
 'PR152의 1,604-column checkpoint는 immutable baseline으로 보존했으며, 동일 checkpoint의 read-only copies에서 기존 방식과 multi-column 방식을 각각 정확히 1 Discovery round + 1 RMP로 비교했다.',
 '이번 실험은 최대 600초의 development microbenchmark이며, 결과를 authoritative D-W root certificate에 합치지 않았다.',
 '선택 기준은 raw column 수가 아니라 audited upper-bound improvement per wall-clock second였다.']
report='\n\n'.join(lines[:3])+'\n\n'+'\n'.join(lines[3:19])+'\n\n'+'\n\n'.join(lines[19:])+'\n'
(OUT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8');(history/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
write(history/'LATEST_REVALIDATION.json',dict(status=status,MULTICOLUMN_SELECTED=selected,scope='clean_revalidation',guard_interruptions=guards,registered_full_wall_efficiency_ratio=ratio,original_PR153_pipeline_efficiency_ratio=core_ratio,performance_measurement_validity_PASS=False,continuous_wall_seconds=PAIR['continuous_wall_seconds'],authoritative_continuation_calls=0,Certification_calls=0,Branch_and_Price_calls=0))
print('CLEAN_INDEPENDENT_FINAL',status,'full-ratio',ratio,'pipeline-ratio',core_ratio,'guards',guards,'wall',PAIR['continuous_wall_seconds'])

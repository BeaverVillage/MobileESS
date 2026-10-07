"""Publish receipt-backed final report after solver shutdown and package audit."""
from practical_support import *
from fractions import Fraction as F
from owned_solver_guard_v4 import owned_controller_alive
import summarize_progress

def run():
    assert remaining(900)<=0,'FINAL_REPORT_RESERVED_FOR_LAST_15_MINUTES'
    assert owned_controller_alive() is None,'SOLVER_MUST_BE_CLOSED_BEFORE_FINAL_REPORT'
    audit=read(OUT/'PACKAGE_AUDIT.json');assert audit['PASS'] and audit['optimize_calls']==0
    assert audit['checkpoint_SHA256']==sha(OUT/'external_production/OPEN_CHECKPOINT.json')
    summarize_progress.run();summary=read(OUT/'ARCHITECTURE_COMPARISON.json')
    checks=read(OUT/'FINAL_TEST_RUNS.json');assert checks['PASS'] and checks['optimize_calls']==0
    monitor=read(OUT/'OWNED_RESOURCE_MONITOR_RESULT.json');assert monitor['PASS']
    summary['resources']['selected_process_lifetime_resources']=monitor
    summary['resources']['peak_known_RSS_including_selected_Windows_lifetime_peak']=max(summary['resources']['peak_completed_receipt_RSS'],monitor['Windows_lifetime_peak_wset'],monitor['observed_peak_RSS'])
    decision=read(OUT/'FINAL_BACKEND_DECISION.json')
    allowed={'M_PRACTICAL_SOLVER_P1_GAP_LE_0P5','M_PRACTICAL_SOLVER_P1_ACCEPTED','M_EXTERNAL_BB_PROMISING_GAP_REMAINS','M_NATIVE_BB_PROMISING_GAP_REMAINS','M_EXACT_BB_TRACTABILITY_FAIL','M_NUMERICAL_INCONCLUSIVE'}
    assert decision['classification'] in allowed
    bounds=summary['current_bounds'];coverage=audit['full_original_incumbent_replay_and_all_node_certificates']['coverage']
    assert float(F(coverage['global_OPEN_min_LB_exact']))==bounds['LB']
    assert float(F(coverage['validated_UB_exact']))==bounds['UB']
    tests={p.name:read(p) for p in sorted(OUT.glob('*TESTS.json'))}
    assert tests and all(r['PASS'] and r.get('optimize_calls',0)==0 for r in tests.values())
    sessions={p.name:read(p) for p in sorted((OUT/'session_results').glob('*.json'))}
    wall_rates={}
    for name,r in sessions.items():
        if r.get('LP_calls_this_session') and r.get('wall_seconds'):
            wall_rates[name]=dict(LP_calls=r['LP_calls_this_session'],wall_seconds=r['wall_seconds'],LP_attempts_per_controller_wall_hour=r['LP_calls_this_session']*3600/r['wall_seconds'],setup_excluded=True)
    natives=[read(p) for p in sorted((OUT/'runs').glob('*/RESULT.json'))]
    stages=dict(M0='기존 ROOT의 수치 정체를 보존하고 운영자 중단. 기존 OPTIMAL ROOT의 정확한 인증을 재사용하여 새 ROOT 재실행 없이 20개 자식 벤치마크 및 OPEN 후속 탐색 완료.',M1='600s 기존 canary 반복 없이 Cuts=0/Heuristics=0 native 대조 1회와 external 성능을 비교.',M2='양쪽 자식, best-bound, 정확한 인증, fixing SHA, checkpoint, crash-safe 복구 및 volatile 독립 감사 캐시를 패키징.',M3='native production 1회가 첫 60분 동안 유효 bound/tree 진전을 보이지 않아 clean stop 후 external로 전환.',M4=f"조건부 primal 개입 {summary['primal_interventions']}회. 노드의 실제 LB 상승 또는 exact fathoming이 없으면 실행하지 않는 등록 gate 적용.",M5='fractional family와 현재 쌍대 row support 분석 후 certified pseudocost/fractionality/dual relevance로 분기 순서 조정. pruning에는 사용하지 않음.',M6='P1 0.5% 목표 및 inherited acceptance가 없으면 P2 실행하지 않음. 원본 energy/count 목적함수와 기존 lock만 사전 준비.',M7='재시작 가능한 전체 OPEN proof ledger, full original replay, source identity, 독립 감사 CLI 및 exactness fixture 제공.',M8=decision['classification'])
    result=dict(UTC=stamp(),classification=decision['classification'],decision=decision,scientific_base_PR=177,scientific_base_HEAD='b86486a6f58d6c39a1ea4ff2c7e984372b6087a5',scientific_authority_PR=162,identity=audit['identity'],objective_identity_PASS=True,objective='minimize rho',scientific_model_modifications=0,initial=dict(LB=INITIAL_LB,UB=INITIAL_UB,gap=(INITIAL_UB-INITIAL_LB)/abs(INITIAL_UB)),final=bounds,full_original_incumbent_replay_PASS=True,complete_OPEN_coverage=coverage,stages=stages,native_runs=natives,external=summary['external'],external_session_wall_throughput=wall_rates,resources=summary['resources'],tests=tests,primal_interventions=summary['primal_interventions'],P2_executed=summary['P2_executed'],P2_preparation=read(OUT/'P2_AUTHORITY_PREPARATION.json'),root_import=read(OUT/'ARCHIVED_ROOT_LP_CERTIFICATE_AUDIT.json'),numerical_conditioning=read(OUT/'ROOT_CONDITIONING_AUDIT.json'),independent_package_audit_SHA256=sha(OUT/'PACKAGE_AUDIT.json'),immutable_deadline=read(OUT/'IMMUTABLE_DEADLINE.json'),reporting_git_HEAD=git('rev-parse','HEAD'),final_publication_HEAD_policy='Final commit HEAD, remote match and clean tree verified after report commit; reported in PR body and chat to avoid a self-referential commit hash',Draft_PR_URL='https://github.com/BeaverVillage/MobileESS/pull/179',native_tree_restartable=False,external_OPEN_queue_restartable=True)
    atomic(OUT/'RESULT.json',result)
    ledger=read(OUT/'GLOBAL_BOUND_LEDGER.json');trajectory=[dict(ledger['initial'],authority='INITIAL_VERIFIED_REFERENCE')]+ledger['events']+[dict(UTC=result['UTC'],LB=bounds['LB'],UB=bounds['UB'],gap=bounds['gap'],authority='FINAL_ALL_OPEN_MIN_AND_ORIGINAL_INCUMBENT_REPLAY')]
    start=datetime.fromisoformat(result['immutable_deadline']['task_start_UTC'])
    for event in trajectory:event['wall_seconds_from_immutable_start']=(datetime.fromisoformat(event['UTC'])-start).total_seconds()
    table(OUT/'GLOBAL_BOUND_TRAJECTORY.csv',trajectory)
    rows=[]
    for name,r in sessions.items():
        if 'UTC' in r:rows.append(dict(UTC=r['UTC'],session=name,processed=r.get('processed'),calls=r.get('LP_calls_this_session'),wall_seconds=r.get('wall_seconds'),global_LB=r.get('coverage',{}).get('global_OPEN_min_LB_exact'),gap=r.get('coverage',{}).get('global_gap')))
    table(OUT/'SESSION_TRAJECTORY.csv',sorted(rows,key=lambda r:r['UTC']))
    native_table=['| 실행 | 상태 | Runtime s | Work | nodes | ROOT 누적 s | 첫 nonroot s | peak RSS bytes |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in natives:native_table.append(f"| {r['name']} | {r['Status']} | {r['Runtime']:.3f} | {r['Work']:.3f} | {r['NodeCount']} | {r['times']['root_complete']} | {r['times']['first_nonroot']} | {r['peak_RSS']} |")
    child_table=['| 자식 LP 설정 | 시도/OPTIMAL | 중앙값 s | p90 s | raw 행 replay PASS | 최대 raw 행 위반 | LP 목적값−exact 인증 중앙값 |','|---|---:|---:|---:|---:|---:|---:|']
    for name,r in summary['external']['by_configuration'].items():child_table.append(f"| {name} | {r['attempts']}/{r['OPTIMAL']} | {r['median_Runtime']:.3f} | {r['p90_Runtime']:.3f} | {r['raw_original_relaxed_replay_PASS']} | {r['max_original_row_violation']} | {r['median_native_objective_to_exact_bound_loss']} |")
    rate_table=['| external 세션 | LP 호출 | controller wall s | LP 시도/시간 |','|---|---:|---:|---:|']
    for name,r in wall_rates.items():rate_table.append(f"| {name} | {r['LP_calls']} | {r['wall_seconds']:.3f} | {r['LP_attempts_per_controller_wall_hour']:.3f} |")
    stage_text='\n'.join(f'- **{k}**: {v}' for k,v in stages.items())
    text=f'''# M-stage practical exact solver 야간 최종 검토

**{result['classification']}**. 최종 유효 LB는 **{bounds['LB']:.16f}**, UB는 **{bounds['UB']:.16f}**, 전역 gap은 **{bounds['gap']*100:.9f}%**입니다. 원본 C3A/route/SOC/PQ/PCS/grid/A1 incumbent replay 및 모든 OPEN 분할 감사는 PASS입니다. 목표 달성 여부: {summary['target_met']}. P2 실행: {summary['P2_executed']}.

| 지표 | 초기 | 최종 | 변화 |
|---|---:|---:|---:|
| LB | {INITIAL_LB:.16f} | {bounds['LB']:.16f} | +{bounds['LB_gain']:.17g} |
| UB | {INITIAL_UB:.16f} | {bounds['UB']:.16f} | 개선 {bounds['UB_gain']:.17g} |
| gap | {(INITIAL_UB-INITIAL_LB)/abs(INITIAL_UB)*100:.9f}% | {bounds['gap']*100:.9f}% | GLOBAL_BOUND_TRAJECTORY.csv |

## 과학적 권한과 범위

PR177 `{result['scientific_base_HEAD']}`에서 분기했으며 PR162 selected C3A의 `minimize rho`를 유지했습니다. objective coefficients/ObjCon/변수 축의 bit identity를 독립 Git blob reader로 검증했습니다. objective hash `{audit['identity']['objective']}`. full MILP에는 원본 types/bounds/physics를 유지하고, external LP에는 원본 B relaxation 및 경로에 기록한 0/1 bound fixing만 적용했습니다. T1, 새 cuts, objective 교체, May/A-stage/downstream 실행은 없습니다.

## 단계 결과

{stage_text}

## Backend 비교

{chr(10).join(native_table)}

Native node 수에는 ROOT가 포함됩니다. first branch는 API에서 최초로 관측한 상한 시각이며 정확한 내부 branch 시각으로 주장하지 않습니다. ROOT LP, barrier/crossover/presolve와 first MIPNODE 세부 시각은 각 RESULT.json 및 원본 log에 있습니다. native control의 post-root 정체를 strong-branching/probing으로 단정하지 않습니다.

{chr(10).join(child_table)}

{chr(10).join(rate_table)}

위 external wall은 controller loop이며 startup build/첫 restart 감사는 제외합니다. 전체 작업 wall은 아래 자원 항목에 별도로 기록했습니다. Native Runtime 기준 처리율과 wall 기준 처리율을 혼동하지 않습니다. 서로 다른 child fixing domain이므로 paired warm-start 또는 cache speedup을 주장하지 않습니다.

Basis supplied/accepted는 {summary['external']['basis_supplied']}/{summary['external']['basis_accepted']}입니다. 두 warm child는 구조적 basis를 수용했지만 TIME_LIMIT와 큰 원본 잔차 및 Kappa 약 1e16 때문에 깨끗한 optimal parent basis로 인정하지 않았습니다. Crossover=0 cold 경로는 basis를 공급하지 않으며 새로운 basis 생성도 주장하지 않습니다. tighter BarConvTol 1회는 SUBOPTIMAL로 끝나 인증을 거부하고 해당 OPEN domain을 원본 byte archive와 함께 cold 경로로 넘겼습니다.

원본 raw primal replay 실패가 있어도 OPTIMAL 이후 sign-clipped exact bounded-Lagrangian 인증은 모든 원본 feasible point에 유효한 하한입니다. LP 목적값이나 infeasible/fractional point는 LB/UB로 사용하지 않았습니다. `CERTIFICATE_LOSS_ATTRIBUTION.json`은 injection_P/Q stationarity 잔차와 넓은 변수 경계가 인증값 손실을 증폭하는 것을 보여줍니다. arithmetic-only injection 등식 보정은 저장된 인증값을 개선했지만 inherited LB를 넘지 않아 production/OPEN에 적용하지 않았습니다.

## 현재 proof 상태와 재시작

생성 노드 {summary['external']['generated_nodes']}, 처리 {summary['external']['processed_nodes']}, OPEN {len(summary['external']['OPEN_ids'])}, unresolved OPEN {summary['external']['unresolved_retained_OPEN']}. pruning counts: `{summary['external']['prune_counts']}`. 양쪽 자식을 모두 유지하고 전역 LB를 모든 OPEN의 최솟값으로 계산합니다. heuristic 분기 점수는 pruning 근거가 아닙니다.

`selected_external_controller.py`와 `OPEN_CHECKPOINT.json`은 실제 OPEN 큐 복구를 지원합니다. `package_audit.py`는 native optimize를 차단하고 원본 배열의 모든 인증/현재 incumbent/fixing-history/SHA를 독립 감사합니다. volatile arithmetic cache는 감사의 동일 수학 입력만 재사용하며 재시작 시 비웁니다. 원래 oracle의 첫 인증 계산은 캐시하지 않습니다. 원본 증명 파일과 모든 입력 hash/replay는 계속 확인합니다. native Gurobi tree는 재시작 가능하다고 주장하지 않습니다.

Primal 개입 {summary['primal_interventions']}회. restricted neighborhood ObjBound를 전역 LB로 사용한 사례는 없습니다. P2 목적함수 energy→count와 inherited `P1_EPS=1e-7`, `COMPONENT_EPS=1e-8`만 준비했으며 acceptance gate 없이 실행하지 않았습니다.

## 자원, 검증 및 한계

Native production의 raw derived LB에 CLI 소수 반올림 문제가 있었으나 그 값을 전역 ledger에 채택하지 않았습니다. `DERIVED_GLOBAL_LB_CORRECTION.json`과 독립 감사의 정확한 native ObjBound를 사용합니다. 또 과거 cold-dual receipt의 infinite parameter sentinel 정규화 오류는 원본 checkpoint byte를 보존하고 optimize=0으로 고쳤습니다. 모델이나 수학적 bound를 바꾸는 복구는 아닙니다.

완료 receipt Native Runtime 합계 **{summary['resources']['completed_receipt_native_Runtime_sum']:.3f}s**, Work 합계 **{summary['resources']['completed_receipt_Work_sum']:.3f}**, 완료 receipt peak RSS **{summary['resources']['peak_completed_receipt_RSS']} bytes**. 새 완료 optimize 호출 {summary['resources']['new_completed_optimize_calls']}. 보고 시점 task wall **{summary['resources']['wall_elapsed_from_immutable_start']:.3f}s**. 고정 시작 `{result['immutable_deadline']['task_start_UTC']}`, deadline `{result['immutable_deadline']['deadline_UTC']}`. build/replay/audit/Git 게시도 이 한 기한에 포함됩니다.

기존 M0는 야간 시작 전부터 실행되었고 native 최종 status/Runtime/Work가 없어 partial elapsed 및 process CPU/RSS를 `M0_OPERATOR_ABORTED.json`에 별도로 보존했습니다. partial lifetime을 새 완료 Runtime 합계에 더하지 않았습니다. 기존 archived ROOT의 251.318s/481.275 Work 역시 이번 새 실행 비용에서 제외했습니다. 따라서 Runtime 합계는 wall과 같지 않습니다.

{len(tests)}개 fixture 묶음 PASS, 모두 optimize=0. 원본 full replay, 완전한 binary partition, unresolved 보존, exact pruning, deterministic tie, crash 단계별 복구, SHA/fixing/receipt 변조 거부, owned-process 구분, known-witness proof conflict 및 one-bit arithmetic-cache invalidation을 확인했습니다. `PACKAGE_AUDIT.json`과 RESULT.json에 개별 근거가 있습니다.

남은 병목: {decision['remaining_bottleneck']}

선정 설정: {decision['recommended_configuration']}

다음 한 가지 권고: {decision['next_action']}

## Git 전달

[Draft PR179](https://github.com/BeaverVillage/MobileESS/pull/179), PR177 위에 stacked. 이 파일의 reporting HEAD는 `{result['reporting_git_HEAD']}`이며 final commit HEAD·remote match·clean tree는 보고서 commit/push 후 PR 본문과 최종 답변에서 확인합니다. 자체 commit SHA를 자기 파일에 삽입하는 순환을 만들지 않습니다. SHA256_MANIFEST.json은 모든 최종 package 파일의 raw bytes를 결속합니다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    print(json.dumps(dict(classification=result['classification'],bounds=bounds,PR=result['Draft_PR_URL'])))

if __name__=='__main__':run()

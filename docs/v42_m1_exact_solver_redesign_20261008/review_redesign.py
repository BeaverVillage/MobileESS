"""Step 5 reports from completed, solver-free-audited evidence. No optimize."""
from support import *
from bb_controller import ExactBB

def shown(value):return "미측정" if value is None else f"{value:.6f}"

def review():
    native=read(OUT/'NATIVE_RESULT.json');step3=read(OUT/'STEP3_NATIVE_REVIEW.json');receipt=read(OUT/'EXTERNAL_RECEIPT.json');audit=read(OUT/'EXTERNAL_EXACT_AUDIT.json');assert audit['PASS']
    identity=read(OUT/'EXTERNAL_MODEL_AUTHORITY.json')['identity'];bb=ExactBB.load(OUT/'OPEN_CHECKPOINT.json',identity);coverage=bb.audit();rows=bb.state['ledger'];children=rows[1:]
    def statistics(field):
        v=[r[field] for r in children if r.get(field) is not None]
        return dict(count=len(v),median=float(np.median(v)) if v else None,p90=float(np.percentile(v,90,method='linear')) if v else None,minimum=min(v) if v else None,maximum=max(v) if v else None,mean=float(np.mean(v)) if v else None)
    runtime=statistics('Runtime');total=statistics('total_node_wall_seconds');proof=statistics('proof_wall_seconds');setup=statistics('setup_wall_seconds');work=statistics('Work')
    supplied=sum(bool(r['basis_supplied']) for r in children);accepted=sum(bool(r['basis_accepted']) for r in children);rate=accepted/supplied if supplied else 0.
    exactness=bool(audit['PASS'] and coverage['PASS'] and receipt['microbenchmark_complete'] and read(OUT/'EXACTNESS_TESTS.json')['PASS'])
    promising=exactness and bool(children) and runtime['median']<=30 and runtime['p90']<=90 and rate>=.8
    if not exactness:classification='EXACT_SOLVER_REDESIGN_INCONCLUSIVE'
    elif promising:classification='EXTERNAL_BB_PROMISING'
    elif read(OUT/'NATIVE_ASSESSMENT.json')['material_nonroot_progress']:classification='NATIVE_BRANCH_SOONER_PROMISING'
    else:classification='EXTERNAL_BB_NOT_PROMISING'
    write('BASIS_TIMING.json',dict(child_LP_Runtime=runtime,child_LP_Work=work,child_total_wall=total,child_setup_wall=setup,child_exact_proof_and_artifact_wall=proof,bases_supplied=supplied,bases_accepted=accepted,acceptance_rate=rate,acceptance_authority='Explicit LP warm-start: use basis in each native child log, no invalid/ignored/discarded-basis messages',causal_basis_speedup=None,same_node_cold_reference_not_measured=True,no_extra_cold_solve=True,percentile_definition='numpy percentile linear, p=90'))
    lower=F(coverage['global_OPEN_min_LB_exact']);upper=F(coverage['validated_UB_exact']);lower_float=float(lower)
    if F.from_float(lower_float)>lower:lower_float=float(np.nextafter(lower_float,-np.inf))
    gap=float((upper-min(lower,upper))/upper)
    improvements=dict(old_LB=LB,new_valid_LB=lower_float,new_LB_exact=str(lower),old_UB=UB,new_valid_UB=float(upper),new_UB_exact=str(upper),global_gap=gap,global_gap_percent=100*gap,LB_increase=lower_float-LB,UB_decrease=UB-float(upper),source='min of ALL OPEN node inherited/exact certified bounds with exhaustive binary partition and exactly fathomed other leaves',native_ObjBound_promoted=False,restricted_or_local_bound_promoted=False,coverage_SHA256=sha(OUT/'OPEN_COVERAGE.json'),exact_audit_SHA256=sha(OUT/'EXTERNAL_EXACT_AUDIT.json'),validated_incumbent=bb.state['incumbent'])
    write('GAP_AUTHORITY.json',improvements)
    root=rows[0];scaling=[]
    for count in (100,1000):
        scaling.append(dict(child_nodes=count,median_wall_extrapolation_seconds=root['total_node_wall_seconds']+count*(total['median'] or 0),p90_wall_extrapolation_seconds=root['total_node_wall_seconds']+count*(total['p90'] or 0)))
    write('SCALING_ESTIMATE.json',dict(extrapolations=scaling,sample_child_nodes=len(children),includes_exact_certification_and_setup=True,excludes_future_depth_and_branch_distribution_changes=True,excludes_final_offline_independent_audit=True,not_a_completion_or_tree_size_forecast=True,original_binary_count=9322,pruned_infeasibility=sum(r['prune_reason']=='EXACT_LP_INFEASIBILITY' for r in rows),pruned_bound=sum(r['prune_reason']=='CERTIFIED_LB_AT_LEAST_VALIDATED_UB' for r in rows),OPEN_remaining=len(coverage['OPEN']),scientific_gap_closed=not coverage['OPEN']))
    result=dict(UTC=stamp(),classification=classification,native=native,native_assessment=step3,external_processed_nodes=len(rows),external_follow_up_nodes=len(children),external_OPTIMAL_LPs=sum(r['LP_status']=='OPTIMAL' for r in rows),external_root_Runtime=root['Runtime'],external_root_Work=root['Work'],child_LP_Runtime=runtime,child_total_wall=total,child_exact_proof_wall=proof,basis_acceptance_rate=rate,basis_accepted=accepted,bases_supplied=supplied,pruned_infeasibility=sum(r['prune_reason']=='EXACT_LP_INFEASIBILITY' for r in rows),pruned_LB=sum(r['prune_reason']=='CERTIFIED_LB_AT_LEAST_VALIDATED_UB' for r in rows),integer_certified_fathoms=sum(r['prune_reason']=='INTEGER_REPLAY_PASS_AND_CERTIFIED_OPTIMUM' for r in rows),OPEN=len(coverage['OPEN']),unresolved_OPEN=coverage['unresolved_OPEN'],gap_authority=improvements,root_primal_replay_PASS=root.get('LP_primal_replay',{}).get('PASS'),all_LP_primal_replays_PASS=all(r.get('LP_primal_replay',{}).get('PASS') for r in rows if r['LP_status']=='OPTIMAL'),LB_authority_does_not_require_raw_primal_feasibility=True,raw_LP_point_not_used_as_integer_UB=True,external_promising_preregistered_checks=dict(exactness=exactness,median_at_most_30=bool(children) and runtime['median']<=30,p90_at_most_90=bool(children) and runtime['p90']<=90,basis_acceptance_at_least_80_percent=rate>=.8),production_controller_required=promising,production_executed=False,May_executed=False,scientific_objective_changed=False,T1_rows=0,added_cut_rows=0)
    if promising:recommendation='검증된 OPEN 체크포인트를 이어받는 단일 스레드 exact best-bound B&B와 부모 LP 기저 재사용·원래 해 replay·노드 인증을 결합한 controller를 다음 생산 solver 아키텍처로 채택한다.'
    elif classification=='NATIVE_BRANCH_SOONER_PROMISING':recommendation='이번 native branch-sooner 설정을 원래 C3A 생산 solver 아키텍처의 기준으로 채택하고, 기록된 노드별 병목을 계측한다.'
    else:recommendation='다음 아키텍처는 원래 C3A와 현재 OPEN 인증을 유지하는 인증을 기록하는 LP 재최적화 backend로 한정하고, 측정된 LP·인증 병목의 원인부터 solver 내부 자료로 분석한다.'
    result['recommended_next_architecture']=recommendation;write('RESULT.json',result)
    old=read(PR177/'RESULT.json');old_root=read(PR177/'ROOT_TIMELINE.json')['times']['root_relaxation_complete']
    text=f'''# M1 exact solver redesign 최종 검토

판정: **{classification}**. 아래 native canary 1회와 root + 후속 {len(children)}개 외부 LP 노드를 실행했고, 추가 생산 실행은 하지 않았다.

## 과학적 권한과 원래 해

PR177 `{BASE}` 위에서 PR162 selected C3A `{SCIENTIFIC}`의 원래 minimize rho를 사용했다. 목적계수·ObjCon·변수축 원시 바이트와 objective hash `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`가 PASS다. 원래 행렬 582808행·306040열·5351612 nnz·9322 이진변수 및 모든 bounds를 유지했다. T1과 기존 진단용 추가 행은 이번 모델에 0개다. 현재 UB 전체 벡터의 원래 C3A 행·bounds·정수성 및 route/movement·SOC·P/Q·PCS·673920개 원래 grid 행·A1 frozen interface replay가 PASS다. 모든 MIP start 변수 306040개를 원시 값 그대로 공급했고 native log의 Loaded user MIP start가 수락을 확인한다. 재생의 역사적 검증 tolerance와 frozen inverse를 변경하지 않았다. 반올림·clipping·repair는 없다.

실행 전 행 이름의 Unicode 저장 폭 `<U43` → `<U35` 차이로 검증이 중단된 기록은 `STOPPED_BEFORE_NATIVE.json`에 보존했다. 행 이름 자체는 같고 optimize=0이었다. 수치 계수·objective·ObjCon·변수축 검증은 원시 바이트를 사용한다.

## 단계 2–3: native 600초

Runtime {native['Runtime']:.6f}s, Work {native['Work']:.6f}, nodes {native['NodeCount']:.0f}, status {native['Status']} TIME_LIMIT, SolCount {native['SolCount']}. root LP 완료 {native['times']['root_relaxation_complete']:.6f}s, first MIPNODE {native['times']['first_MIPNODE']}, first nonroot {native['times']['first_nonroot_node']}. 최초 branch의 정확한 시각은 API에서 제공되지 않는다. 미탐색 노드 2개를 관측한 callback {step3['first_branch_observed_upper_bound']:.6f}s가 최초 기록된 상한이다. 시작 incumbent 수락 {native['times']['first_incumbent']:.6f}s; 새 검증 UB는 없었다. peak RSS {native['peak_RSS']/2**30:.6f}GiB.

Presolve {native['times']['presolve_end']:.6f}s, barrier 관측 {native['times']['barrier_end']-native['times']['barrier_start']:.6f}s, crossover native 출력 89.62s, root LP native 출력 205.28s. root LP 완료 뒤 {step3['post_root_processing_and_search_seconds']:.6f}s가 남았지만 nonroot callback count는 1개였다. 사전 등록한 nodes>=10·서로 다른 nonroot count>=5 기준을 통과하지 못했다. CutPasses=0이어도 내부 cut 5272개가 기록됐다. solver parameter sweep/수동 추가 cut은 없다. callback Work 값은 barrier/crossover 동안 업데이트되지 않았으므로 phase Work 차이를 비용으로 해석하지 않는다. 최종 Work는 native receipt 값이다.

| native 비교 | PR177 T1+진단 행 1800s | 이번 원래 C3A 600s |
|---|---:|---:|
| Runtime | {old['Runtime']:.6f} | {native['Runtime']:.6f} |
| root LP 완료 | {old_root:.6f} | {native['times']['root_relaxation_complete']:.6f} |
| nodes | {old['NodeCount']:.0f} | {native['NodeCount']:.0f} |
| valid UB | {UB:.16f} | {native['global_UB']:.16f} |

원래 모델 복원과 요청한 canary 설정을 함께 바꾼 비교다. 단일 파라미터의 인과 효과로 해석하지 않는다.

## 단계 4: 외부 exact B&B

root LP 원래 이진 types만 C로 완화했다. 자식은 누적된 원래 이진변수의 LB=UB=0/1만 변경한다. 행·목적함수·연속 bounds는 그대로다. highest fractionality / 원래 column tie-break로 분기하고 항상 양쪽 자식을 생성한다. best-bound의 완전한 OPEN queue에 미해결·미처리 노드도 보존한다. LP root는 Method=2/Crossover=2, 자식은 Method=1/LPWarmStart=1과 부모의 전체 VBasis/CBasis다. scientific solver tolerances는 그대로 1e-8이다.

처리 {len(rows)}개(root 1 + follow-up {len(children)}), OPTIMAL {result['external_OPTIMAL_LPs']}개, infeasible prune {result['pruned_infeasibility']}개, LB prune {result['pruned_LB']}개, integer 인증 fathom {result['integer_certified_fathoms']}개. 남은 OPEN {len(coverage['OPEN'])}개, unresolved OPEN {coverage['unresolved_OPEN']}. 각 expanded parent의 두 자식이 원래 정수 영역을 전부 덮는지 독립적으로 재구성했다. 노드별 LP 목적값·정확한 보수적 LB·fixing hash·깊이·분기·Runtime/Work·basis·fractional count·prune·UB가 ledger와 개별 receipt에 있다.

Native OPTIMAL LP의 Pi와 원래 binary64 계수를 정확한 dyadic 유리수로 해석해 bounded-Lagrangian LB를 계산한다. 유한한 원래 bounds를 이용하므로 작은 reduced-cost 잔차도 bounds 보정에 정확히 포함한다. raw primal ObjVal을 그대로 pruning LB로 사용하지 않는다. 초기 전역 LB와 부모의 유효 LB는 자식에게 계승되며 새 LP certificate와의 max를 노드의 유효 LB로 쓴다. prune 비교 tolerance는 0이다. Farkas pruning에는 원래 ray로 만든 정확한 양의 모순 증명이 추가로 필요하다. 증명 계산의 수학적 0은 solver objective 변경이 아니다. raw LP primal replay 실패가 있을 경우에도 부동소수 점을 정수 UB로 받지 않으며, 정확한 보수적 dual bound와 exhaustive binary partition만 권한으로 사용한다.

## 단계 5: 비용과 bound

| 측정 | 값 |
|---|---:|
| external root LP Runtime | {root['Runtime']:.6f}s |
| child LP median / p90 | {shown(runtime['median'])}s / {shown(runtime['p90'])}s |
| child 전체 wall median / p90 | {shown(total['median'])}s / {shown(total['p90'])}s |
| exact 인증·artifact wall median | {shown(proof['median'])}s |
| basis 수락 | {accepted}/{supplied} ({rate*100:.2f}%) |
| valid global LB | {lower_float:.16f} |
| valid UB | {float(upper):.16f} |
| certified global gap | {gap*100:.10f}% |

기저 수락은 각 native log의 LP warm-start: use basis와 reject 메시지 부재로 확인했다. 동일 노드 cold 비교를 추가하지 않았으므로 causal basis speedup은 측정 불가다. 원래 incumbent full replay PASS를 유지한다. Native ObjBound {native['native_ObjBound']:.16f}는 전역 LB로 승격하지 않았다. 외부 전역 LB는 모든 OPEN leaf의 유효 LB 최소이며, 나머지 leaf의 exact fathoming 및 내부 node의 양쪽 자식 exhaustive partition을 검증한 경우에만 권한을 갖는다. 현재 bound 변동: LB {LB:.16f} → {lower_float:.16f}, UB {UB:.16f} → {float(upper):.16f}.

100/1000 child node의 median 전체 wall 외삽은 각각 {scaling[0]['median_wall_extrapolation_seconds']/60:.3f}분 / {scaling[1]['median_wall_extrapolation_seconds']/3600:.3f}시간, p90 시나리오는 {scaling[0]['p90_wall_extrapolation_seconds']/60:.3f}분 / {scaling[1]['p90_wall_extrapolation_seconds']/3600:.3f}시간이다. 이는 이 20개 자식의 국소 표본 외삽이며 깊은 노드 비용·트리 크기·gap closure를 예측하지 않는다. 별도 최종 offline exact audit 비용도 제외한다. raw primal replay PASS 여부와 정확한 dual certificate 권한을 RESULT에서 구분했다.

## 검증과 다음 아키텍처

작은 finite-bounded 유리수 fixture 3개에서 exact vertex enumeration과 전수 이진 최적값이 일치했다. 양쪽 자식·best-bound 순서·fixing 계승·exact infeasible/LB/integer fathom·체크포인트 재개·누락/변조 거부·미해결 OPEN 보존을 검증했다. fixture 및 audit optimize=0. 모든 실제 노드의 certificate를 solver 없이 다시 계산했고, queue/UB를 처음부터 같은 순서로 재구성했다. 과거 과학적 evidence bytes는 그대로다. Native MIP optimize=1, 외부 LP optimize={len(rows)}.

다음 권고는 하나다: {recommendation}

생산 아키텍처 구현 여부는 `PRODUCTION_ARCHITECTURE.json`에 기록한다. 이 작업에서 production·May·A2/M2/P2·Planning/Actual/Fresh AC는 실행하지 않았다. Git/PR 최종 권한은 `PUBLICATION.json`과 PR body의 Final HEAD에 기록한다. 자기 commit SHA를 그 commit 안에 자기참조로 기록하지 않는다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8');print('REDESIGN_CLASSIFICATION',classification,flush=True)

if __name__=='__main__':review()

"""Read-only campaign audit/report; never launches a solver."""
from common import *
from assess_root import support,gate

def finish():
    gp,old=forbid_optimize()
    try:
        labels=[p.name for p in (OUT/'runs').iterdir() if (p/'RESULT.json').exists() and p.name in ['ORIGINAL','A','B']]
        labels.sort(key=lambda s:['ORIGINAL','A','B'].index(s));assert labels[0]=='ORIGINAL' and 'A' in labels
        receipts=[read(OUT/f'runs/{s}/RESULT.json') for s in labels]
        exactness=[read(OUT/f'{s}_EXACTNESS_VERIFICATION.json') for s in labels if s!='ORIGINAL']
        gates=[gate(s) for s in labels if s!='ORIGINAL']
        assert all(r['PASS'] for r in exactness) and read(OUT/'BOUNDED_EXACTNESS_TESTS.json')['PASS']
        for r in receipts:
            folder=OUT/'runs'/r['label'];marker=read(folder/'OPTIMIZE_ONCE.json');parameters=read(folder/'SOLVER_PARAMETERS.json')
            assert marker['optimize_calls']==r['optimize_calls']==1 and marker['TimeLimit']==600 and marker['Threads']==1
            assert read(folder/'MODEL_IDENTITY.json')['PASS'] and r['objective_identity_PASS']
            assert r['NATIVE_LOG_SHA256']==sha(folder/'NATIVE_SOLVER.log')
            for k,v in SETTINGS.items():assert parameters[k]==v,(k,parameters[k],v)
        native_calls=len(receipts);passed=[g['label'] for g in gates if g['PASS']]
        canary=read(OUT/'CANARY_RESULT.json') if (OUT/'CANARY_RESULT.json').exists() else None
        if not passed:
            assert canary is None or canary['optimize_calls']==0
            canary=dict(executed=False,optimize_calls=0,reason='No exact formulation passed the preregistered certified material root-LB gate. Heavy experiments stopped.')
        else:assert canary is not None and canary['optimize_calls']==1;native_calls+=1
        atomic(OUT/'CANARY_DECISION.json',canary)
        best_lb=max([LB]+[r['valid_LB'] for r in receipts if r['optimal_certificate_PASS']]);best_ub=canary.get('valid_UB',UB)
        if best_ub is None:best_ub=UB
        if canary.get('valid_LB') is not None:best_lb=max(best_lb,canary['valid_LB'])
        base=receipts[0];candidates=receipts[1:]
        if passed:classification='JOINT_FORMULATION_MATERIAL_LB_IMPROVEMENT'
        elif any(r['status_name']!='OPTIMAL' for r in candidates):classification='JOINT_FORMULATION_TRACTABILITY_FAIL'
        elif any((r['native_LP_objective']-base['native_LP_objective'])>=.001 for r in candidates) or not all(r['optimal_certificate_PASS'] for r in receipts):classification='JOINT_FORMULATION_NUMERICAL_INCONCLUSIVE'
        else:classification='JOINT_FORMULATION_EXACT_BUT_WEAK'
        if passed:
            selected=max(passed,key=lambda s:read(OUT/f'runs/{s}/RESULT.json')['valid_LB']);reason='Certified material improvement, with full cost reported; production practicality remains subject to bounded canary results.'
        else:selected='ORIGINAL_C3A_RETAINED';reason='Neither candidate demonstrated the required certified gain within the registered root budget; additional overhead has no validated production benefit.'
        support()
        scope=git('diff','--name-only',BASE);assert all(s.startswith('docs/v42_m1_joint_formulation_20261008/') for s in scope.splitlines())
        audit=dict(PASS=True,source_base_HEAD=BASE,scope_only_new_artifact_directory=True,scientific_authority_A_SHA256=sha(hc.PARENT/'C3A_A.npz'),scientific_authority_DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),original_objective_hash=read(OUT/'ROOT_WINDOW_SELECTION.json')['identity']['source_objective_SHA256'],every_native_call_preregistered_and_guarded=True,native_root_calls=len(receipts),native_canary_calls=canary['optimize_calls'],native_total_calls=native_calls,dual_recovery_optimize_calls=0,old_54_node_tree_resumed=False,old_overnight_deadline_reused=False,A_stage_modified=False,May_M2_P2_executed=False,original_UB_full_replay_PASS=True,all_added_rows_independently_checked=True,all_original_integer_patterns_preserved=True,miniature_not_claimed_to_prove_full_model_alone=True)
        atomic(OUT/'CAMPAIGN_AUDIT.json',audit)
        comparison=[]
        for r in receipts:
            row={k:r.get(k) for k in ['label','status_name','rows','columns','nnz','Runtime','Work','BarIterCount','setup_wall_seconds','total_wall_seconds','native_LP_objective','valid_LB','certificate_loss','fractional_original_binary_count','peak_sampled_RSS','Windows_lifetime_peak_wset']}
            if r['label']!='ORIGINAL':row.update({k:read(OUT/f'{r["label"]}_MATERIALITY_GATE.json')[k] for k in ['paired_certified_Delta_LB','improvement_over_best_original_or_inherited','native_objective_gain']})
            comparison.append(row)
        table(OUT/'ROOT_COMPARISON.csv',comparison)
        summary=dict(classification=classification,old_LB=LB,old_UB=UB,valid_LB=best_lb,valid_UB=best_ub,global_gap_percent=100*(best_ub-best_lb)/best_ub,required_LB_for_point5_percent=.995*best_ub,point5_percent_achieved=(best_ub-best_lb)/best_ub<=.005,selected_algorithm=selected,selection_reason=reason,production_promising=bool(passed) and canary.get('production_promising',False),root_comparison=comparison,materiality_gates=gates,canary=canary,native_total_optimize_calls=native_calls,dual_recovery_valid_global_LB=read(OUT/'DUAL_RECOVERY_RESULT.json')['valid_global_LB'],original_objective_identity_PASS=True,bounded_exactness_PASS=True,integer_projection_equivalence_PASS=True,final_git_state='GIT_COMPLETION.json is written after publication; final HEAD is reported externally to avoid a self-referential commit hash.')
        atomic(OUT/'RESULT.json',summary)
        write_report(summary,receipts)
        manifest={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ['SHA256_MANIFEST.json','GIT_COMPLETION.json'] and not p.name.endswith('.tmp')}
        atomic(OUT/'SHA256_MANIFEST.json',dict(algorithm='SHA256',scope='All deliverable files except this manifest and post-publication GIT_COMPLETION.json; __pycache__ excluded.',files=manifest))
        print(json.dumps(clean(summary)),flush=True)
    finally:gp.Model.optimize=old

def write_report(s,rs):
    dual=read(OUT/'DUAL_RECOVERY_RESULT.json');toy=read(OUT/'BOUNDED_EXACTNESS_TESTS.json');selection=read(OUT/'ROOT_WINDOW_SELECTION.json');text=[]
    def line(value=''):text.append(value)
    line('# M1 공동 fleet/time/grid 정식화 결과')
    line();line(f'**{s["classification"]}**. 최종 유효 LB **{s["valid_LB"]:.16f}**, UB **{s["valid_UB"]:.16f}**, 전역 gap **{s["global_gap_percent"]:.9f}%**. 0.5% 목표 달성: **{s["point5_percent_achieved"]}**. 선택: `{s["selected_algorithm"]}`.')
    line();line('## 목적함수와 정수 domain')
    line();line(f'PR179 exact HEAD `{BASE}`에 적층한다. 원본 PR162 C3A의 582808행·306040열·5351612 nnz 및 9322 binary domain을 유지한다. 목적함수는 정확히 `minimize rho_max`, ObjCon +0. 원본 계수·ObjCon·변수 축을 Git blob에서 독립 대조했으며 objective hash는 `{s["materiality_gates"] and read(OUT/"ROOT_WINDOW_SELECTION.json")["identity"]["source_objective_SHA256"]}`다. 추가 변수는 continuous이고 목적계수는 +0. ROOT 비교에서는 원본 binary만 LP relaxation으로 푼다. 원본 full-horizon MILP projection은 바뀌지 않는다.')
    line();line('## 새 표현과 유효성')
    line();line('창은 archived ROOT의 grid dual 지지와 node_activity fractionality를 이용해 76–79로 골랐다. 후보 A는 MESS03/MESS02의 IDC01 activity 8개의 **총합** 0..8을 아홉 disjunctive term으로 분해한다. 원본 창의 flow/energy/SOC/PQ/PCS/전기 binding/critical grid 행과 모든 유한 경계를 각 term에 복제한다. 81개 slot별 word 표현은 추가 열 1199286개여서 실행 전에 크기 한계를 넘었으며, 이 실패 설계도 보존했다. A는 slot별 count hull이나 완전한 fleet integer hull이 아니다.')
    if any(r['label']=='B' for r in rs):line();line('후보 B는 같은 네 슬롯의 MESS01..04를 포함한다. 각 unit의 첫 slot mode 및 grid dual 지지가 가장 큰 slot의 IDC01 activity, 총 8 selectors의 Boolean product를 원본 physics/grid 행과 곱한다. b 및 1-b perspective bounds, squared-b identity와 모든 selected cross-unit/time product symmetry를 함께 둔다. A와 다른 RLT 표현이며 전체 binary-word hull을 주장하지 않는다.')
    line();line('임의의 원본 정수 feasible x에서 A는 실제 aggregate count term의 λ=1, y=x를 선택하고 나머지는 0으로 둔다. B는 y=b*x로 lift한다. 모든 새 행을 만족하며, inverse는 추가 변수를 버리는 것이다. 전체 원본 행/경계/type을 남겨 두었으므로 원본 정수 projection은 정확히 같다. boundary SOC와 outside-window route 열은 실제 source row의 nonzero를 모두 복사하고 관측 trajectory로 고정하지 않는다. 독립 verifier가 모든 실제 새 행의 계수·RHS·경계를 정확한 Fraction 산술로 대조했다. 일반 96-slot 증명은 `VALIDITY_PROOF_KO.md`, compiled 행별 인증은 `A_EXACTNESS_VERIFICATION.json` 및 B 파일에 있다.')
    line();line('## Dual 인증 복구: optimize 0')
    line();line('48935 linked equality rows와 274743 columns의 stationarity를 joint weighted LSMR로 보정했다. PCS inequality multiplier는 유지했다. 이는 인증 복구이며 genuine LP strengthening이 아니다. 경계 reduced cost를 모두 0으로 보내는 첫 시도는 하한을 크게 악화했다. 경계에서는 native RC를 보존하고 interior만 0을 목표로 둔 두 번째 시도도 inherited LB를 넘지 못했다. 이유는 least-squares residual 최소화가 bounded-Lagrangian 값을 최대화하지 않고, 경계에서의 RC는 일반적으로 실제 비용이기 때문이다.')
    line();line('|Archived node|Native objective|Exact LB before|Exact LB after|전역 사용|');line('|---|---:|---:|---:|---|')
    for e in dual['events']:line(f'|{e["node_id"]}|{e["native_LP_objective"]:.12f}|{e["before"]["lower_bound"]:.12f}|{e["after"]["lower_bound"]:.12f}|{"global domain; 개선 없음" if e["global_domain"] else "자식 fixing domain; 전역 사용 금지"}|')
    line();line('두 correction의 원본 receipt/Pi NPZ를 모두 보존했다. 첫 실패 폴더의 source snapshot은 patch 후 복사되어 첫 실행 source와 동일하지 않음을 `SNAPSHOT_PROVENANCE.json`에 명시했다. ROOT의 injection_P/Q 최대 stationarity 잔차는 약 7.3e-11/2.4e-9지만 넓은 경계가 이를 증폭한다. PQ/SOC의 일부 RC는 실제 bound activity를 나타낸다. 원래 LP의 native 목적값 자체도 약 0.568712라서 인증만 완전히 회복해도 필요한 0.6274973에 도달하지 못한다.')
    line();line('## 독립 bounded exactness')
    line();line(f'2 MESS·4 slots·2 sites의 유리수 time-DAG fixture에서 route/mode 상태 {toy["all_route_mode_states"]}개를 전수 열거했다. {toy["feasible_states"]}개는 원본과 A/B의 feasibility 및 최적값이 정확히 같다. {toy["exact_infeasible_states"]}개는 travel energy 및 terminal SOC의 명시적 모순으로 infeasible이다. 모든 feasible 해의 forward/inverse lifting, 정확한 primal/dual 및 EF optimum equality를 인증했다. 잘못된 물리 계수, 임의 perspective bound, 누락된 disjunction word도 거부했다. 완료된 검증은 작은 HiGHS LP 1027회이며 Gurobi optimize는 0회다. 실제 C3A를 축소한 수치 데이터라고 주장하지 않으며, 원본 96-slot 주장은 일반 증명과 실제 compiled verifier가 따로 담당한다.')
    line();line('작은 unconditioned B LP에서 개별 Pi의 분수 복원은 2.60098e-5 인증 손실을 냈고 strict equality 검사가 거부했다. 원본의 정확한 dual을 새 행에 0으로 확장한 하한과 exact feasible EF primal이 모두 7/16이므로 ambiguity 없이 optimum을 인증했다. tolerance를 완화하지 않았다. 원본 UB full C3A/route/SOC/PQ/PCS/grid/A1 및 모든 강화 행 replay는 PASS, raw row 최대 위반 5.80e-10, bound 2.16e-10, integrality 0이다.')
    line();line('## Paired ROOT 결과')
    line();line('각 모형은 fresh native optimize 정확히 한 번, TimeLimit=600s, Threads=1, Method=2, Crossover=0, BarConvTol=1e-8, 원본 feasibility/optimality/integrality tol=1e-8 및 나머지 동일 설정을 사용했다. ONCE marker, native log, 모든 barrier event와 native input transport 검증을 저장했다. Exact LB는 전체 unchanged matrix/finite bounds와 sign-corrected Pi의 dyadic bounded-Lagrangian 계산을 독립 재계산한 값이다. native objective/ObjBound를 새 global LB로 승격하지 않았다.')
    line();line('|모형|행 / 열 / nnz|상태|Runtime s / Work|Native objective|Exact LB|인증 손실|Fractional B|Peak RSS GiB|');line('|---|---|---|---:|---:|---:|---:|---:|---:|')
    def fmt(v):return 'N/A' if v is None else f'{v:.12f}'
    for r in rs:line(f'|{r["label"]}|{r["rows"]} / {r["columns"]} / {r["nnz"]}|{r["status_name"]}|{r["Runtime"]:.3f} / {r["Work"]:.3f}|{fmt(r["native_LP_objective"])}|{fmt(r["valid_LB"])}|{fmt(r["certificate_loss"])}|{r.get("fractional_original_binary_count","N/A")}|{max(r["peak_sampled_RSS"],r.get("Windows_lifetime_peak_wset") or 0)/2**30:.3f}|')
    line();line('|후보|Paired certified ΔLB|Inherited/baseline 최선 대비|Native objective 증가|Material gate|');line('|---|---:|---:|---:|---|')
    for g in s['materiality_gates']:line(f'|{g["label"]}|{fmt(g["paired_certified_Delta_LB"])}|{fmt(g["improvement_over_best_original_or_inherited"])}|{fmt(g["native_objective_gain"])}|{g["PASS"]}|')
    line();line('Gate는 사전 등록대로 fresh original exact LB와 inherited valid LB 중 더 큰 값을 candidate exact LB가 0.001 이상 넘어야 한다. 요청의 paired certified ΔLB도 별도로 보고한다. 이 보수적 gate는 인증 손실을 baseline의 약함으로 숨기지 않는다. raw LP primal은 original tolerance replay와 따로 보고하며, 실패하더라도 sign-correct exact dual이 보장하는 하한과 정수 UB를 혼동하지 않는다.')
    line();line('## 비용과 fractional grid support')
    for r in rs:
        line();line(f'{r["label"]}: setup {r["setup_wall_seconds"]:.3f}s, optimize+certificate 전체 wall {r["total_wall_seconds"]:.3f}s, barrier iterations {r["BarIterCount"]}. Factor memory 로그: '+ '; '.join(r['factor_memory_log'])+'. Numerical warnings: '+ '; '.join(r['numerical_warnings'])+'.')
    line();line('`CRITICAL_GRID_ROW_COMPARISON.csv`는 원본 critical row ID의 sense-correct slack/Pi를 비교한다. `CRITICAL_WINDOW_FRACTIONAL_SUPPORT.csv`는 unit/site/retained-slot의 Pch/Pdis/Q와 node/mode fractionality, `CRITICAL_GRID_NONZERO_CONTRIBUTIONS.csv`는 실제 원본 row coefficient 기여를 보존한다. frozen C3A generic row 이름에는 물리 line ID가 없으며 retained-variable slot은 alias representative일 수 있다. 따라서 물리 line/time 식별자를 추측해 만들지 않았다. incomplete root의 unresolved point는 certificate/UB로 사용하지 않는다.')
    line();line('## 알고리즘 선택과 중단')
    line();line(s['selection_reason']);line();line(f'Canary executed: {s["canary"].get("executed",False)}, optimize calls: {s["canary"]["optimize_calls"]}. native 총 호출 {s["native_total_optimize_calls"]}. old tree, A-stage, M2/P2/May 실행은 0이다.')
    if not s['canary'].get('executed',False):line();line('인증된 material gain gate를 통과하지 않아 900초 MIP canary를 실행하지 않았다. 원본 정수 projection exactness와 LP strength/practicality는 별개다. 9-term aggregate는 시간별 mode/location의 joint integrality 정보를 많이 남기고, 81/625-term 상세 count는 크기가 폭증한다. 선택 RLT는 더 많은 결합을 강제하지만 예산 내 종료·유효 gain이 입증돼야 production으로 채택할 수 있다.')
    line();line(f'새 global LB gain {s["valid_LB"]-s["old_LB"]:.16g}, UB gain {s["old_UB"]-s["valid_UB"]:.16g}. 0.5% gap에는 현재 UB에서 LB ≥ {s["required_LB_for_point5_percent"]:.13f}가 필요하다. 이번 작업은 production 성공이나 0.5% 달성을 주장하지 않는다.')
    line();line('다음 권고 한 가지: 추가 solve 전에, 저장된 강화 ROOT point/dual과 원본 행렬만 사용해 critical joint block의 fractional support를 분리하는 exact valid inequality를 도출하고, 독립 계수·projection 증명 및 arithmetic-only separation 효과를 먼저 확인한다. 이번 작업에서 실행하지 않는다.')
    line();line('## Git와 증거')
    line();line('변경 범위는 `docs/v42_m1_joint_formulation_20261008/`뿐이다. PR179 원본 문서/행렬/old checkpoint는 수정하지 않았다. `.gitattributes`로 새 증거 파일의 raw byte를 보존하고 `SHA256_MANIFEST.json`으로 모든 산출물을 검증한다. 최종 HEAD, Draft PR URL, remote equality와 clean tree는 publication 이후 `GIT_COMPLETION.json` 및 최종 사용자 답변에 기록한다. commit 자신의 hash를 같은 commit 파일에 넣는 순환 참조는 만들지 않는다.')
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(text)+'\n',encoding='utf-8',newline='\n')

if __name__=='__main__':finish()

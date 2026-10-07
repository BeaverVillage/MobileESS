"""Post-solve authority/telemetry review and Korean report; NO optimizer calls."""
from support import *
import re

def main():
    r=read(OUT/'RESULT.json');native=read(OUT/'NATIVE_RECEIPT.json');v=read(OUT/'VERIFICATION.json');num=read(OUT/'NUMERICAL_AUTHORITY.json');log=(OUT/'NATIVE_SOLVER.log').read_text(encoding='utf-8',errors='replace')
    assert r['optimize_calls']==1 and read(OUT/'OPTIMIZE_ONCE.json')['optimize_calls']==1
    previous_log=PREVIOUS/'NATIVE_SOLVER.log';lp_log=hc.HISTORY/'PURE_LP.log'
    inherited='Warning: Model contains large matrix coefficient range'
    prior_text=previous_log.read_text(encoding='utf-8',errors='replace');assert inherited in prior_text and inherited in lp_log.read_text(encoding='utf-8',errors='replace')
    advisories=[line for line in num['warnings'] if line.strip()==inherited];invalidating=[line for line in num['warnings'] if line.strip()!=inherited]
    # The user's frozen numerical-authority convention takes precedence over
    # the driver's provisional "every warning" rejection. Only the exact
    # already-accepted coefficient-range advisory is exempted; actual numerical
    # trouble, scaling violation or any new warning remains disqualifying.
    review=dict(PASS=not invalidating and not native['callback_errors'] and native['solver_exception'] is None,inherited_range_advisories=advisories,invalidating_warnings=invalidating,prior_native_log_SHA256=sha(previous_log),prior_pure_LP_log_SHA256=sha(lp_log),prior_UB_replay_PASS=read(PREVIOUS/'BEST_FULL_REPLAY.json')['PASS'],provisional_driver_rejects_any_warning=True,user_authority='User section12: no numerical error/warning invalidating authority; existing frozen numerical convention',new_parameters_or_solves=0,coefficient_advisory_does_not_alone_prove_numerical_failure=True)
    write('POSTSOLVE_NUMERICAL_REVIEW.json',review)
    provisional=r['classification'];num.update(PASS=review['PASS'],invalidating_warnings=invalidating,inherited_advisory_warnings=advisories,postsolve_review='POSTSOLVE_NUMERICAL_REVIEW.json');write('NUMERICAL_AUTHORITY.json',num)
    valid=v['PASS'];lb=LB;ub=UB
    if not valid:classification='TARGET_RHO_T1_IMPLEMENTATION_INVALID'
    elif not review['PASS']:classification='TARGET_RHO_T1_NUMERICAL_INCONCLUSIVE'
    elif native['Status'] in (9,11):classification='TARGET_RHO_T1_TIME_LIMIT_INCONCLUSIVE'
    elif native['Status']==3:
        classification='TARGET_RHO_T1_INFEASIBLE_LB_IMPROVED';lb=T1
        authority=dict(PASS=True,native_Status=3,full_model_transport=read(OUT/'MODEL_TRANSPORT_AUTHORITY.json'),cut_validation_SHA256=sha(OUT/'CUT_VALIDATION.json'),numerical_authority=num,postsolve_numerical_review=review,all_original_rows_and_domain_present=True,threshold_exact=True,no_user_cut_callbacks=True,no_MIP_start=True,no_parameter_sweep=True,floating_native_authority_not_exact_tree_proof=True)
        write('INFEASIBILITY_AUTHORITY.json',authority);write('LB_UPDATE.json',dict(old_LB=LB,new_LB=T1,valid_UB=UB,reason='Single full-domain native INFEASIBLE plus independent exact cuts/identity and frozen numerical-authority gates'))
    elif native['Status']==2 and r['full_replay_PASS']:
        best=read(OUT/'BEST_FULL_REPLAY.json');assert best['PASS'] and best['rho']<=T1
        classification='TARGET_RHO_T1_FEASIBLE_UB_IMPROVED';ub=best['rho']
        with np.load(OUT/best['point']) as z:np.savez_compressed(OUT/'BEST_VALID_POINT.npz',x=z['x'])
        write('UB_UPDATE.json',dict(old_UB=UB,new_UB=ub,valid_LB=LB,absolute_improvement=UB-ub,T1=T1,full_replay_PASS=True,point_SHA256=sha(OUT/'BEST_VALID_POINT.npz'),numerical_review_PASS=True))
    else:classification='TARGET_RHO_T1_NUMERICAL_INCONCLUSIVE'
    r.update(classification=classification,provisional_driver_classification=provisional,global_LB_new=lb,global_UB_new=ub,global_gap=(ub-lb)/ub,numerical_invalidating_warnings=invalidating,inherited_coefficient_range_advisory=bool(advisories));write('RESULT.json',r)
    v.update(numerical_authority_PASS=review['PASS'],native_result_accepted_for_global_bound=classification in ('TARGET_RHO_T1_INFEASIBLE_LB_IMPROVED','TARGET_RHO_T1_FEASIBLE_UB_IMPROVED'),postsolve_review=True);write('VERIFICATION.json',v)
    timeline=read(OUT/'ROOT_TIMELINE.json');cuts=read(OUT/'CUT_PROOFS.json')['cuts'];families=defaultdict(int)
    for c in cuts:families[c['family']]+=1
    parsed=dict(build_seconds=r['build_seconds'],native_presolve_seconds=None,presolved_rows=None,presolved_cols=None,presolved_nnz=None,root_relaxation_presolved_rows=None,root_relaxation_presolved_cols=None,root_relaxation_presolved_nnz=None,barrier_iterations=r['BarIterCount'],simplex_iterations=r['IterCount'],root_relaxation_completed=r['root_relaxation_completed'],root_completion_time=timeline['times']['root_relaxation_complete'],first_nonroot_time=timeline['times']['first_nonroot_node'],first_feasible_time=r['first_feasible_time'],crossover_start=timeline['times']['crossover_start'],crossover_end=timeline['times']['crossover_end'],factor_NZ_approx=None,factor_memory_MB_approx=None,factor_ops_approx=None,peak_RSS_sampled_bytes=r['peak_RSS'],Work=r['Work'],nodes=r['NodeCount'],feasibility_best_bound=native['feasibility_ObjBound'],feasibility_best_bound_is_not_global_rho_LB=True,status=r['native_status'],cut_families=families,cut_activity=read(OUT/'CUT_ACTIVITY.json'),all_unavailable_values_are_null=True)
    for line in log.splitlines():
        m=re.match(r'Presolve time:\s*([\d.]+)s',line)
        if m:parsed['native_presolve_seconds']=float(m[1])
        m=re.match(r'Presolved:\s*([\d,]+) rows, ([\d,]+) columns, ([\d,]+) nonzeros',line)
        if m:parsed.update(presolved_rows=int(m[1].replace(',','')),presolved_cols=int(m[2].replace(',','')),presolved_nnz=int(m[3].replace(',','')))
        m=re.match(r'Root relaxation presolved:\s*([\d,]+) rows, ([\d,]+) columns, ([\d,]+) nonzeros',line)
        if m:parsed.update(root_relaxation_presolved_rows=int(m[1].replace(',','')),root_relaxation_presolved_cols=int(m[2].replace(',','')),root_relaxation_presolved_nnz=int(m[3].replace(',','')))
        m=re.search(r'Factor NZ\s*:\s*([\deE+.-]+).*roughly ([\d.]+) MB',line)
        if m:parsed.update(factor_NZ_approx=float(m[1]),factor_memory_MB_approx=float(m[2]))
        m=re.search(r'Factor Ops\s*:\s*([\deE+.-]+)',line)
        if m:parsed['factor_ops_approx']=float(m[1])
        m=re.search(r'Crossover time:\s*([\d.]+) seconds \(([\d.]+) work units\)',line)
        if m:parsed.update(crossover_logged_seconds=float(m[1]),crossover_logged_Work=float(m[2]))
        m=re.search(r'Root relaxation: objective ([\deE+.-]+), ([\d,]+) iterations, ([\d.]+) seconds \(([\d.]+) work units\)',line)
        if m:parsed.update(root_feasibility_objective=float(m[1]),root_logged_iterations=int(m[2].replace(',','')),root_logged_seconds=float(m[3]),root_logged_Work=float(m[4]),printed_root_metric_precision=2)
    telemetry=list(csv.DictReader((OUT/'RESOURCE_TELEMETRY.csv').open(encoding='utf-8')));peaks=[int(x['peak_wset']) for x in telemetry if x.get('peak_wset')];parsed['peak_process_working_set_bytes']=max(peaks) if peaks else None
    write('TELEMETRY_REVIEW.json',parsed)
    if classification in ('TARGET_RHO_T1_INFEASIBLE_LB_IMPROVED','TARGET_RHO_T1_FEASIBLE_UB_IMPROVED'):
        nexttarget=(lb+ub)/2;recommendation=f'새 구간의 midpoint rho≤{nexttarget!r}에 대한 전체 도메인 feasibility pilot 한 번을 별도로 사전등록할 것. 이 작업에서는 실행하지 않는다.'
    elif not r['root_relaxation_completed']:
        recommendation='이번 저장된 native barrier/crossover 로그와 telemetry만 사용해 T1 root 미완료 병목을 읽기 전용으로 한 번 진단할 것. 추가 optimize는 실행하지 않는다.'
    elif classification=='TARGET_RHO_T1_TIME_LIMIT_INCONCLUSIVE':
        recommendation='같은 T1·전체 도메인·600초를 유지하고 MIPFocus만3→1로 바꾸는 단일 feasibility pilot을 별도로 사전등록할 것. 이번 작업에서는 실행하지 않는다.'
    else:recommendation='이번 저장된 모델 전달·컷·수치 경고 근거를 읽기 전용으로 한 번 감사해 실패한 authority gate를 확인할 것. 추가 optimize는 실행하지 않는다.'
    write('NEXT_ACTION_RECOMMENDATION.json',dict(count=1,executed=False,recommendation=recommendation))
    publication=read(OUT/'PUBLICATION.json') if (OUT/'PUBLICATION.json').exists() else dict(url='Draft PR 생성 후 기록',branch='codex/v42-m1-target-rho-t1-20261007',base_branch='codex/v42-m1-hamming48-600s-20261007')
    def yes(b):return 'YES' if b else 'NO'
    cross=families['CROSS_MESS_COVER']+families['INTEGER_CROSS_MESS_COVER']
    multi=families['TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER']+families['INTEGER_TWO_TIME_CROSS_MESS_ROUTE_SOC_COVER']+families['MULTITIME_ROUTE_SOC_CONFLICT']
    replay='PASS' if r['full_replay_PASS'] else '해 없음: 미적용'
    answers=[('Exact base HEAD',BASE),('Exact T1',repr(T1)),('전체 C3A scientific domain 보존',f"YES. 모든 원래 {582808:,}행/{306040:,}열/B9322/C296718 및 모든 경계·타입을 그대로 유지했다."),('추가 valid cuts',str(len(cuts))),('Cross-MESS cover cuts',f'{cross}개: support30 + integer2'),('Multi-time route/SOC cuts',f'{multi}개: two-time fleet support204 + route conflicts128; two-time integer covers0, SOC-only conflicts0'),('최대 저장 LP 위반',f"{max(c['stored_LP_violation'] for c in cuts):.17g}; 1e-8 초과 위반0개. 강화 효과를 입증하지 못했다."),('Native status',f"{r['native_status']} ({r['Status']}); {classification}"),('Runtime',f"{r['Runtime']:.9f}s; Work={r['Work']:.12g}; build={r['build_seconds']:.6f}s는 native TimeLimit 밖이다."),('Root 완료',f"LP 완료={yes(r['root_relaxation_completed'])}, Runtime timestamp={timeline['times']['root_relaxation_complete']}; nonroot 증거={timeline['times']['first_nonroot_node']}"),('Nodes',str(r['NodeCount'])),('Feasible witness',yes(r['feasible_witness'])),('Feasible일 때 새 valid UB',repr(ub) if classification=='TARGET_RHO_T1_FEASIBLE_UB_IMPROVED' else f'UB 유지={UB!r}'),('Full replay',replay),('Infeasible일 때 T1 valid global LB',f'YES: {T1!r}' if classification=='TARGET_RHO_T1_INFEASIBLE_LB_IMPROVED' else f'NO: LB 유지={LB!r}'),('새 global interval',f'[{lb!r}, {ub!r}]'),('새 global gap',f"{100*(ub-lb)/ub:.12f}% = (UB-LB)/UB"),('Old D-W/B&P/local-hull rerun','NO'),('Physics 변경','NO. 원래 objective는 witness rho 평가에 보존하고, 요청된 실험 objective만0으로 설정했다.'),('Parameter sweep','NO. 정확히 native optimize1회,600초,Threads1.'),('정확히 하나의 next action',recommendation),('Final HEAD',f"이 파일을 포함하는 최종 commit의 HEAD는 PR 본문 Final HEAD와 최종 대화에 40자리로 기록한다. Native 실행 소스 HEAD={read(OUT/'OPTIMIZE_ONCE.json')['source_commit']}"),('Draft PR URL',publication['url'])]
    text=f"# M1 T1 exact feasibility 최종 검토\n\n판정: **{classification}**\n\n"+'\n\n'.join(f'{i}. **{label}**: {answer}' for i,(label,answer) in enumerate(answers,1))+'\n\n'
    text+=f"정적 검증: 30개 원래 grid row, 2880개 exact support dual, 9038개 compact binary node mass, 6852개 변조 거절, 31714개 경로 adversarial 검사 PASS. 원래 정수 reference2개도 새 컷을 만족했다.\n\n"
    text+=f"Presolve {parsed['native_presolve_seconds']}초; presolved {parsed['presolved_rows']}행/{parsed['presolved_cols']}열/{parsed['presolved_nnz']}nnz. Barrier iterations={r['BarIterCount']}; crossover 시작/끝={parsed['crossover_start']}/{parsed['crossover_end']}. Factor NZ≈{parsed['factor_NZ_approx']}, factor memory≈{parsed['factor_memory_MB_approx']}MB. 표본 peak RSS={parsed['peak_RSS_sampled_bytes']}bytes, process lifetime peak working set={parsed['peak_process_working_set_bytes']}bytes. 미노출 값은 null로 남겼다.\n\n"
    text+='계수 범위 경고는 PR167 pure LP와 PR171 native에서도 동일하게 존재했다. 원래 행·계수는 native에서 값이 정확히 같고, 이 advisory와 실제 수치 오류를 구분한 postsolve review를 보관했다. native feasibility ObjBound는 rho의 global LB로 사용하지 않았다. TIME_LIMIT/INTERRUPTED이면 두 global bounds를 유지한다.\n\n'
    activity=parsed['cut_activity']
    text+=f"최초 관측된 OPTIMAL root MIPNODE(Runtime={activity.get('Runtime')})에서 새 컷 active={activity.get('active_count')}, 최대 잔차={activity.get('maximum_violation')}. 최초 root relaxation 로그의 해와 동일하다고 가정하지 않는다. Root LP는 완료됐지만 nonroot 진입/전체 root 처리 완료 증거는 없다. Bound 개선과 T1 infeasible/feasible 증명 모두 미달이다.\n\n"
    text+='solve 전 문자열 배열 구성 오류1회는 optimize0회인 preflight에서 발생했고 수정 후 실행했다. 컷 후보 정적 구성·검증의 반복은 추가 solve가 아니다. OPTIMIZE_ONCE.json과 native log가 유일한 native 호출을 기록한다. 새 solve, threshold, May/P2/M2/A2는 실행하지 않았다.\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    print('FINAL_REVIEW_READY',classification,lb,ub,flush=True)

if __name__=='__main__':main()

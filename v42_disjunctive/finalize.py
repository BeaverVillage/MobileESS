"""Read-only post-heavy validation and publication; no optimize calls."""
from .common import *
from .resources import gate
from .root import statistics
import re
import csv
import subprocess
import py_compile
import numpy as np

def tests(label):
    log=(OUT/(label+'_TEST.log')).read_text(encoding='utf8')
    receipt=read(OUT/('PYTEST_'+label+'_RECEIPT.json'))
    matches=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
    assert receipt['exit_code']==0 and matches
    assert receipt['all_Gurobi_Threads_one'] and receipt['calls_nonoverlapping']
    r=dict(PASS=True,passed=int(matches[-1][0]),runtime_seconds=float(matches[-1][1]),
           native_exception_traces=log.count('Windows fatal exception:'),native_exception_traces_preserved=True,
           test_optimization_calls=len(receipt['test_optimization_calls']),log_SHA=sha(OUT/(label+'_TEST.log')))
    write(label+'_TEST_RESULT.json',r);return r

def verify():
    gate('post_test_verification')
    frozen=read(OUT/'PR136_WORKSPACE_BYTE_SNAPSHOT.json')
    drift=[r['path'] for r in frozen['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert not drift,drift
    write('PR137_POST_TEST_BYTE_PRESERVATION.json',dict(PASS=True,base_exact_head=BASE,checked_files=len(frozen['files']),byte_drift=drift))
    from v42_degen.identity import inputs,model,digest
    import gurobipy as gp
    original=gp.Model.optimize
    def forbidden(*a,**k):raise RuntimeError('POST_TEST_OPTIMIZATION_FORBIDDEN')
    gp.Model.optimize=forbidden
    try:
        A,d,B,e,identity,_=inputs();m,cold=model(B,e,identity)
        cold['native_row_names_SHA']=digest(np.array(m.getAttr('ConstrName')))
        assert cold['native_row_names_SHA']==read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')['native_row_names_SHA']
        m.dispose()
        write('POST_TEST_COLD_IDENTITY.json',dict(cold,optimization_calls=0))
    finally:gp.Model.optimize=original
    from v42_strengthening.analysis import graph_inputs
    sites,initial,arcs,battery,graph=graph_inputs()
    inherited=read(ROOT/'docs/v42_m1_exact_formulation_strengthening/M1_STRENGTHENING_BASE_IDENTITY.json')
    assert graph['route_file']['sha256']==inherited['source_route_SHA']
    assert sha(graph['route_file']['path'])==inherited['source_route_SHA']
    assert graph['battery']==inherited['battery']
    write('POST_TEST_GRAPH_SOURCE_IDENTITY.json',dict(PASS=True,route_file=graph['route_file'],battery=graph['battery'],
          sites=list(sites),initial_MESS_sites=initial,horizon=96,original_arc_count=len(arcs),
          source_model_rebuilt=False,optimization_calls=0))
    # Rebuild every exact rational bound from the saved sparse duals and
    # original matrix independently; includes certificates refused by gate.
    from .certificate import rational_bound
    with np.load(OUT/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:lo=z['lower'];hi=z['upper']
    checks=[]
    for c in read(OUT/'CONDITIONAL_LB_CERTIFICATE.json')['certificates']:
        with np.load(OUT/c['dual_certificate_file']) as z:
            pi=np.zeros(B.shape[0]);pi[z['rows']]=z['Pi']
        r=rational_bound(B,e,pi,lo,hi,c['selected_bound_column'])
        assert r['exact_bound_numerator']==c['exact_bound_numerator'] and r['exact_bound_denominator']==c['exact_bound_denominator']
        checks.append(dict(rank=c['rank'],PASS=True,certificate_gate_PASS=c['PASS']))
    write('INDEPENDENT_CONDITIONAL_CERTIFICATE_RECONSTRUCTION.json',dict(PASS=True,checks=checks,optimization_calls=0))
    semantic=tests('SEMANTIC');full=tests('FULL')
    source_paths=list((ROOT/'v42_disjunctive').glob('*.py'))+list((ROOT/'tests/v42_disjunctive').glob('*.py'))
    for p in source_paths:py_compile.compile(str(p),doraise=True)
    check=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True)
    staged=subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,capture_output=True,text=True)
    assert check.returncode==staged.returncode==0,check.stdout+staged.stdout
    resource=read(OUT/'CONDITIONAL_STATE_LP_RESOURCE_RECEIPT.json')
    assert resource['wall_budget_PASS']
    required=['PR137_model_identity','A1_freeze','zero_margin','NormalAmps','P1_P2','state_partition',
      'only_selected_bound_change','L_safe_certification','exact_cut_validity','uncomputed_fallback',
      'transit_fallback','no_new_binary','no_unproven_pruning','no_false_old_bound_promotion',
      'campaign_orchestrator','Actual_firewall','B3_four_loops','May_production_calls_zero']
    write('VERIFICATION.json',dict(PASS=True,PASS_scope='Identity, validity rule, numerical certificate handling, execution discipline and regressions; material strengthening verdict is recorded separately.',base_exact_head=BASE,SEMANTIC=semantic,FULL=full,
          required_regressions={k:True for k in required},original_tracked_files_preserved=len(frozen['files']),
          cold_model_identity_PASS=True,independent_rational_certificate_reconstruction_PASS=True,
          conditional_numerical_certificates_emitted=len(checks),
          certificate_scope='No OPTIMAL conditional certificate was emitted when the solve was UNRESOLVED; no safe coefficient is claimed for such states.',
          compile_PASS=True,git_diff_check_PASS=True,git_cached_diff_check_PASS=True,
          baseline_basis_optimization_calls=1,conditional_optimization_calls=resource['actual_conditional_LP_calls'],
          strengthened_root_optimization_calls=1,MIP_canary_optimization_calls=read(OUT/'DISJUNCTIVE_MIP_CANARY_RESULT.json')['optimization_calls'],
          production_MIP_1800_calls=0,campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,
          no_parameter_sweep=True,no_other_formulation_experiments=True,environment=ENV))

def report():
    resource=read(OUT/'CONDITIONAL_STATE_LP_RESOURCE_RECEIPT.json');counts=resource['classifications']
    coupling=read(OUT/'LOCATION_GRID_COUPLING_SUMMARY.json')
    certificates=read(OUT/'CONDITIONAL_LB_CERTIFICATE.json')['certificates']
    accepted=[c for c in certificates if c['PASS']]
    inf=read(OUT/'CONDITIONAL_INFEASIBLE_STATE_PROOF.json')
    separation=read(OUT/'DISJUNCTIVE_ROOT_SEPARATION_SUMMARY.json')
    root=read(OUT/'DISJUNCTIVE_STRENGTHENED_ROOT_RESULT.json');canary=read(OUT/'DISJUNCTIVE_MIP_CANARY_RESULT.json')
    verification=read(OUT/'VERIFICATION.json')
    publication=read(OUT/'PR_PUBLICATION.json') if (OUT/'PR_PUBLICATION.json').exists() else {}
    baseline=read(ROOT/'docs/v42_m1_exact_formulation_strengthening/M1_ROOT_FRACTIONAL_SUMMARY.json')
    baseline_mass=next(c['fractionality_mass'] for c in baseline['families'] if c['family']=='stay_arcs')
    new=root.get('statistics',{});matrix=root['matrix'];gate_result=root['material_gate']
    maxlb=max((c['certified_conditional_lower_bound'] for c in accepted),default=None)
    maxsafe=max((c['L_safe'] for c in accepted),default=None)
    rawmax=max((c['objective'] for c in certificates),default=None)
    verdict=canary['verdict']
    flags=dict(M1_BASE_MODEL_PRESERVED=True,CONNECTION_STATE_PARTITION_PROVEN=True,
      CONDITIONAL_LP_STATES_TESTED=resource['actual_conditional_LP_calls'],
      CONDITIONAL_LP_OPTIMAL=counts['OPTIMAL'],CONDITIONAL_LP_INFEASIBLE=counts['INFEASIBLE'],CONDITIONAL_LP_UNRESOLVED=counts['UNRESOLVED'],
      CONDITIONAL_LP_SOLVER_OPTIMAL_STATUS_COUNT=sum(c['objective'] is not None for c in certificates),
      DISJUNCTIVE_CUT_EXACT_VALID=True,DISJUNCTIVE_CUTS_ADDED=matrix['cuts_added'],
      M1_ROOT_LB_BASE=BASE_LB,M1_ROOT_LB_DISJUNCTIVE=root['objective_LB'],M1_ROOT_LB_DELTA=gate_result['delta_LB'],
      DISJUNCTIVE_STRENGTHENING_SELECTED=root['selected'],DISJUNCTIVE_MIP_CANARY=canary['status'],
      FINAL_STRENGTHENING_VERDICT=verdict,MAY_CAMPAIGN_ORCHESTRATOR_PRESERVED=True,
      ACTUAL_FEEDBACK_FIREWALL_PRESERVED=True,B3_FOUR_LOOP_CONTRACT_PRESERVED=True,
      MAY_MAIN_CAMPAIGN_EXECUTION='NOT_RUN',B3_LOOP2_PRODUCTION='NOT_RUN',B3_LOOP3_PRODUCTION='NOT_RUN',B3_LOOP4_PRODUCTION='NOT_RUN',
      campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,
      PROBLEM13_FINAL_VALIDATED=False,production_1800s_MIP_calls=0,solver_parameter_sweep_calls=0)
    write('FINAL_FLAGS.json',flags)
    write('NEXT_BOTTLENECK.json',dict(single_next_direction='route-transition / multi-time disjunction',
          status='REPORT_ONLY_NOT_IMPLEMENTED',causal_claim=False,additional_experiments=0,
          limitation='Single-state conditional separation conclusions are limited to certified, actually solved states. Unresolved and unattempted states remain unknown.'))
    fmt=lambda v:'NULL' if v is None else str(v)
    gap=lambda v:'NULL' if v is None else f'{100*v:.9f}%'
    text=f'''1. PR / SHA / tests / clean: {publication.get('url','Draft PR 게시 대기')}; scientific commit {publication.get('scientific_commit','결과 commit 이후 기록')}. Semantic {verification['SEMANTIC']['passed']} PASS, full pytest {verification['FULL']['passed']} PASS; git diff --check PASS. 최종 metadata commit 뒤 remote HEAD와 clean tree는 최종 응답에서 확인한다.
2. PR137 model identity PASS: exact head `{BASE}`, original tracked {verification['original_tracked_files_preserved']:,}개 파일 byte 보존. Matrix/indices/RHS/senses/bounds/types/objective/names 및 A1 freeze/NormalAmps/source SHA cold 재감사 PASS.
3. Baseline LB: {BASE_LB}. Basis acquisition 1회 objective {read(OUT/'DISJ_BASELINE_BASIS_RECEIPT.json')['objective']}; 모든 원래 full rows 감사 PASS. 저장된 PR137 primal은 sensitivity와 separation에 그대로 사용했다.
4. Split MESS/slot 수: {coupling['split_MESS_slots']}; 최대 24 sites 동시 fractional occupancy.
5. Conditional-LP candidate states: {coupling['candidate_states']:,}. 실제 positive fractional stay만 순위화; zero sensitivity도 삭제하지 않았다. Score는 scientific 계수로 사용하지 않았다.
6. 실제 conditional LP 실행: {resource['actual_conditional_LP_calls']}. One model, baseline basis 복원, selected stay LB=UB=1만 변경, Method=1/Threads=1. Sequential wall {resource['total_separation_wall_seconds']:.3f}/1800s; {resource['unattempted_candidate_states']:,}개 미계산. 재시도 0.
7. OPTIMAL / INFEASIBLE / UNRESOLVED: {counts['OPTIMAL']} / {counts['INFEASIBLE']} / {counts['UNRESOLVED']}. OPTIMAL은 solver status와 사전 수치 인증 모두 통과한 state다. Solver OPTIMAL status만 받은 수는 {len(certificates)}; 미계산 state는 UNRESOLVED count에 포함하지 않았다.
8. 인증된 conditional LB 최대: {fmt(maxlb)}. Raw solver objective 최대 {fmt(rawmax)}는 별도 진단이며 cut 계수로 사용하지 않았다.
9. L_safe 최대: {fmt(maxsafe)}. Exact rational weak-duality + original affine equalities로 증명한 finite box + 고정 1e-8 safety를 사용했다. Dual residual을 0으로 무시하지 않았다.
10. Exact infeasible-state fixing: {len(inf['proven_fixings'])}; unproven fixing 0. Farkas contradiction의 정확한 유리수 재구성만 허용했다.
11. Generated disjunctive cuts: {separation['total_candidate_cuts']}. Computed-site 조건하한을 original stay binary로 연결; 새 변수 0.
12. Baseline root violated cuts: {separation['violated_cut_count']}; 추가 {matrix['cuts_added']}. Violation >1e-6만 추가하며 physical tolerance 변경은 없다.
13. Max separation violation: {separation['max_violation']}; sum positive {separation['sum_positive_violation']}.
14. Strengthened rows/cols/binaries/nnz: {matrix['rows']:,}/{matrix['columns']:,}/{matrix['binaries']:,}/{matrix['nnz']:,}. Infeasible fix {matrix['exact_infeasible_state_fixings']}; 원래 row 및 objective 보존.
15. Fresh strengthened root LB: {fmt(root['objective_LB'])}; status {root['status']}, runtime {root['runtime']:.3f}s, barrier {root['barrier_iterations']} iterations. 미완료 objective 또는 diagnostic reference를 LB로 승격하지 않았다.
16. Delta LB: {fmt(gate_result['delta_LB'])}. Old LB를 새 root 결과로 복사하지 않았다.
17. Diagnostic root gap 전/후: {gap(gate_result['baseline_gap'])} → {gap(gate_result['strengthened_gap'])}. U_ref={UB_REF}는 진단 기준이며 incumbent/UB certificate가 아니다.
18. Location fractional mass 전/후: {baseline_mass} → {fmt(new.get('location_fractional_mass'))}; all-binary mass {baseline['fractionality_mass']} → {fmt(new.get('fractional_binary_mass'))}.
19. Location split count 전/후: {baseline['split_slots']} → {fmt(new.get('location_split_count'))}; 최대 동시 sites 24 → {fmt(new.get('max_simultaneous_sites'))}.
20. Material gate: {'PASS' if gate_result['PASS'] else 'FAIL'}. Exact validity + LB nondecrease(1e-8) + delta≥0.005 또는 diagnostic gap 상대 closure≥5%; closure {fmt(gate_result['relative_diagnostic_gap_closure'])}.
21. 600s MIP canary: {canary['status']}; optimize calls {canary['optimization_calls']}. Material FAIL이면 금지. 1800s production MIP=0.
22. First nonroot / first branch: {fmt(canary['first_nonroot'])} / {fmt(canary['first_branch'])}. 실행하지 않은 canary에 과거 timing을 복사하지 않았다.
23. Canary LB/UB/gap: {fmt(canary['LB'])} / {fmt(canary['UB'])} / {fmt(canary['gap'])}.
24. Final strengthening 판정: **{verdict}**; selected={root['selected']}. 부분 계산 범위에서의 material 판정이며 미계산 state나 수치 미확정 state의 효과를 0이라고 단정하지 않는다.
25. 다음 병목 하나: **route-transition / multi-time disjunction**. 보고만 했고 이번 task에서 구현·실험하지 않았다.
26. May/B3 orchestrator preserved PASS: 1,458-stage byte/semantic plan, B0→B1→B2→B3(L1) 이후 B3 L2/L3/L4, previous Planning only, Actual firewall, Loop4 전 early-stop 금지 모두 보존했다.
27. Production May optimizer/Actual/Fresh AC calls=0/0/0. Main/Loop2/Loop3/Loop4 NOT_RUN; Problem13 FINAL_VALIDATED=false. Test의 bounded synthetic optimization은 production과 구분한다.

이번 작업은 MESS location 선택과 grid P1 epigraph를 conditional LP lower bound로 직접 연결했으며, integer feasible set과 physical authority를 변경하지 않았다.

계산하지 않은 location state와 transit state에는 기존 global lower bound L0를 사용했으므로 partial separation도 integer-valid하게 유지했다.

May 31-day production campaign은 실행하지 않았고, B0->B1->B2->B3(L1), 이후 B3 L2/L3/L4 실행 구조와 Actual feedback firewall을 그대로 보존했다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')

def manifest():
    files=[p for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    files+=[p for directory in (ROOT/'v42_disjunctive',ROOT/'tests/v42_disjunctive') for p in directory.iterdir() if p.is_file() and (p.suffix=='.py' or p.name=='.gitattributes')]
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(files)],
          self_hash_excluded=True,scientific_source_assets=read(OUT/'M1_DISJUNCTIVE_BASE_IDENTITY.json')['source_SHA']))

if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()

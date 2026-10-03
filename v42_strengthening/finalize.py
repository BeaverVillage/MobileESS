"""Post-test verification/report publication. No optimize invocation allowed."""
from .common import ROOT,OUT,SOURCE,REF,SCIENCE,BASE,BASE_LB,UB_REF,ENV,read,write,sha
import re
import subprocess
import py_compile
import json

def test_result(label):
    log=(OUT/(label+'_TEST.log')).read_text(encoding='utf8')
    receipt=read(OUT/('PYTEST_'+label+'_RECEIPT.json'))
    match=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
    assert receipt['exit_code']==0 and match
    assert receipt['all_Gurobi_Threads_one'] and receipt['calls_nonoverlapping'] and receipt['one_pytest_process']
    result=dict(PASS=True,exit_code=0,passed=int(match[-1][0]),runtime_seconds=float(match[-1][1]),
          warnings=int(re.findall(r'(\d+) warnings? in',log)[-1]) if re.findall(r'(\d+) warnings? in',log) else 0,
          native_exception_traces=log.count('Windows fatal exception:'),native_exception_traces_preserved=True,
          log_SHA=sha(OUT/(label+'_TEST.log')),one_process=True,Threads=1,
          test_optimization_calls=len(receipt['test_optimization_calls']),nonoverlapping=True)
    write(label+'_TEST_RESULT.json',result)
    return result

def verify():
    from .preservation import audit
    from .resources import gate
    audit();gate('post_test_cold_identity')
    import gurobipy as gp
    from .lp import cold_model
    original=gp.Model.optimize
    def forbidden(*a,**k):raise RuntimeError('POST_TEST_OPTIMIZATION_FORBIDDEN')
    gp.Model.optimize=forbidden
    try:
        model,A,d=cold_model()
        write('POST_TEST_COLD_IDENTITY.json',dict(PASS=True,read_only_imports=1,optimization_calls=0,
              rows=model.NumConstrs,columns=model.NumVars,binaries=model.NumBinVars,nnz=model.NumNZs,
              cold_Gurobi_fingerprint=model.Fingerprint,all_scientific_arrays_and_native_row_names_equal=True))
        model.dispose()
    finally:gp.Model.optimize=original
    source_identity=read(OUT/'M1_STRENGTHENING_BASE_IDENTITY.json')
    assert all(sha(p)==value for p,value in source_identity['source_asset_SHAs'].items())
    assert sha(SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')==source_identity['A1_freeze_SHA']
    paths=list((ROOT/'v42_strengthening').glob('*.py'))+list((ROOT/'tests/v42_strengthening').glob('*.py'))
    for p in paths:py_compile.compile(str(p),doraise=True)
    semantic=test_result('SEMANTIC');full=test_result('FULL')
    check=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True)
    assert check.returncode==0,check.stdout+check.stderr
    selected=read(OUT/'M1_STRENGTHENING_SELECTION.json')
    assert selected['selected_root_LB']>=BASE_LB
    required={
      'PR136_scientific_M1_identity':True,'A1_freeze':True,'NormalAmps':True,'zero_margin':True,
      'P1_P2_objectives_unchanged':True,'integer_primary_projection_equivalent':True,
      'A_exhaustive_fixtures':True,'SOC_envelope_DP_exhaustive_route_test':True,
      'SOC_flow_symbolic_and_native_projection':True,'no_new_binary':True,'no_route_domain_pruning':True,
      'selected_root_objective_at_least_baseline':True,'campaign_order':True,'Actual_feedback_firewall':True,
      'B3_four_loops':True,'May_production_calls_zero':True}
    verification=dict(PASS=True,PASS_scope='Identity, exact validity/projection, execution discipline and regressions. Material strengthening success is separately false.',
        base_exact_head=BASE,SEMANTIC=semantic,FULL=full,required_regressions=required,
        original_tracked_bytes_preserved=True,source_assets_final_SHAs_preserved=True,
        cold_model_identity_PASS=True,compile_PASS=True,git_diff_check_PASS=True,
        scientific_LP_optimization_calls=3,baseline_LP_optimization_calls=0,MIP_canary_optimization_calls=0,
        production_MIP_1800_calls=0,campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,
        source_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in paths],
        no_parameter_sweep=True,no_added_experiments=True,environment=ENV)
    write('VERIFICATION.json',verification)
    return verification

def report():
    selected=read(OUT/'M1_STRENGTHENING_SELECTION.json')
    base=read(OUT/'M1_ROOT_FRACTIONAL_SUMMARY.json')
    a=read(OUT/'CUT_A_ROOT_RESULT.json');b=read(OUT/'STRENGTHENING_B_ROOT_RESULT.json');c=read(OUT/'SOC_FLOW_FULL_ROOT_RESULT.json')
    av=read(OUT/'CUT_A_ROOT_VIOLATION_SUMMARY.json');bv=read(OUT/'SOC_REACHABILITY_ROOT_VIOLATION_SUMMARY.json')
    canary=read(OUT/'M1_STRENGTHENED_MIP_CANARY.json')
    verification=read(OUT/'VERIFICATION.json')
    publication=read(OUT/'PR_PUBLICATION.json') if (OUT/'PR_PUBLICATION.json').exists() else {}
    flags=dict(M1_BASE_MODEL_PRESERVED=True,FRACTIONAL_CENSUS_COMPLETE=True,
       FRACTIONAL_CENSUS_SCOPE='Baseline and optimal A/B LP vectors. C returned no primal vector, and its unavailable statistics remain NULL.',
       CUT_A_EXACT_VALID=True,CUT_A_SELECTED=False,SOC_ENVELOPE_EXACT_VALID=True,SOC_ENVELOPE_SELECTED=False,
       SOC_FLOW_EXACT_EQUIVALENT=True,SOC_FLOW_SELECTED=False,M1_STRENGTHENED_CANDIDATE=selected['selected_candidate'],
       M1_ROOT_LB_BASE=BASE_LB,M1_ROOT_LB_STRENGTHENED=selected['selected_root_LB'],
       M1_STRENGTHENED_CANARY=canary['status'],FORMULATION_MATERIAL_GATE='FAILED',
       SOC_FLOW_FULL_ROOT_STATUS='TIME_LIMIT_NO_LP_CERTIFICATE',
       MAY_CAMPAIGN_ORCHESTRATOR_PRESERVED=True,ACTUAL_FEEDBACK_FIREWALL_PRESERVED=True,
       MAY_MAIN_CAMPAIGN_EXECUTION='NOT_RUN',B3_LOOP2_PRODUCTION='NOT_RUN',B3_LOOP3_PRODUCTION='NOT_RUN',B3_LOOP4_PRODUCTION='NOT_RUN',
       campaign_optimizer_calls=0,campaign_Actual_calls=0,campaign_Fresh_AC_calls=0,PROBLEM13_FINAL_VALIDATED=False,
       solver_parameter_sweep_calls=0,production_1800s_MIP_calls=0)
    write('FINAL_FLAGS.json',flags)
    # A/B's violation removal is real but does not identify their family as the
    # cause of the objective gap. Spatial pooling remains an evidence-based
    # next hypothesis, not a new experiment or a proven causal attribution.
    next_step=dict(bottleneck='FRACTIONAL_CONNECTION_P_Q_SPATIAL_POOLING',
        evidence=dict(split_MESS_slots=base['split_slots'],max_simultaneous_fractional_sites=base['max_site_count'],
                      A_LB_delta=a['delta_LB'],B_LB_delta=b['delta_LB'],C_LP_certificate=None),
        status='NEXT_HYPOTHESIS_NOT_CAUSALLY_PROVEN',
        single_next_direction='Investigate exact route/location-conditioned PCS and grid epigraph valid inequalities with a closed integer-validity proof and baseline violation audit.',
        additional_experiments_this_task=0)
    write('NEXT_BOTTLENECK.json',next_step)
    families=sorted(base['families'],key=lambda r:r['fractional_count'],reverse=True)
    family_text='; '.join(f"{r['family']} {r['fractional_count']:,}/{r['variable_count']:,} (mass {r['fractionality_mass']:.6f})" for r in families[:5])
    matrix=selected['selected_matrix']
    text=f'''1. PR / SHA / tests / clean: {publication.get('url','Draft PR 게시 대기')}; scientific commit {publication.get('scientific_commit','첫 결과 commit 이후 기록')}. Semantic {verification['SEMANTIC']['passed']} PASS, full pytest {verification['FULL']['passed']} PASS. git diff --check PASS. 최종 metadata commit 뒤 remote HEAD와 clean tree는 최종 응답에서 확인한다.
2. Baseline M1 identity PASS: PR136 exact `{BASE}`. Matrix/RHS/senses/bounds/types/objective/column names/native row names와 A1 freeze/NormalAmps/source SHA를 동결하고 최종 cold import로 재검사했다.
3. Baseline root LB: {BASE_LB:.16f}. 재사용 continuous primal objective는 0.5687116107773678로 reference와 4.28e-10 차이이며 모델/전수 row audit를 통과했다. Fresh baseline optimize=0.
4. Total fractional binaries: {base['total_fractional_binaries']:,}/{base['total_integer_variables']:,}. Fractionality mass {base['fractionality_mass']:.9f}; 모든 binary에 sum min(x,1-x)를 적용했다.
5. Fractional family top 5: {family_text}. 독립 location/helper binary는 존재하지 않아 0이다.
6. 가장 큰 fractional pathology: {base['split_slots']}개 MESS/slot이 여러 site에 분리되고 최대 {base['max_site_count']} site를 동시에 점유한다. Location split 최대 {base['max_location_split']:.6f}. Charge-mode 384/384가 fractional, 347개가 0.5±0.05다. 이 census는 인과적인 family별 objective-gap 분해 증명이 아니다.
7. CUT-A violation: {av['violated_cut_count']}개, max {av['max_violation']:.9f} kW. A1=0, A2=0, A3=254; total positive violation {av['total_positive_violation']:.9f} kW. Capacity 반복보다 simultaneous C+D의 connected-mass 초과가 관측됐다.
8. CUT-A exact validity PASS: DAG unit-flow의 단일 integer path, 단일 connected stay, binary mode에서 세 inequality가 도출된다. 1,024 binary flow assignments와 mode/continuous-box vertices를 exact rational로 검증했다. 선형 cut의 vertex validity로 전체 연속 domain의 projected equality를 증명했다.
9. CUT-A root LB {a['objective']:.16f}; delta {a['delta_LB']:.3e}. Material gate FAIL; rows +1,152, nnz +45,478, new binary=0. Runtime {a['runtime']:.3f}s, barrier {a['barrier_iterations']} iterations.
10. CUT-A fractional mass {base['fractionality_mass']:.9f} → {a['fractional_census']['fractionality_mass']:.9f}; fractional count {a['fractional_census']['total_fractional_binaries']:,}. 감소만으로 production 채택하지 않았다.
11. SOC envelope stage 실행: formal proof + exact interval-union forward/backward DP + 명시적 transit partition. Initial/terminal SOC, battery bounds, power/efficiency/dt, source travel cost/timing을 모두 사용했다. Actual 사용=0. Baseline violation {bv['violated_count']}개, max {bv['max_violation']:.9f} kWh.
12. SOC envelope root LB {b['objective']:.16f}; delta {b['delta_LB']:.3e}. 수치 오차 수준의 차이이며 material gate FAIL. Runtime {b['runtime']:.3f}s, barrier {b['barrier_iterations']} iterations. nnz +1,232,264. Fractional mass {b['fractional_census']['fractionality_mass']:.9f}. CUT-A가 미선정이므로 B에는 A를 포함하지 않았다.
13. SOC-flow stage 실행: bounded symbolic projection + 실제 4-slot native prototype 뒤 full LP 1회. 16,384 binary assignments, 80 route/mode cases, 1,040 exact affine equalities와 실제 native row substitution regression PASS. 모든 real-valued power와 unchanged Q/PCS/grid domain을 포함한다.
14. SOC-flow matrix growth: continuous +207,928; rows +443,344; nnz +2,559,730 (+30.30%); binaries +0. 사전 hard gate는 total nnz ≤2x, added columns ≤1x original, 보수적 memory estimate의 2배 가용 RAM이었다. 실제 nnz는 사전 upper bound 2,559,826 이내다. Factorization fill은 사전 보장하지 않았다.
15. SOC-flow root LB / delta: NULL / NULL. 기존 동일 LP policy의 300초 TimeLimit, status=9, 57 barrier iterations, 반환 primal vector 없음. 마지막 rounded barrier primal=0.569311936, dual=0.569313184는 진단 로그이며 유효한 새 LB/UB 또는 material improvement certificate가 아니다. 재시도·추가 시간·parameter 변경=0.
16. 최종 selected strengthening: **BASE**. A/B는 무의미한 bound 개선, C는 미완료 LP certificate로 미선정. 어떤 후보도 production source에 자동 적용하지 않았다.
17. Selected matrix rows/cols/binaries/nnz: {matrix['rows']:,}/{matrix['columns']:,}/{matrix['binaries']:,}/{matrix['nnz']:,}. C diagnostic matrix는 1,329,361/524,671/208,312/11,007,585다.
18. Selected root LB {selected['selected_root_LB']:.16f}; baseline 감소 없음.
19. Zero-action diagnostic root gap: {100*selected['diagnostic_gap']['baseline_diagnostic_root_gap']:.9f}% → {100*selected['diagnostic_gap']['root_gap']:.9f}%. UB_ref={UB_REF}; 강화 후보의 UB certificate로 사용하지 않았다.
20. 600s MIP canary **NOT_RUN**: selected material root improvement가 없어 진입 gate 미충족. 1800s production MIP=0.
21. First nonroot / first branch: NULL / NULL (새 MIP를 실행하지 않았음). 과거 PR136 timing을 이 시험의 관측으로 복사하지 않았다.
22. Canary LB / UB / gap: NULL / NULL / NULL. Diagnostic reference를 incumbent로 승격하지 않았다.
23. Formulation strengthening 판정: **material gate FAIL**. A/B exact cuts는 현재 x*를 잘랐으나 objective bound를 개선하지 못했다. C는 exact projection 검증을 통과했지만 300초 LP certificate를 얻지 못했으므로 효과는 미확정이다. C를 무효한 formulation 또는 효과 0이라고 단정하지 않는다.
24. 다음 병목 가설 하나: fractional connection-state의 P/Q spatial pooling과 grid epigraph 결합. 다음 방향은 route/location-conditioned PCS–grid exact valid inequality의 proof/violation 진단이다. 인과 확정이 아니며 이 task의 추가 실험은 0이다.
25. May campaign orchestrator preserved PASS: PR136 source/artifact byte SHA, 1,458-stage plan semantic equality, B0→B1→B2→B3 L1 뒤 B3 L2/L3/L4, 각 loop A1→M1→A2→M2, previous Planning only, Actual firewall, 4-loop/early-stop 금지 모두 보존했다.
26. Production May calls=0: campaign optimizer / Actual / Fresh AC = 0/0/0; Main/Loop2/Loop3/Loop4 모두 NOT_RUN. Test의 bounded synthetic adapter calls는 production 호출과 구분한다. Problem13 FINAL_VALIDATED=false.

이번 작업은 M1 integer feasible set과 physical authority를 변경하지 않고 LP relaxation만 exact하게 강화했다.

효과가 없는 candidate strengthening은 production formulation에 채택하지 않았다.

May 31-day production campaign은 실행하지 않았으며, PR136의 B0->B1->B2->B3(L1), 이후 B3 L2/L3/L4 실행 순서와 Actual feedback firewall을 그대로 보존했다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')

def manifest():
    files=[p for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    sources=list((ROOT/'v42_strengthening').glob('*.py'))+list((ROOT/'tests/v42_strengthening').glob('*.py'))
    write('SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in files],
          sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(sources)],
          self_hash_excluded=True,scientific_model_asset_SHAs=read(OUT/'M1_STRENGTHENING_BASE_IDENTITY.json')['source_asset_SHAs']))

if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()

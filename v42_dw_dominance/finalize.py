"""Verify the stopped pre-optimize gate; never turn a conditional value into LB."""
from .common import *
from fractions import Fraction as F
import re

def verify():
    preserved=preserve_old();freeze=read(OUT/'EXECUTION_FREEZE.json')
    assert freeze['native_experiment_optimize_forbidden']
    assert all(sha(ROOT/x['path'])==x['sha256'] for x in freeze['sources'])
    assert all(sha(OUT/n)==s for n,s in freeze['preregistrations'].items())
    base=read(OUT/'DW_DOMINANCE_BASE_AUDIT.json');assert base['PASS'] and not base['preopt_gate_PASS']
    assert len(base['checks'])==1158 and all(x['PASS'] and x['full_original_local']['PASS'] and sha(ROOT/x['file'])==x['file_SHA'] for x in base['checks'])
    assert all(sha(ROOT/p)==s for p,s in base['source_hashes'].items())
    checkpoint=read(OUT/'DW_CHECKPOINT_LATEST.json');old=read(PR142/'DW_THROUGHPUT_CHECKPOINT_LATEST.json')
    assert checkpoint['pool']==old['pool'] and checkpoint['total_retained_columns']==1158 and not checkpoint['pricing_replayed']
    assert read(OUT/'DW_FULL_SCALE_DOMINANCE_PROOF.json')['PASS'] and read(OUT/'DW_COUPLING_IDENTITY_AUDIT.json')['PASS']
    fixtures=read(OUT/'DW_DOMINANCE_ENUMERATION_FIXTURES.json');assert fixtures['PASS'] and fixtures['native_optimize_calls']==0
    for x in fixtures['fixtures']:assert F(x['z_arc_LP'])<=F(x['z_DW_LP'])<=F(x['z_original_integer'])==F(x['z_DW_integer'])
    agg=read(OUT/'DW_BOUND_AGGREGATION_PROOF.json');assert not agg['PASS'] and agg['adopted_floor'] is None
    r=read(OUT/'DW_THRESHOLD_FINAL_RESULT.json');assert r['new_RMP_solves']==r['new_pricing_calls']==r['total_optimize_wall_union']==r['new_discovery_columns']==0
    original=read(PR142/'DW_THROUGHPUT_FINAL.json');assert r['final_interval']==original['final_interval'] and r['best_corrected_LB']==original['best_corrected_LB']
    diagnosis=read(OUT/'DW_PRICING_BOUND_DIAGNOSIS.json');assert not diagnosis['incumbent_used_as_LB']
    # Independent exact reconstruction of every existing PR142 pricing certificate.
    from v42_disjunctive.certificate import rational_bound,down
    from v42_dw_root.models import subset
    from v42_degen.identity import inputs
    from v42_dw_root.partition import axes
    import numpy as np
    A,d,B,e,*_=inputs();owner,row_owner=axes();g=np.flatnonzero(row_owner<0);zcols=np.flatnonzero(owner<0);G=B[g][:,zcols]
    assert np.all(np.abs(e['lower'][owner>=0])<1e90) and np.all(np.abs(e['upper'][owner>=0])<1e90)
    with np.load(OLD/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    gd=subset(e,g,zcols,native);gd['constant']=e['constant']
    with np.load(PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz') as z:lo=z['lower'][zcols];hi=z['upper'][zcols]
    certs=[]
    for file in sorted((PR142/'bound_certificates').glob('ROUND_*.json'))+sorted((POLICY/'bound_certificates').glob('ROUND_*.json')):
        directory=file.parent.parent;c=read(file);p=read(directory/c['pricing_receipts'][0])
        with np.load(directory/p['dual_file']) as z:pi=z['pi'];alpha=z['alpha']
        proof=rational_bound(G,gd,pi,lo,hi);value=F(int(proof['exact_bound_numerator']),int(proof['exact_bound_denominator']))
        correction=sum((F(float(a))+min(F(0),F(float(beta))) for a,beta in zip(alpha,c['beta_safe'])),F(0))
        exact=value+correction
        assert exact==F(int(c['exact_numerator']),int(c['exact_denominator'])) and down(exact)==c['L_corr']
        for i,pfile in enumerate(c['pricing_receipts']):
            price=read(directory/pfile)
            assert price['dual_SHA']==c['dual_SHA'] and price['valid_bound'] and price['native_status'] in (2,9)
            assert price['global_bound_includes_ObjCon'] and price['objective_transport_exact']
            assert price['settings']['Threads']==1 and price['settings']['FeasibilityTol']==price['settings']['IntFeasTol']==price['settings']['OptimalityTol']==EPS
            assert c['beta_raw'][i]==price['ObjBound']
            assert F(c['beta_safe'][i])<=F(price['ObjBound'])-F(EPS)
        certs.append(dict(source=file.relative_to(ROOT).as_posix(),round=c['iteration'],PASS=True,L_corr=c['L_corr'],exact_fraction_reconstructed=True,pricing_incumbent_used=False))
    assert max(c['L_corr'] for c in certs)==r['best_corrected_LB']
    tests={}
    for label in ('SEMANTIC','FULL'):
        receipt=read(OUT/f'PYTEST_{label}_RECEIPT.json');log=(OUT/f'{label}_TEST.log').read_text(encoding='utf8')
        matches=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
        assert receipt['exit_code']==0 and matches and receipt['all_Gurobi_Threads_one'] and receipt['calls_nonoverlapping']
        tests[label]=dict(PASS=True,passed=int(matches[-1][0]),seconds=float(matches[-1][1]),native_test_calls=len(receipt['calls']),scope='Regression fixture solves after the preopt gate stop; not production or full-scale experiment')
    semantic=dict(PR142_identity=True,checkpoint_1158=True,conv_inclusion=True,coupling_identity=True,full_projected_feasible_set_inclusion=True,enumeration_dominance=True,integer_equivalence=True,arc_floor_adoption='BLOCKED_UNVERIFIED_ARC_LP_LOWER_CERTIFICATE',max_rule='PROVED_CONDITIONALLY_NOT_APPLIED',BestBd_semantics=True,incumbent_not_LB=True,smoothing_Discovery_only='REGISTERED_NOT_RUN',true_dual_acceptance='REGISTERED_NOT_RUN',four_way_same_dual='PR142_AUDITED_NEW_NOT_RUN',no_domain_restriction=True,no_column_deletion=True,RAM_1GiB='REGISTERED_NOT_RUN',May_workers_4_1_4_1=True,B2_inner1_B3_inner4=True,May_production_zero=True)
    write('VERIFICATION.json',dict(PASS=True,scope='Evidence integrity, formal inclusion, exhaustive fixtures, correct refusal at the failed floor gate, and regressions. Does not assert that the requested arc-LP scalar lower bound was certified.',scientific_experiment_completed=False,preopt_gate_PASS=False,stop_stage=4,base_head=BASE_HEAD,old_tracked_files_preserved=preserved,source_freeze_PASS=True,columns_revalidated=1158,certificates=certs,tests=tests,regression_contract=semantic,new_optimize_calls=0,production_calls=[0,0,0],git_diff_check='Run separately before commit',manifest_self_excluded=True))
    report(tests)
    manifest()
    print('STOPPED_GATE_VERIFICATION_PASS',tests,flush=True)

def report(tests):
    r=read(OUT/'DW_THRESHOLD_FINAL_RESULT.json');p=read(OUT/'DW_PRICING_BOUND_DIAGNOSIS.json');last=p['rounds'][-1];rows=[x for x in p['per_MESS'] if x['round']==last['round']]
    proof=' / '.join(f"{x['MESS']}: {x['proof_gap_m']:.3g}" for x in rows)
    text=f'''1. 요청 branch `codex/v42-m1-dw-dominance-threshold-bound-v1`. Draft PR과 최종 remote SHA는 게시 후 PR 본문에 기록한다. Semantic {tests['SEMANTIC']['passed']} PASS, full pytest {tests['FULL']['passed']} PASS. Git clean은 게시 후 확인한다.
2. PR142 exact head `{BASE_HEAD}` 및 remote Draft identity PASS.
3. checkpoint retained trajectory 1,158개 전부 SHA, 원본 local rows, raw integrality, physical semantics, coupling projection 감사 PASS. Old pricing replay 0.
4. `conv(X_m^I) ⊆ P_m^arc`, 원본 축 복원 및 full-scale projected inclusion PASS. 따라서 `z_arc_LP ≤ z_DW_root`. 이는 모든 미발견 legal trajectory에도 성립하는 affine inclusion이다.
5. route split, charge mode, SOC/travel energy, PCS, grid coupling, terminal SOC, multi-MESS 등 7개 bounded fixture의 모든 integer face/continuous vertices를 Fraction으로 전수 열거했다. `z_arc ≤ z_DW ≤ z_integer` 및 integer master 동등성 PASS. Native optimize 0.
6. **요청 scalar floor 채택은 중단했다.** `0.5687116103498322`의 저장 출처는 interrupted integer MIP의 terminal global BestBd다. Exact original arc-LP dual certificate는 없고, root message는 반올림값이며 LP point에는 primal values만 있다. 기존 integer certificate를 부정한 것이 아니라 DW root로의 bound 전이를 인증하지 못한 것이다. LP objective와의 수치적 근접성은 수학적 lower-bound 증명이 아니다.
7. optimize 없이 유지한 certified PR142 interval: `[{r['best_corrected_LB']}, {r['smallest_RMP_upper']}]`. 조건부 arithmetic `[{BASE_LB}, {r['smallest_RMP_upper']}]`는 별도로 기록했으며 certified interval로 표시하지 않았다.
8. PR142 Certification pricing diagnosis: exact negative RC가 약한 corrected LB를 설명한다. 최종 기존 receipt 네 개 모두 OPTIMAL, native BestBd=incumbent objective, native gap 0.
9. 최종 PR142 MESS proof gaps: {proof}. 수치 RC 재계산의 1e-8 이내 음수 roundoff는 diagnostic gap에서 0으로 표시했다.
10. Pricing root objective는 native log가 cutoff인 경우 NULL이다. Root relaxation 완료 시간도 objective가 노출된 로그만 기재했다. First incumbent exact timestamp는 저장되지 않아 NULL. Terminal bounds/RC/native gap/node count는 CSV에 있다. 관측되지 않은 root gap을 만들어 쓰지 않았다.
11. PR142 receipt 기반 `PRICING_BOUND_CLASSIFICATION={p['classification']}`. Summed actual negative RC magnitude={last['sum_negative_incumbent_magnitude']:.12f}; summed proof weakness room={last['sum_proof_weakness_room']:.12g}. Causal uniqueness를 주장하지 않는다.
12. 새 Discovery rounds 0. Lower-floor gate에서 중단했다.
13. 새 validated columns 0; retained 1,158.
14. 새 columns/min N/A. 실행하지 않은 실험을 0 throughput 측정으로 보고하지 않았다. PR142 reference 6.910010.
15. 새 RMP upper trajectory 없음; 기존 smallest audited upper `{r['smallest_RMP_upper']}` 유지.
16. 기존 certified point의 `D_U={r['D_U']:.12f}`, `D_L={r['D_L']:.12f}`. Floor 미채택 기준이다. 새 trajectory 없음.
17. Final Certification NOT_RUN_PREOPT_GATE_STOP. 새로운 900-s budget 사용 0 s; 자동 연장 없음.
18. 유지한 best pricing-corrected LB `{r['best_corrected_LB']}`. 기존 마지막 PR142 corrected LB `{last['L_corr']}`는 별도 기록.
19. `max(arc,corr)` theorem은 두 lower bound가 같은 DW optimum을 대상으로 유효하다는 조건 아래만 성립한다. Arc premise 미인증으로 적용하지 않았다. Aggregated lower floor NULL.
20. Smallest audited RMP upper `{r['smallest_RMP_upper']}`.
21. 최종 certified DW interval `[{r['best_corrected_LB']}, {r['smallest_RMP_upper']}]`.
22. 요청 material threshold `{T_MATERIAL}` 유지. Threshold 숫자와 floor certificate는 별도 authority다.
23. DW materiality INCONCLUSIVE. 이번 threshold experiment NOT_RUN; budget 소진 실험으로 포장하지 않았다.
24. Exact CG convergence 인증 안 됨. 기존 pricing optimum들은 실제 negative RC다.
25. 다음 단일 blocker: 원본 frozen arc LP에 대한 lower-bound certificate 확보. 이 gate가 통과한 뒤의 CG 방향은 fixed four-way smoothed Discovery다. 이번 작업에서 pricing formulation redesign/추가 CG/parameter tuning은 하지 않았다.
26. Branch-and-Price NOT_RUN; future gate 변경 없음.
27. May day workers 4/1/4/1, 각각 31일, Threads 1 보존.
28. B2 inner pricing 1 / B3 inner pricing 4 보존.
29. May optimizer / Actual / Fresh AC calls 0/0/0. Production M1/P2/A2/M2 미실행.
30. A1 freeze, 4 MESS, 96 slots, full original route/mode/PCS16/SOC/grid/objective/P2 scientific contract 및 모든 기존 tracked source/artifact bytes 보존. Warm RMP 재시험/worker/RAM/alpha sweep 없음.

요청된 마지막 문구 중 “기존 arc-LP lower bound를 … 사용했다”는 이번 결과에는 적용할 수 없다. 정확한 결과는 다음과 같다.

이번 작업에서는 full-scale feasible-set inclusion을 증명했지만, 기존 scalar의 arc-LP lower-bound authority가 확인되지 않아 D-W root의 independent lower floor로 사용하지 않았다.

Pricing incumbent는 global lower bound로 사용하지 않았으며,
pricing BestBd와 feasible reduced-cost trajectory의 차이는
certification weakness 진단에만 사용했다.

Adaptive dual smoothing은 Discovery에만 사용하고,
column acceptance와 scientific certificate는 true RMP dual authority를 유지하도록 preregister했다. 이번 작업의 새 pricing은 gate 실패로 실행하지 않았다.

Branch-and-Price와 May production은 실행하지 않았다.
'''
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')

def manifest():
    prefixes=('v42_dw_dominance','tests/v42_dw_dominance','docs/v42_m1_dw_dominance_threshold_bound');files=[]
    for folder in prefixes:
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.name!='SHA256_MANIFEST.json' and not p.name.endswith('.tmp'):
                files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    write('SHA256_MANIFEST.json',dict(files=files,self_excluded=True,policy='Exact staged blob bytes required; old tracked tree immutable; no self-referential commit SHA embedded'))

if __name__=='__main__':verify()

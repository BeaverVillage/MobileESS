"""Publish truthful stop artifacts; never launches a solve or a recovery."""
from pathlib import Path
import json,csv,hashlib,subprocess,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'docs/v42_m1_dual_authority_early_bap';OLD=ROOT/'docs/v42_m_stage_exact_completion'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def text(n,s):(OUT/n).write_text(s,encoding='utf8')
def table(n,rows,fields):
    with (OUT/n).open('w',encoding='utf8',newline='') as f:w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
def run():
    result=read(OUT/'FORENSIC_COMPLETION.json');assert not result['EXACT_DUAL_AUTHORITY_PASS'] and result['fullscale_native_calls']==0
    xml=ET.parse(OUT/'TEST_RESULTS.xml');suites=list(xml.getroot().iter('testsuite'))
    test_result=dict(tests=sum(int(s.get('tests',0)) for s in suites),failures=sum(int(s.get('failures',0)) for s in suites),errors=sum(int(s.get('errors',0)) for s in suites),skipped=sum(int(s.get('skipped',0)) for s in suites))
    assert test_result['failures']==test_result['errors']==0
    native=[]
    for p in sorted((OUT/'toy_snapshots').rglob('*.json')):
        m=read(p)
        if 'origin' in m and 'snapshot_SHA' in m:native.append(dict(file=str(p.relative_to(OUT)),origin=m['origin'],Runtime=m['runtime'],status=m['status']))
    write('TOY_NATIVE_RUNTIME_LEDGER.json',dict(calls=len(native),native_Runtime_sum=sum(x['Runtime'] for x in native),scope='Only tiny Gurobi LP fixtures; historical certificate tests also include tiny SciPy LP enumeration, outside M1 grant and not Gurobi Model.Runtime.',calls_detail=native))
    repair_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    write('DUAL_SIGN_FIX_REGRESSION.json',dict(PASS=True,scope='New evidence-durability/terminal-LP guard and existing corrected-bound regressions only; not resolution of RMP43.',test_result=test_result,new_guard_tests=15,
        native_sign_fixtures_PASS=True,strong_duality_bound_fixture_PASS=True,existing_column_RC_fixture_PASS=True,sense_negation_scaling_PASS=True,
        axis_stale_dual_point_rejection_PASS=True,Pi_BarPi_representation_rejection_PASS=True,strict_tiny_wrong_sign_rejection_PASS=True,
        rejected_point_saved_before_gate_PASS=True,EXACT_DUAL_AUTHORITY_PASS=False,sign_gate_relaxed=False,sign_projection=False,
        fullscale_native_calls=0,pricing_calls=0,guard_commit=repair_commit))
    prereg='''# Early B&P preregistration — blocked before optimization

Authority: Draft PR155 0b557f6318b8192e08ee99102046576e68dd27d4.
Child branch: codex/v42-m1-dual-authority-early-bap. PR155 history is immutable.
The approved pool has1841 valid columns; audited RMP42 used1825. Starting root
LB=.5687115725336208. Restricted LP .5729695797088222 is never integer UB.
Materiality PROVEN_NONMATERIAL is preserved and not re-proven.

No native full-scale model build/solve, pricing, restricted integer master,
600s comparison or7200s grant can run while EXACT_DUAL_AUTHORITY_PASS=false.
Rejected RMP43 raw X/Pi/RC/row matrix snapshot was not persisted. This request's
STOP_DUAL_AUTHORITY_UNRESOLVED gate is binding; no recovery retry is launched.

Conditional design only (not implemented/executed): after actual authority PASS,
port PR145 8c27932d303bc38c2d2c927b9c24348e9fa154e9 node/queue/branch/Phase-I
framework into a new child implementation without overwriting saved evidence.
The branch is in original route/location/state space; deterministic fractional
quantity selection/tie breaking, exhaustive disjoint children, restrictions
enforced for retained and unseen columns. Node LB=max(inherited certified LB,
new independently certified full-domain-pricing corrected LB when available).
Unfinished RMP objective is never node LB. Global LB=min active valid node LBs;
valid original-feasible integer incumbent is UB; no integer UB means no gap stop.
Prune only exact Phase-I infeasibility or valid LB>=valid UB under existing
authority. TIME_LIMIT pricing may contribute only a validated global bound,
never a fabricated optimum. Root CG convergence is not a logical prerequisite.

Only after all required dual/B&P equivalence tests PASS: sequential (not concurrent)
root continuation versus integer UB+early B&P comparison, total continuous wall<=600s
including preparation for both. Preregister split based on measured build costs;
do not reset wall clock. Compare integer global gap progress, not LP interval.
One 7200s total new native grant only if practical selection gate succeeds;
all node/RMP/pricing/integer/proof/P2 runtimes share that one ledger.
Then P1 gap<=.005 permits frozen locks and P2 movement energy->movement count,
only within remaining grant. These learned-checkpoint runs are development,
never fresh production/paper runtime. No campaign/A2/M2/B2/B3 launches.
'''
    text('EARLY_BAP_PREREGISTRATION.md',prereg)
    blocked=dict(status='NOT_RUN_DUAL_AUTHORITY_UNRESOLVED',EXACT_DUAL_AUTHORITY_PASS=False,new_native_calls=0,new_native_runtime=0.,reason='Mandatory user stop gate; rejected point missing and native retained-column RC vector missing.')
    write('RESTRICTED_INTEGER_MASTER_RESULT.json',dict(**blocked,integer_UB=None,restricted_LP_not_integer_UB=True,retained_valid_columns=1841))
    write('EARLY_BAP_SCIENTIFIC_EQUIVALENCE.json',dict(**blocked,PASS=False,framework_authority='8c27932d303bc38c2d2c927b9c24348e9fa154e9',port_executed=False,branch_union_disjointness='NOT_RUN',child_pricing_enforcement='NOT_RUN',node_bound_validity='NOT_RUN',toy_direct_MILP_early_BAP_equivalence='NOT_RUN'))
    write('EARLY_BAP_MICROBENCHMARK.json',dict(**blocked,EARLY_BAP_SELECTED=False,selection_evaluated=False,comparison_run=False,continuous_wall_limit=600.,root_baseline_scope='Historical PR155 only; not fresh A/B benchmark.',historical_root_certified_LB_start=.5687115725336208,historical_root_certified_LB_end=.5687115725336208,historical_root_LB_improvement=0.,historical_root_new_native_union=1010.1359987999604,historical_restricted_LP_upper_start=.5741861223241257,historical_restricted_LP_upper_end=.5729695797088222,root_integer_global_gap=None,early_BAP_integer_global_gap=None,early_BAP_node_count=0,pricing_calls=0,RMP_calls=0,engineering_20_percent_gate_evaluated=False))
    write('M1_7200_DEVELOPMENT_RESULT.json',dict(**blocked,run_executed=False,grant_consumed=0.,grant_max_if_selected=7200.,P1_ACCEPTED=False,integer_UB=None,starting_certified_LB=.5687115725336208,new_global_LB=None,global_gap=None,nodes=0,development_only=True,automatic_extension=False))
    write('M1_P2_RESULT.json',dict(**blocked,movement_energy=None,movement_count=None,P1_ACCEPTED=False))
    for name,fields in {
        'BAP_NODE_LEDGER.csv':['node','parent','status','inherited_valid_LB'],
        'BAP_BRANCH_LEDGER.csv':['parent','quantity','children','exhaustive','disjoint'],
        'BAP_NODE_BOUND_LEDGER.csv':['node','certificate','inherited_LB','new_valid_LB','LB'],
        'BAP_GLOBAL_BOUND_LEDGER.csv':['time','active_nodes','valid_integer_UB','valid_global_LB','gap'],
        'BAP_PRICING_LEDGER.csv':['node','unit','native_status','global_BestBd','valid_bound','runtime'],
        'M1_P1_GLOBAL_GAP_TRAJECTORY.csv':['time','integer_UB','global_LB','gap']}.items():table(name,[],fields)
    table('RESOURCE_LEDGER.csv',[dict(phase='OFFLINE_FORENSIC_ONLY',wall_seconds=result['forensic_wall_seconds'],RSS_start_bytes=result['RSS_start_bytes'],RSS_end_bytes=result['RSS_end_bytes'],RSS_OS_high_water_bytes=result['RSS_os_high_water_bytes'],memory_policy='READ_ONLY',fullscale_native_calls=0)],['phase','wall_seconds','RSS_start_bytes','RSS_end_bytes','RSS_OS_high_water_bytes','memory_policy','fullscale_native_calls'])
    forensic='''# RMP dual sign forensic

## Proven findings and unresolved cause

The PR155 executed master constructor transports the original CSR coefficients,
RHS, senses, names and bounds verbatim; no row negation/normalization. Convexity
is sum(lambda)=1. For minimization native Pi has <= nonpositive, >= nonnegative,
equality unrestricted signs. Pricing uses c-B.T@Pi-alpha with multiplier+1.
The saved RMP42 obeys this convention for every original row family and all four
convexity equalities. Row/dual-axis SHA matches the checkpoint.

Source: [Gurobi Pi/BarPi reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/constraintlinear.html).
Method2/Crossover1 returns terminal X/Pi/RC after crossover. BarPi describes the
barrier point and must not be substituted for terminal Pi. The code used Pi;
there is no evidence that RMP43 mixed representations. Barrier numeric->optimal
in its log is a warning/observation, not a proof of the exact failed dual entry.

RMP43 point_file/dual_SHA/objective are null. The executed source asserts the
Pi signs BEFORE np.savez of point/pi/alpha/lambda. Thus the rejected raw vector
and row-level failure were lost. This evidence-capture defect is proven. The
FIRST failed family, value, and exact sign root cause remain UNRESOLVED. Code
conversion, row normalization, stale/serialized dual and numerical mechanisms
cannot be selected without inventing evidence. No full-scale replay was run.

## Independent existing-state audit

All1841 retained-column reduced costs are computed two independent ways:
stored master coupling c-a.T@Pi-alpha versus original local-domain objective
(c-B.T@Pi).T@x-alpha. Max difference5.204170427930421e-18.
This proves transport identity, not equality to a saved native RC vector.
RMP42 used1825 lambdas;16 subsequent columns were not in that optimal RMP.
Native RC vectors/bound duals were not saved; only max-error scalar2.997428694140325e-14
is preserved. CSV explicitly marks native RC comparison UNRESOLVED, never fakes
per-column solver RC. Primal objective independently reconstructs exactly the
saved .5729695797088222. Free-coordinate manual stationarity residual up to
1.9804307933163345e-15 precludes substituting unbounded support from an incomplete
b.T@Pi sum. No residual is rounded away to claim exact strong duality.

Existing corrected-bound rational arithmetic (RMP36/global proof/alpha/same-dual
pricing lower bounds with unchanged1e-8 safety) reconstructs .5501655188774129.
Aggregated approved root floor .5687115725336208 is preserved. This formula
check is not materiality recomputation or authority for RMP43.

## Implemented repair and guard

Before any gate, durable snapshot saves exact CSR/row and column axes, native
X/Pi/RC and optional BarX/BarPi/bases from the same terminal model. Immutable
identity hashes reject axis/point/dual mutations. Independent audit includes
all reduced costs and lower/upper bound dual terms in strong duality; nonzero
support at an infinite bound is rejected. Actual wrong-sign Pi, even1e-15,
remains rejected with no projection or tolerance change. Pricing is reached
only after this guard AND the existing original-row/manual-RC audits; existing
full-domain corrected-bound certificate remains unchanged.

Small sign/scaling/bound/representation/rejection fixtures pass. This repairs
evidence preservation and strengthens future acceptance. It DOES NOT establish
EXACT_DUAL_AUTHORITY_PASS for the missing historical rejected point.

## Mandatory stop

STOP_DUAL_AUTHORITY_UNRESOLVED / EXACT_DUAL_AUTHORITY_PASS=false.
No restricted integer master, new root solve/pricing, early-B&P,600s comparison,
7200s development, P2, campaign or materiality solve. No full-scale solver
parameters, scientific inputs, physical constraints or thresholds were changed.
'''
    text('DUAL_SIGN_FORENSIC.md',forensic)
    peak=result['RSS_os_high_water_bytes']/2**30
    report=f'''# 최종 보고 — DUAL_AUTHORITY_UNRESOLVED

PR155의 원본 증거를 보존한 child branch에서 dual forensic과 영구 guard를 구현했다.
사용자 지정 STOP 조건에 따라 exact dual authority가 해결되기 전 모든 full-scale
최적화와 B&P 개발 실행을 중지했다. sign gate를 우회하지 않았다.

| 항목 | 결과 |
|---|---|
|1. exact dual-sign root cause|RMP43 원시 Pi/X/RC 미저장으로 첫 실패 행/원인 미확정. assertion 후 저장한 증거 유실은 확인.|
|2. exact fix|거부 전 durable snapshot 및 독립 terminal dual guard. 실제 RMP43 부호 오류 해결은 미확정.|
|3. strong duality|bound terms 포함 tiny fixtures PASS. 저장된 full-scale point의 native RC/bound dual vectors 미보존으로 요청된 완전 감사 미해결.|
|4. existing-column RC|1841개 two-path transport 오차 최대5.204e-18. native per-column RC 비교는 미해결. RMP42 활성1825개와 추가16개 분리.|
|5. restricted integer UB|없음; integer master NOT_RUN. LP .5729695797088222를 UB로 사용하지 않음.|
|6. starting certified LB|.5687115725336208 보존. corrected-bound 기존 rational arithmetic PASS.|
|7. early B&P branch rule|미구현/NOT_RUN. PR145 original-space exhaustive branch만 조건부 계획.|
|8. child inheritance|조건부 수학 계획 LB_child>=LB_parent. 실제 child proof/test NOT_RUN.|
|9.600s benchmark|NOT_RUN_DUAL_AUTHORITY_UNRESOLVED.|
|10. root-CG baseline|기존1010.136 native union 동안 aggregate LB 증가0; restricted LP 감소는 integer gap 진척으로 간주하지 않음.|
|11. early-B&P gap progress|측정 없음.|
|12. selected/rejected|선택 안 함; 성능 비교를 평가하지 않아 EARLY_BAP_REJECTED로 오표시하지 않음.|
|13.7200s run|실행 안 함, grant debit0.|
|14. B&P nodes|0.|
|15. best integer UB|null.|
|16. global certified LB|새 B&P global LB 없음; starting root certificate만 보존.|
|17. global MIP gap|null (valid integer UB 없음).|
|18. P1 accepted|false.|
|19. P2 movement energy|NOT_RUN.|
|20. P2 movement count|NOT_RUN.|
|21. native runtime|새 full-scale0초. tiny Gurobi LP {sum(x['Runtime'] for x in native):.6f}초/{len(native)}calls; 개발 grant와 분리.|
|22. resource peak|offline forensic OS process high-water {peak:.3f}GiB; peak machine memory/optimization RSS라고 주장하지 않음.|
|23. tests|{test_result['tests']} PASS, errors/failures0. 신규 guard15개 및 기존 corrected-bound 회귀. branch/B&P tests NOT_RUN.|
|24. commit / Draft PR|guard repair {repair_commit}; child Draft PR publication receipt 참조.|

## 요구된 종료 문구의 사실관계

“RMP dual 부호 오류를 해결했다”는 선언은 현재 할 수 없다. row convention과
fixture는 검증했지만 RMP43 raw evidence가 없어 EXACT_DUAL_AUTHORITY_PASS=false다.
Exact root convergence가 early B&P의 논리적 선행조건이 아니라는 설계는 명시했으나
B&P를 실행하지 않아 node/global-bound 사용·0.5% 종료 달성을 주장하지 않는다.
Restricted LP objective를 global LB/integer UB로 사용하지 않았다.
휴리스틱-only pruning, approximate pricing, convergence tolerance 완화는 사용하지 않았다.

## 보존 및 중단

원본 PR155 docs의 byte hashes,1841-column checkpoint, valid RMP42,
PROVEN_NONMATERIAL, ROOT_CG_CONVERGED=false 및 B&P NOT_RUN 상태를 그대로 보존했다.
Full-scale 추가 실행/재현으로 없는 RMP43 point를 만들어 과거 증거처럼 쓰지 않았다.
증거가 없는 상태에서 임의 부호를 뒤집거나 guard를 끄지 않았다.
May campaign과 다른 downstream production을 재개하지 않았다.
'''
    text('FINAL_REVIEW_KO.md',report)
    required=['DUAL_SIGN_FORENSIC.md','RMP_DUAL_CANONICAL_CONVENTION.json','RMP42_RMP_REJECTED_DUAL_DIFF.json','DUAL_STRONG_DUALITY_AUDIT.json','EXISTING_COLUMN_RC_IDENTITY.csv','DUAL_SIGN_FIX_REGRESSION.json','EARLY_BAP_PREREGISTRATION.md','RESTRICTED_INTEGER_MASTER_RESULT.json','EARLY_BAP_SCIENTIFIC_EQUIVALENCE.json','EARLY_BAP_MICROBENCHMARK.json','BAP_NODE_LEDGER.csv','BAP_BRANCH_LEDGER.csv','BAP_NODE_BOUND_LEDGER.csv','BAP_GLOBAL_BOUND_LEDGER.csv','BAP_PRICING_LEDGER.csv','M1_7200_DEVELOPMENT_RESULT.json','M1_P1_GLOBAL_GAP_TRAJECTORY.csv','M1_P2_RESULT.json','RESOURCE_LEDGER.csv','FINAL_REVIEW_KO.md']
    preserve=read(OUT/'PR155_BYTE_PRESERVATION.json')['files'];unchanged=all(sha(ROOT/n)==v for n,v in preserve.items())
    assert unchanged and all((OUT/n).exists() for n in required)
    write('VERIFICATION.json',dict(status='DUAL_AUTHORITY_UNRESOLVED',EXACT_DUAL_AUTHORITY_PASS=False,STOP_DUAL_AUTHORITY_UNRESOLVED=True,PR155_byte_preservation_PASS=unchanged,PR155_files=len(preserve),starting_pool=1841,active_RMP42_pool=1825,
        corrected_bound_arithmetic_PASS=True,root_materiality_recomputed=False,fullscale_native_calls=0,pricing_calls=0,BAP_nodes=0,restricted_integer_master_run=False,microbenchmark_run=False,run7200=False,P1_ACCEPTED=False,P2_RUN=False,May_campaign_run=False,
        strict_sign_gate_unchanged=True,full_domain_certificate_formula_unchanged=True,numerical_authorities_unchanged=True,scientific_inputs_unchanged=True,
        new_memory_protection_added=False,resource_solver_tuning_added=False,tests=test_result,guard_commit=repair_commit,required_artifacts=required,
        new_native_runtime_scope='Tiny fixtures only; full-scale development grant debit0.',root_cause_unresolved_reason='Missing RMP43 raw dual/point and full-scale native per-column RC/bound-dual vector prevents all required authority checks.',
        global_integer_UB=None,global_gap=None,EARLY_BAP_SELECTED=False,performance_selection_evaluated=False))
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name not in ('SHA256_MANIFEST.json','PUBLICATION_RECEIPT.json')]
    write('SHA256_MANIFEST.json',dict(files={str(p.relative_to(OUT)):sha(p) for p in sorted(files)},self_reference_excluded=True,publication_receipt_separate=True))
    print(json.dumps(dict(status='DUAL_AUTHORITY_UNRESOLVED',tests=test_result,fullscale_native_calls=0,byte_preservation=unchanged,guard_commit=repair_commit,artifacts=len(required)+2)))
if __name__=='__main__':run()

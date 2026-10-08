"""Publish saved, validated evidence without calling native optimization."""
from .common import *
import shutil
import py_compile
import argparse
from .analysis import csv_rows

DEST=ROOT/NAMESPACE
REQUIRED=['BINARY_9322_FULL_MAPPING.csv','BINARY_MAPPING_AUDIT.json','PHYSICS_GROUP_DEFINITION_KO.md',
    'GROUP_CRITICAL_GRID_SCORES.csv','GROUP_SOC_PCS_COUPLING.csv','CANDIDATE_GROUP_RANKING.csv',
    'SELECTED_BRANCH_VARIABLES.json','BRANCH_DOMAIN_COVERAGE_PROOF.md','DUAL_CERTIFICATION_REPAIR_AUDIT.json',
    'CHILD_LP_RESULTS.csv','CHILD_0_EXACT_CERTIFICATES.json','CHILD_1_EXACT_CERTIFICATES.json',
    'GROUP_GLOBAL_LB_COMPARISON.csv','FRACTIONAL_SOLUTION_COMPARISON.json','PHYSICAL_INTERPRETATION_KO.md',
    'RUNTIME_WORK_BENCHMARK.csv','PROCESS_ISOLATION_AUDIT.json','FINAL_DECISION.json','SHA256_MANIFEST.json','FINAL_REVIEW_KO.md']

def format_number(v,digits=12):return '미측정' if v is None else f'{v:.{digits}f}'

def reports():
    final=read(REPORTS/'FINAL_DECISION.json');controller=read(REPORTS/'CONTROLLER_RESULT.json')
    physical=read(REPORTS/'PHYSICAL_INTERPRETATION_DATA.json')['children']
    rows=csv_rows(REPORTS/'CHILD_LP_RESULTS.csv');pairs=csv_rows(REPORTS/'GROUP_GLOBAL_LB_COMPARISON.csv')
    repair=read(REPORTS/'DUAL_CERTIFICATION_REPAIR_AUDIT.json');numeric=read(REPORTS/'CHILD_NUMERICAL_AUDIT.json')['children']
    review=[f'# Physics-Guided Two-Way LP 실제 검증\n\n판정: **{final["classification"]}**. 실제 Native optimize {final["native_optimize_calls"]}회, 총 Runtime {final["Native_Runtime_sum"]:.6f}초, Work {final["Work_sum"]:.6f}를 소비했다. 예산 6회/2,880초를 지켰다.\n',
        f'기존 LB {LB:.16f} → 인증 Global LB **{final["new_valid_global_LB"]:.16f}**, ΔLB **{final["Delta_LB"]:.16f}**. UB는 {UB:.16f}로 유지한다. Global Gap {final["old_global_gap_percent"]:.12f}% → **{final["new_global_gap_percent"]:.12f}%**. Material ΔLB≥0.001 Gate={final["Material_Gate_PASS"]}, M1_ACCEPTED={final["M1_ACCEPTED"]}. Production·P2·downstream 실행은 모두 0회다.\n',
        '## 실제 양방향 하한\n\n|후보 / 실제 원본 변수|Child|Native 목적값|Exact LB|인증 손실|Runtime(s)|Work|독립 인증|\n|---|---:|---:|---:|---:|---:|---:|---|']
    if final.get('authorized_z0_continuation_calls'):
        original=read(WORK/'children/C01/z0/RESULT.json')
        review.insert(2,f'첫 z=0은 TIME_LIMIT, Runtime {original["Runtime"]:.6f}초/Work {original["Work"]:.6f}였다. 사용자의 추가 지시로 z=0만 TimeLimit=1,800초의 fresh solve를 1회 실행했다. 나머지 설정과 scientific model은 그대로이며 z=1은 재실행하지 않았다. 다음 표의 z=0은 추가 실행 결과다. 최초 480초 원시값·diagnostic exact proof와 판정은 INITIAL_480 및 children/C01/z0에 보존했다. 총 호출/Runtime에는 이 첫 실패도 포함한다.\n')
    for r in rows:
        def n(k):return 'NOT_RUN' if not r.get(k) else format_number(float(r[k]),12)
        review.append(f'|{r["candidate"]} {r["variable"]}|{r["value"]}|{n("native_objective")}|{n("exact_LB")}|{n("certificate_loss")}|{n("Runtime")}|{n("Work")}|{r.get("certificate_PASS",False)}|')
    review.extend(['\n|후보|LB_pair = min(양쪽 Exact LB)|보존한 Global LB|ΔLB|병렬 Wall(s)|Native 합계(s)|Work 합계|\n|---|---:|---:|---:|---:|---:|---:|'])
    for p in pairs:
        def n(k):return 'NOT_RUN' if not p.get(k) else format_number(float(p[k]),12)
        review.append(f'|{p["candidate"]}|{n("LB_pair")}|{n("valid_global_LB")}|{n("Delta_LB")}|{n("parallel_wall_seconds")}|{n("Native_Runtime_sum")}|{n("Work_sum")}|')
    review.append('\nC01의 병렬 Wall은 최초 480초 pair의 관측값이고 Native 합계/Work 합계는 최종 proof를 제공한 새 z=0과 재사용 z=1의 합계다. 최초 실패 비용 480.078초를 포함한 모든 소비는 전체 Runtime과 RUNTIME_WORK_BENCHMARK에 들어 있다. C02의 성능 열은 실제 동시 실행의 동일 pair다. C03은 추가 pair를 실행하면 총7회가 되어 호출 예산을 넘으므로 NOT_RUN_CALL_BUDGET다.\n')
    measured=[p for p in pairs if p.get('LB_pair')]
    if measured:
        best=min(measured,key=lambda p:-float(p['LB_pair']))
        review.append(f'실측 후보 중 가장 강한 pair는 **{best["candidate"]} {best["variable"]}**, Exact pair LB {float(best["LB_pair"]):.16f}이다. 그러나 inherited Global LB보다 낮아 최종 개선과 Material Gate를 통과한 후보는 없다.\n')
    review.extend(['\n## 영역·과학적 동치성과 인증\n',
        'PR187 exact HEAD `e67ecfa827e4262c2f2df17c226d6442656af18b` 및 원본 C3A hash를 검증했다. 원본 582,808행/306,040열에 기존 B2 651행만 이어 사용했다. 원본 min rho_max 목적 계수·ObjCon·변수축·목적 hash `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`를 보존했다. 각 Child는 선택 binary bounds 한 개만 0/0 또는 1/1로 고정했고 나머지 binary를 LP에서 C로 완화했다. route_flow 207,736개는 원래 continuous를 유지했다. 원래 feasible integer 영역의 두 부분 합집합을 증명했으며, Child 하한 하나나 Native 목적값을 전체 Global LB로 승격하지 않았다.\n',
        f'저장 ROOT의 equality repair Exact LB={repair["independent"]["certified_LB"]:.16f}, 인증 손실={repair["native_minus_certificate"]:.16f}, 옛 1e-4 품질 Gate={repair["certification_pilot_gate_PASS"]}를 그대로 보존했다. 사용자의 재개 지시로 손실 크기는 진단으로만 사용하고, 독립 exact proof PASS를 실행 Gate로 삼았다. 기존 DUAL_CERTIFICATION_BLOCKED 표기는 당시 상태이며 최종 실제 실험 판정은 이 문서와 FINAL_DECISION이다.\n',
        f'선택된/진단용 exact proof {final["independent_exact_checks"]}개를 Worker별 CSR 독립 checker와 Controller 사후 checker가 재검증했다. Native 미완료 Child의 diagnostic certificate는 Global pair에 채택하지 않는다. Producer는 CSC 열, checker는 CSR 행을 exact integer dyadic으로 계산하며 모든 306,040개 finite-bound support를 대조한다. 부호가 잘못된 raw Pi를 거부하고 별도 sign-cone/equality multiplier를 저장했다. 원시 X/Pi/RC/slack과 repair 전후 증거를 보존했다. 최종 portable verify_saved도 solve 없이 이 증거를 검사한다.\n',
        'Raw fractional 해의 strict C3A/복원 FULL replay 결과는 FRACTIONAL_SOLUTION_COMPARISON에 그대로 기록한다. FAIL 해를 실제 물리 운전이나 integer incumbent로 표현하지 않으며 UB를 갱신하지 않는다. 인증된 weak-duality LB는 primal replay와 별도 수학적 증거다.\n',
        '## 병렬 성능과 다른 작업\n',
        f'Controller Wall 합계={final["controller_wall_seconds"]:.6f}초(초기 병렬+추가 z=0+Phase B, 분석·사용자 steering 사이 시간 제외). launch/checkpoint 시각으로 관측한 실험 elapsed Wall={final["observed_experiment_elapsed_wall_seconds"]:.6f}초는 사용자 steering·코드·분석 사이 시간을 포함한다. 최초 pair는 spawn 독립 Process 두 개, 독립 Env/Model, Threads=1, TimeLimit=480초다. 두 모델이 동시에 license를 확보한 후 공통 event로 시작했다. 최초 병렬 Wall={final.get("initial_parallel_wall_seconds")}초, 추가 z=0 Worker Wall={final.get("additional_z0_wall_seconds")}초다. worker별 model loading/build, wait, Native Runtime/Work, certificate, CPU/RSS를 별도로 보존했다. max_workers=2를 유지했고 추가 z=0은 Worker 한 개다.\n',
        '동일 TimeLimit/종료상태의 완전한 순차 baseline은 없다. 최초 z=0과 추가 z=0은 matched barrier prefix를 비교하지만 elapsed ratio는 시간제한·종료상태 및 공유 host 경합의 영향이 있는 진단이다. Native Runtime 합계/Native span도 실제 겹침 지표이며 speedup이 아니다. PR187 210.226초 ROOT는 historical baseline으로만 사용한다. 다른 May12 native 작업이 관측된 공유 host이므로 인과적인 병렬 가속이나 무경합 성능을 주장하지 않는다. 메모리 대역폭 counter는 NOT_MEASURED다. CPU/RSS/page fault/I/O는 관측했으며 MemLimit/SoftMemLimit이나 RAM 기반 자동 종료는 추가하지 않았다.\n',
        '첫 admission에서 다른 solver의 존재만으로 보류한 optimize=0 증거를 PRE_ADMISSION 파일과 첫 snapshot에 보존했다. 첫 호출 전 CPU 여유 및 독립 Threads=1 process 기준으로 admission을 보완하고 사전등록했다. 다른 작업의 프로세스·설정·증거는 중지하거나 수정하지 않았다.\n',
        '## 분기 실용성과 후속 판단\n',
        '9,322개 전수 변수 및 764개 primary group을 매핑했다. C01은 MESS02/77 충방전 모드, C02는 MESS01/STA12/67 outgoing node mass, C03은 MESS04/77 충방전 모드다. 전체 그룹을 고정하거나 multi-way 분할하지 않았다. 위치 through-mass는 STAY와 같지 않으며 이동 중 site activity가 모두 0일 수 있다. Label96 terminal aliases 96개는 physical slot95로 전수 검증했다.\n',
        ('Material Gate를 통과한 pivot만 후속 BranchPriority canary의 후보로 제안한다. 전체 0.5% gap에 이르지 않았다면 M1_ACCEPTED=false다.\n' if final['Material_Gate_PASS'] else
         '이 scalar group ranking을 production BranchPriority나 전체 Branch-and-Cut에 통합할 근거를 확보하지 못했다. 새로운 많은 분기를 추가하지 않는다. 점수는 후보 순위이며 인증 하한이 아니다. Native 목적값 증가와 Exact certificate/global 개선을 분리했다.\n'),
        'Gurobi BranchPriority는 scalar fractional binary 우선순위이며 물리 그룹 전체를 정확히 분할하는 사용자 branching 기능과 같지 않다. 미해결 sibling의 낮은 하한을 버리면 안 된다. 여러 변수의 joint branch는 전체 조합 coverage 증명이 필요하며 이번에 실행하지 않았다.\n',
        '[Gurobi multiprocessing 공식 지침](https://support.gurobi.com/hc/en-us/articles/360043111231-How-do-I-use-multiprocessing-in-Python-with-Gurobi)은 process마다 독립 Env를 요구한다. [BranchPriority 공식 속성](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#branchpriority)은 scalar variable 우선순위를 설명한다.\n',
        f'다음 행동은 정확히 하나: **{final["next_action"]}** 이번 작업에서 실행하지 않았다.\n',
        '## 재현·Git\n',
        '모든 신규 코드와 원시 evidence, 0/1 dual proof, 원본 source identity, 사전등록·call ledger·resource telemetry·한국어 보고서가 새 namespace에 포함된다. SHA256_MANIFEST는 자신을 제외한 증거·코드 hash를 보존한다. 원본 PR187/PR185 파일과 과학 모듈 hash는 unchanged다. 최종 commit/stacked Draft PR URL·remote equality·clean tree는 commit 자기참조를 피하여 WORK/reports/GIT_COMPLETION.json과 최종 대화에 기록한다.\n'])
    (REPORTS/'FINAL_REVIEW_KO.md').write_text('\n'.join(review),encoding='utf-8')
    text=['# 실제 LP 분기의 물리적 해석\n',
        '다음 값은 복원된 original FULL 변수축에서 측정한 fractional LP 진단이다. strict replay가 FAIL이면 운전 feasible 해로 해석할 수 없다. SOC 표의 min/max는 한 점의 시간축 범위이며 최적화로 구한 SOC feasible envelope가 아니다.\n',
        '|후보|Child|MESS/slot/site|선택 slot Pch(kW)|Pdis(kW)|Q(kvar)|SOC 시간 min/max(kWh)|Travel energy 가중합(kWh)|FULL replay|\n|---|---:|---|---:|---:|---:|---|---:|---|']
    for r in physical:
        p=r['selected_unit'];t=r['slot']
        text.append(f'|{r["candidate"]}|{r["value"]}|{r["MESS"]}/{t}/{r["site"] or "mode"}|{p["Pch_by_slot"][t]:.8f}|{p["Pdis_by_slot"][t]:.8f}|{p["Q_by_slot"][t]:.8f}|{p["minimum_SOC"]:.8f}/{p["maximum_SOC"]:.8f}|{p["weighted_travel_energy_kWh"]:.8f}|{r["strict_FULL_relaxed_replay"]["PASS"]}|')
    text.extend(['\nC01/C03의 z=0은 해당 MESS/slot에서 charge를 차단하고 discharge를 허용한다. z=1은 discharge를 차단하고 charge를 허용한다. 24개 원래 site의 Pch/Pdis와 SOC/PCS/grid coupling을 사용하며 Q는 모드와 독립이다. Q나 다른 MESS의 위치를 추가로 고정하지 않았다. 따라서 다른 위치와 시점으로 power·SOC·route를 재배분해 단일 mode 고정을 우회하는 fractional 대체해가 가능하다. 실제 재배분은 PHYSICAL_INTERPRETATION_DATA와 가족별 L1 변화에 기록한다.\n',
        'C02 z=0은 MESS01/STA12/67 outgoing flow를 원본 equality와 nonnegativity로 0으로 만든다. z=1은 이 vertex의 through-mass를 1로 제한한다. 이는 travel departure도 허용하므로 STAY나 charging을 강제하지 않는다. 다른 site 활동과 travel의 시간 cut을 함께 고려하며 임의 one-hot를 추가하지 않았다.\n',
        '원본 critical rho 행 100개의 실제 branch/time label을 source descriptor와 대조했다. Child별 정상화 slack, raw Pi, SOC97/Pch96/Pdis96/Q96/stay/travel weighted trajectories, 주요 node_activity 변화 20개를 보존한다. Voltage/thermal/PCS/route/SOC binding 행의 strict violation은 FRACTIONAL_SOLUTION_COMPARISON의 physical_row_families에 기록했다. Raw Pi는 shadow-price 인증으로 사용하지 않는다.\n',
        '정확한 Q/PCS 수치 손실과 binary 고정의 구조 효과는 별개다. CHILD_NUMERICAL_AUDIT는 선택된 multiplier의 finite-bound 손실과 row-residual 항을 분해하며 float 분해를 exact 증명과 구분한다. 원본 tolerance·물리 제약과 651개 B2 행은 변경하지 않았다.\n'])
    for r in numeric:
        top=r.get('finite_bound_loss_by_family',[])[:3]
        text.append(f'- {r["candidate"]}/z{r["value"]}: 상위 finite-bound 손실 '+', '.join(f'{v["family"]}={v["finite_bound_loss"]:.12g}' for v in top)+'.')
    (REPORTS/'PHYSICAL_INTERPRETATION_KO.md').write_text('\n'.join(text)+'\n',encoding='utf-8')

def package():
    prior.forbid_optimize();reports();final=read(REPORTS/'FINAL_DECISION.json')
    assert read(REPORTS/'POSTRUN_INDEPENDENT_AUDIT.json')['PASS'] and final['budget_PASS']
    modules=sorted((ROOT/'v42_group_branching').glob('*.py'))
    for p in modules:py_compile.compile(str(p),doraise=True)
    write(REPORTS/'FINAL_EVIDENCE_AUDIT.json',dict(PASS=True,new_native_calls=0,compiled_modules=[p.name for p in modules],
        completed_native_calls=final['native_optimize_calls'],required_files=REQUIRED,all_original_evidence_preserved=True))
    DEST.mkdir(parents=True,exist_ok=True)
    for directory in ('reports','logs','checkpoints','artifacts','children'):
        for p in sorted((WORK/directory).rglob('*')):
            if not p.is_file() or p.suffix=='.tmp' or p.name in ('GIT_COMPLETION.json','PACKAGING_CONTROLLER.log','COMMITTED_REPLAY_CONTROLLER.log','COMMITTED_EVIDENCE_REPLAY.json'):continue
            if directory=='children' and 'tmp' in p.relative_to(WORK/directory).parts:continue
            relative=p.relative_to(WORK/directory)
            target=DEST/relative if directory=='reports' else DEST/directory/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    shutil.copyfile(WORK/'tmp/activate.ps1',DEST/'ACTIVATE_D_WORKSPACE.ps1')
    (DEST/'README_KO.md').write_text('''# 완료 증거의 optimize=0 재현

실제 실행은 v42_group_branching.experiment의 spawn Worker 2개씩 최대3 pairs였다. 소비된 launch/child token을 삭제하거나 experiment를 다시 실행하지 않는다. 추가 solve는 승인 범위에 없다. Native scientific model/objective/bounds identity는 Worker별 MODEL_IDENTITY에, all9322 mapping은 CSV에 저장했다.

`python -m v42_group_branching.verify_saved`는 이 Git namespace만 이용해 original C3A+B2를 로드하고 저장된 exact dyadic support 전체를 CSR 독립 checker로 재검증한다. Native optimize는 명시적으로 금지한다. 과학 원본 배열과 ROUTE_TABLE은 SOURCE_IDENTITY에 지정된 SHA로 D: workspace에 준비해야 한다. authority 원본은 기존 scientific namespace에 보존되어 있다. README의 명령은 소비된 실험을 반복하지 않는다.

children/Cxx/z0와 z1의 RAW.npz, 원본 Pi, 별도 sign-cone/equality multiplier, exact payload, Native log, MODEL_IDENTITY, RESULT 및 resource receipt를 보존했다. Controller만 합친 pair 및 global min/max 결과는 FINAL_DECISION과 GROUP_GLOBAL_LB_COMPARISON에 있다. Absolute 실행 경로는 당시 receipt의 역사적 경로이며 verify_saved는 proof basename을 committed child 폴더로 안전하게 복원한다.

기존 saved-root equality repair와 옛1e-4 품질 FAIL은 변경하지 않았다. REVISED_EXECUTION_GATE와 사용자 반영 사전등록이 이를 diagnostic-only로 바꾼 후 실제 LP를 수행했다. 처음 optimize=0 자원 보류도 PRE_ADMISSION 기록에 보존했다. Actual parallel overlap과 CPU/RSS는 측정했으나 순차 baseline 및 memory bandwidth counter는 없어서 speedup/대역폭은 미측정이다. 다른 May12 작업과 같은 host였음을 숨기지 않는다.

SHA256_MANIFEST는 자기 자신을 제외한 모든 증거와 신규 source modules의 raw SHA256을 포함한다. GIT_COMPLETION은 최종 HEAD의 자기참조를 피하여 Git 밖 WORK/reports에 저장한다. 중간 산출물은 reports/checkpoints에 있으며 Python 새 writes는 D: WORK로 한정했다. 모든 production/P2/downstream calls는0이다.
''',encoding='utf-8')
    files={p.relative_to(DEST).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'}
    write(DEST/'SHA256_MANIFEST.json',dict(source_HEAD=BASE187,files=files,
        source_modules={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in modules},
        inherited_PR187_manifest_SHA256=sha(SOURCE187/'SHA256_MANIFEST.json'),inherited_PR185_manifest_SHA256=sha(SOURCE185/'SHA256_MANIFEST.json'),
        scientific_source_hashes=read(SOURCE187/'SHA256_MANIFEST.json')['scientific_source_hashes'],
        completed_native_calls=final['native_optimize_calls'],manifest_self_excluded=True,new_native_calls_in_packaging=0))
    assert all((DEST/n).exists() for n in REQUIRED)
    assert all(sha(DEST/n)==v['sha256'] for n,v in files.items())
    print('GROUP_PACKAGE_PASS',len(files),'files',sum(v['bytes'] for v in files.values()),'bytes',flush=True)

if __name__=='__main__':package()

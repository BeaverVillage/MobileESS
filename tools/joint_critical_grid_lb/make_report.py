"""Render the measured Joint16 report; no model loads or solver imports."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/v42_joint_critical_grid_lb_pilot'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def gib(value):
    return f'{value / 1024**3:.6f}'


def table(headers, rows):
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---']*len(headers)) + ' |']
    lines.extend('| ' + ' | '.join(map(str, row)) + ' |' for row in rows)
    return '\n'.join(lines)


def main():
    r90 = read(OUT/'RESULT.json')
    r360 = read(OUT/'native360/RESULT.json')
    cert90 = read(OUT/'INDEPENDENT_CERTIFICATE.json')
    cert360 = read(OUT/'native360/INDEPENDENT_CERTIFICATE.json')
    if not (cert90['PASS'] and cert360['PASS']):
        raise ValueError('A failed certificate requires a failure report, not this successful-report renderer.')
    facts = read(OUT/'MODEL_REPORT_FACTS.json')
    before = read(OUT/'native360/PRE_RUN_RESOURCE_HOLD.json')
    post = read(OUT/'native360/POST_RUN_RESOURCE_HOLD.json')
    n0 = read(OUT/'NATIVE0.json')
    reuse = read(OUT/'native360/MODEL_REUSE.json')
    rows = []
    for item in facts['per_vehicle_census']:
        rows.append([item['unit'], f"{item['physical_rows']:,}", f"{item['physical_columns']:,}",
                     f"{item['binaries']:,}", f"{item['physical_nnz']:,}"])
    rows.append(['물리 합계','143,260','244,264','9,322','1,243,224'])
    rows.append(['공통 rho + K16','16','1','0','4,624'])
    rows.append(['Joint 전체','143,276','244,265','9,322','1,247,848'])
    sizes = table(['부분','Rows','Columns','Binary','NNZ'], rows)
    krows=[]
    for k,item in enumerate(facts['K16'],1):
        krows.append([k,item['original_row'],item['slot'],item['branch_name'],item['facet'],
                      f"{float(item['fixed_term_float']):.15g}"])
    grid = table(['K','FULL Row','slot','line / phase','facet','b (표시용)'],krows)
    comparison=table(['기준','Global LB / 목표','검증 UB 기준 Gap','Source18r Full 대비'],[
        ['PR209 가중합','0.11666465693783702',f"{100*(r360['UB']-r360['PR209_LB'])/r360['UB']:.9f}%",'-0.17273583414765202'],
        ['Source18r Full Solver','0.28940049108548904',f"{100*(r360['UB']-r360['Source18r_Full_ObjBound'])/r360['UB']:.9f}%",'기준'],
        ['Joint 90초',repr(r90['ObjBound']),f"{r90['global_gap']*100:.9f}%",f"+{r90['delta_Source18r_Full']:.15f}"],
        ['Joint 360초',repr(r360['ObjBound']),f"{r360['global_gap']*100:.9f}%",f"{r360['delta_Source18r_Full']:+.15f}"],
        ['3% 목표',repr(r360['goal_LB']),'3%','성능 목표']])
    native=table(['항목','90초 원래 파일럿','사용자 승인 360초 추가 실행'],[
        ['Status',r90['Status'],r360['Status']],['Runtime (s)',r90['Runtime'],r360['Runtime']],
        ['Optimize wall (s)',r90['optimize_wall_seconds'],r360['optimize_wall_seconds']],
        ['Model build (s)',r90['model_build_seconds'],r360['model_build_seconds']],
        ['Root 완료',r90['root_relaxation_completed'],r360['root_relaxation_completed']],
        ['NodeCount',r90['NodeCount'],r360['NodeCount']],['IterCount',r90['IterCount'],r360['IterCount']],
        ['ObjBound',r90['ObjBound'],r360['ObjBound']],['ObjBoundC',r90['ObjBoundC'],r360['ObjBoundC']],
        ['ObjVal (축소 문제만)',r90['ObjVal'],r360['ObjVal']],['축소 MIPGap',r90['MIPGap'],r360['MIPGap']],
        ['SolCount',r90['SolCount'],r360['SolCount']],
        ['Peak process RSS (GiB)',gib(r90['peak_process_RSS_bytes']),gib(r360['peak_process_RSS_bytes'])],
        ['OS peak private commit (GiB)',gib(r90['peak_private_commit_bytes']),gib(r360['peak_private_commit_bytes'])],
        ['Gurobi MaxMemUsed (GB)',r90['MaxMemUsed_GB'],r360['MaxMemUsed_GB']],
        ['최소 RAM available (GiB)',gib(r90['minimum_RAM_available']),gib(r360['minimum_RAM_available'])],
        ['최소 commit available (GiB)',gib(r90['minimum_commit_available']),gib(r360['minimum_commit_available'])],
        ['메모리 중단 / 수치 오류',f"{r90['memory_stop']} / {r90['callback_errors']}",f"{r360['memory_stop']} / {r360['callback_errors']}"]])
    memories=[]
    for label,p in [('360 실행 전',before['system_after']),
                    ('360 모델 생성 후',read(OUT/'native360/NATIVE_READBACK.json')['memory_after_build']['system']),
                    ('360 최종 Admission',read(OUT/'native360/MEMORY_ADMISSION.json')['sample']['system']),
                    ('360 종료 후',post['system_after'])]:
        memories.append([label,gib(p['RAM_available']),gib(p['Commit_total']),gib(p['Commit_limit']),gib(p['Commit_available'])])
    ram=table(['시점','RAM available GiB','Commit used GiB','Commit limit GiB','Commit available GiB'],memories)
    roots='\n'.join(f'- {name}: `{line}`' for name,r in [('90초',r90),('360초',r360)] for line in r['presolve_summary'])
    text=f'''# V42 — 4-MESS Joint Critical-Grid Reduced MILP 결과

최종 판정은 **{cert360['classification']}**이다. 사용자 승인 360초 추가 실행의 Global LB는 **{r360['ObjBound']:.16f}**, 검증 UB 0.6760534504652341 기준 Global Gap은 **{100*r360['global_gap']:.9f}%**다. Source18r Full Solver Bound보다 **{r360['delta_Source18r_Full']:+.16f}**, PR209 가중합 LB보다 **{r360['delta_PR209']:+.16f}** 개선했다. 3% 목표 달성 여부는 **{r360['goal_3percent']}**다.

이는 전체 원본 최적값에 대한 수치적 Solver Bound다. 모델 관계·계통식·보수적 반올림의 독립 exact 인증은 PASS지만, 숫자에 대한 독립 exact B&B trace 인증은 없다. 새 incumbent를 원본 Planning 가능해 또는 Actual PASS로 사용하지 않았다.

## 실행 범위와 후속 사용자 지시

처음에는 단일90초 Optimize를 수행했다. 종료 뒤 사용자가 **“90초 짧아 360초 돌려”**라고 지시했으므로 같은 고정 모델에 추가360초 Optimize를 한 번 수행했다. 원래90초 latch와 결과·인증은 그대로 보존했다. 추가 실행은 `native360/`에서 별도 latch와 fresh Readback/메모리/동시 Worker 검사를 통과한 뒤 실행했다. 모델·K16·가중치는 바꾸지 않았다. 원본 Source 모델과 Joint CSR를 재생성하지 않고8개 고정 증거를 bytes 그대로 재사용했다. 추가 Native 실행용 Gurobi Joint 모델은 이 고정 CSR에서 새로 생성했으며 생성시간을 별도로 기록했다.

이번 연구 전체 Native Optimize는 **2회**, 총 Solver Runtime은 **{r90['Runtime']+r360['Runtime']:.9f}초**다. 추가360초 실행의 한도는 TimeLimit=360이며 Gurobi의 한계 감지와 반환에 따른 실제 Runtime을 위 수치 그대로 기록한다. Full MILP, 별도 LP, 캠페인, 가중치 반복, DW/CG/Benders/Branch-and-Price,16→32 확대는 모두0회다. 이번360초 종료 뒤 자동 연장·재실행하지 않았다.

360초는 최대 TimeLimit다. 추가 실행은 축소 MIPGap **{100*r360['MIPGap']:.9f}%**로 설정3%를 충족해 **{r360['Runtime']:.6f}초에 Status2 / OPTIMAL(허용오차 기준)**로 조기 종료했다.360초를 모두 소비한 TIME_LIMIT로 표시하지 않는다. 이 축소 모델의 거의 확정된 구간은 `[ObjBound={r360['ObjBound']}, incumbent={r360['ObjVal']}]`이며 남은 수치적 폭은 **{r360['ObjVal']-r360['ObjBound']:.16f}**이다.

## 기준과 SHA

- 롤백 Source18r / PR207: `497609b46faa14ea7e32a9483a333ab32fd264ef`
- 연구 부모 PR209: `9383a99f1bdcabbd49c79b3ad9f9ee36d523868a`
- B2 /2025-05-01 Case: `{facts['case_sha']}`
- 원본 FULL CSR: `{facts['original_matrix_sha']}`
- 원본 FULL Domain: `{facts['original_domain_sha']}`
- Source18r C3A CSR: `{facts['Source18r_C3A_matrix_sha']}`
- Source18r C3A Domain: `{facts['Source18r_C3A_domain_sha']}`
- Joint CSR: `{facts['frozen_Joint_matrix_sha']}`
- Joint Domain: `{read(OUT/'INDEPENDENT_NATIVE0.json')['joint_actual_domain_sha256']}`
- PR209 WEIGHTS: `{facts['PR209_weights_sha256']}`

Forecast input SHA는 `76abed1653a8a2eeea21d8cd808cb0d23f125472b7db2fc9b6848957236f0458`이며 고정 AIDC/계통 anchor와 response correction은 PR209 `GRID_PROVENANCE_AUDIT.json`의 동일한 Source18r 증거를 재사용했다. PR147/203의 과거 LB·Column·Dual·Pricing 결과는 현재 하한에 사용하지 않았다.

첫 Native0 추출은 저장 security summary에 최상위 PASS가 없는 스키마 차이로 실패했다. `BUILD_FAILURE.json`에 보존하고 실제 독립 proof 경로를 바로잡았다. Optimize 전에 수정됐고 FULL 모델 재생성은0회다. 저장 CSR의 SHA 확인을 재시도한 사실은 숨기지 않는다.

## 수학적 포함관계와 물리 영역

원본 가능영역을 F, PR209의 차량별 원본 물리 영역을 X_m이라 한다. 이상적인 Joint J는 `x_m∈X_m (m=1..4)`, 원본 rho Domain [0,1], 그리고 모든 k∈K16에 대한 `rho≥b_k+Σ_m a_km^T x_m`이다. 원본에서 helper equality를 정확히 대입한16개 원본 thermal 행을 만족하므로 `π(F)⊆J`이고 `min_J rho≤min_F rho`다.

실제 모델은 저장된 Node-Activity Compact/C2/C3A의 물리 행을 유지하고 계통 helper 및 선택하지 않은 계통 행을 제거한 뒤 K16을 각각 추가했다. 원본의 공통 injection equality를 차량마다 복제하지 않았다. 대신 `injection_P=Σ_m(Pdis-Pch)`, `injection_Q=Σ_m Q`를 각16개 식에 정확히 대입했다. 변수의 kW/kvar·SOC kWh, thermal RHS 부호와 rho 계수−1, 목적계수1·ObjCon0·원본 Bounds를 감사했다.

Source18r Compact의 continuous route_flow는 Binary node_activity와 원본 DAG flow/link에 의해 하나의 정수 경로로 복원된다. 시간은 엄격히 증가하고 원점 유량1과 활성 node의 유량1이 유지된다. 평행 arc가 있으면 기존 Compact가 Binary로 유지하는 정책을 그대로 재사용한다. 현재 데이터의 retained route_flow207,736개는 모두C이며 node_activity8,938개와 charge_mode384개가 Binary다. 단순한 원본52k Binary 블록4개 결합은 수행하지 않았다.

각 차량의96개 Mode와96개 energy_balance, SOC97개(95개 retained+초기/종단760의 exact alias2개), 원본 travel time/connect 및 출발 다음 SOC에서의 이동에너지 차감, 접속 Pch/Pdis/Q와 transit 금지, 실제 충전 Rebound를 유지한다. terminal location은 H=96의 아무 실제 site로 끝나는 원본 조건이며 출발지 복귀 조건을 추가하지 않았다. 삭제 terminal4행은 retained flow의 exact 합으로 함의된다.

Static Presolve의 SOC/Q/source node Bounds는 원본 물리식의 exact 함의이며 새 grid 기반 제한이 아니다. C3A 추가 affine Bound 강화는 제거한 injection/response helper에만 적용돼 retained 물리 변수에 추가 강화0개다. 삭제 PCS16 53,652행, Q link17,884행, terminal4행은 exact Farkas/flow-sum으로 재검증했다. 남은 block당10면이 원래 PCS16 영역과 동등하다.

원본 물리134,514행과 Compact link8,746행을 계수·RHS·sense까지 exact 재대입했고, C3A 삭제71,540행과 SOC endpoint 삭제8행도 검증했다. 삭제 Compact link292개(288 tautology+4flow implication)의 강화 검사는90초 Native가 시작된 뒤 완료됐다. 그 사후 검사는 `*_EXTENSION` 파일로 분리했고, 실행 전 증거는 prereg commit5afca1c6의 원시 bytes로 보존했다. 모델 행렬·Bounds·파라미터 변경은 없었다.360초 실행은 같은 고정 모델·증거를 재사용하고 새 Readback을 수행했다.

원본 열 좌표는 `CURRENT_C2_AXES.columns`를 사용한다. C3A column axis는 local identity이며 FULL 번호가 아니다. K16의4,608개 원본 P/Q 열은 모두 retained이고 이름이 일치했다. FULL/C3A Solver 모델은 생성하지 않았다. Native 프로세스에는 Joint 모델만 상주했다.360초 준비·실행 중 FULL/C3A CSR를 추가로 적재하지 않았다.

## 실제 규모

{sizes}

Binary≤10,000, Rows≤300,000, NNZ≤3,000,000 게이트를 모두 통과했다. SOC endpoint의 제거는 exact 상수 대입이며 단말 SOC 조건 제거가 아니다. Solver 내부 presolve가4개 continuous 변수를 binary로 인식해 presolved Binary9,326개로 표시했으나, 입력 MILP에는 새 Binary를 추가하지 않았다.

## 유지한 K16

{grid}

FULL Row는 저장 CSR의0-based 행 번호이며 slot/facet도 원본 row name의0-based 축이다. 각 행은 같은 rho 아래의 별도 부등식이다. 평균으로 대체하지 않았다. 기존 `w=1/16`은 수학적 비교에만 사용했다. 정확한 유리수 b와288개 P/Q 계수씩은 `K16_EXACT_ROWS.json`에 공개했고 표의 b는 표시용 소수다. 원본 고정 Forecast/AIDC, response_line_P/Q, response_line_correction, anchor와 thermal RHS를 포함한다.

정확한 행 `a^T x-rho≤-b`를 Native binary64 계수 ahat로 옮길 때 `E=Σ_j max((ahat_j-a_j)l_j,(ahat_j-a_j)u_j)`를 유리수로 계산했다. RHS는 `ceil_binary64(-b+E)`다. 모든 원본 가능해가 실제 Native 행도 만족한다. 아주 작은 계수를 삭제하지 않았으며 최소 K16 비영 계수는1.8233972854287928e-12다. Native readback에서 실제 CSR/RHS/sense/Bounds/types/objective가 모두 일치했다.

정확한 Joint 최적값에는 `L_w*≤min_J rho≤min_F rho`가 성립한다. 보수적 Native 행은 J를 미세하게 완화하므로 최적값 비교 오차를 별도로 감쌌다. `min_Jnative rho≥L_w*−ε_w≥PR209 certified LB−ε_w`, `ε_w≤7.54459444712759e-16`이다. 미완료 B&B Bound에는 이 최적값 하한에 도달했음을 강제하지 않는다.

## U4 및 Native0/인증

U4 원본 FULL의 저장 replay PASS, 최대 위반9.896011248814483e-11을 확인했다. Joint 사영 replay는 최대 행 위반{n0['U4']['joint_max_violation']}, Binary 위반0이며 rho는 검증 UB다. 두 Native 모두 같은 U4 사영을 MIP Start로 받아들였다.360초는 동일한8개 파일의 SHA를 다시 확인한 reuse gate PASS 후 실행했으며 Source/CSR 재생성 및 Native0 재생성은0회다. 새 Gurobi Joint 모델 입력은 다시 Readback했다. 추가 incumbent의207,736개 continuous route_flow도 모두 정확히0/1,9,322개 Binary도 정확히0/1이었다. 물리·K16 replay의 최대 행 오차는{r360['incumbent_joint_replay']['max_violation']}이며 FULL 가능성이나 새UB 인증은 아니다.

독립 Native0와 각 최종 인증은 Gurobi를 import하거나 추가 최적화하지 않는다. `ObjBound(native)≤min_Jnative rho≤min_F rho`에 의해 수치적 Bound를 원본 Global LB로 전달한다. 마지막 ObjBound의 권위는 Gurobi 최소화 B&B의 수치 계약이다. 독립 exact rational B&B proof trace 또는 원본 최적해 확정은 아니다. Source18r Full ObjBound0.28940049108548904도 Root 미완료의 수치적 Solver Bound로만 비교한다.

## 측정 결과와 Gap

{comparison}

360초는90초 대비 ObjBound가 **{r360['ObjBound']-r90['ObjBound']:+.16f}** 변했다. Global Gap은 `(검증 UB−Global LB)/검증 UB`로 계산하며 축소 MILP의 MIPGap과 구분한다. 새 축소 incumbent를 원본 UB로 사용하지 않는다. Material 기준은 Full Bound+0.001=`0.29040049108548904`이며 성능 목표3%와 별개다.

{native}

Native 설정은 각각TimeLimit90/360, Threads1, Worker1, MIPGap0.03, MIPFocus3, Seed42, FeasibilityTol/IntFeasTol/OptimalityTol1e-8이다. Gurobi13.0.2, Intel i7-13620H Windows 환경이다. 작은 계수/범위 경고를 보존하고 수치 허용오차를 완화하지 않았다. 로그의 coefficient-range 경고와 실제 Numeric error를 구분했으며 인증기는 Numeric trouble/Out of memory/Numeric error가 없음을 확인했다.

{roots}

## RAM/Commit과 보존

{ram}

모델 생성 후4GiB RAM/6GiB Commit reserve에 `max(2GiB, 관측된 build private 증가의4배)`가 더 들어갈 여유를 확인했다. 실행 직전 fresh peer inventory에서 다른 Heavy Gurobi/Native Worker는0개였다. Callback으로 시스템 RAM/Commit, process RSS/private/OS peak를 감시했고 위험 시 지원되는 terminate로 종료하도록 구성했다. 이번 실행의 memory stop은{r360['memory_stop']}다. Gurobi GB는 Solver 표기 단위이며 Windows 실측은 bytes와GiB로 별도 기록한다.

전후 감사는 모두 PASS다. PR207/PR209 원본 HEAD와 clean 상태, HOLD marker SHA, Windows Supervisor/Monitor Disabled, 관련 자동화 PAUSED를 유지했다. 기존7개 controller는 각 관측에서 stopped와CPUdelta0으로 기록했으며 기존 conhost 자식은 그대로 보존했다. 관측 밖의 연속CPU0을 주장하지 않는다. Source18r/U4/PR209 기존 코드·결과, StageBudget·NativeStopRequested·A1/A2/M-stage 예산 및 캠페인 실행 코드는 수정하지 않았다. 부모 대비 기존 경로의 변경0개는 최종 Git 검증에 기록한다.

## 기존 방법과 채택 판단

PR147은 과거 원본 arc LP 바닥과 DW/CG의 exact dual/pricing 전달 연구였다. PR203은 모든 결합 계통 행을 유지한 trajectory DW master와 pricing/cover 인증 연구였다. PR209는 하나의 계통 가중합으로4개의 원본 integer 물리 support 문제를 분리해 계산했다. 이번 연구는 Source18r Compact의4차량 정수 물리를 함께 유지하고16개 thermal 하한을 개별 적용하는 직접 MILP다. RMP·dual·pricing·column 또는 과거 수치를 이 LB의 권위로 사용하지 않았다.

**하한 전용 Compact Joint16 방식은 유의미한 후보로 채택한다.** 이번 측정은 거대한 Full Root를 호출하지 않고 Full Solver 기준을 개선했으며 메모리 제한을 충족했다. **원본 Planning/Actual 또는3% 최적성 인증으로의 채택은 기각한다.** 현재 Gap은 아직 크고 생략한 계통 제약을 확인하지 않았다. **같은 K16에서 시간만 추가하는 확대는 기각한다.**360초 한도 실행이 축소 최적값에 매우 근접해 조기 종료했지만 Global LB 개선은0이었다. 현 모델의 수치적 최적값 상한0.4258955562 자체가3% 목표0.6557718470보다 훨씬 낮다. 이는 작은 반올림 보정과 별개로 K16 완화가 가진 강도 한계를 보여준다. 이후 제약 확대·재실행·다른 알고리즘 개발은 이번 결과에서 자동 승인하지 않는다.

주요 증거: [90초 인증](INDEPENDENT_CERTIFICATE.json), [360초 인증](native360/INDEPENDENT_CERTIFICATE.json), [360초 원시 로그](native360/NATIVE.log), [수학 검토](MATH_REVIEW_KO.md), [물리 exact 감사](PHYSICAL_RELATION_AUDIT.json), [Native0](NATIVE0.json), [모델 사실표](MODEL_REPORT_FACTS.json), [종료 후 HOLD/자원](native360/POST_RUN_RESOURCE_HOLD.json). 원래90초와 추가360초의 durable latch는 각각 보존되어 있으며 추가 실행은 차단된다.
'''
    (OUT/'JOINT_CRITICAL_GRID_LB_REPORT_KO.md').write_text(text,encoding='utf-8')
    print('Report rendered from independently certified measurements.')


if __name__=='__main__':
    main()

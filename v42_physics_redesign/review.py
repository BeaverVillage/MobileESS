"""Readable Korean explanations, generated from verified receipts."""
from .common import LB, UB


def documents(classification, root, decision, temporal, inherited_cert):
    lb = decision['new_LB']
    gap = decision['global_gap_percent']
    return {
        'ROOT_CAUSE_ANALYSIS_KO.md': f'''# 구조 진단

PR183 master는 graph·z·f·theta와 20개 cut을 반영하고, 전체 96-slot SOC·충전·P/Q·PCS를 recourse로 넘겼다. 첫 저장 배정에는 충전 가능한 정차가 없으면서 네 MESS에 합계 3,996.531325 kWh의 이동 에너지가 필요했다. Initial SOC와 terminal SOC가 같으므로 충전 없는 에너지 수지는 모순이다.

완료된 `(z,f)` 작업의 별도 original CSR exact certificate는 energy equality 384개와 zero-capacity charging gate 8,942개를 결합해 separation `{inherited_cert['delivered_source_value']}`를 얻었다. Native TIME_LIMIT를 INFEASIBLE로 해석한 결과가 아니다. Raw native Pi를 사용하지 않은 별도의 수학적 multiplier이며, 원래 finite-bound support와 기존 witness 20개 검사를 통과했다. 기존 로그·상태·후속 certificate는 읽기 전용으로 보존했다. 기존 review는 이 늦은 certificate 이후 재작성하지 않았다.

Full C3A에는 이미 전체 물리가 있다. Archived ROOT의 continuous route_flow 207,736개 중 140,502개가 진단 기준 1e-8 < x < 1−1e-8의 분수값이고 최댓값은 0.270720702다. Charge_mode 384개도 모두 분수다. SOC는 약 689.13–1,080 kWh이며 높은 SOC에도 이동 mass를 허용한다. 실제 원본 계수에서 도출한 arrival-SOC reachability 651행의 최대 위반은 0.722566787 kWh다. Critical-grid 행은 rho 열과 Pi를 따라 추적하고 전체 grid 행을 보유한다. Archive에 native Slack이 없어 CSR로 재구성했다. Raw ROOT point는 strict residual 검사에 실패했으므로 정수 UB나 global LB로 채택하지 않았다.

Native ROOT 목적값 0.568711942993466은 현재 유효 LB {LB}와 가깝다. 수치 인증 보정만으로 0.5% 목표 LB {UB*.995}까지 올릴 수 없다. 현재 UB {UB}의 최적성도 증명되지 않았으므로 남은 9.500515051% 전체를 진정한 integrality gap으로 단정하지 않는다.

물리를 master로 옮기면 PR183의 물리적으로 불가능한 배정을 배제하지만 original C3A LP 자체는 강화되지 않는다. H2의 정확한 SOC 치환도 같은 LP이며 예상 nnz가 25,937,190으로 늘어난다. 새 강화 요소는 정수 경로의 이동 중 dispatch가 0임을 이용한 다기간 route–SOC disjunction이다. 추가 열 없이 정수 영역을 보존한다. 실제 M1의 certified LB 효과는 `{decision['performance']}`다.
''',
        'PHYSICS_STRENGTHENED_ARCHITECTURE.md': '''# 계산 구조

H1은 원래 node_activity·charge_mode·continuous route_flow·SOC·Pch·Pdis·Q·injection P/Q·rho 축을 공유한다. 실제 CSR audit에서 shared 248,765열, physics-only 213,868행·2,780,220 nnz, residual network 57,275열, coupling 368,940행을 확인했다. 변수 복사는 없다. Native +1 pivot definition 48,551개를 확인했지만 network 변수 13,224개는 이 family 기준에서 직접 정의가 증명되지 않았다. 이를 자유 변수나 유일 affine auxiliary라고 단정하지 않고 원래 bounds와 모든 행을 유지한다.

잔여 grid를 복구하면 H1은 원래 C3A와 동일한 B1이다. 별도 거대 recourse LP와 반복 row-generation 대신 모든 물리·grid 행과 원래 network auxiliary를 보유한 compact monolithic branch-and-cut 후보를 선택했다. 이 구조 변경 자체는 LP 강화가 아니며 B1 ROOT를 중복 실행하지 않는다.

B2는 모든 4대 MESS와 전체 96-slot 이동 arc에서 유도한 정수 유효 route–SOC 제약을 원래 변수에 추가한다. 795,944개 후보를 exact arithmetic으로 검토하고 archived fractional point에서 위반한 651개를 모두 포함했다. 총 306,040열·583,459행·5,352,914 nnz이며 새 열·새 binary는 0개다. 모든 원래 행·grid 행·bounds·types를 유지한다. Critical-grid top-K 축소는 없다. 각 추가 행에는 원래 arc/SOC 인덱스·계수·RHS·outward transport certificate가 있다.

H2는 별도 계산 구조다. SOC 380열을 제거하고 원래 energy 384행의 누적식, SOC bound 760행과 terminal equality 4행으로 같은 projection을 표현한다. cumulative.py의 matrix-free forward/inverse와 bound 검사에서 실제 원본 계수를 사용한다. 전체 prefix CSR는 만들지 않았다. 예상 nnz가 약 2,594만이고 LP 완화가 같으므로 material ROOT 후보에서 제외했다. SOC를 이산화하거나 전체 상태를 열거하지 않았다.

ROOT → certified gain≥0.001와 tractability → canary≤900초 → 실용 canary → production의 gate를 유지한다. ROOT가 미측정인 현재는 canary·production·downstream을 실행하지 않는다. Production-ready=false다.
''',
        'ORIGINAL_INTEGER_EQUIVALENCE_PROOF.md': '''# 원본 정수 영역 동치

B1의 forward/inverse는 원래 306,040축의 identity다. 모든 C3A 582,808행·RHS·senses·objective·ObjCon·bounds·types가 남아 있다. B2의 추가 행이 모든 original integer schedule에서 유효하므로 B2 forward도 identity다. B2에서 original로는 추가 행을 무시하면 된다. 정수 feasible set과 min rho 목적값을 보존한다.

Route flow f는 원래 continuous다. 정수성은 types 변경이 아니라 binary node_activity와 원래 unit-path projection에서 유도한다. 원래 time DAG에는 parallel endpoint arc가 없다. Nonnegative unit flow의 path 분해에서 binary vertex mass는 모든 양의 path에 같은 occupied vertices를 강제한다. 시간 순서와 parallel arc 부재로 경로와 f가 유일하다. Source·terminal·alias(terminal stay 95→node_activity 96)·zero identities를 확인한 PR183 일반 증명의 SHA를 보존하고 새 D: traffic copy에서 DAG를 독립 대조했다.

H2의 forward는 SOC 380좌표만 제거한다. Inverse는 원래 FULL energy 384행의 실제 계수로 initial SOC부터 누적 SOC를 복원한다. 모든 원래 SOC bound를 해당 누적 표현의 bound로 대체하고 terminal condition을 유지한다. Retained bounds·types·objective는 그대로다. 전체 CSR에서 SOC가 non-energy 행에 등장하지 않음을 확인했다. Real arithmetic의 symbolic bijection과 floating reconstruction replay를 구분한다. 작은 fixture만으로 실제 C3A 동치성을 주장하지 않는다.
''',
        'TEMPORAL_SOC_PCS_ROUTE_COUPLING_PROOF.md': '''# 전체 시간 물리 결합

4대 MESS의 96-slot FULL energy 384행을 C3A energy 행에 exact dyadic arithmetic으로 전달해 계수·RHS·senses 일치를 검증했다. 실제 dt=0.25시간, eta=0.95, Pmax=300 kW, PCS=400 kVA, SOC=440..1,080 kWh, initial=terminal=760 kWh다. 원래 route arc의 energy를 사용하고 PCS 16-face·connected Pch/Pdis·mode·P/Q·grid 행을 모두 유지한다.

이동 arc a=(depart, connect, e)의 f=1이면 원래 DAG의 유일 경로는 이동 구간의 site vertices를 건너뛴다. 원래 connection/PCS 행으로 해당 구간 Pch=Pdis=Q=0이다. 원래 energy 행을 합하면 Econnect−Edepart+e=0이다. f=0일 때도 endpoint bounds를 만족한다. D=Econnect−Edepart+e, U=max(0,uconnect−ldepart+e), L=min(0,lconnect−udepart+e)라 두면 D≤U(1−f), D≥L(1−f)가 정수 일정에서 유효하다. 또한 Edepart≥ldepart+max(0,lconnect+e−ldepart)f, Econnect≤uconnect−max(0,uconnect−udepart+e)f다.

시간별 local-hull EF 복제 대신 모든 실제 travel interval과 전체 96-slot 경로에 대한 원래 변수의 제약을 사용한다. 이번에 실제 위반한 651행은 모두 arrival-SOC reachability다. 넓은 후보 검토를 완전한 trajectory hull이라고 주장하지 않는다. ROOT의 f 값을 정수로 cast하지 않는다. 추가 제약은 정수 projection에 유효하며 분수 f를 배제할 수 있다.

IEEE 계수 전달 오차 delta_j에 대해 RHS를 Σ max(delta_j*l_j,delta_j*u_j)만큼 outward 증가시킨다. 전체 original finite box에서 전달 행이 exact 행보다 강해지지 않음을 검증했다. 독립 verifier는 원래 arc·endpoint bounds로 651행을 재구성하고 잘못된 travel energy와 안전하지 않은 RHS 변조를 거부했다. 기존 witness 20개와 최선 UB를 제거하지 않았다.
''',
        'GRID_EXACT_SEPARATION_PROOF.md': '''# Grid 원본 보존과 정확한 separation

모든 original voltage·thermal·transformer·injection-binding·response-binding 행과 finite bounds를 처음부터 보유한다. 일부 critical row만 남기는 축소나 변수 복사는 없다. 잔여 network variables의 유일 affine 표현을 가정하거나 임의로 삭제하지 않는다.

Archived fractional LP와 원래 integer UB를 v42_rowgen.core.separate로 전체 582,808행에서 검사했다. Sparse product의 roundoff enclosure로 screening하고 1e-8 boundary의 불명확한 행은 exact binary-rational dot으로 판정한다. 모든 위반을 반환하며 top-K는 없다. Fractional point의 strict residual FAIL을 보존하고 UB/global LB로 사용하지 않는다. 원래 UB는 전체 C3A와 unreduced grid 673,920행, A1·route·SOC·P/Q·PCS replay를 통과했다.

새 ROOT에서는 모든 원래 행과 유효 추가 651행을 명시적으로 포함한다. LB는 그 augmented array와 원래 finite bounds의 weak-duality certificate에서만 채택한다. Grid-only row generation을 다시 실행하는 구조가 아니다. 신규 강화 요소는 route–SOC temporal integer disjunction이며 실제 LB 효과는 새 ROOT에서 측정해야 한다.
''',
        'FINAL_REVIEW_KO.md': f'''# 최종 검토

**{classification}** — 구현과 동치성 검증을 완료했지만 다른 A-stage native 작업을 보호하기 위해 새 heavy ROOT를 실행하지 않았다. 실제 M1 하한 개선과 계산시간 개선은 아직 미측정이다.

직접 기준은 PR183 `{decision['source_BASE']}`, 과학적 기준은 PR162 C3A다. 완료된 `(z,f)` 작업은 읽기 전용으로 보존했으며 다른 프로세스와 A-stage 산출물을 중지하거나 변경하지 않았다. 새 D: worktree에서 원본 objective identity와 full physical replay를 검증했다.

전체 96-slot 물리를 포함하는 compact monolithic 후보와 별도 exact cumulative H2 operator를 구현했다. B1은 C3A와 동일한 LP이므로 중복 ROOT를 생략했다. H2도 LP를 강화하지 않고 예상 nnz가 약 2,594만으로 늘어 ROOT 후보에서 제외했다. B2에는 원본 계수에서 도출한 route–SOC 제약 651행·1,302 nnz를 추가했다. 새 열과 새 binary는 없다. 양방향 정수 projection, energy 384행 identity, 계수·RHS의 outward transport, 기존 witness 20개, 최선 UB replay, 변조 거부 검사를 통과했다.

작은 fixture의 정수 assignment 32개를 열거해 정수 최적값 0.5와 feasible projection을 보존했다. Fixture LP는 0.25→0.5로 강화됐지만 이를 실제 M1 성과로 전용하지 않는다.

| 지표 | 결과 |
|---|---|
| 새 모델 | 306,040열 / 583,459행 / 5,352,914 nnz |
| 신규 full-scale ROOT optimize | {root.get('native_optimize_calls',0)}회 |
| 신규 canary / production | 0 / 0회 |
| 새 ROOT Runtime / Work | 미측정; 소비한 native 예산 0 |
| 작은 HiGHS fixture | 100회, 합계 약 0.055초 |
| 제약 생성 wall time | {temporal['build_wall_seconds']:.6f}초 |
| 유효 global LB | {lb} |
| 검증된 UB | {UB} |
| Global gap | {gap:.9f}% |
| 신규 certified LB 개선 | {lb-LB}; B2 효과는 {decision['performance']} |
| 0.5% 목표 LB | {UB*.995} |
| M1_ACCEPTED / production-ready | false / false |

자원 감사에 실제 PID·생성 시각·명령·작업 디렉터리·RSS·CPU와 ROOT 진입 판정을 보존했다. 외부 A-stage worker가 실행 중이므로 RESOURCE_PENDING으로 종료한다. RAM은 관측만 하며 자동 종료와 유한 MemLimit·SoftMemLimit을 추가하지 않았다. 과거 Runtime·Work를 보존했다.

추가 651행은 archived LP point를 분리하지만 certified ΔLB≥0.001와 실용 Runtime을 동시에 달성했는지는 미확인이다. 현재 UB의 최적성이 증명되지 않았으므로 남은 gap을 전부 진정한 integrality gap으로 부르지 않는다. Cut 개수나 fixture 강화만으로 성공을 주장하지 않는다.

**다음 행동은 하나다.** {decision['next_structural_experiment']}

이 실험은 현재 실행하지 않았다. ROOT material gate 전에는 canary·production·downstream을 실행하지 않는다. Source·scientific identity·CSR coupling·증명·archived primal/Pi/RC·재구성 Slack·이전 작업 보존 감사·row separation·fixture를 SHA256으로 고정했다. 최종 publication HEAD·PR URL·remote equality·clean tree는 외부 GIT_COMPLETION.json에 기록한다.
'''}

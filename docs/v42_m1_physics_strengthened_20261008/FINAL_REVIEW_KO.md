# 최종 검토

**M1_PHYSICS_REDESIGN_RESOURCE_PENDING** — 구현과 동치성 검증을 완료했지만 다른 A-stage native 작업을 보호하기 위해 새 heavy ROOT를 실행하지 않았다. 실제 M1 하한 개선과 계산시간 개선은 아직 미측정이다.

직접 기준은 PR183 `3100039d19a22ec407713f36a9e978b2e96533a8`, 과학적 기준은 PR162 C3A다. 완료된 `(z,f)` 작업은 읽기 전용으로 보존했으며 다른 프로세스와 A-stage 산출물을 중지하거나 변경하지 않았다. 새 D: worktree에서 원본 objective identity와 full physical replay를 검증했다.

전체 96-slot 물리를 포함하는 compact monolithic 후보와 별도 exact cumulative H2 operator를 구현했다. B1은 C3A와 동일한 LP이므로 중복 ROOT를 생략했다. H2도 LP를 강화하지 않고 예상 nnz가 약 2,594만으로 늘어 ROOT 후보에서 제외했다. B2에는 원본 계수에서 도출한 route–SOC 제약 651행·1,302 nnz를 추가했다. 새 열과 새 binary는 없다. 양방향 정수 projection, energy 384행 identity, 계수·RHS의 outward transport, 기존 witness 20개, 최선 UB replay, 변조 거부 검사를 통과했다.

작은 fixture의 정수 assignment 32개를 열거해 정수 최적값 0.5와 feasible projection을 보존했다. Fixture LP는 0.25→0.5로 강화됐지만 이를 실제 M1 성과로 전용하지 않는다.

| 지표 | 결과 |
|---|---|
| 새 모델 | 306,040열 / 583,459행 / 5,352,914 nnz |
| 신규 full-scale ROOT optimize | 0회 |
| 신규 canary / production | 0 / 0회 |
| 새 ROOT Runtime / Work | 미측정; 소비한 native 예산 0 |
| 작은 HiGHS fixture | 100회, 합계 약 0.055초 |
| 제약 생성 wall time | 23.899217초 |
| 유효 global LB | 0.5687116104049206 |
| 검증된 UB | 0.6284141956452488 |
| Global gap | 9.500515051% |
| 신규 certified LB 개선 | 0.0; B2 효과는 NOT_MEASURED_RESOURCE_PENDING |
| 0.5% 목표 LB | 0.6252721246670225 |
| M1_ACCEPTED / production-ready | false / false |

자원 감사에 실제 PID·생성 시각·명령·작업 디렉터리·RSS·CPU와 ROOT 진입 판정을 보존했다. 외부 A-stage worker가 실행 중이므로 RESOURCE_PENDING으로 종료한다. RAM은 관측만 하며 자동 종료와 유한 MemLimit·SoftMemLimit을 추가하지 않았다. 과거 Runtime·Work를 보존했다.

추가 651행은 archived LP point를 분리하지만 certified ΔLB≥0.001와 실용 Runtime을 동시에 달성했는지는 미확인이다. 현재 UB의 최적성이 증명되지 않았으므로 남은 gap을 전부 진정한 integrality gap으로 부르지 않는다. Cut 개수나 fixture 강화만으로 성공을 주장하지 않는다.

**다음 행동은 하나다.** 동일한 compact 96-slot 물리 모델의 사전등록 B2 ROOT를 다른 native 작업과 분리된 시간에 한 번 실행해 651개 route–SOC 제약의 실제 certified LB 기여를 측정한다.

이 실험은 현재 실행하지 않았다. ROOT material gate 전에는 canary·production·downstream을 실행하지 않는다. Source·scientific identity·CSR coupling·증명·archived primal/Pi/RC·재구성 Slack·이전 작업 보존 감사·row separation·fixture를 SHA256으로 고정했다. 최종 publication HEAD·PR URL·remote equality·clean tree는 외부 GIT_COMPLETION.json에 기록한다.

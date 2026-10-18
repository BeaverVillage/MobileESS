# V44 r027 오류 복구와 May02 B3 P1 병목 수정

2026-10-18 사용자 지시에 따라 별도 revision `v44_recovery_r027`을 봉인했다. 실행 중인 r026f1 소스와 과거 PASS·실패·Raw·Native 원장은 변경하지 않았다.

## May02 B3가 5,400초를 쓴 이유

attempt012의 측정 Native 합계는 **5,400.089005초**다. Phase I의 LP 52호출은 359.365000초, 전체 Local Pricing 2,957호출은 938.258005초, 주 P1 LP 19호출은 4,102.466000초였다. Phase I는 해당 단계 Pricing을 포함해 **576.991003초**에 Φ=0을 인증했다. 이후 P1 18라운드와 Pricing을 완료했으나 19번째 주 LP에서 잔여 한도를 소진했다. 정수 복원에는 진입하지 않았고, 물리적 불가능성을 증명한 결과도 아니다.

원본 `activate`는 이전 가능해를 새 모델에 정확히 포함하고 `compact_inverse`로 검산한 점까지 반환하지만, P1 루프는 두 번째 반환값을 버렸다. 매 라운드 새 LP에 이전 가능해가 전달되지 않았다. 동일한 Local Pricing 행렬도 objective만 바뀌는데 이전 basis를 재사용하지 않았다. 마지막 완료 라운드는 검증된 개선 블록 103개를 찾았으나 activation의 기본 상한 때문에 64개만 추가했다. 주 LP 시간은 첫 31.077초에서 후반 300~400초 수준으로 증가했다.

r027은 검산한 가능해를 PStart로 전달하고, objective를 제외한 행렬·bounds·senses·RHS·types 전체 바이트가 동일한 Local Pricing LP에만 basis를 재사용한다. Full Pricing과 support 재검산을 통과한 개선 블록을 매 activation에 전부 추가한다. 전체 Pricing 범위, 독립 LB·Gap, 원본 행·정수성·물리 검산은 유지한다. **실측 가속 배율과 새로운 May02 PASS는 아직 확인되지 않았다.**

## B1 구현 오류와 Planning 재사용

- May03~05 B1: 이전 r025a의 worker 복제에서 keyword-only 기본값이 유실돼 A1 진입 전에 실패했다. r027은 원본 `m1=None`을 유지하며 실제 installer의 호출 경로를 회귀 검증했다. 해당 attempt에는 재사용할 완료 Planning이 없어 A1부터 새로 실행한다.
- May06 B1: 정수 변수 잔차 약 4.59e-7이 GPU 역산에서 약 -1.84e-6으로 증폭돼 내보내기가 실패했다. 단순 반올림은 원본 행 검산에 실패하므로 사용하지 않는다. 저장된 P1 closure와 정수 결정은 재사용하고, 정수 bounds를 정확히 고정한 뒤 연속 변수만 별도 solve로 복원한다. 새 점은 원본 행·bounds·정수성·물리·독립 Gap과 기존 내보내기 기준을 모두 다시 통과해야 한다. 기존 Native **12.263999초**를 새 원장에 명시적으로 승계하고 복원 시간을 합산한다.
- May07 B1: 이미 완료된 Planning은 유지하며 실행 중 Actual/Fresh의 자연 종료를 기다린다.

실제 May06 모델 693,549행·22,616열에서 원본 typed fingerprint, 동일한 행렬/RHS/objective와 연속 bounds, P1 인증·입력, 기존 Native 승계를 Native0로 검증했다. **실제 연속해 복원과 최종 Actual/Fresh PASS는 아직 확인되지 않았다.**

## 사용자가 확정한 전압 완화 폭

선택된 A2 위반 행의 최대 완화 폭을 **±0.005 pu**로 줄였다. 하한은 **0.945 pu = 0.893025 pu²**, 상한은 **1.055 pu = 1.113025 pu²**다. 기존 엄격 행에서의 제곱 RHS 변화는 하한 -0.009475, 상한 +0.010525다. 전체 Eligible Class Pricing 1회, 실제 연속 두 Column Activation의 각 Φ 감소율 5% 미만, 전압 인공변수 비중 95% 이상이라는 기존 조건은 유지한다. 미선택 행과 M2·Actual/Fresh는 **0.95~1.05 pu**를 유지한다.

## 검증과 실행 인계

회귀 **291개 PASS**. 원본 r026f1 회귀 276개와 실제 May06 Native0 검증도 확인했다. 새 소스 48개를 봉인했으며 SHA는 `73ba874ace2c42f64badf9afdd31bceaf7f7a6064ab6dbaabef94f64621c5498`다.

`MobileESS_V44_Campaign004_Recovery_R027`은 현재 May07 B1의 전체 Actual/Fresh 완료와 원래 coordinator의 자연 종료를 기다린다. 새로운 permit의 retry release는 그 경계 이후에만 공유 queue에 게시한다. 기존 실패를 덮어쓰지 않고 별도 attempt를 생성한다. 전체 A Native5400초와 Phase I LP+Pricing Native1500초 한도는 유지한다. 최종 성공은 각 재실행의 독립 인증으로 판정한다.

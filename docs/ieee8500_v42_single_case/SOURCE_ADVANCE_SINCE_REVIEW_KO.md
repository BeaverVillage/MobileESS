# 검토 이후 V42 소스 진전의 읽기 전용 감사

이번 연구가 동결·검토한 기준은 `de6f79cd2cd215f0ed657b99d24b9ac26980ddc1`이다. GitHub `v42`의 확인 시점 HEAD는 [87480938c4c3eb9faca9eadef7a87e8e12a44d18](https://github.com/BeaverVillage/MobileESS/commit/87480938c4c3eb9faca9eadef7a87e8e12a44d18)이다. 두 커밋 사이에는 **41개 파일 추가만 있고 기존 파일 수정·삭제는 없다.** 기존 962개 V42 source의 작업트리 SHA256 및 두 커밋의 Git blob identity가 모두 일치한다. 기존 검토 기준을 현재 최신 HEAD라고 부르지 않는다.

최신 커밋은 격리 ref `refs/ieee8500-v42-source-audit/advance-87480938`로만 가져와 Git object를 읽었다. Checkout/rebase와 V42 source import, Worker·Native·FULL build·AC·외부 campaign 쓰기는 실행하지 않았다. 현재 구성 SHA `8f1ad20d080ecf04609be7a66fe912983dcb6ce8bf5b6afdd740b4bccc6aa1f6`, 선정 mapping SHA `4a70fd13bf08c8512d30f74e48dfafb46fdddd4e112a3aee92a8191f22cad016`, 현재 주요 6개 결과 CSV는 그대로다.

| V10 추가 interface | 기준 대비 변경과 유지 사항 |
|---|---|
| `numerical.py:precision_enabled/set_precision` | B1 A `INTEGER_CONTROL`을 기존 `PHASE_I/ORIGINAL_P1` 고정밀도 범위에 추가한다. FeasibilityTol/OptimalityTol=1e-9, NumericFocus=3, ScaleFlag=2, Phase I Presolve=0이다. 기존 Method/IntFeasTol/Heuristics를 바꾸지 않는다. 날짜는 May2025, 직접 허용 arm은 B1/B2다. |
| `a_stage.py:native_port/run_port/failure_classification` | 원 V6 A의 실행·수치 정책·버전 metadata를 V10으로 route하고 예외 receipt의 분류를 추가한다. 수치 LB/UB 충돌과 callback 오류를 단순 시간 초과로 분류하지 않는다. 원 source의 역 AST 동일성 assert를 검토했으며 여기서 해당 adapter를 import/실행하지 않았다. |
| `budget.py:DateBudget.__init__/native_optimize` | 외부 B1 May31 재시도는 manifest-bound 이전 ledger의 SHA 및 측정 가능 여부를 검증하고 194.44199967384338초를 합산한다. 5400초 측정 Native Runtime, Threads=1, P2=0을 유지하며 이전 point/LB/UB는 이전하지 않는다. |
| `policy.py:verify_policy/verify_request` | V9 chain과 입력·과학적 authority를 유지하며 V10 manifest/attempt, May31 명시 재시도, INTEGER_CONTROL precision roster를 추가한다. 완료·기시작 날짜를 임의 재분배하지 않는다. |
| M/Actual/Fresh 및 build gate | V10 `m_stage.py/operations.py/execution.py/full_validation.py`는 V9 대응 파일과 byte-identical이다. `deferred_validation.py`는 경로/receipt/launch namespace, Worker는 V10 module identity를 추가한다. Native=0 full-validation도 실제 모델 생성과 파일/lock/heartbeat 쓰기를 수행할 수 있으므로 읽기 전용 검사를 위해 호출하지 않았다. |

**새 IEEE8500 연구의 독립 ledger에서 이전 Runtime은 0초다.** 외부 복구의 Runtime 부채·해·LB/UB·checkpoint·manifest·permit를 가져오지 않는다. 각 단계는 같은 동결 연구 입력을 쓰되 독립 ledger와 예산을 갖추어야 한다. 여기서는 새 Native ledger도 생성하지 않았다.

기존 4대 축은 `v42_bootstrap.m1.native_inputs`와 Native90 `operations._accepted`의 `(96,4)` P/Q/location·`(97,4)` SOC 및 MESS01–04 검사에 남아 있다. IEEE123는 frozen input fixture와 inherited physical Authority로 유지된다. 새 V10 추가 자체가 IEEE8500 6대·LV source hook을 제공하지 않는다. 원 M의 FULL row/bound/integer/raw point, PCS·SOC·경로·TRANSIT replay, strict UB/exact LB 및 Gap≤3% 검사는 유지된다. inherited Operations의 PASS는 Fresh 실행·authority 완료 검사이며 `physical_violation`을 별도 결과로 전달하므로, PASS 한 단어만으로 무위반을 뜻하지 않는다.

Git에 추가된 외부 May31 B1 final verification은 그 원 캠페인에 대한 기록이다. 본 감사가 재실행한 증거도, IEEE8500의 Global AC FAIL을 해소한 증거도 아니다. PR191은 기존 고정 head `40b6f94…`, PR192는 `74908e99…`로 OPEN이며 이 V42 delta가 B3 연결 코드를 병합한 것은 아니다. V10 `set_precision`의 B3 직접 호출은 허용되지 않아 B3 A1/A2 최신 정책 route도 별도 검증이 필요하다.

외부 read-only 보존 receipt는 원 관찰의 138개 authority 파일과 원 scheduler 정의가 그대로이고 RecoveryV10 task3개·manifest1개를 추가 관찰했다고 기록한다. 전체 live snapshot이 이전과 같다고 주장하지 않는다. 이 작업은 해당 등록/변경을 수행하지 않았다.

정확한 신규 source SHA256/Git blob, 함수 signature/line, GitHub 확인 시점, Git commit delta, 구성 보존 및 실행 0회 근거는 `SOURCE_ADVANCE_SINCE_REVIEW.json`에 있다. **최신 V42에 대한 IEEE8500·6대·LV Native/Actual/Fresh adapter, added-port FULL→Compact→C3A 동치성 및 전체 B0/B1/B2/B3 성능 비교는 계속 UNVERIFIED/NOT_RUN이다.**

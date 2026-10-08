# V42 단일 개발환경 통합 보고서

기준 작업공간은 **D:\MobileESS_v42**, 브랜치는 **v42**다. PR186 완료 HEAD `9a1b41260aff3bc70d2e36d7e1c293c03ea114de`에서 출발했고, PR188 완료 HEAD `4b19e85089171729a3225529a40cb00bf31f43d5`의 검증된 C3A 모델·축약·독립 증명 모듈만 선택 반영했다. PR162 C3A authority HEAD는 `1d922c91eb27056a5ccc79c92ef18146707099ab`다. 원래 A/M PR과 commit history는 재현 기준으로 유지한다. 전체 실험 branch merge는 하지 않았다.

추가 D-only 지시 전 D worktree를 만들면서 C의 공유 Git 저장소에 worktree/v42 등록을 추가했다. 추가 지시 직후 D의 `.git`을 독립 Clone으로 전환했고, 그 뒤 C Git 메타데이터에는 쓰지 않았다. 이전의 공유 등록을 C에서 정리하는 작업도 하지 않았다. 현재 저장소는 `.git`과 objects가 D 내부이며 alternate/shared object directory가 없다. 기존 C 데이터·코드는 해시 검증 후 D에 복사하여 재생한다. 기존 M worktree의 미완료 파일을 읽거나 프로세스를 종료·수정·재시작한 작업은 없다.

## authority 감사

A/M 공통 조상은 `52ef855a59144a7c561df44b81dc2ad265babdbd`다. `SOURCE_AUTHORITY_AUDIT.json`에 각 기준의 전체 변경 파일과 전후 Git blob, 공통 Python 모듈의 A/M SHA256·동일성을 기록했다. 선택 파일 전체는 `SELECTIVE_M_IMPORT.json`의 완료 M HEAD/blob/SHA256으로 추적한다. 기존 A scientific 데이터·목적함수·행렬·Freeze·과거 예산은 변경하지 않았다. 새 운영 scope 연결만 기존 `v42_a_stage_domain_v2/execution.py`에 추가했다.

공통 물리 파일은 PR186/PR188/PR162에서 동일하다.

| 파일 | 세 기준에 동일한 Git blob |
|---|---|
| `v42_native/mess.py` | `99f76d5f6ea1e466a2a08c7300069222cde4b5b3` |
| `v42_bootstrap/m1.py` | `045471310eff50f0e4d77591ee6404d7bd01d8ec` |

C3A matrix SHA256는 `45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8`, data SHA256는 `20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467`, start SHA256는 `be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5`다. Physical NormalAmps authority는 `0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51`다. Native 기본 모델은 이 C3A의 original MILP이며 실패한 branching/Benders 실험 설정은 채택하지 않았다.

## 단일 진입점과 단계 계약

PowerShell에서 `D:\MobileESS_v42\Start-V42.ps1`을 사용한다. TEMP/TMP/cache와 실행 산출물은 D에 지정된다. Python 라이브러리와 실행기는 기존 설치를 읽으며 패키지를 C에 설치하지 않는다. 공통 설정은 `V42_CONFIG.json`, 파이프라인은 `v42_unified/pipeline.py`, 현재 evidence backend는 `v42_unified/backend.py`다.

| 명령 | 동작 |
|---|---|
| `.\Start-V42.ps1 status` | 과학 상태와 M1 미해결 상태 출력 |
| `.\Start-V42.ps1 run` | 원본 증거의 A1 P1-only를 검증하고, 새 입력의 인증된 M1이 없으면 정상 중단 |
| `.\Start-V42.ps1 replay` | 원본 A 정수·물리 재생 + C3A 전체 독립 증명·정수·물리 재생. Native optimize=0 |
| `.\Start-V42.ps1 build-only` | C3A Native 모델 생성과 모든 행렬·RHS·목적함수·axes/types/bounds 정확한 동일성 검사. optimize=0 |
| `.\Start-V42.ps1 audit` | 완료 Git 객체를 기준으로 A/M source authority 재감사 |
| `.\Start-V42.ps1 handoff-check -Handoff D:\completed_M_handoff.json` | 완료 M 결과의 선택적 수용 전 검사 |

모든 단계는 같은 frozen input authority, 실제 day, grid array identities, workload axis identities, upstream/decision SHA256을 사용한다. 상태값은 accepted·not certified·pending을 구분한다. 정당한 전체영역 bound와 원본 정수·물리 독립 증명을 통과해야 다음 단계로 이동한다. 새 Native 실행 프로그램은 `PipelineBackend.execute/verify` 계약을 구현하고 `NativeBudget.optimize`로 모든 LP/pricing/MIP/P2 호출을 한 단계 ledger에 누적해야 한다. 현재 제공되는 기본 backend는 저장 증거 재생이다. 새로운 May12 M1 및 실제 A2/M2 최적화 프로그램의 성공을 주장하지 않으며, 최종 M 결과를 검증해 이 단일 backend를 확장한다.

| 단계 | 동결 입력/authority | 결정변수와 출력 | 다음 단계 gate |
|---|---|---|---|
| A1 | 원본 jobs/resources/rack/gang/WAN, Runtime/CC4, grid·route·battery authority | 원본 job start/placement/migration, site-time electrical footprint, rho; P1-only 또는 정식 P1+P2 result | 정확한 전체영역 LB/정수 UB Gap, job·전기 footprint 독립 replay. P1-only는 M1만 허용 |
| M1 | A1 job schedule·AIDC P를 상수로 고정, 동일 계통·교통·battery/initial sites | MESS route/connection/mode/Pch/Pdis/Q/SOC와 rho, M P2 intervention | 원본 route/이동 에너지/연결 지연/PCS16/SOC/grid, Global Gap 및 필요한 P2 인증 |
| A2 | accepted M1을 고정, 같은 원본 AIDC 영역·물리 데이터 | 원본 AIDC 결정 재최적화; A1 warm start | M1 anchor unchanged, 원본 정수·물리/P1/P2 증명 |
| M2 | accepted A2 AIDC를 고정, M1 warm start | 같은 MESS 결정·목적함수 | fixed A2 no regret, 원본 정수·물리/P1/P2 증명 |
| Planning Freeze | accepted A2+M2와 동일 모든 input hash | reloadable immutable plan/정책/계통/decision SHA | 네 단계 모두 독립 인증, write-once |
| Actual | Planning Freeze와 해당 realized source inputs | 고정된 schedule/route/PQ/SOC의 기존 causal replay | global MILP/PQ repair 없음, frozen plan SHA 동일 |
| Fresh AC | 기존 `v42_native.actual.run_dday_actual` 내부의 유일한 Fresh AC 호출 | OpenDSS fresh/convergence/전압·line·NormalAmps·kVA certificate | 새 AC receipt와 정확한 plan/grid SHA. 별도 단계는 이 receipt를 검증·저장 |
| Validation | 전체 동일 입력·계획·Actual·AC receipts | 최종 PASS 또는 명시적 미인증 | 입력 동일성 및 모든 물리 위반 0 |

## P1-only에서 M1으로의 정당한 전달

PR186의 `A1_P1_ONLY_ACCEPTED=true`와 기존 `A1_ACCEPTED=false`를 그대로 유지한다. P1은 원본 min rho 전체 integer 영역의 Global Gap을 인증한 결과이며, migration/shift/prestart 값은 해당 schedule의 평가값이다. P2를 최적화한 결과가 아니다. `P2_certificate=null`, `P2_objectives_optimized=false`를 명시한 `V42_A1_P1_ONLY_TO_M1_V1` 인터페이스를 새로 만들었다.

M1은 이 AIDC footprint를 상수로 받으며 AIDC 결정변수와 AIDC Q 결정변수를 만들지 않는다. MESS의 joint route·충방전 P/Q·SOC·경로 제약은 유지된다. 전체 130-class STAY/migration 원본 영역, 원본 job/WAN/rack/gang/서비스/carryout/Runtime/CC4 및 계통 배열을 검증한다. Handoff 생성 함수와 별개의 verifier가 원본 freeze·certificate·input array에서 직접 비교한다. 재해시한 schedule/control/input/grid/axis/bound/P2 변조도 거부한다.

새 May12 입력에는 1,782개 job이 있고, M 연구의 C3A 모델/저장 point는 May01 1,499개 job authority다. 두 입력의 point·LB·UB를 서로 전용하지 않았다. 새 계약의 M1 결과는 `NOT_RUN_NOT_CERTIFIED`다. 완료 PR188의 현재 global LB=0.5687116104049206, UB=0.6284141956452488, Gap=9.500515051068552% 및 `M1_ACCEPTED=false`는 과거 authority 상태로 별도 보존했다. 미완료 M 연구 결과는 반영하지 않았다.

## 시간과 검증

새 A1/M1/A2/M2마다 Native 최적화 누적 상한 5,400초, 단계 실제 Wall 실용성 기준 90분, Global Gap≤0.5%, Threads=1이다. 실패 native 호출도 Runtime/Work ledger에 포함한다. 모델 생성과 검증 비용은 Native Runtime과 분리 기록하며 Wall 기준을 넘으면 practicality FAIL로 표시한다. Wall을 추가 Native 예산으로 간주하지 않는다. MemLimit/SoftMemLimit을 설정하거나 RAM에 따라 종료하는 코드가 없다. 기존 600/1,800/3,600초와 모든 과거 실행 기록은 보존했다. A 원본 feasibility/optimality 1e-6·integer 1e-5, M scientific solver 1e-8 및 기존 1e-7/1e-8 objective lock를 유지했다. 기존 physical checker의 별도 허용오차도 바꾸지 않았다.

원본 A 정수 모델 3,184,901행/1,141,597열을 exact dyadic로 재생하고, 선택 job schedule·control·global binding 및 모든 원본 물리를 확인했다. 11개 frozen input과 47개 grid array의 bytes/dtype/shape/hash, workload axes identity가 동일하다. Native optimize=0. 최종 성공 replay Wall은 약 24.6초이며 정확한 비용은 `A1_ORIGINAL_INTEGER_PHYSICAL_REPLAY.json`에 있다.

C3 independent verifier는 C2 전체 654,348행, 제거행 71,540개, 새 경계 48,551개를 retained rows와 원본 bound에서 독립 증명했다. C1 alias를 독립 복원하고 원래 full rows/types/bounds/PQ/SOC/mode/route physics를 재생했다. 물리 point의 rounding/clipping/repair는 하지 않았다. 성공 C3 증명·원본 physics replay Wall 약 150초, Native=0이다. Native build-only는 582,808행/306,040열의 목적함수·CSR·RHS·axes·types·bounds가 정확히 동일함을 확인했다. 해당 실제 비용은 `NATIVE_BUILD_ONLY.json`에 있다.

최종 공통·interface 검증은 **422 PASS / 12 SKIP / 0 FAIL**이다. solve-dependent 기존 fixture 12개는 zero-Native profile에서 명시적으로 건너뛰었고 PASS로 계산하지 않았다. 별도 새 계약 테스트 36개에는 실제 원본 P1 edge, 변조 거절, 누적 예산/실패 비용, D-only copy, 단계 순서/warm start, M1 pending 차단, operational scope의 optimization 금지, 완료 M handoff의 필수 scientific identity 누락 거절이 포함된다. 전체 단계의 test double은 실제 Fresh AC 또는 과학 캠페인 실행으로 계산하지 않는다. 최초 axis test 실패는 test fixture가 expected axis와 같은 list를 공유했기 때문이며 independent tuple로 수정했다. 최초 historical gap float 비교 실패는 연산 순서 차이였고 원래 기록과 같은 계산 순서로 재검증했다. 실패 로그는 D tmp에 보존했다.

기존 27일 PASS는 135개 stage receipt를 해시 확인한 뒤 D에 복사해 별도 검사했다. 원래 계약은 four-objective A1, MESS_OFF, A1→Planning→Actual→Fresh→Validation이다. M1/A2/M2 또는 새 P1-only handoff가 없으므로 새 A/M 파이프라인 PASS로 자동 승계하지 않았다. 기존 PASS 자체는 보존된다. 이번 작업에는 전체 May B1 캠페인, 신규 대규모 M1 optimize, 신규 Actual/Fresh AC가 없다.

## 최종 Git와 미해결 상태

정확한 최종 v42 HEAD와 테스트 receipt SHA256, 변경 모듈, A/M scientific authority, clean 상태는 commit 후 생성하는 `D:\MobileESS_v42\V42_INTEGRATION_READY.json`에 있다. 자기 commit의 SHA를 같은 commit 내부에 저장하는 순환을 피하기 위해 이 파일은 Git ignored runtime receipt이며 생성 프로그램과 검증 근거는 commit한다.

현재 통합 기반은 준비됐지만 M1 scientific acceptance는 미해결이다. M1의 정확한 새 입력 결과와 A2/M2·운영 실행을 완료했다고 표시하지 않았다. 최종 M 완료 변경분의 수용 절차는 `FINAL_M_HANDOFF_KO.md`와 `v42_unified/handoff.py`에 있으며 자동 대기·전체 merge·실패 solver 승격을 하지 않는다. 후속 개발은 이 단일 v42에서 수행한다.

# Source30 검증 및 실제 배포 증거

Source30의 과학 소스 commit은 `bb9052225b440e4d70cd0441fb0c8dc8c6708e47`, 실행 소스 98개의 SHA는 `f6ed2fee8b50208e64a2b0abffc65b7485eb717e4af4c1b29f82cea19a4de788`이다. 실제 `D:\v42run30`의 Git HEAD와 모든 봉인 파일을 읽기 전용으로 확인했다. 원본 과학 소스 1007개는 실행 중이던 Source27의 원본 맵과 동일하고, 추가 자산 5개를 포함한 정확한 합집합 1110개가 모두 바이트/SHA 일치한다.

이 폴더는 선택된 raw 영수증과 운영 보조 스크립트를 원본 바이트 그대로 보존한다. 스크립트는 실행 이력 자료이며 이 문서 패키징 과정에서 실행하거나 운영 경로를 변경하지 않았다. 절대 경로를 담은 영수증은 원래의 파일을 계속 가리킨다. `SHA_INVENTORY.json`은 원래 경로와 복사본의 상대 경로를 대응시키고, `SHA256SUMS.txt`는 복사된 파일과 인벤토리의 체크섬을 담는다. 대형 실제 모델, NPZ/CSR, 13MB 과학 검증 패킷 및 전체 종료 RESULT는 복사하지 않았고, 선택된 영수증 안에 원래의 경로/SHA를 보존했다.

## 검증 범위

| 자료 | 실제 결과와 범위 |
| --- | --- |
| Root 통합 실행 | 300개 전체 테스트 PASS, 실제 Native 모델 생성/optimize 0 |
| 독립 통합 검토 | 최초 전체 실행 299 PASS + 기존 임시 경로 전제의 테스트 1개 실패; 동일 소스/테스트로 해당 1개를 올바른 저장 경로에서 다시 실행해 PASS. 서로 다른 300개 테스트 통과이며 전체 300개 재실행을 주장하지 않는다. 최초 실패 영수증과 출력도 보존한다. |
| Cache 작성자 | 120 PASS, 실제 Native/model 0; 최초 pytest Tee.isatty 오류는 테스트 0개 실행의 실패 영수증으로 별도 보존 |
| RMP 작성자 | 72 PASS, 실제 Native/model 0; 작성자 시점 소스 맵 이후 Root 통합 테스트가 최종 Source30 맵에 연결한다. |
| READY 교체 제어 | 작성자 84 PASS 및 독립 84 PASS, 실제 작업자 실행/중단/Native 0 |
| 배포 실행 독립 감사 | 180개 검사 PASS: 실제 소스 해시, 27개 요청, READY 교체 범위, 기존 Native 호출 및 비-Native 비용 기록의 정확한 prefix, Supervisor 실제 신원/HTTP8794 |

각 테스트 집합은 겹칠 수 있으므로 합쳐서 고유 테스트 수를 만들지 않는다. Native 0 테스트의 PASS는 실제 날짜의 최종 과학 PASS나 목표 Gap 달성을 뜻하지 않는다. 실제 Source30 RMP 수치 상태, FULL 검증, 독립 Global LB 및 최종 Gap은 별도의 실제 실행 결과로 확인해야 한다.

## 성능 자료의 정확한 범위

`saved_draft_CPU`의 단 한 번 허가된 저장 May01 projection-only 계산은 모델 생성/Native 0이다. 원래 계산 wall 37.092348초, 당시 초안 cache의 첫 계산 wall 47.971974초, hit 16.114732/15.202666초였고 Scope/source snapshot의 별도 시작 비용은 0.459043초다. 첫 계산은 약 10.88초 더 느리고 시작 비용까지 포함하면 약 11.339초 더 느리다. 작은 fixture의 느려진 결과도 보존한다.

이 계산은 당시 초안의 전체 guard/해시 비용을 포함한다. 새 production factory와 추가 guard를 포함한 Source30의 실제 하루 속도 향상을 측정한 결과가 아니다. Source27의 3일 실제 L1-L4 소비 영수증과 정적 callgraph는 같은 attempt의 case/decomposition을 네 번 사용하는 근거를 제공한다. 실행 중 객체 ID는 당시 계측하지 않았다. 모든 round의 새 dual/price, 원래 local bound 및 독립 FULL signed checker는 계속 새로 계산하며 price/Global LB/결과를 cache하지 않는다.

## 실제 배포와 시간별 상태

2026-10-09 21:07:00.352988 UTC의 봉인된 배포 영수증에는 Source30 READY 9개가 있다. 첫 3일의 priority는 1000, 다음 6일은 100이다. 9일 × 3개 slot의 요청 27개 모두 sealed fresh0 요청이며 이전 checkpoint/native carry가 없다. 기존 Source28의 **미시작 READY 9개만** 새 Source30으로 교체했고, 원래 요청/결과/원장/교체 이력은 보존했다. 정상 Source27 작업을 배포 과정에서 중단하지 않았다. Supervisor PID87676/create/cmd/cwd가 유지되고 HTTP8794가 정상이다.

독립 baseline은 20:55:56 UTC이다. 이후 Source27의 May01/02/03은 각각 21:10:35.281431 / 21:12:54.458865 / 21:14:42.887030 UTC에 Native 예산을 소진해 `TIME_LIMIT_FEASIBLE_NOT_CERTIFIED`, `PASS:false`로 종료했다. 측정 Runtime은 5400.5409989356995 / 5400.3580005168915 / 5400.426999807358초다. 공개 상태는 FAIL이며 PASS로 바꾸지 않았다. 기존 호출 기록은 baseline의 정확한 prefix로 남아 있고, 새 프로세스 생성 시각은 각 기존 작업의 종료 이후다.

21:13:37 UTC의 배포 감사에서는 자연 전환 후 Source30 2개가 실행 중, 7개가 READY였다. 21:14:35 UTC의 별도 supplement에서는 May01/02의 실제 새 원장이 각각 Native0/호출0/예산5400/no carry였다. Root의 21:15:35 UTC 봉인 관측과 21:17:04 UTC의 추가 독립 supplement는 Source30 May01/02/03 PID105888/106284/78332의 실제 create/cmd/cwd/요청/source와 세 birth0 원장을 확인한다. 추가 독립 관측 시점에도 세 원장은 Native0/호출0이었고 원래 static presolve 단계였다. 이후 진행 상태는 이 문서의 snapshot과 구분해야 한다. 세 날짜의 최종 PASS는 이 자료에서 주장하지 않는다.

`actual_root_watch`는 Root의 timestamp별 raw 관측이다. 최초 관측과 재관측을 모두 보존한다. 관측기 프로세스 신원 assertion의 일시적인 도구 오류는 실제 작업자 실패로 바꾸지 않았으며, Root는 재조회 후 exact identity 확인 및 불일치시 admitted:false/deferred 재관측 로직으로 수정했다. 최신 관측 스크립트는 `operational_helpers`에 있다.

## 보존과 운영 분리

`execution_audit`는 바이트를 한 번 읽고 그 바이트를 봉인한 baseline/최종 snapshot 및 명시적인 queue schema 보정 영수증을 포함한다. 최초 baseline의 generic status 키 해석은 별도 queue 보정 영수증으로 수정했고 원래 raw snapshot은 바꾸지 않았다. 중간 감사 실행의 부분 snapshot은 D의 원래 감사 폴더에 남겼다. 최종 영수증은 현재 Source30 freeze 경로와 과거 Source27 freeze 경로를 구분한다.

`deployment/CODEX_HOURLY_AUTOMATION_VERIFICATION_20261009T210838.json`은 저장된 시간당 자동화 설정이 ACTIVE임을 확인한 관측이다. 실제 예약 실행을 관측했다는 주장은 하지 않는다. B2/B3 전체 캠페인의 실제 수행과 현재 채팅의 첫 3일 최종 PASS 확인은 계속 진행된다. 이 패키징은 source/queue/manifest/프로세스/Native를 변경하지 않았으며 Git commit/push는 Root가 담당한다.

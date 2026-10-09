# 검토·재현 순서

이 PR은 운영 후보를 승인하지 않는다. `FINAL_SINGLE_SCENARIO.json`의 선택 운영 시나리오는 null이며, 단일 연구 snapshot은 `STUDY_CONFIGURATION_DRAFT_BLOCKED`다. 모든 명령은 이 독립 checkout에서 실행한다. 기존 Production 경로·Worker·Scheduler·permit·ledger에 쓰는 명령은 없다. B1/B2/B3 또는 Native 전체 모델을 실행하는 경로는 제공하지 않는다.

실제 시험 환경은 Python3.11, NumPy1.26.4, SciPy1.14.1, pandas2.2.3, Matplotlib3.11.2, OpenDSSDirect.py0.9.4, dss-python0.15.7/backend0.14.5다. 정확한 환경·시험 수·로그는 `FINAL_LIGHTWEIGHT_TEST_RECEIPT.json`에 있다. 저장된 자료만 읽는 감사는 다른 날짜나 독립 D-day Actual이 아니다.

기존 환경을 바꾸지 않으려면 별도 가상환경을 사용한다. 아래 `python`은 필요한 패키지를 갖춘 그 환경의 Python이다. 현재 작업 환경의 실행 파일은 `.runtime/Scripts/python.exe`다. `.runtime` 자체는 commit하지 않는다.

원 데이터와 code 계약을 먼저 확인한다.

봉인 상태만 확인하려면 `python -B -X utf8 tools/ieee8500_v42/verify_artifact_package.py`를 실행한다. 이 명령은 원962개 소스, 연구구성·mapping SHA, 파일 전체 roster/hash, 현재 main CSV와 저장 AC 일치, 76개 시험 receipt와12개 global FAIL을 읽어서 검사한다. Solver를 실행하지 않는다. `--seal`은 최초 봉인에만 쓰며 기존 manifest 교체를 거부한다. Manifest와 자체 검증 receipt는 순환 SHA를 피하기 위해 roster에서 제외한다.

```powershell
python -B -X utf8 tools/ieee8500_v42/run_lightweight_verification.py
python -B -X utf8 -m ieee8500_v42.review_joint_scores
python -B -X utf8 -m ieee8500_v42.review_selected_ac_v3
python -B -X utf8 -m ieee8500_v42.review_selected_port_ac
```

첫 명령에는 실제 원 OpenDSS와 120/240V 상별 주입 검사가 포함된다. 나머지는 원본 선정·스케일·포트의 저장 결과를 독립 재계산한다. Fixture/contract 검사와 source-byte 검사는 Native/전체 AC 영역 인증이 아니다. 수정한 데이터에서 과거 checksum을 그대로 PASS로 만드는 옵션은 없다.

최종 연구 배치의 실제 B0와 동일 입력 Fresh를 재현할 때는 다음 순서를 사용한다. `selected_case_v3`는 12개 사전 스케일×96슬롯을 계산하며 12개 모두 global voltage FAIL 결과를 보존한다. `selected_port_ac`는 9,216개 fixed 정격 표본과384개 원 automatic 표본을 계산한다. `selected_auto_port_audit`는 automatic384개에 국부PCC 읽기·상태SHA를 보강하는 집중 재검사다. 이들 작업은 기존 연구 증거를 재생성하므로 재현용 checkout에서 실행하고 먼저 원 `ARTIFACT_SHA256_MANIFEST.json`을 보존한다.

```powershell
python -B -X utf8 -m ieee8500_v42.selected_case_v3
python -B -X utf8 -m ieee8500_v42.verify_selected_b0
python -B -X utf8 -m ieee8500_v42.selected_port_ac
python -B -X utf8 -m ieee8500_v42.selected_auto_port_audit
python -B -X utf8 -m ieee8500_v42.selected_response
python -B -X utf8 -m ieee8500_v42.review_selected_port_ac
```

그림과 한국어/CSV 집계만 재생성할 때는 다음 명령을 쓴다. 실제AC를 새로 수행하지 않는다.

```powershell
python -B -X utf8 -m ieee8500_v42.selected_location_audit --root . --plots
python -B -X utf8 -m ieee8500_v42.congestion_report
python -B -X utf8 -m ieee8500_v42.plot_selected_b0
python -B -X utf8 -m ieee8500_v42.assemble_report
```

기존 v3 고정 방향의 exact certificate, 원 정적0.912pu 원인, 교통55296route·ETA·거리·traction, known1649UID 유연성, 전체606MV/1177LV×4시간 P/Q 응답은 각 명명의 audit/review 모듈과 봉인 입력에 있다. 전체 후보 AC는 이미 저장돼 있으므로 위 독립 감사에 다시 필요하지 않다. 고정tap 중앙미분,8개 정격점,4시간 automatic 또는 Fresh 동일입력은 연속96슬롯 자동제어 영역·actualSUMO·실제 보호 승인·unseen day 성과를 증명하지 않는다.

루트 6개 main CSV의 현재 의미와 과거 byte archive는 `README.md`를 따른다. 이전 fixed-v3 재현에는 `historical_fixed_v3_outputs/`를 사용한다. 선택 mapping SHA와 원 selector pre-registration은 바뀌지 않았다. 경로에서 원 Source series Reactor를 누락한 메타데이터의 정정 전후는 `PATH_METADATA_CORRECTION.json`과 `PATH_METADATA_FROZEN_PIN_CHAIN.json`에 저장돼 있다.

`isolation after`는 실제 D: 캠페인이 존재하는 이 호스트에서만 read-only 관측한다. 다른 컴퓨터에서는 기존 before/after JSON을 읽는다. 원138개파일·44개등록의 보존과 별도로 외부 RecoveryV10 신규등록3개·신규manifest를 명시했으며 live 상태의 완전동일성을 요구하지 않았다. 새 IEEE8500 ledger는0부터 시작하고 외부캠페인 Runtime·point·LB·UB·permit를 이전하지 않는다.

현재 적격운영case가0이므로 분석결과에 맞춰 source/Vreg/전압·전류·CT정격을 바꾸거나 B0–B3 solver를 실행하지 않는다. 새 연구조건의 정당화와 원 모델·six-unit·SOC·grid·실제 지리/하드웨어·독립 평가 gate를 갖춘 이후 별도 검토가 필요하다.

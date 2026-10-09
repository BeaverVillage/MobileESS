# 기존 캠페인 관측 범위

이번 작업은 기존 캠페인 소스·ledger·워커·예약 작업을 편집하거나 중단하지 않았다. 외부 쓰기, 워커 중단, scheduler mutation 호출은 모두 0회다.

시작 시 수집한 원본 소스·입력·manifest/permit 1,105개는 종료 관측에서 SHA와 경로가 모두 같았다. 별도 진행 중인 작업으로 보이는 신규 파일·manifest 20개가 관측됐다.

예약 작업은 종료 관측에서 아래 차이가 있었다. 변경 주체는 이 스냅샷만으로 인증하지 않는다. 따라서 **전체 예약 등록 상태가 동일했다는 PASS는 선언하지 않는다.** 이번 작업의 호출은 읽기 전용 CIM/Get-ScheduledTask 조회뿐이었다.

* 추가: `MobileESS_V42_B2_native90_build_reuse_20261009_01_DirectLPV18_Coordinator`
* 변경: `MobileESS_V42_B1B2_P1_native90_build_reuse_20261009_01_RecoveryV13_Monitor`
* 삭제: 0개

정확한 관측값은 `CAMPAIGN_BEFORE.json`, `CAMPAIGN_AFTER.json`, `CAMPAIGN_PRESERVATION.json`에 있다. `original_authorities_equal=false`는 예약 등록 변경까지 포함한 판정이며, 원본 파일의 `changes=[]`와 구분한다. 가동 중인 워커의 진행 상태나 ledger의 시간적 변화 자체를 동결하려 시도하지 않았다.

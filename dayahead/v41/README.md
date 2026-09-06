# V41 실행과 감사

정책별 실행 순서는 Day-Ahead → Joint Freeze → Actual입니다. 실행은 `dayahead.v41.execution`에서 시작하며, Actual 입력은 Day-Ahead receipt와 전체 파일 manifest를 검증한 뒤 읽습니다.

ML 입력은 PENDING의 Rolling Track-P L2 Q90 초/슬롯과 81개 H4 창의 capped GPUh 스칼라입니다. H4 서비스 수준은 0.85입니다. 원시 H4 예측은 별도 필드로 유지합니다.

전체 May는 `dayahead/tools/run_v41_may_campaign.ps1`로 실행합니다. 상태 확인, 정상 중단 요청, 재시작 스크립트는 같은 폴더에 있습니다. 중단은 실행 중인 원자적 저장과 현재 단계를 마친 뒤 적용됩니다. 과학 코드가 바뀌면 이전 receipt의 재사용을 거부합니다.

결과는 `frozen_artifacts/v41_may_campaign/`, 로그는 `logs/v41_may_campaign/`에 저장합니다. 각 정책·일자의 `UNIT_SCIENTIFIC_MANIFEST.json`이 전체 경로·행 수·스키마·SHA256을 연결합니다. 요약은 `python -m dayahead.v41.aggregate`로 저장된 결과에서 다시 만들 수 있습니다.

전체 실행 전에는 May-1 B0/B1 파일럿, B0-in-B1 feasibility, 목적함수 동일성, P0-01~07 및 배경 부하 중복 감사, 회귀시험, 124개 실행 설정, 독립 실행 시험, 최종 인터페이스 commit이 모두 필요합니다. S5R1과 R6R1의 기존 FAIL 판정은 유지합니다.

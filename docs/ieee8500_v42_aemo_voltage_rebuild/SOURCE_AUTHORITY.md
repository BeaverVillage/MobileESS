# Source authority

현재 V42: `625bbcb8b9a54a00c1660c26d96f7737c2f75457`. 전기·배치 기준 PR193: `7d2253c1c9cd6db0720e5930692e55352141a878`. 과거 PR62: `cf6d0c86c877e73db09e09eec903f176486d2df1`.
원본 V42 Python/HTML 962개와 PR193 봉인 자료 691개는 byte identity 검증했다.
시작 시 최신 V42와 기존 core 사이 변화는 신규 파일 114개였으며 기존 input/reference/queue/Actual/RegControl 구현은 동일했다.
원본 IEEE8500 DSS31개, 3703 Lines(활성3698), 1190 Transformers, 2354원본 Loads, 8531노드 및 교통24개 매핑 SHA `4a70fd13bf08c8512d30f74e48dfafb46fdddd4e112a3aee92a8191f22cad016`를 보존했다.

PR62는 PV의 원본 고객 버스·상·정격 배분 방법과 전압 overlay의 역사적 근거다. 해당 overlay는 **모든12RegControl Vreg123.5**를 적용했다. P3의 feeder-only 변경과 같다고 주장하지 않는다.
PR62 rule의 PV_alpha=.5와 당시 실제 dispatch BG=.552 사이 불일치를 발견했다. 과거 dispatch는 사용하지 않고, 설치비율0.11852937486188635만 현재 V42 solar normalization으로 구동했다.
과거 알고리즘·차량 정격·AIDC 정격·좌표·스케줄은 복사 실행하지 않았다.

정확한 경로·SHA·blob은 `SOURCE_AUTHORITY.json`, 원자료·추출행은 `ieee8500_v42_aemo/data/sources/`, 최종 외부 캠페인 비교는 `CAMPAIGN_PRESERVATION.json`에 기록한다.
생성물은 새 worktree만 기록하며 기존 live소스/ledger/워커/예약 작업을 편집하거나 중단하지 않았다.

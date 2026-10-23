# V2_add AIDC 원본 QoS 및 실행 유연성

원본 FULL Job1499개(1GPU1489개, 4GPU10개)의 생성자와 validate/resources_used/resource_limit을 재사용했다. 원래 WINDOWS를 다시 바인딩한 실제 A-stage 수용 Adapter에서 기존 캐시414개의 START_WINDOW 위반을 거부한다. 캐시의 accepted 표시로 우회하지 않는다. 동일 수용 경로가 새 A1/A2 결과에도 적용되도록 execute_a_stage를 구현했지만 실제 IEEE8500 A1 호출기의 전체 연결은 아직 완료되지 않았다. 새로운 A1 accepted 해나 Global LB를 만들지 않았다.

Actual의 과거192개는 opt-in Known 연구정책의 사후 측정이라는 분류를 유지한다. Source 고객의 QoS 인증이 아니다. 기존1024개 Window 유연 Job 수를 kW로 환산하지 않는다. 기존 전체 gang/allowed-start/완전 rebound 검색에서 비영 시간 이동 witness는0개였지만 이 값은 전체 사전배치·이주의 불가능성 상한이 아니다.

원본 FULL 개별 Job 도메인에서 PENDING1395개가 다른 사이트 사전배치 선택을 가진다. 용량·rack·residency·서비스량·Window 검사를 수행하고 AC 성과를 보지 않는 UID/목적지 순서로8632483→AIDC02 명령을 선택했다. 원본 이벤트 엔진으로 인과적 실행과 독립 Fresh를 수행했으며 의도적 QoS 초과0개, GPU 용량 초과0개였다. 미래 실행시간은 simulator 내부에만 두었다.

그러나 이 실행은 **인증된 비영 유연성 witness로 거부**했다. 대조 전력이 동결 r043 FCFS와 최대41.62701842kW 다르고, B0/B1의 flexible admission 경로 차이도 포함된다. 일내 compute GPUh 차이는566.99111111이며 carryout을 포함한 전체 작업량/완료 동등성과 Original FULL 공동 Job·Grid 검증이 닫히지 않았다. 관측 슬롯31의 IT/PCC 차이6.57268696kW와 슬롯74의0kW를 제어 가능한 전력으로 보고하지 않는다. 인증된 비영 Actual 유연전력/GPUh는 **미확정(null)** 이며0이라는 전체 상한도 아니다. 당시 재생/전력/Job/Queue 결과는 Runtime SHA Manifest에 보존했다.

Time-shift, Pre-site, checkpoint1800초, Multi-GPU gang, GPUh/완전 서비스, WAN/1개 동시 transfer, checkpoint/restart, rack/residency, 인과적 도착 및 Known/Unknown 구분은 원본 제약으로 유지해야 한다. 별도의 고객 권한/실행 capability 없이 Can_Checkpoint_Migrate를 켜지 않았다. Migration 실행 witness와 FULL 재생은 미인증이다. Unknown849개의 원래 양수 지연 budget은0개라는 앞선 감사를 재사용한다. 고객의 데이터 이동 동의는 설치 GPU나 초기 연구 위치로부터 추론하지 않는다.

필요한 구현: 현재 r043 FCFS/Actual 정책의 동일 원본 기준 재생, 초기·tail·완료 작업량 보존, 실행 capability·WAN/residency의 실제 바인딩, Planning/Actual C1 및 FULL 검증기/Global LB의 동일 case 연결이다. 단순 kW/GPU UID 복제로 이를 대신하지 않는다.

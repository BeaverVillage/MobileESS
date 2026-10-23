# AIDC 정책·실제 실행 가능성

Planning414개는 원본 FULL WINDOWS.allowed_starts 밖의 cache Accepted start다. `v44/planning.py:golden`의 cache 수용과 도메인 인증은 별개다. V44_POLICY_OR_PHYSICAL_VIOLATION은 Planning FULL 범위에 한정한다. 원본 A1을 다시 풀거나 Actual 연구정책 구현 오류라고 단정하지 않았다.

Actual192개는 모두 Known이며 KNOWN_RESEARCH_WINDOW_ASSUMPTION 이벤트가 있다. `v43_corrective/known_window.py`/`v44/actual_policy.py`의 opt-in 연구정책에서 원래 latest/deadline/QoS는 사후 측정이다. V44_RESEARCH_POLICY_COMPLIANT_BUT_SOURCE_QOS_NOT_CERTIFIED로 분류했다. 원본 Source_authorized=False, QoS_PASS=NOT_CLAIMED를 유지한다. UID별 Window/Budget/Deadline/Intentional Burden/권한·정책·근거 Source는 두 재감사 CSV에 있다.

전체 Gang/allowed start/복수 Job/Site, Prefix·Capacity·Budget·Deadline·완전 Rebound로 확대한 동일 Site 지연 witness는0개다. 사유는 {"SOURCE_PREFIX_ALREADY_STARTED_NO_RETROACTIVE_SHIFT": 1031, "NO_ORIGINAL_ALLOWED_START_WITH_BUDGET_DEADLINE_COMPLETE_REBOUND_CAPACITY": 298, "NO_COMPLETE_REBOUND_WITHIN_HORIZON": 66}이다. Pending Known1395개는1GPU, 이미 RUNNING254개 중70개는 multiGPU다. Window 후보1024개를 kW로 환산하지 않는다. Unknown849개의 양수 Budget은0개다. 이번 witness 범위의 이동GPUh/피크74 이동/Rebound는0이고 원본 C1 Actual 전력 재현오차0kW, 서비스/GPUh 변화0이다. 전체 AIDC 유연량의 상한0을 뜻하지 않는다.

Pre-site/Migration은 NOT_VERIFIED/null이다. 호환12 Site/boolean capability를 feasible kW로 인증하지 않는다. 원본 causal controller/admission/reservation, capability packet,1800초 checkpoint,WAN80GB,Rack/GPU/Residency/경로,Source/Destination 동시 점유,Restart/공유 Budget의 FULL witness가 필요하다. 같은 시작시각 Site 이동으로 Window 밖인364개를 엄격 witness로 만들 수 없다. 별도 PREPLACE_MIGRATION 감사가 이를 기록한다. 비영 Actual AIDC/Joint 성과를 주장하지 않는다.

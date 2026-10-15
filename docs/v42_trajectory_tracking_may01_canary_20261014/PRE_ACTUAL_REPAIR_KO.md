# Actual 시작 전 서비스량 계약 수정

추가한 양성 Migration fixture가 nominal remaining compute 1.0 GPUh에 대해 1.25 GPUh를 집계하는 오류를 검출했다. 전송·재시작 중 GPU hold는 물리 점유와 전력에는 포함되지만 computing service는 아니다. 초기 22개 계약 fixture가 통과했더라도 이 양성 사례의 실패를 숨기지 않았다. 실패 XML은 `PRE_FIX_MIGRATION_VOLUME_TESTS.xml`에 보존했다.

이때 실제 Actual Replay와 Target Freeze는 아직 시작하지 않았다. 자신의 준비 worker 두 개만 명령줄·parent PID를 확인한 후 중단했다. conhost 프로세스가 child 목록에 포함되어 최초 엄격한 PID 확인이 거부했으며, 다른 Python 또는 기존 Monitor를 종료하지 않았다. 중단 receipt와 watchdog/Native 원장을 그대로 보존한다. A1은 원본 full domain/graph 준비를 442.227초 시도했지만 Native Optimize에 도달하지 못했다. 신규 A1은 `NEW_A1_NOT_CERTIFIED`다.

수정 후 Migration 점수는 두 적분을 구분한다. 물리 GPU hold 전체는 resource/grid/PCC 진단에 사용하고, nominal assignment/share는 restart 종료 이후 remaining Q50 compute만 반영한다. 이전 배분의 checkpoint 이전 부분은 fractional-slot 비율로 보존한다. 같은 UID의 미래 compute 배분만 바꾼다. 양성 fixture는 수정 후 통과했다.

기존 A1 준비 Case SHA와 수정 후 Tracking Case SHA는 다르다. 중단된 A1을 수정 후 Case의 최적해 또는 인증으로 승격하지 않는다. Original PR228 7개 core와 A1 목적/physics는 바이트 동일하다. 새 Target은 수정 후 Source/Case에 동결한 과거 V5 A1 diagnostic anchor다. C0/C2/C3는 모두 같은 수정 후 입력을 사용한다.

Native Solver 재시도는 없다. 실제 실행 wall은 중단 시도의 watchdog 446.953초와 수정 후 Diagnostic watchdog 시간을 누적하며 1,200초 한도를 공유한다. 개발 수정과 회귀 테스트 wall은 별도로 구분한다. 과거 PR228/PR227 Native 원장을 변경하지 않는다.

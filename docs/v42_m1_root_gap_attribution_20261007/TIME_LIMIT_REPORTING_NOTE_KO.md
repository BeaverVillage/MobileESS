# 설정 TimeLimit과 실제 Runtime

첫 선택적 정수화 시험은 `TimeLimit=300`, `Threads=1`로 실행했으며 native Status는 TIME_LIMIT(9), 실제 Runtime은 `300.12800002098083`초다. 실제 측정값을 300으로 잘라 쓰지 않았다. 두 번째 시험도 원래 동일한 설정으로 순서대로 실행하며 개별 RESULT와 CSV에 실제 Runtime을 보존한다.

Gurobi의 [공식 TimeLimit 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#timelimit)는 제한에 도달한 직후 반드시 멈추는 것은 아니며, 종료된 최적화의 속성 계산 때문에 Runtime이 설정값보다 커질 수 있다고 설명한다. 이 일반 동작과 이번 작은 종료 초과는 부합한다. 실제 종료 내부 작업의 세부 종류는 로그만으로 단정하지 않는다.

`VERIFICATION.json`에는 설정 제한, 실제 Runtime, 초과 초수와 `strict_runtime_within_300_seconds`를 별도로 남긴다. 검사기의 1초 종료 보고 여유는 configured TimeLimit이나 물리 tolerance 변경이 아니다. 추가 실행, 설정 재탐색, 결과 재시도는 하지 않는다.

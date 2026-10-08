# 사용자 추가 지시: z=0 단일 연장 실험

사용자는 첫 480초 양방향 실행 후 "z=0 더 계속 돌려봐 그대로 끝내지 말고. 결과를 보고 싶어."라고 지시했다. 종료·dispose된 Env/Model의 tree/checkpoint를 재개했다고 주장하지 않는다. 같은 C01 charge_mode[MESS02,77]=0, 원본 C3A+B2 651행/min rho_max, 나머지 binary LP relaxation 및 모든 native scientific 설정을 재사용해 새 독립 spawn Worker 한 개에서 fresh optimize를 정확히 한 번 실행한다.

변경은 TimeLimit=480→1800뿐이다. Threads=1, Method=2, Crossover=0, 원본 tolerance 등은 그대로다. 원래 Worker source는 freeze된 상태로 보존하고 continuation_worker는 그 source에서 TimeLimit 설정/receipt 두 부분만 바꾼 복사본이다. Native API에서 실제 설정과 행·objective·bounds·axis를 다시 읽어 검사한다.

기존 소비 879.545000076초 / calls2를 보존한다. 남은 총 예산 2000.454999924초, 이번 limit1800초로 총 예상 최대2679.545초이며 전체2880초/calls6 상한을 늘리지 않는다. 자동 반복·다른 후보·z=1 추가 solve는 없다. z=1의 원시 결과와 독립 proof를 같은 scientific child domain의 sibling으로 재사용한다.

새 0 Child가 Native OPTIMAL 및 독립 exact certificate PASS이면 기존 1 Child와 min을 다시 계산한다. 미완료 또는 미인증이면 pair를 인정하지 않고 Global LB를 보존한다. UB=0.6284141956452488을 유지한다. M1_ACCEPTED=false, production/P2/downstream=0을 유지한다. 두 파일 경로와 SHA를 별도로 저장해 initial480 결과를 지우거나 덮어쓰지 않는다.

다른 May12/A-stage/M-stage 작업은 중지·수정하지 않는다. CPU 여유를 읽기 전용으로 확인하고 CPU/RSS/page fault/I/O를 관측한다. MemLimit/SoftMemLimit 및 RAM 기반 자동 종료는 없다. 최초 두 LP의 실제 병렬 결과는 그대로 보존한다. 이 연장 호출은 한 Worker이며 병렬 speedup 실험으로 표현하지 않는다.

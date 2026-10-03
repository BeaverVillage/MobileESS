PR134 M1은 root relaxation/crossover 이후 DegenMoves에서 시간을 쓰며 600초까지 nonroot/branch와 incumbent가 없었다. 동일 reduced MPS와 새 A1 freeze를 읽기 전용으로 재사용하고 scientific matrix/objective/bounds/vtypes/RHS 및 source/A1/NormalAmps SHA를 검증했다. 모든 solver 설정을 유지해 DegenMoves=0만 적용하는 단일 P1 실행과 새 zero-action Start 검증을 추가한다.

Zero-action Start valid=False, used=False. 전압 upper 행 3개가 1e-8을 넘었고 최대 위반은 3.07292584711405e-8이다. Fail한 후보는 보존하고 SOC/PQ/route를 수리하지 않았다. P1 status=TIME_LIMIT, runtime=1800.2779998779297 s, UB=None, LB=0.5687116103498322, gap=None, P1_ACCEPTED=False; ROOT_PATH_FIX=FAILED, first nonroot=None s. P2 acceptance=False; M1_ACCEPTED=False. 두 MIPSOL 모두 독립 물리 검증은 통과했지만 원본 변수 bound 위반 약 1.423e-8이 strict 1e-8을 넘어 rejected이며 scientific UB에서 제외했다. Old UB/LB/gap은 비교 artifact에만 보존한다.

Callback은 literal phase/30초 trace/solution 점을 memory buffer에 기록하고 종료 후 artifact를 쓴다. Native callback time PR134 66.91 s → 108.67 s; body wall/CPU와 호출 수는 별도 기록한다. 노출되지 않는 DegenMoves/root-completion/branch 시각과 정확한 600초 상태는 NULL로 보존하며 마지막 관측값을 구분한다. Paired wall-time만으로 causal speedup을 주장하지 않는다.

1 worker / Threads=1, ENV pools=1. Heavy 종료 후 semantic 46 PASS, full 1544 PASS; compile/diff/model/certificate/source 및 PR134 4859개 파일 byte 보존 감사. A1 재실행/새 LP solve/restart/parameter sweep/추가 formulation/Actual/Fresh AC는 0회. 다음 병목은 post-crossover/root processing 하나만 기록한다.

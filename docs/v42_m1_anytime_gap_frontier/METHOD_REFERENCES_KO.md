# 인증과 계측의 근거

Restricted Master의 값은 전체 원본 column에 대한 pricing 검사가 없으면 minimization Global LB로 사용할 수 없다. 본 연구는 원본 다중 grid 행의 signed rational dual과 4개 full96 local-domain dual을 원본 CSR에 결합하고, finite-box residual을 exact Fraction으로 보정한다. 차량별 LP 영역이 원본 정수 trajectory를 포함한다는 분해 검사와 모든 원본 coefficient/row/axis의 identity를 별도로 확인한다. Column generation과 Lagrangian bound의 관계 및 dual 안정화의 근거는 [Desrosiers & Lübbecke, A Primer in Column Generation (2005)](https://www.or.rwth-aachen.de/files/research/publications/primer.pdf)에 있다. 이 문헌이 본 사례에서 3% 또는 5%의 성능을 보장한다고 해석하지 않는다.

`OPTIMAL`은 Solver tolerance 아래의 상태이고 hard rational integer-pricing closure의 대체물이 아니다. Runtime은 실제 Solver 시간, Work는 같은 하드웨어와 설정 아래의 계산 작업량이므로 Wall과 각각 기록한다. [Gurobi 모델 attribute 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html)를 기준으로 실제 Runtime/Work callback sample과 완료 attribute를 사용한다. 제한 UB neighborhood 또는 RMP의 ObjBound를 원본 Global LB에 승격하지 않는다. 진행 중 ledger의 sample age를 남기고 실제 완료값은 정산 때 대체하며 소비 비용을 삭제하지 않는다.

Independent checker는 certificate 완료 뒤 공개된 실제 시각만 first passage로 인정한다. 전체 binary는 literal 0/1, full original matrix/Route/SOC/PQ/PCS/grid replay는 원래 tolerance를 사용한다. 원본 C3A/FULL와 May01 AIDC anchor의 hash가 동일해야 하며 다른 입력으로 성능을 전용하지 않는다.

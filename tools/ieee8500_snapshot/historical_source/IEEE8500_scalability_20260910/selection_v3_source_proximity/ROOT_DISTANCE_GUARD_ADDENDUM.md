# Source-proximity guard: v2 procedure with one added exclusion

selection_v2 및 기존 evidence는 immutable하게 보존한다. 변경은 원래 638개 pool의 root electrical distance 5th percentile 미만 후보를 제거하는 guard 하나다. 원본 topology, eligibility 및 source/substation/regulator/secondary/single/two-phase 제외 규칙과 기존 그룹 ID는 유지한다. AIDC 수는 정확히 12개다.

## 선정 전 동결 rule

638개 primary_upstream_impedance_ohm에 NumPy quantile(q=0.05, method='linear')를 적용한다. 0-based 보간 위치는 (638-1)*0.05=31.85이다. root_distance < q05만 제외하고 equality는 유지한다. Bus ID, v2 선정 여부, 운영 성능은 cutoff 계산에 쓰지 않는다.

q05 = **1.3819547376654384 ohm**. 32개를 제외하고 **606개**가 남는다. 이는 outcome-blind topology guard이며 electrical benefit을 측정하거나 입증한 결과가 아니다. 분포, 638개 keep/exclude 판정, 제외 32개 및 남은 606개 목록을 저장한다.

## 변경하지 않는 기준과 절차

- E_coord <=0.20, E_pair <=0.20, nearest-neighbor retention >=0.50.
- 모든 66 pair electrical distance >=0.9129072401559803 ohm 및 geographic distance >=2221.532547954318 원본 좌표 단위. 새 pool에서 pair threshold를 다시 계산하지 않는다.
- Melbourne proper-rotation geometry, nearest-neighbor 정의, 기존 major-lateral/group ID를 유지한다.
- Maximum shared ratio, mean shared ratio, negative minimum electrical distance, major-lateral/group diversity, geographic dispersion, E_coord/E_pair/retention, lexical bus tuple의 v2 ordering을 유지한다.
- Objective normalization도 원래 638개 pool의 electrical/geographic maximum을 유지한다.
- 72 rotations * 7 scales * 25 centers, Hungarian assignment, 32 feasible/64 infeasible starts, repair 12 sweeps, 상위 16 feasible searches *20 sweeps, 66 swaps, seed=0/no random draws, single-thread 및 1e-9 objective rounding을 유지한다.

Geometric seed의 bounding box/RMS radius는 v2의 같은 공식에 수정된 606개 pool을 넣는다. Hungarian 및 1-site 교체의 대상 크기만 638에서 606으로 바뀐다. v2 mapping을 seed로 쓰지 않으며 재선정 후 비교에만 사용한다.

v2 selector의 복사본에 초기화 종료 직전 pool slicing과 교체 loop의 len(ids)만 추가한다. 평가 함수, 정렬, search control flow는 유지하며 code diff를 저장한다. 이 문서와 입력/code를 실행 전에 PROCEDURE_FREEZE_MANIFEST.json으로 고정한다.

## 검증 및 경계

별도 검증기는 frozen corridors에서 638개 root distance/quantile과 선택된 12개 경로를 재계산한다. 모든 새로운 guard 및 v2 hard criteria를 검사하고 같은 deterministic procedure를 2회 실행해 mapping/decision logs를 비교한다. 통과 시 TOPOLOGY_ONLY_DETERMINISTIC_FEASIBLE_SELECTION이며 전역 최적성을 주장하지 않는다. 실패 시 기준을 완화하지 않는다.

허용 데이터는 frozen static features/pair matrices/Melbourne anchors/primary corridors/bus eligibility 및 v2 topology-selection evidence이다. V41R4, May/B0-B3, voltage/loading/sensitivity/performance 결과는 읽지 않는다. OpenDSS compile, AIDC load/PCC 추가 및 B0-B3 실행을 하지 않는다. 모든 새 파일은 selection_v3_source_proximity 아래에만 쓴다.

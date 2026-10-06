# 현재 4-MESS V42 M1 exact 행 중복 감사 결과

최종 상태: **EXACT_REDUNDANCY_PROVEN_BUT_NO_SPEEDUP**. 증명된 감소는 190,280행 / 2,860,885 nnz이며, 원본과 축소 monolith의 단 한 번 순차 비교를 완료했다. **EXACT_REDUNDANCY_REDUCTION_SELECTED=false**.

기준은 PR159의 정확한 커밋 `07c9ae892335b34a32faf82cff6266ab5cf80aac`이다. 별도 child branch/worktree에서 작업했고 원래 4대, 모든 열·목적함수·물리 한계·수치 권한을 유지했다. 원본 데이터 해시와 PR159 scientific signature를 일치시켰다.

## 삭제량과 범주

| 증명 범주 | 고유 삭제 행 | 삭제 nnz | 전체 행 비율 |
|---|---:|---:|---:|
| EXACT_DUPLICATE | 49,709 | 0 | 5.6104% |
| EXACT_DOMINATED | 0 | 0 | 0.0000% |
| PROVABLY_CONSTANT_SAFE | 15,738 | 1,160 | 1.7763% |
| ROUTE_REACHABILITY_CERTIFIED | 2,643 | 26,116 | 0.2983% |
| SOC_PQ_ENVELOPE_CERTIFIED | 0 | 0 | 0.0000% |
| GRID_SENSITIVITY_CERTIFIED | 122,190 | 2,833,609 | 13.7909% |
| OTHER_EXACT_STRUCTURAL | 0 | 0 | 0.0000% |

총 **190,280행(21.4759%)**, **2,860,885 nnz(33.8652%)**를 고유 삭제했다. 축소 모델은 **695,737행 / 5,586,970 nnz**이고 316,743열은 그대로다. 중복과 절대 비활성 후보의 사전 겹침은 49,436행이며 최종 합계에는 한 번만 포함했다. 범주별 nnz·family 비율·전체 비율은 M1_FINAL_REDUCTION_CENSUS.json에 있다.

| 보안 family | 원본 행 | 삭제 행 | 남은 행 | family 삭제율 |
|---|---:|---:|---:|---:|
| line_thermal_face | 402,433 | 60,101 | 342,332 | 14.9344% |
| transformer_kVA | 110,592 | 74,802 | 35,790 | 67.6378% |
| voltage_lower | 36,960 | 27,357 | 9,603 | 74.0179% |
| voltage_upper | 36,960 | 16,227 | 20,733 | 43.9042% |
| NormalAmps | 11,520 | 11,520 | 0 | 100.0000% |

## 요청한 26개 질문에 대한 답

1. 원본은 886,017행, 316,743열, 이진 208,312개, 연속 108,431개, nnz 8,447,855개다. 보안 행은 598,465개다.
2. 정확한 중복은 49,709행이다. transformer_kVA 49,436행과 flow 273행이며 모두 빈 LHS를 갖는다. 따라서 이 범주의 삭제 nnz는 0이다.
3. 추가 exact dominated 행은 0개다. 전체 모델에서 정확한 dyadic 비례 벡터/유리수 RHS로 검사했다.
4. 고유 zero-support constant-safe 삭제는 15,738행이다. 중복 범주와 겹친 zero-support 후보는 별도로 집계하여 이 숫자에 중복 가산하지 않았다.
5. 전체 사이트 허용 상계는 실패하지만 원본 경로 도달성 상계가 통과한 추가 삭제는 2,643행이다.
6. SOC/PQ envelope 범주의 별도 추가 삭제는 0개다. SOC 상계는 계산·검증했지만 연속 위치 혼합에 aggregate SOC 한계를 사이트별로 배분하지 않았다. PCS16 support는 grid-sensitivity 증명에 포함했다.
7. grid-sensitivity 범주의 고유 삭제는 122,190행이다.
8. 고유 총 삭제 행은 190,280개다.
9. 고유 총 삭제 nnz는 2,860,885개다.
10. 행 감소율은 21.4759%, nnz 감소율은 33.8652%다.
11. 행 수 기준 최대 기여는 transformer_kVA 74,802행이다. nnz 기준 최대 기여는 voltage_lower 1,313,136개다.
12. line_thermal_face는 342,332행이 남는다. 과거 사분면이나 운전점으로 face를 제외하지 않았다.
13. transformer_kVA는 35,790행이 남는다. NormalAmps는 별도로 전부 11,520행이 독립 상계 증명을 통과했다.
14. voltage_lower 9,603행, voltage_upper 20,733행, 합계 30,336행이 남는다.
15. 등식은 273개의 빈 flow 0=0 exact duplicate만 제거했다. 모든 비어 있지 않은 경로/SOC/affine 등식은 유지했으며 한쪽 부등식 screening으로 등식을 제거하지 않았다.
16. 190,280개의 삭제 행을 모두 별도 verifier가 독립 재검증했다. production 삭제 결정 함수는 재사용하지 않았다.
17. 삭제 의존성은 최종 retained representative 또는 독립 절대 비활성 certificate로 닫혔다. cycle은 없고 모든 도메인 증명 anchor를 유지했다.
18. 기존 12개 physical fixture의 1,536개 bounded binary assignments가 모두 동등했다. 실현 가능 49개, 불가능 1,487개이며 목적값과 최적 이진 패턴 집합이 일치했다. 두 모델의 각 반환 해가 원본 P/Q/SOC/grid 행을 모두 만족했다. 퇴화 연속 최적해의 좌표 자체는 같을 필요가 없다.
19. 12개 추가 적대적 검증이 통과했다. 양방향 전압, 선로 face, 역 P/Q, transformer face, fractional site convex hull, unreachable 고감도 사이트, transit·terminal location, terminal SOC/travel trajectory, 정확 중복·근접 비비례, equality 일방 삭제 금지, 무한 bound를 검사했다. 독립 replay는 hash/RHS/upper/self-cycle 변조 4종을 모두 거부했다.
20. 사전 materiality 기준(행 20% 또는 nnz 15%)은 둘 다 통과했다. 이는 실행 가치 기준이며 수학적 타당성 기준과 분리된다.
21. 처음에는 다른 fleet optimizer가 실행 중이어서 static/no-solve 감사만 진행했다. 사용자가 해당 실행을 중단했다고 알리고 계속 실행하라고 지시한 뒤, 각 build/optimize 직전 native process 검사에서 외부 optimizer가 없음을 확인했다. 두 arm을 순차 실행했고 동시 heavy solve는 없었다.
22. 원본 root 완료=False, root 시간=None; 축소 root 완료=False, root 시간=None. Native runtime은 270.750s → 271.217s, Work는 580.910000 → 421.678150. 각 TimeLimit=270s / arm wall cap=300s이며 추가 비교는 하지 않았다.
23. 유효 UB는 0.6694159238756877 → 0.6694159238756877, global LB는 0.5687115725336208 → 0.5687115725336208, global gap은 15.04361455% → 15.04361455%다. Verbatim native BestBd는 0.2529539575959 → 0.25295395759592587로 별도 기록했다. 동일한 기존 full-domain valid LB와 원본 검증 시작점을 양쪽에 사용했다.
24. 표본 peak RSS는 3.300GiB → 2.729GiB, process commit은 4.919GiB → 4.349GiB, 최소 available RAM은 15.642GiB → 15.064GiB다. 0.5s 표본 peak이며 절대 peak를 주장하지 않는다.
25. EXACT_REDUNDANCY_REDUCTION_SELECTED=false. Root 시간 gate=False, valid LB/gap gate=False, beyond-root transition gate=False. 메모리 감소나 미완료 root의 서로 다른 Work 양만으로 선택하지 않았다.
26. 과학적 기준 exact commit은 위 PR159 head다. 이 감사의 evidence commit 및 새 Draft PR은 발행 후 PUBLICATION.md와 최종 응답에 기록한다. PR159는 수정하지 않았다.

## 증명의 범위와 재현

Route 도메인은 정수 경로의 합뿐 아니라 단위 DAG flow의 연속 convex combination을 포함한다. 따라서 한 시각의 사이트별 PCS support를 단순 합산하지 않고, 각 MESS의 도달 가능한 사이트 union support의 최댓값으로 상계를 구성한다. 실제 terminal_location 식은 특정 사이트 고정이 아니라 허용된 모든 horizon sink의 합=1이다. 원래 terminal 가능성을 그대로 보존했다. SOC endpoint/energy 계수는 원래 sparse 행과 정확히 대조했다.

12개의 tiny fixture 비교는 exact duplicate/finite-bound 삭제의 native 구현 검증이다. 전체 규모의 route/PCS/affine support 삭제는 별도의 적대적 analytic 검증과 모든 삭제 행의 독립 interval replay로 검증했다. Tiny fixture 결과를 전체 도메인의 증명으로 대체하지 않았다. 상세 수식·산술·closure는 M1_CANONICAL_ROW_SPEC.md, 행별 원본 계수는 M1_CANONICAL_ROWS.npz, 행별 증명은 M1_REMOVED_ROW_CERTIFICATES.csv에 있다.

재현 명령: `python -X utf8 audit_m1_redundancy.py`, `python -X utf8 verify_redundancy_fixtures.py`, `python -X utf8 -m v42_redundancy.replay`. 모두 이 작업 공간의 출력 경로만 사용한다. Immutable 외부 scientific 입력은 기존 source 해시로 검증하며 쓰지 않는다. 캐시는 REDUNDANCY_LOCAL만 사용한다. 증명된 row subset은 M1_EXACT_REDUCED_A.npz / M1_REDUCTION_AXES.npz로 구성했고, native constructor는 v42_redundancy/model.py에 있다. 전 열·이름·bounds·types·목적값의 native transport는 12개 fixture에서 확인했다. Full-scale original/reduced native model transport를 각각 확인한 후 각 arm에서 한 번씩만 optimize를 호출했다. 총 208개의 solver parameter를 캡처했고 LogFile을 제외한 207개 값이 일치했다.

## 필수 진술

이번 작업은 현재 4-MESS V42 M1의 scientific feasible set을 변경하지 않고, 원래 제약에 의해 수학적으로 중복 또는 영구 비활성임이 증명된 row만 제거하는 exact formulation reduction이다.

과거 운전점에서 위반되지 않았다는 사실이나 작은 sensitivity만으로는 제약을 제거하지 않았으며, 증명되지 않은 row는 모두 유지했다.

Route reachability, SOC/PQ envelope 및 grid sensitivity는 원래 feasible set을 포함하는 보수적 outer domain을 구성하는 데만 사용했으며, 그 outer domain에서조차 위반될 수 없는 제약만 영구 제거했다.

병렬로 수행 중인 MESS fleet-size 실험과 source/worktree/runtime을 분리했으며, 다른 heavy optimizer가 실행 중일 경우 본 작업의 heavy benchmark는 수행하지 않았다.


## 결과 저장 오류의 복구 범위

원본 arm은 정상적으로 time limit에 도달하고 raw/final 해 저장과 원본 검증을 끝냈다. 그 뒤 JSON metadata 직렬화가 무한대 기본 parameter 값에서 실패했다. 원본 optimize를 재실행하지 않았다. 원본 native runtime·Work·BestBd는 남은 native 로그의 인쇄 정밀도로 복구했고, 정확한 build wall 및 첫 native/독립 incumbent wall은 복구 불가로 null을 기록했다. 동일 시작점의 독립 검증 완료 시각은 양쪽에서 0으로 정의했으며, 이 값과 native incumbent wall을 혼동하지 않았다.

축소 arm에는 동일 solve/callback/model/settings/budget AST를 유지하고 parameter 기록 함수만 무한대를 문자열로 인코딩하도록 수정했다. 원본 실행 소스는 EXECUTED_SOURCE에 원래 바이트 그대로 보관했고 AST 비교가 통과했다. 원본 parameter payload는 같은 설치 Gurobi 기본값과 정확한 원본 POLICY에서 optimize 없이 복원했다. 각 arm의 full-domain 해·열·row transport는 검증했다. 원본의 종료 로그와 비교 조건을 바꾸지 않았으며, 불완전한 기록 정밀도는 BASELINE_RESULT.json recovery에 명시했다.

원본의 total_arm_wall은 자원 telemetry로 얻은 보수적 upper bound다. 두 resource ledger의 wall 값은 active-monitor elapsed를 이어 붙인 값이며 중간 저장 오류 복구 시간을 포함한 연속 wall이 아니다. UTC가 실제 경과 시각을 보존한다. 각 arm 300초 예산과 native 270초 제한을 확인했고 총 optimize 호출은 원본 1회, 축소 1회다. 미완료 root의 Work 감소만으로 선택하지 않았다.
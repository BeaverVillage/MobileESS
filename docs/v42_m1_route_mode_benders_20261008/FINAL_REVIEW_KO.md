# M1 Integer-First Exact Decomposition 최종 검토

판정: **INTEGER_FIRST_CUT_CERTIFICATION_FAIL**. 원본 동치와 feasible recourse는 통과했으나, 첫 새 master 배정에서 인증된 separating cut을 얻지 못했다. production-promising=False이며 0.5% exact convergence는 달성하지 못했다.

| 항목 | 결과 |
|---|---:|
| 원본 objective / ObjCon / axis bit identity | PASS |
| 전체 integer projection / recourse / epigraph 증명 | PASS |
| 20개 원본 배정 feasible full replay | 20 PASS / 0 infeasible / 0 unknown |
| recourse Runtime median / p90 / max | 2.002000 / 2.230800 / 2.308000 s |
| 초기 native cut 인증 | 19 accepted / 1 rejected |
| 명시적 optimize=0 multiplier 교정 후 valid optimality cuts | 20 |
| full-scale valid feasibility cuts | 0 |
| initial / final LB | 0.5687116104049206 / 0.5687116104049206 |
| initial / final UB | 0.6306505800203936 / 0.6284141956452488 |
| valid UB improvement | 0.0022363843751448 |
| global gap | 9.500515051% |
| full-scale native Runtime / Work | 158.475000 s / 234.057248 |
| full-scale controller wall 합계 | 292.752193 s |
| bounded fixture native Runtime / Work, log-rounded | 0.10 s / 0.04 |
| 전체 optimize 횟수 | 92 (과학적 full scale 22; 작은 fixture 및 실패 교정 70) |
| peak RSS | 2206081024 bytes (2.055 GiB) |
| 0.5% 달성 / production 준비 / 자동 continuation | False / False / 없음 |

총 native 합계는 full-scale API 158.475초에 작은 fixture의 0.01초 정밀도 로그 합계 0.10초를 더한 값이다. controller wall 합계는 벤치마크와 canary만 포함하며 Git, 정적 감사, 문서 작성 및 작은 fixture wall과 구분한다. 전체 작업공간 생성부터 PR 게시까지의 경과시간은 외부 GIT_COMPLETION에 남긴다. 시간과 알고리즘 조건이 다른 PR179/182에 대해 인과적 speedup을 주장하지 않는다.

## 첫 canary의 실제 종료

등록 상한 900초에서 master 1회와 새 recourse 1회만 실행했다. master는 OPTIMAL, Runtime 2.218999863초, Work 2.831414536, 1 node, root barrier 1.17초 / crossover 0.02초였다. complete integer candidate의 binary와 implied route-flow 오차는 모두 0이다. BestBd는 inherited LB와 같다.

첫 새 recourse는 simplex Method=1, 원본 min rho로 120.000999928초 / Work 194.927626185 / 133287 iterations 뒤 TIME_LIMIT이다. 원본 전체 행렬에서 큰 primal infeasibility가 남았다. terminal infeasibility proof나 replay-PASS point를 얻지 못했고, 이 결과를 INFEASIBLE이라고 바꾸거나 restricted bound를 global LB로 사용하지 않았다. cut-validity gate에서 campaign을 중단했으므로 900초를 억지로 소비하지 않았다. 새 feasibility cut, 두 번째 candidate, 재실행, 1800초 continuation은 없다.

## Cut 강도와 수치 검증

20개 optimality cuts는 각 feasible source에서 거의 tight하지만 첫 master candidate에서 최대 delivered value가 0.5506661698094345로 floor 0.5687116104049206보다 작다. 따라서 모두 valid해도 이 배정의 theta를 올리지 못한다. 첫 새 배정을 제외할 인증된 feasibility cut이 나오지 않아 LB 진전이 없다. 시간을 늘리지 않고 이 원인을 `CUT_STRENGTH_DIAGNOSIS.json`에 보존했다.

raw multiplier wrong sign 3.671267600429335e-10인 한 certificate를 reject했다. native source 파일은 그대로 보존하고, admissible sign cone의 별도 multiplier에서 exact matrix products / finite-bound support / floating transport envelope 전체를 다시 계산하여 새 valid cut을 얻었다. 묵시적 coefficient clamp나 불완전한 ray 채택은 없다. PCS/grid/injection stationarity 잔차를 0이라고 가정하지 않는다. 원본 bounds는 모두 finite다. 큰 coefficient-range warning은 원본 matrix에서 발생하며 original coefficient나 rho objective는 변경하지 않았다.

작은 bounded **algebraic validation fixture** 두 개는 독립 direct monolithic MILP와 1e-8 이내 일치했다. 1 MESS/2 slots/2 sites는 objective 0.6, 2 MESS/3 slots/2 sites는 0.5565866383266509다. fixture에서 optimality 11개와 feasibility 7개를 통과시켰다. fixture는 과학적 synthetic physical input이나 원본 network 대체 데이터가 아니다. 처음 barrier INFEASIBLE에서 Farkas attribute가 없었던 실패와 이후 native sign rejection도 보존했다. 일반 full C3A 동치 증명은 별도 문서에 있다.

## 유효 UB의 출처

UB 개선은 첫 20개 recourse의 배정 018에서 나왔다. 원본 node activity와 route path는 기존 center와 같고 charge_mode 1개만 다르다. 바뀐 binary는 ['charge_mode[MESS01,0]']다. 원본 continuous dispatch를 optimize했고 route/movement/SOC/PQ/PCS/grid/A1의 full replay를 통과했다. best vector와 native dual/RC/slack는 검증 전에 저장했다. 14개의 서로 다른 integer route pattern과 20개 distinct binary pattern을 표본으로 검사했지만 이를 global search domain으로 제한하지 않았다.

## 경로와 보존 감사

새 checkout 및 Git common directory는 `D:\v42_m1_route_mode_benders_20261008\repo` / `.git`이다. artifacts, logs, tmp, cache, checkpoints, reports는 모두 같은 D: root 아래다. 모든 heavy solve 전에 TEMP/TMP/TMPDIR/PIP_CACHE_DIR/PYTHONPYCACHEPREFIX 및 solver LogFile/NodefileDir를 확인했다. 설치 Python/Gurobi executable만 C: 예외다. 원본 C3A / A1 / 과거 PR evidence / concurrent A-stage를 수정하거나 중단하지 않았다. zero scientific objective와 downstream 실행은 0회다.

**경로 규약 누락을 명시한다:** 초기 historical graph reader가 동결 traffic raw input을 C:에서 읽었다. 뒤에 D: 복사와 source-before / source-after / copy SHA256 일치를 검증하고, 이후 reader를 D:로 재지정했다. 초기부터 모든 scientific read가 D:였다고 주장하지 않는다. 새 실험파일과 C: scientific 쓰기는 없다. `RAW_INPUT_RELOCATION.json` 및 D audit에 이 편차를 보존했다.

## 다음 행동 정확히 하나

저장된 첫 master 배정 한 개에 대해, 원본 continuous route_flow를 상단 master의 좌표 f로 명시하고 z와 f를 함께 고정하는 original min-rho recourse 및 (z,f) affine cut의 exact support 인증을 120초 단일 파일럿으로 비교한다. 원본 정수 projection 증명과 finite-bound weak duality를 유지하며 새로운 과학적 물리식이나 route 제한은 추가하지 않는다.

이번에는 실행하지 않았다. native solve를 모두 종료했고 이 단일 canary 뒤 멈췄다. final HEAD / Draft PR / remote HEAD match / clean tree는 게시 뒤 `D:\v42_m1_route_mode_benders_20261008\reports\GIT_COMPLETION.json`에 기록하며 최종 답변에도 제공한다.

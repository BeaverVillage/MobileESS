# V40L strong-support H100-standby provenance

원인 분류: **TEMPORAL_COVARIATE_SHIFT**. 기존 **V40L_TAIL_MODEL_INSUFFICIENT / winner NONE / shadow SEALED**를 유지한다.

세 기간의 저장된 causal columns와 동일한 Apr01 동결 support lookup을 조인했다. fit/predict/Support.transform/retuning을 실행하지 않았고 runtime/status/outcome columns를 읽지 않았다.

| Period | Total H100-standby | Strong | Sparse | Regime mismatch | Out of support | Exact P5 | P50 | P95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Apr-01--07 | 2,291 | 1,772 | 48 | 114 | 357 | 0 | 3,237 | 50,939 | 50,939 |
| Apr-08--14 | 383 | 130 | 8 | 173 | 72 | 0 | 0 | 50,939 | 50,939 |
| Apr-15--23 | 1,317 | 4 | 35 | 1,153 | 125 | 0 | 0 | 0 | 50,939 |

Strong 비중은 **77.346% → 33.943% → 0.304%**다. Selection 전체 H100-standby가 4개였던 것이 아니라, 1,317개 중 exact_count>=100인 집합이 4개였다.

| Requested walltime | Apr01–07 N | Apr08–14 N | Apr15–23 N |
|---|---:|---:|---:|
| 0.5h | 2 | 0 | 0 |
| 2h | 10 | 0 | 0 |
| 3h | 103 | 0 | 0 |
| 4h | 0 | 20 | 0 |
| 6h | 11 | 225 | 72 |
| 9h | 2 | 1 | 1 |
| 12h | 26 | 7 | 1223 |
| 16.5h | 0 | 0 | 1 |
| 24h | 573 | 78 | 6 |
| 36h | 605 | 13 | 0 |
| 48h | 959 | 39 | 14 |

핵심은 **과거 48h profile에 현재 12h 요청이 들어온 것**이다. Selection의 1,223/1,317개(92.863%)가 12h다. 그중 1,153개는 아래 두 profile이며, walltime 이외 8개 key는 과거에 충분히 존재한다.

| Near-key profile SHA prefix | Selection 12h N | Historical walltime | Historical count | Current exact count |
|---|---:|---|---:|---:|
| 6d6e21d6e54d | 808 | 48h only | 3237 | 0 |
| 0186187da5c2 | 345 | 48h only | 1501 | 0 |

동결된 exact key는 requested_seconds, nodes, cores, GPUs, memory, partition, QoS, user, account의 9개다. Near key는 이 중 requested_seconds만 제외한다. 따라서 이 1,153개는 STRONG이 아니라 사전등록한 REGIME_MISMATCH로 분류된다. 12h 특별 규칙이나 threshold 변경을 추가하지 않았다.

나머지는 sparse 35개, OOD 125개, strong 4개다. Strong 4개의 job identity, submit time, walltime, exact/near counts는 JSON에 기록했다.

Hardware는 partition에 h100 포함(대소문자 무시), standby는 QoS.lower()==standby다. 세 기간의 해당 집단은 모두 partition=gpu-h100-stdby / QoS=standby였다. 모든 key는 동일한 numeric float/string/missing-value 정규화를 사용했고 독립 canonical-key 구성의 불일치는 0개다. 동일 source/lookup SHA를 검증했다.

Support authority는 Apr01에 고정됐고 세 기간 사이에 April jobs를 추가하지 않았다. Strict exact matching이 이 변화를 support 부족으로 드러내지만, 이번 진단은 규칙이 너무 엄격한지에 대한 대체 실험을 수행하지 않았다. Implementation inconsistency나 전체 H100-standby population scarcity가 주원인이라는 근거는 없다.

분류는 관측된 허용 cohort에 한정한다. Whole-row-group/시각 firewall 때문에 calibration에는 Apr08이, selection에는 Apr21–23이 포함되지 않는다. 제외된 job이나 전체 raw calendar population까지 같은 shift로 일반화하지 않는다.

V40L support threshold/gate/classification은 변경하지 않았다. 추가 fit/prediction/retuning은 0회이며 shadow는 계속 SEALED다.

# V42 workload eligibility 최종 검토

**R1/R2를 새 main workload rule로 승격할 근거가 없다. 기존 R0를 유지한다.** R1은 추가 작업/GPUh가 없고, R2는 더 좁은 지연 예산 때문에 standby 43 job-days, 56.5 GPUh를 제외한다. 이는 registered 규칙에서 얻은 결과이며 20/30/40%에 맞추는 재조정은 하지 않았다.

## 1. 기존 rule은 얼마나 보수적인가?

단순 standby gate와 실제 이동 가능성은 같지 않다. 아래는 동일한 May reference와 raw power authority에서 다시 계산한 값이다.

| R0 definition | Job-days | Day GPUh | GPUh % | Incremental PCC % |
|---|---:|---:|---:|---:|
| stored standby eligibility gate | 18,588 | 143,867.50 | 28.760644 | 20.796256 |
| exact restored production temporal domain | 4,767 | 52,192.75 | 10.433886 | 7.544538 |
| registered standalone capacity-witness screen | 1,611 | 17,273.50 | 3.453156 | 2.496910 |

보수성의 원인은 QoS 하나만이 아니다. R1의 latency-tolerant normal은 702 job-days이고 그중 당일 시작 대상은 456건이다. 456건 모두 safe-duration reference가 D24를 넘기므로 terminal 잔여 service 증가 금지에 의해 시작 상한이 reference start와 같아진다. 즉 이 frozen reference에서는 standby hard gate만 제거해도 추가 temporal 후보가 없다. 모든 normal workload가 본질적으로 유연하지 않다는 결론은 아니다.

## 2–3. Baseline 및 R1/R2 flexible GPUh는?

| Rule | Flexible job-days | Jobs % | Flexible GPUh | GPUh % | Incremental PCC kWh | PCC % | Added job-days / GPUh |
|---|---:|---:|---:|---:|---:|---:|---:|
| R0 | 1,611 | 3.427003 | 17,273.50 | 3.453156 | 9,461.109778 | 2.496910 | 0 / 0.00 |
| R1 | 1,611 | 3.427003 | 17,273.50 | 3.453156 | 9,461.109778 | 2.496910 | 0 / 0.00 |
| R2 | 1,568 | 3.335531 | 17,217.00 | 3.441861 | 9,430.163377 | 2.488742 | 0 / 0.00 |

표의 primary는 사전 등록한 **다른 작업을 B0에 고정한 단일 작업 이동의 용량 witness** 기준이다. 이를 기존 production optimizer의 전체 flexibility라고 부르지 않는다. Production geometric domain의 R0/R1 GPUh 비중은 각각 10.433886053% / 10.433886053%, R2는 10.422591102%이다. 원래 gate의 비중은 28.760643992%다. 기존 14.x%를 복사하거나 GPUh와 PCC 분모를 혼용하지 않았다.

분모는 47,009 job-days, 500,223.50 당일 admitted GPUh, 378,912.796624 PCC kWh다. 고유 작업은 raw bridge에서 18,955개다. 전체 safe-duration service 분모 2,707,618.00 GPUh는 당일 GPUh와 구별하며 CSV에 별도 기록한다. fixed/unadmitted/post-day 작업도 membership에서 삭제하지 않았다.

## 4. 20%, 30%, 40% 중 자연스럽게 나타나는 수준은?

새 규칙의 실제 temporal domain과 단일 작업 capacity witness 기준에서는 **셋 모두 도달하지 않는다**. 단순 standby gate는 20%를 넘지만 이동 권한/terminal/용량을 모두 통과했다는 뜻이 아니다. 기존 spatial 권한을 합한 union은 99.992703%로 크지만 그것을 새로운 temporal flexibility로 주장하지 않는다. CSV는 이 정의들을 분리한다.

## 5. 증가분의 QoS/workload cohort는?

증가분은 **0**이다. 모든 temporal witness는 standby / STANDBY_QUEUE_CONTROLLED에서 온다. R2가 제외한 43건도 standby다. QoS, partition, workload class, GPU bucket, reason별 모집단·포함량·추가량은 `INCLUSION_BY_COHORT.csv`, 단계별 탈락은 `ELIGIBILITY_FUNNEL.csv`에 있다. 결과를 보고 cohort나 median/N/slot threshold를 변경하지 않았다.

## 6. Service/QoS/terminal constraints는 보존되는가?

새로 열거한 standalone 옵션에서 safe duration, RW reference completion, 개별 terminal 잔여량, 원래 admission, whole-gang/site/rack 한계를 모두 검사했다. 다른 작업 B0 occupancy를 포함해 용량 위반 옵션을 제거했고, witness가 없는 작업은 이 screen에서 fixed다. protected temporal membership 변화는 0이며 전체 job-day 및 GPUh 질량을 보존했다. 기존 spatial/migration membership은 그대로다. 조합된 여러 이동을 동시에 실행하는 스케줄의 feasibility나 실제 runtime SLA는 검사하지 않았다. 기존 migration의 별도 완료 규칙을 새 universal deadline으로 바꾸지 않았다.

독립 구현은 141,027행, 139,061옵션, source hash 228개를 검증했고 original R0 terminal 함수와 일치한다. 8개 contract test도 통과했다. TRAIN은 2025-01-01 이전 완료 439,534개이며 evaluation realized start/end/queue는 eligibility에 사용하지 않는다. 과거 request/QoS version provenance 미인증 때문에 운영 수준의 no-future-leakage 증명은 아니다.

## 7. Trace-derived인가, 문헌 가정인가?

TRAIN queue 분포·N·GPUh 및 frozen reference별 수치는 trace-derived다. Queue 중앙값을 추가 지연 허용량으로 해석하는 부분과 N=100은 **문헌으로 수치가 인증되지 않은 연구 가정**이다. 15분은 기존 scheduling resolution이다. [Carbon-Aware Computing for Datacenters](https://arxiv.org/abs/2106.11750)는 지연 허용 작업과 daily service 보존이라는 방향을 뒷받침하며, [NLR QoS 문서](https://natlabrockies.github.io/HPC/Documentation/Slurm/batch_jobs/)는 standby idle-node semantics를 뒷받침한다. 어느 쪽도 Kestrel normal 작업의 개별 SLA를 제공하지 않는다.

## 8. V42 main workload rule 근거는 충분한가?

**Latency-aware R1/R2 승격에는 불충분하다. R0 유지 권고다.** 추가 효과가 없고 실제 지연 허용 계약 및 historical request version 인증이 없다. 운영 승격에는 issue-time request version와 사용자/서비스 지연 예산의 authority가 필요하다. 현재 자료만으로 terminal 완화, workload scaling, 미래 realized 정보, threshold 역산을 추가하지 않았다.

전체 기간 제한: `ALL_AVAILABLE`은 frozen V41R4 authority가 존재하는 May 31일 전체다. 원 raw trace 전체 기간의 동일 eligibility 수치는 **NOT_AVAILABLE**이다. 다른 기간을 새로 admission/runtime 계산해서 메우는 것은 이번 금지 범위와 충돌하므로 하지 않았다. 따라서 요청한 전체 raw 기간 비교는 미충족 항목으로 명시한다.

## 최종 flags

`TRUE`는 offline May/standalone-option 검증 범위다. latency tolerance의 운영 인증 또는 jointly executable optimizer solution을 뜻하지 않는다. share는 0–1 단위다.

```json
{
  "BASELINE_REPRODUCED": true,
  "LATENCY_AWARE_RULE_VALID": true,
  "SERVICE_PRESERVATION_PASS": true,
  "FLEXIBLE_GPUH_SHARE_R0": 0.03453156439071735,
  "FLEXIBLE_GPUH_SHARE_R1": 0.03453156439071735,
  "FLEXIBLE_GPUH_SHARE_R2": 0.03441861487914902,
  "V42_WORKLOAD_RULE_RECOMMENDED": "R0",
  "PRODUCTION_CHANGED": false,
  "OPTIMIZER_CHANGED": false,
  "ML_CHANGED": false,
  "FLAG_SCOPE": "offline May reference, registered standalone capacity-witness temporal metric; not global optimizer flexibility or operational certification",
  "FULL_RAW_PERIOD_ELIGIBILITY_AVAILABLE": false,
  "OPERATIONAL_LATENCY_TOLERANCE_CERTIFIED": false,
  "PRODUCTION_DOMAIN_GPUH_SHARE_R0": 0.10433886052934338,
  "PRODUCTION_DOMAIN_GPUH_SHARE_R1": 0.10433886052934338,
  "PRODUCTION_DOMAIN_GPUH_SHARE_R2": 0.10422591101777505,
  "PRODUCTION_GATE_GPUH_SHARE_R0": 0.28760643992135515
}
```

기존 frozen evidence overwrite, production/optimizer/ML 변경, 금지된 pipeline 실행은 없었다.

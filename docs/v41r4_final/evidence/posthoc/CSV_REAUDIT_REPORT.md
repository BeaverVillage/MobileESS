FINAL_REAUDIT_CLASSIFICATION: C

CSV_EXPORT_VALID_BUT_SCIENTIFIC_TERMINAL_BIAS_REQUIRES_PAPER_LIMITATION

1. May31 AC issue: **RESOLVED**.
2. Final campaign: **124/124 accepted**, pending=0.
3. 619 records: **reproduced** (B1=306, B3=313; 60 policy-days; all checkpoint-migrated).
4. 원인: frozen migration semantics가 허용한 실제 D-day 서비스의 post-day 이연. Reference/좌표/namespace 오류가 아니다.
5. Terminal constraint: standalone time-shifted non-migrated PENDING에는 적용. Checkpoint migration에는 적용하지 않음.
6. B1 extra terminal service: **15,897.0 GPUh**.
7. B3 extra terminal service: **16,020.5 GPUh**.
8. P1 상대 개선률과의 Pearson/Spearman: B1 0.3727/0.3798, B3 0.1096/0.0770 (각 N=31).
9. 결과 해석: service-neutral 비교가 아니다. D-day 부하 감소와 migration 위치 변경, MESS 제어가 혼재한다. 주원인이라는 인과 판정은 불가능하다.
10. 논문 limitation: **필요**. 가능하면 별도 service-neutral / bounded-wait ablation을 이후 연구로 제시할 것. 이번에는 실행하지 않았다.
11. CSV 수정: 619개 값 수정/제거 불필요. `00_experiment_authority.csv`의 `method_SHA` 한 셀 메타데이터 누락만 수정한 새 폴더를 생성했다.
12. CSV 최종 status: **projection PASS after metadata correction; scientific terminal limitation retained**. 기존 FAIL_CLOSED 파일은 역사 기록으로 보존한다.

## 판정의 범위

A를 선택하지 않은 이유: 이연량이 작다고 볼 수 없으며, 일부 job은 거의 하루 동안 중단된다. B를 선택하지 않은 이유: 619건은 exporter bug가 아니다. D를 선택하지 않은 이유: 실제 이연은 확인됐지만 B1/B3 P1 개선의 **주요 원인**이라는 causal attribution은 archived 관측 비교만으로 입증되지 않았다. C는 영향을 무시하거나 전체 결과를 폐기하는 판정이 아니다.
619건의 accounting 분류는 `PAPER_EXPORT_ADDITIONAL_INVARIANT_NOT_PART_OF_FROZEN_METHOD`이다. 이것과 실제 horizon 이연에 따른 논문 해석상 limitation은 동시에 성립한다.
이 수치는 frozen safe-duration decision에 대한 **계획/예약 compute service**이다. realized job runtime 또는 실제 측정 GPU 사용시간으로 바꾸어 부르지 않는다. 동일 job_uid가 여러 독립 D-day 평가에 반복될 수 있다. 31일 합계를 연속 실행의 월말 누적 backlog로 해석하지 않는다.

## 독립 계산과 좌표 검증

기존 exporter 함수는 재계산에 import하지 않았다. 최종 FINAL_RESULT_INDEX → ACCEPTANCE.new_joint → SHA가 일치하는 FROZEN_JOINT_DECISION을 사용하고, 같은 날짜 B0 job_uid로 join했다. 188,036개 job-policy-day를 모두 대조했다.
Compute segment를 겹치지 않는 반열린 구간으로 확인한 뒤, pre-day=(-∞,24), in-day=[24,120), post-day=[120,∞)와의 교집합 길이를 독립 적분했다. Issue-origin 120은 day-origin 96이다. CSV timestamp +10:00은 Parquet UTC timestamp와 같은 시각이며 10시간의 좌표 오류가 없다.
619건 모두 총 compute service와 pre-day service가 보존된다. 각 건에서 post-day 증가 GPUh와 D-day 감소 GPUh가 정확히 같다. 중복 segment, missing segment, 잘못된 B0 참조, stale May31 namespace가 원인이 아니다.

## Frozen contract / code evidence

- Archive `frozen_artifacts/v41r4_may/loop_wall_v4/audit/2025-05-01/domain/DAILY_DOMAIN_AUTHORITY.json`의 `sources`가 아래 네 소스의 SHA를 제공한다. PR #42 HEAD의 Git blob과 **byte-identical**임을 확인했다. 모든 결과 수치는 archive에서만 읽었으며 PR은 method semantics에만 사용했다.
- [terminal.py L59–73](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41r1/terminal.py#L59), [L120–130](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41r1/terminal.py#L120): non-migrated PENDING의 start domain과 `PER_JOB_TERMINAL_RESIDUAL_INCREASE` 검사.
- [temporal_restore.py L20–35](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/temporal_restore.py#L20), [L40–58](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41/temporal_restore.py#L40): standalone temporal option만 복원하며 shifted-start + migration 조합은 금지. 기존 terminal.check가 유지된다.
- [migration.py L85–112](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41r1/migration.py#L85), [L115–134](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v41r1/migration.py#L115): 첫 checkpoint, 고정 시작, 한 번의 migration, D-day 내 재시작/유용 서비스 조건. `terminal_residual_constraint_active=False`, `service_neutrality_constraint_active=False`.
- [domain.py L73–88](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v40g/domain.py#L73), [L141–172](https://github.com/BeaverVillage/MobileESS/blob/33a86d31c27051aedbdb93d60b844216533a45a9/dayahead/v40g/domain.py#L141): transfer wait와 1-slot restart만큼 종료가 연장되고 총 segment service는 safe duration과 같다. Active migration의 reference tail은 service ledger이며 cap이 아니다.
- Archive `frozen_artifacts/v41r4_may/loop_wall_v4/2025-05-DD/B1/dayahead/A0/DAY_BOUNDARY_AUDIT.json:1`와 `B3/dayahead/A1/DAY_BOUNDARY_AUDIT.json:1` **62/62**에서 terminal/service-neutrality FALSE, issue_begin=24, issue_end_exclusive=120, grid slots=96, post-H grid variables=0을 확인했다.
따라서 `service_neutrality_constraint_active=False`는 총 서비스가 사라진다는 뜻이 아니다. Full-duration 서비스는 보존되지만 D-day 내부 서비스량의 동등성은 강제하지 않는다는 뜻이다. 중단 동안 source/destination에서 compute가 없고 그 서비스는 종료 시점 이후로 지연된다. 전원효과를 동일 서비스 효율 개선으로 주장하면 안 된다.

## 규모와 분모

| Metric | B1 | B3 |
|---|---:|---:|
| Total extra GPUh | 15,897.000 | 16,020.500 |
| Mean, affected 30 days | 529.900 | 534.017 |
| Median, affected 30 days | 248.125 | 251.750 |
| P90, affected 30 days | 1,589.825 | 1,589.825 |
| Max, affected 30 days | 2,652.000 | 2,652.000 |
| Mean, all 31 days | 512.806 | 516.790 |
| Median / P90, all 31 days | 243.500 / 1,579.250 | 243.500 / 1,579.250 |
| Affected / selected job-policy-days | 306 / 46,092 (0.6639%) | 313 / 46,092 (0.6791%) |
| Affected / migrated job-policy-days | 306 / 333 (91.8919%) | 313 / 344 (90.9884%) |
| Extra / all B0 D-day scheduled GPUh | 3.17798% | 3.20267% |
| Maximum daily extra / B0 scheduled GPUh | 17.4087% | 17.4087% |

두 정책 모두 affected day=30, unaffected day=May19 한 날이다. affected vs unaffected는 30 대 1이므로 통계적 대조군처럼 해석하지 않는다.

## 중단은 단순 1-slot restart가 아니다

| 619개 flagged cohort의 gross interruption component | B1 GPUh | B3 GPUh |
|---|---:|---:|
| Checkpoint → WAN transfer 대기 | 13,435.00 | 13,556.00 |
| WAN transfer | 2,065.25 | 2,061.50 |
| 1-slot restart | 623.25 | 627.50 |

Gross interruption 합은 post-day extra와 같지 않을 수 있다. Reference가 D-day 안에서 끝나는 job은 중단 후 D-day 내부에서 일부 서비스를 회복한다. 이 표는 interruption 분해이며 최종 이연량은 위 15,897 / 16,020.5 GPUh이다.
최장 중단=94 slots (23.5h), 최장 transfer 전 대기=92 slots (23h). 정책별 54건은 48 slots 이상 중단된다. 이는 모두 저장된 event에서 읽은 값이며, 대기가 WAN contention 때문에 불가피했는지 optimizer 선택의 결과인지는 별도 counterfactual 없이 확정하지 않는다.
예: May15 job 8952973 (60 GPU), B1/B3 모두 reference [0,168), optimized [0,24)+[105,249). Checkpoint=24, transfer_start=99, transfer_end=104, restart=105. 총 168 slots는 같지만 D-day 96→15, post-day 48→129로 변해 **1,215 GPUh**가 이연된다.

## 개선과의 관계 (진단용)

Improvement는 B0−policy; percentage는 (B0−policy)/B0×100이다. Spearman은 동률 평균순위를 사용한다. 독립 D-day 31쌍이며 p-value/유의성을 주장하지 않는다.

| Policy / improvement | Pearson | Spearman | N |
|---|---:|---:|---:|
| B1 P1_absolute_improvement | 0.432316 | 0.401009 | 31 |
| B1 P1_percent_improvement | 0.372677 | 0.379829 | 31 |
| B1 DA_rho_absolute_improvement | 0.435336 | 0.406657 | 31 |
| B1 DA_rho_percent_improvement | 0.376159 | 0.393949 | 31 |
| B1 Actual_rho_absolute_improvement | -0.142880 | 0.049652 | 31 |
| B1 Actual_rho_percent_improvement | -0.143183 | 0.042991 | 31 |
| B3 P1_absolute_improvement | 0.335690 | 0.161105 | 31 |
| B3 P1_percent_improvement | 0.109618 | 0.077024 | 31 |
| B3 DA_rho_absolute_improvement | 0.100860 | -0.097187 | 31 |
| B3 DA_rho_percent_improvement | -0.093470 | -0.138522 | 31 |
| B3 Actual_rho_absolute_improvement | -0.038169 | -0.034076 | 31 |
| B3 Actual_rho_percent_improvement | -0.148572 | -0.008065 | 31 |

| Policy | Affected days / mean P1 improvement % | Unaffected days / mean P1 improvement % |
|---|---|---|
| B1 | 30 / 0.436263% | 1 / 0% |
| B3 | 30 / 15.434318% | 1 / 13.135594% |

B1은 중간 정도의 양의 association이 있어 무관하다고 말할 수 없다. B3 상대 개선과의 association은 약하고, May19는 flagged residual 없이도 13.14% 개선된다. B3 전체 이득을 이연으로 설명할 근거는 없다. 반대로 이 상관관계만으로 B1 개선에서 이연 기여율을 산정할 수도 없다. 해당 frozen grid sensitivity authority와 service-neutral counterfactual이 없어 인과 기여율은 NOT_AVAILABLE이다.

## D-day compute / energy

124개 final decision의 96×12 GPU occupancy를 segment에서 다시 구성하여 FROZEN_AIDC_POWER.gpu와 정확히 대조했다. 존재하는 123개 Parquet 단위에서는 JOB_SLOT_OCCUPANCY 4,423,623행, SITE_TRAJECTORIES의 GPU/IT/PCC/QCC 566,784셀도 일치한다. May31 B2의 원래 failed DA 디렉터리에는 이 Parquet들이 없지만 final accepted AIDC decision과 frozen GPU array 대조는 통과한다.
619건에 귀속되는 정확한 IT-energy 감소 [kWh]는 **NOT_AVAILABLE**. Archive의 exogenous authority는 `V24T_C1_QUASISTATIC_MODEL.json`과 power builder의 외부 경로/해시를 가리키지만 그 모델/매핑 본문은 archive에 없다. Occupancy에서 GPU→IT power를 임의 피팅하거나 외부 workspace에서 보충하지 않았다.
별도 관측값: raw FROZEN_AIDC_POWER.it의 B0−policy D-day 에너지 합은 B1 **8,707.166982 kWh**, B3 **8,774.810884 kWh**. 이는 **전체 정책의 계획 IT trajectory 차이**이며 619건만의 인과효과나 realized Actual IT 절감량으로 표시하지 않는다.

## CSV 11개 재감사

전 파일 UTF-8 BOM decode/encode, header/schema, row count, SHA256, 500 MB 상한과 원본 manifest 일치를 확인했다. Numeric projection 비교는 float round-trip 값까지 대조했다. 약 159만 grid/MESS/Q/scalar 셀의 최대 absolute difference는 0. TRUE/FALSE 표기와 NOT_AVAILABLE/NaN 의미를 검사했고, 아래 method_SHA 누락 한 건을 분리했다.
P1–P5는 archived objective ledger, Fresh/Actual/pre-Q/historical grid는 phase arrays, Q는 pre/post execution arrays와 events, P/SoC identity는 array equality, AIDC count는 final jobs, MESS 이용률은 final executed P/Q/SoC에서 독립 계산했다. 07의 runtime/H4/route metric도 archived prediction-label pair에서 재계산했다. 08/09는 같은 31일 denominator를 유지한다. 09의 **22개 음의 개선율 셀**과 619개 terminal flag를 모두 보존한다.
ML denominators: runtime=40,335, H4=2,511, selected routes=72. Full-link validation은 NOT_AVAILABLE. B0 feeder peak는 final rho/Vmax와 맞는 historical table이 있는 20일만 사용하고 11일은 NOT_AVAILABLE. `NaN`은 Q changed-cell denominator=0인 경우이며 0으로 바꾸지 않았다.

| CSV | Rows | Bytes | Original SHA256 |
|---|---:|---:|---|
| 00_experiment_authority.csv | 1 | 1,217 | `cd2830a4f2f177780a6da00ecccae58c702b51990f1fdcb173daee21bd46c8ff` |
| 01_policy_day_summary.csv | 124 | 53,583 | `3f0255668ecc000fd29e705d8706106cb50cc0135aef16d4f3ea73b890f0f1a3` |
| 02_actual_summary.csv | 124 | 118,644 | `838f6846da70d6834da16b533ae35f90c05357c5cba2f3b56895ca2275762615` |
| 03_q_correction_summary.csv | 124 | 69,565 | `42acb4bf288b70d98a3bb6a9997e26ade1eaed64e20a1c3646e80d1bcc4c2196` |
| 04_mess_timeseries.csv | 47,616 | 29,786,368 | `dce66e191330783cda1e0b6a7b3c4ca27c2ee2d149e2c0c82a2fa9c3e51cc621` |
| 05_grid_timeseries.csv | 43,392 | 15,898,027 | `b8694c7293e1adfc1b16ede8316e68e1b7ecf81a85aa0a759019bf06fc59401a` |
| 06_aidc_decisions.csv | 188,036 | 40,896,823 | `bde2c3fc182622bcfbd8176492b3638dc92256cda99b8dbce7c6dcb899d43853` |
| 07_ml_performance.csv | 22 | 4,514 | `30eae97ef4fd4374badb60efd81d209816d71351b5afc96c868e051647c2a557` |
| 08_policy_aggregate_statistics.csv | 4 | 2,224 | `5f68e10c33e1f6f676a7a5884deb1beaf1d8d6155658c54405718c2902c1aaa5` |
| 09_paired_policy_comparisons.csv | 31 | 22,824 | `e72b541352bcdcdec668d255be7d9148d4a8e598b5367be9aa5c3b875094f8d7` |
| 10_mess_utilization_statistics.csv | 124 | 26,751 | `7861d491a6ebf23e4a3e314e57585b4f0fa7de8b251f827a715306b55a8ca197` |

### 수정한 메타데이터

`00_experiment_authority.csv: method_SHA`의 `NOT_AVAILABLE`을 `710a50cd439a9bb42cc8e6ea77b47eb1a5536c37cef894456a0859aeae9db368`로 채웠다. 이는 archive RULE_FREEZE.actual_method.sha256와 모든 124개 candidate receipt가 같은 값으로 연결한 method이다. 619건과 P1/DA/Actual 수치는 변경하지 않았다.
새 폴더: `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\결과 데이터\MobileESS_V41R4_Paper_CSV_Export_corrected_20260909_112635`. 나머지 10 CSV는 원본과 byte-identical. 원본 11 CSV, 원본 README/FINAL_REPORT/MANIFEST/VALIDATION_FAILURES는 변경하지 않았다.
새 폴더의 MANIFEST는 독립 재감사에 따라 projection PASS와 terminal limitation을 구분한다. `_scripts`에는 method_SHA 한 줄을 고친 exporter를 보존했다. Exporter 자체의 이전 paper-invariant gate는 유지되어 있으므로 그 스크립트만 재실행하면 추가 invariant FAIL_CLOSED가 다시 표시될 수 있다. 이는 이 독립 재감사의 C 판정을 대체하지 않는다. 전체 archive 재-export는 수행하지 않았다.

## May31 B2 최종 반영

| Field | Archived accepted / CSV |
|---|---|
| status / full_PQ_fallback | PASS / TRUE |
| line rho | 0.6319676083483373 |
| Vmin / Vmax | 0.9528912500659789 / 1.049570015262741 |
| transformer phase-current / kVA | 0.9870033465393178 / 0.9999903138843736 |
| all four violation counts / convergence | 0 / 96 |
| AIDC / route identity | unchanged / unchanged |
| DA optimization / route search | none / none |

FINAL_AUDIT total_accepted=124, pending=[] 확인. May31 B2 old FAIL과 forensic witness는 최종 CSV source로 사용하지 않았다.

## 논문 표기 권고

> Frozen one-shot checkpoint migration preserves total planned compute service, while checkpoint-to-transfer waiting, WAN transfer, and restart can defer part of that service beyond the D-day evaluation window. A terminal-residual cap is enforced for restored standalone temporal shifts but not for checkpoint migration. Consequently, D-day loading improvements are not strictly service-neutral. The post-horizon service differences are reported separately; their causal share of the grid-objective improvement is not identified by this post-hoc audit.
“No dumping”, “동일 D-day 서비스 제공하의 순수 효율 향상”, “619건 scientific contract violation”, “31일 campaign failed”라는 표현은 이 결과에 맞지 않는다. 정량 이연량, 긴 migration 대기 및 attribution 한계를 함께 명시해야 한다.

## 재현성과 보존

Archive SHA256 `1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`; 13,524,418,762 bytes. 압축 archive 전체를 새로 스트리밍해 69,297 file member를 해시했고 package manifest의 69,293 source hashes를 모두 검증했다. 기존 추출 cache는 각 read마다 이 새 archive-member hash와 일치하는 byte만 사용했다.
External workspace result read count=0. Gurobi/OpenDSS/SUMO/ML retraining/DA/Actual/route rerun=0. 원본 archive의 크기/mtime는 감사 전후 불변이다. 원본 CSV SHA는 산출물 작성 전후 불변이다.
독립 스크립트, 입력 해시, 비교 범위, 메타데이터 수정 내역과 warning은 CSV_REAUDIT_MANIFEST.json에 기록한다.

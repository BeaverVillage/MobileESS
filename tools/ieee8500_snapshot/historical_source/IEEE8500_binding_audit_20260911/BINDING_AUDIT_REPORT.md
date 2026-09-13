# IEEE8500 AIDC production binding audit — FAIL-CLOSE

현재 실행과 그 산출물의 분류는 **NONAUTHORITATIVE_PRE_AIDC_BINDING_AUDIT**이다. Scientific result로 사용할 수 없으며 B0/B1/B2/B3 재실행도 금지한다. 이전 preflight PASS는 최종 V41R4 AIDC binding PASS를 의미하지 않는다.

PID 50600에 Windows CTRL_C_EVENT를 전달했다. Python KeyboardInterrupt가 campaign 예외 처리 및 finally 정리 경로를 거쳐 프로세스가 종료되었다. 강제 kill은 사용하지 않았다. B1 도중 정지했으며 B2/B3는 시작되지 않았다. 기존 파일은 원위치에 보존했고 분류용 sidecar만 추가했다.

| 항목 | 실행에서 독립 집계 | 요청한 production contract |
|---|---:|---:|
| Installed GPU capacity | 780 | 780 (capacity authority 일치) |
| Reference jobs | 708 | 같은 날짜의 reference UID와 일치 |
| Jobs with temporal options | 39 | 452 — 불일치 |
| Jobs with spatial options | 364 | 동일 optimizer 정의로 집계 |
| Jobs with migration options | 364 | checkpoint >= 0 옵션 존재 |
| Restored temporal candidates | 16,392 | 117,252 — 불일치 |
| Base candidates | 1,325,555 | 4,772,575 — 불일치 |
| Total candidate universe | 1,341,947 | 4,889,827 — 불일치 |
| PARTIAL/shared jobs included | 361 / 708 | 포함 확인 |

Temporal jobs는 한 job의 서로 다른 option.start가 2개 이상인 경우, spatial jobs는 서로 다른 option.site가 2개 이상인 경우로 집계했다. 이는 기존 v40g.optimizer domain_counts 정의와 같다. Migration은 issue 시점 RUNNING에 한정하지 않으며, PENDING에서 첫 checkpoint 이후 migration이 가능한 작업도 포함한다. Standalone non-migration relocation이 있는 작업은 147개이고, candidate manifest의 initial-placement relocation 정의에서는 261개이다. 서로 다른 정의를 혼용하지 않았다.

PARTIAL/shared는 requested_gpus < 4 × requested_nodes 규칙으로 원본 job ledger에서 다시 계산했다. 361개가 reference와 candidate universe에 모두 포함되며, temporal 39개 / spatial 311개 / migration 311개이다. Aggregate GPU occupancy에 포함되고 별도 shared-job 시설 전력을 추가하는 모델은 사용하지 않는다.

GPU capacity vector (AIDC01–AIDC12): 80, 40, 80, 40, 100, 80, 40, 80, 40, 80, 40, 80. 합계 780 GPU. 일부 legacy module 상수의 624 값과 달리 실행의 site power 함수에는 frozen capacity 780 vector가 명시적으로 전달된다.

날짜별 authority를 구분해야 한다. 실제 IEEE8500은 frozen operating date 2025-05-21의 V41R4 daily domain을 읽었고, 이 artifact 자체는 39 / 16,392 / 1,341,947로 동결되어 있다. 요구된 452 / 117,252 / 4,889,827은 로컬 V41R3-restored/V41R4 lineage의 2025-05-04 authority에 존재한다. V41R4 May runtime은 일별 domain 수치로 temporal 상수를 바인딩한다. 따라서 후보 수 차이를 곧바로 temporal 옵션 삭제로 해석할 수는 없다. 실제 May21 base 후보는 모두 보존되었다. 다만 현재 요청의 기대 contract와 다르므로 FAIL-CLOSE이며, 날짜나 workload를 교체하거나 기대 수치를 재해석해 PASS로 승인하지 않았다.

확인된 모델 불일치:

- 기존 B1은 v40g.optimizer의 공동 모델과 BoundedLex를 사용하며, B3-A1은 v41r4_b3_equivalent adapter로 같은 B1 모델을 재사용한다. IEEE8500은 새 aidc_search8500의 rotating 8/12/16-job neighborhood 모델을 사용했다. 이는 feeder/PCC/coefficient/operating-point 변경 범위를 넘는다.
- 기존 P1→P2→P3→P4→P5 단계별 solve와 상위 objective lock이 IEEE8500에서는 주로 P1, 매 다섯 번째 neighborhood의 P2, 그리고 acceptance 단계의 P3/P4/P5 비교로 대체되었다. 4-hour budget 변경 허용은 이 절차 변경을 승인한 것이 아니다.
- 기존 P5는 frozen original cohort rank를 사용하지만 IEEE8500 vector는 sorted 개별 UID rank를 사용한다. 같은 옵션·비용을 공유하는 non-migration cohort의 충분조건 witness 21개를 확인했다. 따라서 P5 coefficient도 동일하지 않다.
- IEEE8500이 기존 materialize/audit, power 및 reserve 함수를 일부 사용하고 exact AC에서 feasible하더라도 위 model/objective identity 위반을 해소하지 못한다.

아래 SHA256은 파일 bytes의 SHA256이다. candidate_set_SHA는 압축 해제된 JSONL stream의 별도 SHA256이다. 모든 입력은 읽기 전용으로 조사했고 모델 import/optimization/OpenDSS 재실행은 하지 않았다. 기존 May B1/B2/B3 performance 및 Actual 데이터는 읽지 않았다.

## Workload/reference 및 후보 authority

| Source | SHA256 |
|---|---|
| [COMMON_B0_REFERENCE_JOBS.json](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r3_may/inputs/2025-05-21/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json>) | `48e30359345469e18459eb48c486a648d0ec0876696182e26ef07558e75ee57c` |
| [COMMON_DA_SERVICE_AUTHORITY.json](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r3_may/inputs/2025-05-21/common_q90_v3/COMMON_DA_SERVICE_AUTHORITY.json>) | `f28de1e26f3ac73fda864827481c6ad4737f0a377392452b5534776db6b5fc8d` |
| [COMMON_INPUT_RECEIPT.json](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r3_may/inputs/2025-05-21/common_q90_v3/COMMON_INPUT_RECEIPT.json>) | `f3b90f0d28553fd9f28a78392a50d555a870e1e6197017bba0860e51c48c8fbb` |
| [V41_ML_SNAPSHOT_2025-05-21.json](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r3_may/inputs/2025-05-21/V41_ML_SNAPSHOT_2025-05-21.json>) | `7248bf646a10f8fd9042c1432b064b32a5abc8d766308c675ad4280b41ad7043` |
| [V37_R4A_JOB_LEDGER.parquet](<C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-21/V37_R4A_JOB_LEDGER.parquet>) | `fdf88cf42b16e60756efddd4ced94cb679f538acef2f7c1f4cd88b825151b633` |
| [DAILY_DOMAIN_AUTHORITY.json](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r4_may/audit/2025-05-21/domain/DAILY_DOMAIN_AUTHORITY.json>) | `3b0e8d95d4c5c6e572696d7ddb58cc532ad177fd4303263eef3f99c58db5fc21` |
| [FULL_CANDIDATES.jsonl.gz](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/frozen_artifacts/v41r4_may/audit/2025-05-21/domain/combined/FULL_CANDIDATES.jsonl.gz>) | `3b2fa54789211aff3ce2e5fd3a3bb5f1db32ce51026524a7b74072d11a05bf35` |
| [V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/artifacts/v41r3_fast_power_scale_freeze/V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json>) | `c4b0a88712e6b11d5fa090207a80a3443b2c3f8376ea5864bfe949662af41f35` |
| [V41R2_780GPU_CAPACITY_AUTHORITY.json](<C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v41r2_780gpu_capacity_rebase/V41R2_780GPU_CAPACITY_AUTHORITY.json>) | `f8200de1092ee0daac6c91798f0f5e24429b203cff4d66baca2eca387affb6e7` |

Combined decompressed candidate stream SHA256: `878116c6e5d9204b8b02cf651ca669c23f1afab1f2cd03920f8620cc5fc82397`
Base decompressed candidate stream SHA256: `9aca125d3d4e2d081d1d72c19acf96b0b9e1393f2b6898cce11e3cf580c39975`

## AIDC power-model authority/source SHA256

P_IT(site, active GPU) = [site capacity × 104.1606964512843 W + active GPU × 547.7239090195797 W] / 1000. PCC power는 frozen C1 및 선택일 D−1 weather를 적용하며 Q는 기존 PF 관계를 따른다. 입력/함수의 동일 SHA는 확인했으나 이 사실만으로 전체 optimization binding을 PASS로 처리하지 않는다.

| Source | SHA256 |
|---|---|
| [power.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v39a/power.py>) | `ff264b087b2f7c1549121034ee4606a90af55b666ccd4f47314f18d9cc3e010e` |
| [contracts.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v39a/contracts.py>) | `2e69721fc48495d19bba97d08b1f12d140dfb36d580369fe0d60f062287a1446` |
| [c1_affine.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v28r2/c1_affine.py>) | `912c870a2c062431cac60f2157f3b4399ad824119facdafbd7ac3f1788c40c13` |
| [formulation.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v28r2/formulation.py>) | `83967d66d490a1878f9ee76f9e7c06c171e61e047094c8d1e8ff69949f93deda` |
| [canonical.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v40g_segments/canonical.py>) | `bd29a6333a96076a410503d975bf355fb0e7cd08a0053dad792239ae939aec31` |
| [V24T_C1_QUASISTATIC_MODEL.json](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json>) | `02a19e6c2d8cb44ec6b90ff1a4c98f21d5e848cda2dc34f2aaf2f959f9e6579e` |

## V41R4 B1/A1 model/objective/constraint source SHA256

| Source | SHA256 |
|---|---|
| [optimizer.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v40g/optimizer.py>) | `f2a64cbd0c28215f8eeaac48235f1d2b3d58d6c07cd5ce321a6535ae050ba3cc` |
| [domain.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v40g/domain.py>) | `0631175ce7a63379673dae0579baf213b82a9b06a43b17b73e51d7167337e6b5` |
| [objectives.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41/objectives.py>) | `a5f385a0893796e67b3995dd13ce9aef7f02c4f965944b95c7746bc276a2fd85` |
| [reserve.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41/reserve.py>) | `f0b6fd207321599f8903ac842025907a0f12b10b9aa41cf7aca79344c8e090ba` |
| [temporal_restore.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41/temporal_restore.py>) | `7153a4cfafa33f5546348c1e0957475606957265a01dad8d38bdb719d9ba39b0` |
| [frozen_candidates.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41/frozen_candidates.py>) | `56027b29006156350e3e1cbe5db2d08d7d07b52244f7104ee537184128f19ce2` |
| [common.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41/common.py>) | `e21bde3188d1a246dbebfb50262c7722782ff2fa69b7e9b331ff2fba8a9d8a75` |
| [bounded_solver.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/bounded_solver.py>) | `db57efc8da824fb6777bdf5ca7a7181030d6d4104a084c0cf107cea738b79d13` |
| [feasible_seed.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/feasible_seed.py>) | `a69f8b043da3d9c7b20ecb16008a1313a744dbfc5ff35c3eade6f4c94151fd70` |
| [exact_aggregation.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/exact_aggregation.py>) | `d4c5e3e08d6e4d357ee98a5185e0c18198097aedf1b51f89ba57f7aeff3954d9` |
| [migration.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/migration.py>) | `c8908d56662dcb3820d90412dc1fa4a1094b73c95638938ff5096a4bdad37aff` |
| [terminal.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/terminal.py>) | `593721d7cc85512bf34b900255468473607550af4011c00de1c5fecafef44c41` |
| [migration_factor.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/migration_factor.py>) | `a80703d481b7c66c1ddacc4f0409bf3fe0d84af4f532be1d44dbe534624257c1` |
| [migration_admission.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/migration_admission.py>) | `966872c6279e1a99f5d286d080dfa216e7100ab07753543838948e1943c1792a` |
| [v41r4_runtime.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/v41r4_runtime.py>) | `3c13e6be893ef96b6f05fdb52f2dba915d5797e3ccfc89484014bf115f074362` |
| [v41r4_domain.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/v41r4_domain.py>) | `bc56de0457a868e00c0c38dd8d3b245f9562fd78b8eb3780edf4f602190a7def` |
| [v41r4_b3_equivalent.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/v41r4_b3_equivalent.py>) | `284b1557590bd492d3baa988bbff3b3fcb8590eb2f39f276de0e1f12752b7ecb` |
| [v41r4_loop_runtime.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/v41r4_loop_runtime.py>) | `ff8228fe4a0f7f8e4514ab46e26fb57e9e74ba6bfac6c8f3dd94b284566a8c10` |
| [v41r4_loop_budget.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/v41r4_loop_budget.py>) | `68ae5b101db061979f04024bf5a33b2bcea819f14b56400dd8ff3a7194e9e28c` |
| [authority.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r3/authority.py>) | `6eacdc4338169109a13d54db2406b4259cb3fe8a158b98b46a13416fb57012db` |
| [aidc_materializer.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v37/aidc_materializer.py>) | `64dfd70b9b898cc3c0b870ed0770bb042831a90a64090bc0f55ba7017f1f1022` |

## 실제 IEEE8500 실행 source SHA256

| Source | SHA256 |
|---|---|
| [non_electrical_inputs.py](<D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911/non_electrical_inputs.py>) | `3c4a93b148961ac968fb7f8142f59214a24e0dc739b619e05ef407c161b29ea2` |
| [aidc_search8500.py](<D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911/aidc_search8500.py>) | `f9ab3edde1077849b3ba776396b8374f2cd9caebf098bc34f5c997ea81419e0c` |
| [run_support.py](<D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911/run_support.py>) | `625c9451dc575b406923ebe66e6ee2d813e93530c9061a032a2918cf8f96d551` |
| [grid8500.py](<D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911/grid8500.py>) | `15179dc74e47ed954ba3145f2be1e6b4b297d3852e456d183c6e2bb6e61cd255` |
| [production_campaign.py](<D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911/production_campaign.py>) | `3d47f760d55f086e76a1855500f61fdf5b19f5732e17155f953c63b05d23e9df` |
| [production_campaign_v2.py](<D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911/production_campaign_v2.py>) | `fbeb77f58ab7298799c2ec10ce891523fbb35457d3e4498ccbc16632f0e31903` |
| [ac8500.py](<D:/ChatGPT/Mobile ESS 2/IEEE8500_production_20260911/ac8500.py>) | `390f7a520dcda5535234f3563e432837ac5895e215b6770370db1f399e83ffaf` |

## 정지 및 evidence 보존

| Scope | Files | SHA drift |
|---|---:|---:|
| preserved_stopped_production | 4638 | 0 |
| preexisting_source_topology_PCC_operating_authorities | 3997 | 0 |
| execution_inputs_code_coefficients | 4249 | 0 |
| execution_v2_adapter | 3 | 0 |
| read_only_audit_inputs | 59 | 0 |

현재 production PID 존재: False. 보존된 checkpoint: 30 min, 1 h. 2 h / 4 h checkpoint는 정지 전에 도달하지 않아 생성되지 않았다. 불완전한 run을 4-hour completed result로 사용하지 않는다.

[정지 증거](<D:/ChatGPT/Mobile ESS 2/IEEE8500_binding_audit_20260911/GRACEFUL_STOP_RECEIPT.json>), [보존 검증](<D:/ChatGPT/Mobile ESS 2/IEEE8500_binding_audit_20260911/PRESERVATION_VERIFICATION.json>), [전체 보존 SHA manifest](<D:/ChatGPT/Mobile ESS 2/IEEE8500_binding_audit_20260911/PRESERVED_PRODUCTION_SHA256.json>), [job별 집계](<D:/ChatGPT/Mobile ESS 2/IEEE8500_binding_audit_20260911/PER_JOB_BINDING_CENSUS.json>).

이 감사는 진단 결과만 작성했다. AIDC/MESS scale, topology, host/PCC mapping, stress authority 및 V41R4 원본 코드는 수정하지 않았다. Binding audit가 PASS하기 전 모든 policy 재실행을 금지한다.

# V20 ML-independent final authority review

RESULT CLASSIFICATION: **V20_INDEPENDENT_AUTHORITY_C_PHYSICAL_AND_LOCKED_TEST_GAPS**

## 1. Site-specific AIDC scale

| Site | April-2025 evidence | boundary | confidence | IT harmonizable? | model site weight | model IT/PCC peak |
|---|---:|---|---|---|---:|---:|
| Equinix ME4 | null  | UNKNOWN | B | no | null | null |
| Micron21 | 2.0 MW | BUILD_CAPACITY | C | no | null | null |
| Fujitsu Noble Park | 2 x 4 MVA | MVA | B | no | null | null |
| AAPT / TPG Richmond | 2.5 MVA | MVA | C | no | null | null |
| NEXTDC M2 | 42.0 MW | OPERATING_CAPACITY | A | no | null | null |
| NEXTDC M3 | 13.5 MW | OPERATING_CAPACITY | A | no | null | null |
| Vocus Mitcham | 9.0 MW | BUILD_CAPACITY | C | no | null | null |
| NEXTDC M1 | 15.0 MW | OPERATING_CAPACITY | B | no | null | null |
| Equinix ME5 | 4.175 MW | GENERATOR_NAMEPLATE | C | no | null | null |
| CDC Brooklyn BK1 | null  | UNKNOWN | B | no | null | null |
| IBM MEL01 | null  | UNKNOWN | D | no | null | null |
| STACK MEL01A | 36.0 MW | OPERATING_CAPACITY | A | no | null | null |

운영 상태와 수치 경계를 분리했다. NEXTDC M2/M3의 42/13.5 MW는 2025-02-25 공식 1H25 자료의 built capacity이며, STACK MEL01A 36 MW는 개장된 건물 용량이다. 이들을 IT MW로 자동 변환하지 않았다.

## 2. Aggregate scale

최종 real-world numerator, rho, IEEE123 equivalent는 모두 **null**이다. 4개 사이트의 동일 `OPERATING_CAPACITY` 합 106.5 MW와 2025 forecast host peak 567.9513 MW를 사용한 rho 0.187516은 부분범위 진단일 뿐이다. 기존 0.9 MW를 목표로 사용하지 않았다.

## 3. D-1 state

Exact snapshot은 없고 완전한 retrospective causal reconstruction도 불가능하다. 기존 queued 6621.642222 GPU-h / running 5303.617222 GPU-h는 7일 Level-C oracle 진단으로만 유지한다.

## 4. Partial-node power

새 권한은 없다. 0.48563611660901085 kW/GPU board-only 하한을 유지하며 CPU increment와 유한 상한은 null이다.

## 5. Integration framework

FORECAST_BUNDLE_V1과 SITE_SCALE_BUNDLE_V1은 모델명 독립적이다. C-MASS accepted면 이를 사용하고, 아니면 V19 training-only blocked-CV accepted baseline으로 자동 fallback한다. Synthetic fixture G1~G14는 모두 PASS다.

## 6. Locked test

새 untouched 기간을 seal하지 못했다. April target/예측과 May~December 기존 human-visible 결과 이력이 있으므로 E3로 fail-closed했다.

## 7. Remaining blockers

12/12 공통경계 site scale, GPU weights, 실제 PCC rating, untouched test, V19 forecast authority가 남았다.

## 8. Ready flags

- SITE_SCALE_AUTHORITY_READY = false
- D1_STATE_EXTENSION_READY = false
- PARTIAL_NODE_POWER_UPGRADE_READY = false
- MODEL_AGNOSTIC_INTEGRATION_READY = true
- LOCKED_TEST_AUTHORITY_READY = false
- PRE_ML_INTEGRATION_READY = false
- FINAL_SCIENCE_READY = PENDING_V19_MODEL_AUTHORITY

## 9. Generated artifacts + SHA256

- `V20_PRECHANGE_MANIFEST.json`: `d0f08839a60eafb97545ac6f686d1c7ad6810b91ed833aff92d2328dd5b7d6e8`
- `V20_READY_FLAGS.json`: `652410206591bb6553dfad0482ba677f32e6b741b0adc4ea3b9daa33a722cd71`
- `V20_TEST_REPORT.json`: `25f606495ca2f775d366b45a65553d4d0bee9c29539d95b4de773e7b8d7efd83`
- `V20A_CAPACITY_BOUNDARY_HARMONIZATION.json`: `f4094d8c0de895f6fe4813a1663a1e6f5a21bd7bec1260b02102a4055633ae21`
- `V20A_FINAL_SCALE_REVIEW.json`: `c822ae38c1df07c4a7a42cdb7a9e72bd0c2c588a3f3d56d24ba4ff2e4cca5992`
- `V20A_FINAL_SCALE_REVIEW.md`: `2ef7926141f27f2bb6e203831d2c125fcffb359411355734fe81454903e9e781`
- `V20A_HOST_GRID_DENOMINATOR_REVIEW.json`: `eb60b78dceb33210502f0994665e4e0ede17e2bf044d8ddc01580489d1ddc5e3`
- `V20A_IEEE123_EQUIVALENT_SCALE_CANDIDATES.json`: `5b02d335fa3399a3918a01c5f6e02b48eda35cc22ff6e146edf9fa582ef93dda`
- `V20A_MELBOURNE_12SITE_CAPACITY_EVIDENCE.csv`: `408020b75253712aac7c0764733a5b72a7e63bbad4a3bf52a4fe5ac92017063b`
- `V20A_PCC_TRANSFORMER_INTERFACE_AUDIT.json`: `b37b1eb7844c28d452e52a6aa09e4ae6a9c20043e6b04b47c35245ade9a4656b`
- `V20A_REALWORLD_AIDC_NUMERATOR_REVIEW.json`: `facaf9e37fd7427ada2e38ceca4fe69e3c6ab838b427481aa425a0a90ce08434`
- `V20A_SITE_CAPACITY_SOURCE_REGISTRY.json`: `5228e5abed715640fb39281c99ffe76354a2ad436ffba97708524b7bfccb7882`
- `V20A_SITE_GPU_WEIGHT_AUTHORITY_GAP.json`: `9ba6665b55b4fee260e896877b50c7feaa82951482726c6081dbb37f018d69fa`
- `V20A_SITE_SPECIFIC_POWER_WEIGHT_AUTHORITY.json`: `f961f44f37dfe62392616f15386fb623dba536d34bfd14ba3a4e1b544a9a8271`
- `V20B_D1_QUEUE_RECONSTRUCTABILITY_AUDIT.json`: `6a1fc8ff0883790dfc592a99c23b48276273ec50b90f0048c9c8f1d8984e3aac`
- `V20B_D1_RUNNING_RECONSTRUCTABILITY_AUDIT.json`: `c8b072ea1f6e2ae2b57804cc6883cdb3b331fcb6d96f496144489b4bad2a0934`
- `V20B_D1_STATE_FINAL_REVIEW.json`: `3a005250d76d7392925ca7a8430c65660de3e68e0bfe8f9f649086f9f931bcb2`
- `V20B_D1_STATE_FINAL_REVIEW.md`: `8c75e5d0c02eee92fcf4fdcc6f3958e9447c14a38c3688854113781876fb0fc3`
- `V20B_D1_STATE_SOURCE_DISCOVERY.json`: `e2f65a03791c3291e533d888309b97d6551a4fc76b7b857422ee06a3d7e2af71`
- `V20B_RETROSPECTIVE_CAUSAL_STATE_DATASET_CONTRACT.json`: `0a09f1344a1f98c3521994355ef5a4601c31d110e27fcaca51f4a84dd4c7a1b9`
- `V20C_PARTIAL_NODE_CPU_HOST_ADMISSIBILITY.json`: `1e5762866d3d437868f977d934495285a372544a602169690310694d3094c336`
- `V20C_PARTIAL_NODE_PACKING_IDENTIFIABILITY.json`: `6339e171cbeaf85392456216b06a734131c062edecf476821368af83f9b44b13`
- `V20C_PARTIAL_NODE_POWER_BOUND_CONTRACT.json`: `5032e8ce7d5d06b2140ef796d83016802209f083a70d45b726581c2a4ba7a5eb`
- `V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.json`: `c1a2d6022667553a2ea1e3cdb1bce896949f3ba93e6ae1f8020a8284b6d692e6`
- `V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.md`: `a91a2b91becdbcec20c40a4bae2cf65513df35585dcc96b64e512179c28459f5`
- `V20C_PARTIAL_NODE_POWER_SOURCE_AUDIT.json`: `aa5dfcd6f36c59be9eeb5a71b3f62a108325bc3e77283aec90c46ec2925d14c8`
- `V20D_FINAL_INTEGRATION_PREFLIGHT_CONTRACT.json`: `ee962e66c1120e77ba16a6d087e142799ed6b3c1992f3edfdd4436ad7780e424`
- `V20D_FINAL_INTEGRATION_PREFLIGHT_TEST.json`: `62ced595e72908c68cf5567ae377502b5a65e0819caaeaf330adb980db98e976`
- `V20D_FORECAST_BUNDLE_CONTRACT.json`: `7e48b6f1b1287315c3ce2fcf7bba42771d09825c24cc6c68ed075880312d64e2`
- `V20D_MODEL_SELECTION_ADAPTER_CONTRACT.json`: `3431bcd4dc412b358bff7d25fb86b6272c9a72e8fe794afc42f5ac58512f6d22`
- `V20D_SCIENCE_RUN_AUTHORIZATION_TEMPLATE.json`: `d8d5e584626adb3c14076595fc4b015b5777af31e51c0db0a45f5ab88954c6ca`
- `V20D_SITE_SCALE_BUNDLE_CONTRACT.json`: `f599c476a474d3507ee884e4537c627552ae3260e53048b7640db05db86591a6`
- `V20E_LOCKED_TEST_CANDIDATE_AUDIT.json`: `e43a36cca2a4b3b66de1f331d143a1aff77aeefa5cec8f415320a6ac26945af1`
- `V20E_LOCKED_TEST_FINAL_REVIEW.json`: `7d77c5e52c7b6218e075c31d9501fb44dc15a4bcae0d3f5dbc10b4cd5f20cff1`
- `V20E_LOCKED_TEST_FINAL_REVIEW.md`: `b085011571feafc0349ce7bfe3035ee78e52436883f3af2556186efeb4fb4e53`
- `V20E_TEST_PERIOD_ACCESS_LEDGER.csv`: `bdbcfabe4bc06e95a4b7c8e9ae91266a18fcf7e335abfcec4d530ed08d1d20d2`

## 10. Git

- worktree: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v20_independent`
- branch: `codex/v20-independent-authorities`
- starting HEAD: `77a86e3ded8087ea0109ccfca631bd2396ecd9fe`
- head before final review commit: `f2a619223415ec33fb8c43d4b9958a8b94506e2e`

B0-B3, OpenDSS, AC/grid science, ML 학습은 실행하지 않았다.

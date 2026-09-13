# FINAL DATASET PROVENANCE AUDIT — V41R4 May 2025

작성일: 2026-09-09. 범위: PR #42 최종 V41R4 31일/124-policy 결과의 외부 데이터 provenance. 모든 분류는 기존 code, artifact, manifest, receipt와 source authority를 읽어서 수행했다. 재계산·학습·OpenDSS·SUMO·optimization 실행은 하지 않았다. 생성한 CSV의 집계는 감사 메타데이터 집계일 뿐 scientific result 재계산이 아니다.

## 판정 기준과 읽는 법

A는 최종 numerical input 또는 그 전처리 입력, B는 최종에 남는 모델 파라미터·명시적 검증·소프트웨어 authority, C는 과거 사용/검토 후 최종에서 빠진 자료, D는 현재 감사 범위에서 acquisition/inventory 외의 final numeric binding이 없는 자료, E는 원천·부분집합 연결이 닫히지 않은 자료다. A의 direct_or_indirect는 runtime에서 raw를 바로 읽었는지, 전처리/고정 artifact를 통해 읽었는지를 used_for와 preprocessing_output으로 구분한다.

`final_V41R4_used=YES`는 A/B에만 허용했다. B에는 수치 생성용 파라미터와 validation-only를 role로 분리했다. `paper_citation_required=YES` 표는 최종 방법과 실제 수행된 검증을 설명할 때 인용할 source만 포함한다. 내부 생성 라벨과 C/D/E는 인용표에서 제외했다. 같은 dataset의 사본은 하나의 family로 묶었고, 한 폴더 안에서 역할이 다른 subset은 별도 행으로 나눴다. 표의 행 수는 고유 DOI 수나 폴더 수가 아니다.

first/final relevant version은 감사에서 확인한 최초·최종 관련 버전이지 저장소 전체 최초 도입을 보장하는 값이 아니다. C의 final relevant version은 마지막으로 확인한 과거 검토 버전이며 final V41R4 사용을 뜻하지 않는다. E는 사용되지 않았다고 확정한 항목이 아니다. D의 부정 판정도 아래 명시한 검색 범위에 한정된다.

## 최종 authority와 변경 금지 대상

- Final archive: `V41R4_May2025_31days_124policies_raw_20260909_102655.tar.gz`, SHA256 `1d57950fd073ead32bcb68a8d65c06ad6023f3d556acc672eae911651438f6d3`. 기존 검증 index와 mirror를 사용했다. 이번 감사에서 13.5GB archive 전체를 다시 해시하지 않았다.
- PR worktree HEAD: `3140307a664a366d231227db2ed69d99ea123f59`. Audit outputs는 저장소 밖 별도 디렉터리에 작성했다.
- Transitive input inventory SHA256 `ba220f2280ff5e8cd8b6b9d3a3396ff9aa9fc41d0abeb51533b032d94ab5fa94`.
- Traffic chain은 이전 read-only 복구의 62 M1 identity, 31 forecast/route pairs, 95 committed departure-row binding과 PR19 model authority를 계승한다. 이번에는 그 상위 데이터 원천을 확장했다.
- Corrected paper CSV, 모델, raw 자료, scientific 결과는 변경하지 않았다.

## Inventory 범위

- 사용자 데이터 루트 전체: `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS`. 최초 file metadata inventory 42,736개, raw folder group 51개. `LOCAL_FILE_INVENTORY.csv` 참조.
- raw directory tree는 빈 폴더까지 별도 `RAW_DIRECTORY_METADATA.json`에 기록했다. 최초 inventory의 493 오류 및 재검사 오류는 별도로 보존했다. NLR 문서 repository의 unreadable/reparse entries가 포함되므로 “모든 파일 내용 확인”으로 해석하면 안 된다.
- Windows 최종 workspace 및 transitive references: `TRANSITIVE_DATASET_REFERENCES.json` (621 source documents, 31,740 path references). Archive에서 채택한 metadata는 기존 member SHA와 대조했다.
- WSL dataset roots 15개, metadata files 24,317개. `EXTERNAL_WSL_FILE_INVENTORY.csv`와 root summary 참조. 동일 source의 raw/derived 복사본은 별도 metadata entries다.
- Static negative search: `STATIC_SEARCH_SCOPE.json`와 `STATIC_SOURCE_SEARCH.csv`. Production repo, pfr contracts, power rebuild code의 UTF-8 text ≤2MB를 검색했다. 원자료 내용 전체 또는 컴퓨터 전체의 모든 과거 workspace를 읽었다는 주장은 하지 않는다.
- Raw SHA checks: 기존 expectation 9개 모두 MATCH; Jemena 3개는 현재 hash만 신규 기록했다. 기록 hash와 재검증 hash를 혼동하지 않는다. `RAW_HASH_VERIFICATION.json` 참조.
- 추가 검증: final inventory에 묶인 core inputs/assets 103개 SHA MATCH, May AEMO forecast raw archives 4개 MATCH, May source receipts 31일 확보, corrected paper CSV 11개 SHA MATCH. `AUDIT_VALIDATION.json` 참조.
- 외부 Windows cache/root inventory는 `EXTERNAL_WINDOWS_FILE_INVENTORY.csv`와 `EXTERNAL_WINDOWS_ROOT_INVENTORY.json`에 추가했다. code workspace 목록과 numeric cache 범위를 구분했다.
- WSL의 거대한 `mobile_ess_work/frozen_artifacts`는 raw dataset root가 아닌 과거 결과 보관소다. 이 root는 top-level entry inventory만 남겼고 전체 하위 artifact 전수 스캔은 중단했다. 최종에 필요한 파일은 transitive references로 별도 확인했다. 이 범위 제한은 `HISTORICAL_DERIVED_ROOT_TOPLEVEL.json`에 명시했다.

## 핵심 결과와 논문 표현 제한

1. Kestrel은 최종 작업/학습 원천이다. Dataset312 v2는 GPU power parameter, ESIF는 C1 cooling/IT shape source다. 서로 다른 경계의 데이터를 실제 단일 Melbourne 데이터센터 관측으로 합쳐 표현하면 안 된다.
2. H100/B200 두 폴더는 같은 Figshare family다. H100만 secondary bound validation에 남고, B200은 최종 H100 magnitude에 쓰이지 않는다. Eagle telemetry/jobs와 EuroSys Zenodo는 실제로 과거 검토했으므로 downloaded-only가 아니다.
3. Córdoba는 PF=0.95의 validation-only 자료다. 버스별/시변 PF, local AIDC Q control, actual Melbourne P/Q authority는 아니다.
4. AEMO Planning은 PREDISPATCH demand와 PV forecast, Actual은 DISPATCHREGIONSUM과 PV actual이다. DISPATCHPRICE는 old preprocessing 이력만 있으며 최종 price optimization 입력이 아니다. 2025 full-year normalizers는 ex-post scenario scale임을 밝혀야 한다.
5. Traffic의 실제 모델 데이터는 SCATS + HERE/MeTS 관측에 anchored한 simulation-generated labels다. 최종 5-minute full-link 데이터 자체를 실측 label로 부르면 안 된다. MeTS release 2021/2022는 코드에서 관측연도 2019/2020으로 매핑된다.
6. IEEE123는 synthetic test system, Jemena는 부하 다양성/Q 변화의 전이 입력, Vicmap/OSM은 terrain/road geometry다. 실제 Melbourne feeder topology를 사용했다는 주장은 성립하지 않는다.
7. SNDlib Abilene preinstalled link capacity만 primary WAN에 반영된다. Zhang OD traffic subtraction, RIPE RTT, M-Lab throughput은 primary final input이 아니다. 80GB/GPU checkpoint payload는 NVIDIA memory specification에 근거한 engineering proxy다.
8. Operator capacity와 utility forecast peak, utilization 0.46은 raw download 유무와 무관하게 최종 AIDC scale에 남은 parameter sources다. 이들은 실제 사이트의 계측 부하와 구별해 인용해야 한다.

MESS의 28t mass, drag/rolling/efficiency 및 battery/PCS limits는 frozen engineering scenario contract다. 외부 vehicle drive-cycle 또는 실측 EV battery/energy dataset의 사용은 확인되지 않았다. 해당 상수의 존재를 별도 measured dataset 사용으로 판정하지 않았다.

## 분류 집계

| 분류 | 행 수 |
|---|---:|
| DIRECT_PRODUCTION_INPUT | 15 |
| MODEL_PARAMETER_OR_VALIDATION | 29 |
| HISTORICAL_SUPERSEDED | 11 |
| DOWNLOADED_ONLY_UNUSED | 13 |
| UNRESOLVED | 4 |

## 논문에 인용할 production 데이터

| ID | Dataset | 역할 / 판정 근거 |
|---|---|---|
| DC01 | NLR Kestrel Jobs — consumed job history and May cohort | Historical runtime labels; causal request-state proxy; May pending/running workload and realized execution history |
| PW01 | AEMO VIC1 demand forecast — selected April/May vintages | D-1 18:00 fixed-AEST demand input for final May Planning |
| PW02 | AEMO rooftop PV forecast — selected April/May vintages | D-1 18:00 fixed-AEST PV input |
| PW03 | AEMO VIC1 realized demand — May DISPATCHREGIONSUM | Final Actual replay demand |
| PW04 | AEMO realized rooftop PV — May | Actual replay PV |
| WX01 | NOAA GFS D-1 weather — final May GRIB subsets | D-1 weather supplied to C1 for May Planning |
| WX02 | NOAA NCEI Melbourne observed weather | Final Actual-replay weather; also earlier transfer/forecast validation |
| GR01 | EPRI IEEE 123-node canonical case | Native bus/phase P/Q, feeder lines/regulators and AC replay model |
| GR04 | Jemena feeder load traces | Relative temporal diversity of background loads on synthetic electrical zones |
| GR05 | Jemena zone-substation MW/MVAr measurements | Relative Q variation; preserve native IEEE123 mean P/Q allocation |
| TR01 | Victoria SCATS traffic volumes — consumed canonical years | 15-minute demand patterns for traffic simulation; causal traffic features and observation-anchored label construction |
| TR03 | Stage25F calibrated SUMO link travel-time labels | PR19 Traffic model training/validation and committed-route provenance |
| TR04 | OpenStreetMap Melbourne road extracts | Physical road graph, reduced-link mapping and mobility routes |
| TR05 | Vicmap Elevation DEM 10 m | Road grade/elevation for deterministic MESS route-energy physics |
| WN01 | SNDlib Abilene preinstalled topology/capacity | Final WAN migration capacity and deterministic fixed paths |

## 파라미터·검증·소프트웨어용 인용

| ID | Dataset | 역할 / 판정 근거 |
|---|---|---|
| DC02 | NLR Dataset 312 v2 — H100 measured GPU power | Final GPU-slot active-power magnitude, 620.2239090195797 W/GPU CENTER; final swing 547.7239090195797 W/GPU after idle subtraction |
| DC03 | Dataset 312 associated paper — dedicated H100 idle test | 72.5 W/GPU idle component in final active-minus-idle GPU swing |
| DC04 | NLR ESIF PUE / IT power / outside-weather series | C1 quasi-static cooling/PCC model parameter fit and NLR IT-power shape authority |
| DC05 | Scientific Data / Figshare H100 training workloads — H100 subset | Secondary H100 power-bound cross-check of Dataset312 authority |
| DC07 | University of Córdoba data-center P/Q | Independent aggregate PF=0.95 plausibility screen |
| DC19 | HPC-ODA Commons — preserved input normalization | Pinned Slurm memory normalization reproduced in final input builder |
| PW05 | AEMO 2025 demand and PV annual normalization archives | Frozen feeder demand scale and PV normalization |
| GR03 | OpenDSS / DSS-Python simulation engine | Historical generation of sensitivities and final Fresh/Actual AC validation outputs |
| GR06 | Jemena AMI voltage report | External realism benchmark during power_v70 model development |
| TR02 | HERE Traffic4cast movies and MeTS-10 Melbourne derived observations | Sparse speed observations for Stage20E/K 15-minute traffic correction calibration and transfer validation |
| TR06 | SUMO traffic simulation engine | Generation of raw 5-minute traffic shape used by final model labels |
| WN05 | NVIDIA H100 memory specification | 80GB/GPU aggregate framebuffer proxy for migration payload |
| PS01 | TPG Telecom Richmond [S_AAPT_INFLECT] | AIDC04 IT-equivalent capacity 1.8846153846153846 MW |
| PS02 | CDC Independent Valuation - 31 March 2025 [S_CDC_INFRATIL_2025] | AIDC10 IT-equivalent capacity 34.0 MW |
| PS03 | 2024 Transmission Connection Planning Report [S_DPTS_TCPR_REACCESS] | HOST_DPTS 2025 forecast peak 276.75199999999995 MW |
| PS04 | Locations of Fujitsu data centres [S_FUJITSU_OFFICIAL] | AIDC03 IT-equivalent capacity 28.0 MW |
| PS05 | AusNet Distribution Annual Planning Report 2025-2029 [S_HOST_AUSNET] | HOST_BWR 2025 forecast peak 52.865 MW |
| PS06 | CitiPower 2024 DAPR network data [S_HOST_CITY] | HOST_R 2025 forecast peak 31.9 MW; HOST_PM 2025 forecast peak 14.4336 MW; HOST_VM 2025 forecast peak 59.8554 MW |
| PS07 | Jemena 2024 Distribution Annual Planning Report [S_HOST_JEMENA] | HOST_TMA 2025 forecast peak 23.43 MW; HOST_FW 2025 forecast peak 36.16 MW; HOST_TH 2025 forecast peak 25.47 MW |
| PS08 | United Energy 2024 DAPR Max Demand Template [S_HOST_UE] | HOST_NP 2025 forecast peak 50.81 MW; HOST_NW 2025 forecast peak 56.47 MW |
| PS09 | Metronode opens second Melbourne data centre [S_ME4_ITNEWS] | AIDC01 IT-equivalent capacity 12.0 MW |
| PS10 | ME5 Melbourne data center [S_ME5_EQX] | AIDC09 IT-equivalent capacity 2.346153846153846 MW |
| PS11 | Digital Realty ICN10 / PlatformDIGITAL APAC portfolio presentation [S_MEL11_DLR_HISTORICAL_2020] | AIDC11 IT-equivalent capacity 7.02 MW |
| PS12 | Micron21 Melbourne Australia - Specs [S_MICRON_DCM] | AIDC02 IT-equivalent capacity 2.0 MW |
| PS13 | NEXTDC 1H25 Results Presentation [S_NEXTDC_1H25] | AIDC05 IT-equivalent capacity 42.0 MW; AIDC06 IT-equivalent capacity 13.5 MW |
| PS14 | NEXTDC data centre locations and technical details [S_NEXTDC_GUIDE] | AIDC08 IT-equivalent capacity 15.0 MW |
| PS15 | STACK opens first data center in Australia [S_STACK_OPEN] | AIDC12 IT-equivalent capacity 36.0 MW |
| PS16 | Vocus Data Centre - Mitcham - Specs [S_VOCUS_DCM] | AIDC07 IT-equivalent capacity 9.0 MW |
| PS90 | Primary IT load utilization 0.46 | 0.46 primary IT operating-load/design-capacity multiplier |

## 과거 사용 또는 검토 후 최종 제외

| ID | Dataset | 역할 / 판정 근거 |
|---|---|---|
| DC06 | Scientific Data / Figshare B200 subset | No final H100 magnitude or final runtime input |
| DC08 | Eagle GPU six-node telemetry | Historical identifiability and dimensionless transfer analysis; no final H100 parameter |
| DC09 | Eagle Jobs + Additional Energy Metrics | Historical Eagle job/telemetry joins only |
| DC16 | EuroSys Untangling GPU Power — GitHub and Zenodo artifacts | Historical H100 identifiability/transfer screening |
| DC17 | NLR RADDiT recovered payload | Rejected recovered power-domain authority |
| PW06 | AEMO 2025 DISPATCHPRICE | Historical power_v61 price array; no final scientific input dependency |
| PW10 | AEMO and GFS Jan–Mar trust-certificate inputs | Historical V29R1–V32R1 certification work, not final May exogenous arrays |
| GR02 | Earlier IEEE123_OpenDSS working case | Earlier power_v61 prevalidation; final canonical asset chain takes precedence |
| WN02 | Abilene Zhang 5-minute OD traffic archive | Provenance/sensitivity candidate; not subtracted in primary final WAN capacities |
| WN03 | RIPE Atlas RTT | No final latency/throughput input |
| WN04 | M-Lab throughput | No final latency/throughput input |

## 다운로드·inventory만 확인된 미사용 후보

| ID | Dataset | 역할 / 판정 근거 |
|---|---|---|
| DC10 | Eagle full-node power annual archives | No numeric or model consumption found in audited final dependency closure |
| DC11 | Alibaba GPU Cluster Trace v2026 job execution summary | No numeric or model consumption found in audited final dependency closure |
| DC12 | Alibaba Server Hourly | No numeric or model consumption found in audited final dependency closure |
| DC13 | Alibaba Network Hourly | No numeric or model consumption found in audited final dependency closure |
| DC14 | BurstGPT v2.0 | No numeric or model consumption found in audited final dependency closure |
| DC15 | Microsoft Azure LLM Inference Dataset 2024 | No numeric or model consumption found in audited final dependency closure |
| DC18 | NLR FastSim | No numeric or model consumption found in audited final dependency closure |
| PW08 | AEMO Generation Information spreadsheets | No numeric or model consumption found in audited final dependency closure |
| PW09 | AEMO 2026 demand/PV/dispatch extra downloads | No numeric or model consumption found in audited final dependency closure |
| WX03 | ERA5-Land Melbourne shortcut | No numeric or model consumption found in audited final dependency closure |
| GR07 | Jemena zone substations ZIP | No numeric or model consumption found in audited final dependency closure |
| GR08 | Jemena sub-transmission loops ZIP | No numeric or model consumption found in audited final dependency closure |
| NG01 | Download logs and shortcut-only administrative records | No numeric or model consumption found in audited final dependency closure |

## 판정 유보

| ID | Dataset | 역할 / 판정 근거 |
|---|---|---|
| DC20 | NLR HPC docs / SchedMD snapshots — component-level binding | QoS/hardware semantics are implemented, but exact local document-to-final-rule binding is incomplete |
| PW07 | AEMO 2024 demand/PV/price archives | No exact final dependency binding to these 36 archives found |
| WX04 | Miscellaneous raw weather / NOAA AWS folder aliases | Some idx files exist; exact relationship of all leftovers to May and V24T consumed ranges not closed |
| TR07 | SCATS archives outside explicitly bound 2019–2025 label years | 2014–2018 and later extra downloads have no fully resolved contribution to final model beyond canonical context metadata |

## 미해결 경계와 재현 한계

E 항목은 `UNRESOLVED_DATASETS.csv`에 별도로 남겼다. 원천 family의 사용이 확인됐더라도 모든 archive year나 local alias의 사용이 확인된 것은 아니다. raw source 개별 byte chain이 약한 경우 notes에 명시하고, 존재하는 preprocessing receipt 및 최종 derived SHA가 증명하는 범위까지만 채택했다.
직접 parameter source의 본문 인용은 archived registry의 선택 source ID를 사용한다. null source_SHA는 로컬 원문 다운로드가 없다는 뜻이며, 현재 웹페이지의 값으로 과거 authority를 교체하지 않았다. Capacity source에는 일부 secondary publication/directory와 engineering conversion이 포함된다.
상세 path, reader, artifact, SHA, version, section은 CSV에 모두 기록했다. EVIDENCE_FILES.csv는 이번 감사에서 직접 읽은 핵심 증거 파일의 현재 SHA를 제공한다. RAW_FOLDER_CLASSIFICATION_COVERAGE.csv는 folder-level 누락과 mixed-use alias를 확인하기 위한 보조표다.

## 산출물

- FINAL_DATASET_PROVENANCE_AUDIT.csv: 전체 dataset/subset/parameter authority 판정.
- PAPER_DATA_SOURCE_TABLE.csv: 실제 사용이 확인되어 논문 방법/검증에서 인용할 source만.
- UNUSED_DOWNLOADED_DATASETS.csv: D 후보 (administrative logs 제외).
- UNRESOLVED_DATASETS.csv: E 항목.
- 보조 evidence: inventories, source references, line-numbered searches, current SHA verification and evidence registry.

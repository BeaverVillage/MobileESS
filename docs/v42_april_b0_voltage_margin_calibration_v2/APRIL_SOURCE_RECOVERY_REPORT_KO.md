# April current V42 source recovery

PR118 exact BASE: `86d77673a5f1cc04729cc742090bba1fb72a09fa`.
April scientific voltage calibration remains incomplete because physical GPU
requests cannot be uniquely recovered from the available sources. Historical
mapping-file absence is not a STOP condition and historical requested walltime
is never promoted to service authority.

지정한 external raw root 전체 23,601개 파일을 read-only inventory했다.
23,578개 파일의 SHA256을 계산했고, 나머지 23개는 Git symbolic link
descriptor·target·object SHA를 기록했다. Directory traversal 오류는 0개다.
Raw payload 총 67,668,671,144 bytes를 hash했으며 raw 파일을 Git에 복사하지
않았다. Inventory에는 absolute path, filename, size, format, schema와 date
coverage의 근거를 저장했다. Row coverage가 없는 파일은 path metadata 또는
NOT_DECLARED로 표시하며 실제 날짜를 추정하지 않는다.

GPU/source 후보 928개를 조사했다. April Kestrel request export는 ZIP 2개이며
동일 SHA `3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f`다.
March/April parquet의 전체 50-field schema에 `gpus_requested`와
`gpu_nodes_occupied`는 있지만 ReqTRES/ReqGRES/RegTRES/Slurm JSONB는 없다.
Eagle sample의 `gpus_req` 및 controlled benchmark의 SLURM_GPUS_ON_NODE는
해당 April UID/submission request authority와 일치하지 않는다.

LFS pointer 47개 모두 다른 raw 하위 폴더의 materialized payload와 size 및
SHA256이 일치했다. Embedding payload에는 UID/GPU request가 없다. 추가
Kestrel trace 2개는 각각 2,557,884 rows이며 submission은 2025-03-10에
끝난다. 16,574 target UID와 exact ID/submission/start overlap은 0개다.
별도 text probe에서 같은 숫자가 나온 파일 7개는 Eagle 2022의 job ID 또는
다른 job의 telemetry 숫자다. Fuzzy match와 다른 시스템의 UID 재사용은
복구로 인정하지 않았다.

| Population | Initial missing observations | Recovered | Unresolved |
| --- | ---: | ---: | ---: |
| Known D-1 | 5,173 | 0 | 5,173 |
| Initial D-Day H100 arrivals | 16,284 | 0 | 16,284 |

Recovery 0%, ambiguous 0, initial SOURCE_FIELD_ABSENT 21,457 observations이다.
UTC와 -06:00의 같은 시각을 exact instant로 비교하여 문자열 표기 차이
82건을 identity failure로 잘못 분류하지 않도록 수정했다. Expanded source
inventory는 82,323 post-issue Actual observations이고 그중 GPU 누락은
20,459개다. Known 및 expanded Actual을 합친 recovery ledger는 25,632
missing observations/16,574 unique jobs다. Missing physical GPU 때문에 전체
GPUh 및 GPUh 누락 비중은 미산출이며 평균으로 채우지 않는다.

Forecast 및 realized load/PV raw inputs는 30일 확보했다. Current frozen
V42 Runtime provider identity/inference는 PASS이고 requested walltime은
feature만 제공한다. Submission-version history는 UNVERIFIED_SOURCE_PROXY다.
Submission cutoff 검사와 full request-version causality는 구분한다.
Every known row and expanded arrival is retained; no synthetic GPU filling or
workload drop occurs. Approved common reference generation follows a complete
input gate. The five known-only diagnostic mappings are not selected days.

Bundle complete 0/30, approved common reference NOT_GENERATED, B0 executed
0 days다. AIDC/workload present=true, flexibility=false, MESS=false 계약을
유지했다. Physical IT/PCC energy·served workload·Fresh AC PASS는 미검증이다.
V_PLAN/V_DA_AC/V_DDAY_AC, residual quantiles, 0.005 coverage 및 candidate band는
미산출/null이다. B1/B2/B3/May/M1 NOT_RUN, FINAL_MARGIN_ACCEPTED=false다.

Inventory 한계도 보존했다: 관련 없는 SCATS 2019 압축 method 일부와 vendor
JSON syntax/nested non-job archive schema는 별도 오류/listing으로 기록한다.
April scheduler request source가 아니며 그 오류를 source-field-absence
증거로 사용하지 않았다. Git links and LFS stubs were resolved as above.

재현 순서는 initial `audit`, whole-root `scan_external`, metadata/LFS/exact
join `finish_external`, 30-day `build_april`, then `verify --record` / `verify`다.
Runtime source files and local raw authorities must exist at the recorded paths;
no raw source code, pickle or external scripts are executed. Source bundle
generation never calls optimizer or OpenDSS. Scientific statistics must bind
the authoritative node/phase axis and all 96 slots via
`complete_calibration_residuals`.

검증: 983 tests passed, one inherited Runtime log1p warning. PR118 source,
tests, coordinator/Actual chain and production voltage constants are preserved.

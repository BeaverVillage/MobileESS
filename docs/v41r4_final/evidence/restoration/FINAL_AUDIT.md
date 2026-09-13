# V41R4 revised post-DA closure and selective Actual audit

Status: COMPLETE

{
  "total_accepted": 124,
  "existing_DA_reused": 123,
  "new_required_DA": 1,
  "primary_PASS_no_op": 111,
  "existing_final_unchanged": 122,
  "changed_by_new_restoration": 1,
  "Actual_REUSED": 122,
  "Actual_RERUN": 0,
  "Actual_NEW": 2,
  "existing_DA_reoptimization_calls": 0,
  "existing_route_search_reruns": 0,
  "hashes_verified": 50490
}

Primary Fresh is the unmodified pre-restoration check. A retained Primary FAIL can have final Fresh PASS after closure. All accepted rows below have final Fresh PASS. For May31 B2 the old SHA describes the failed original trajectory, not a previously accepted result.

| day / policy | old/new Primary Fresh | local restoration | full-PQ | Vmin / Vmax | line % | Tx current % | Tx kVA % | old → new trajectory SHA | Actual | reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 2025-05-11 / B3 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.955440508 / 1.049939349 | 57.662284 | 65.904022 | 55.744344 | 82ac4467b399 → 82ac4467b399 | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-13 / B2 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.968276389 / 1.049932576 | 64.497787 | 73.391358 | 61.920835 | c767868bce80 → c767868bce80 | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-13 / B3 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.960748567 / 1.049932122 | 64.697343 | 70.917553 | 60.430072 | 8dfed5fb0adf → 8dfed5fb0adf | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-16 / B2 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.951296889 / 1.049932902 | 66.558806 | 73.627948 | 63.218115 | f794cf75db9c → f794cf75db9c | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-16 / B3 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.961180360 / 1.049945926 | 63.596256 | 69.664692 | 61.054965 | 36ac0bcedcaa → 36ac0bcedcaa | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-17 / B3 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.951572908 / 1.049964948 | 59.034923 | 65.801088 | 55.255528 | 19abcfededd8 → 19abcfededd8 | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-19 / B2 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.951256838 / 1.049918381 | 74.427160 | 82.995270 | 71.507896 | 450ea41f3a1f → 450ea41f3a1f | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-21 / B3 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.951105228 / 1.049930472 | 74.552490 | 83.527308 | 71.725199 | 90ef978a9178 → 90ef978a9178 | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-22 / B2 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.951965095 / 1.049954207 | 75.068249 | 84.571201 | 73.631792 | 487dc5a18b05 → 487dc5a18b05 | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-25 / B3 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.951096046 / 1.049936085 | 59.908667 | 64.338816 | 55.118026 | b5df32df9665 → b5df32df9665 | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-27 / B2 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.951174089 / 1.049990170 | 68.334517 | 77.629140 | 67.839194 | 2e8660b2348a → 2e8660b2348a | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-30 / B3 | FAIL/FAIL | PASS_REUSED_BY_HASH | False | 0.958861157 / 1.049991171 | 66.576812 | 74.425991 | 63.083990 | d41eef005112 → d41eef005112 | REUSED | Existing local PASS preserved and independently replayed |
| 2025-05-31 / B2 | FAIL/FAIL | INFEASIBLE | True | 0.952891250 / 1.049570015 | 63.196761 | 98.700335 | 99.999031 | 6e748bc11c86 → 6f06b2939ff6 | NEW | Full physical PQ correction after local INFEASIBLE |
| 2025-05-31 / B3 | N/A/PASS | NOT_CALLED | False | 0.951299328 / 1.049824791 | 61.032828 | 67.411231 | 58.411891 | N/A → ff70219a71c1 | NEW | Primary Fresh PASS: no-op |

Full SHA values and all 124 policy-day rows are in FINAL_AUDIT.json.

Minimum normalized squared PQ deviation among exact-validated deterministic candidates; no global AC minimum claim.

First NEW May31 B3 bootstrap attempt failed before optimization because child environment omitted date binding; preserved, then relaunched with original dispatcher environment. No completed DA reoptimized.

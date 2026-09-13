# IEEE8500 final Day-Ahead and Actual evidence

This package records the completed 2025-05-21 IEEE8500 experiment and the B2 Actual mobility correction. Movement eligibility uses physical arrival, while electrical availability still requires connection readiness. A vehicle that has arrived may depart on its next planned trip during the unfinished connection delay. Only an arrival later than the planned departure delays movement to the next slot.

The frozen Day-Ahead P/Q clock, routes, vehicle identities, visit order, destinations and operating point remain unchanged. Unavailable commands are discarded without catch-up. Original QSAFE robust V2 acts only at the actually connected PCC, including early arrivals, and never changes executed P.

## Final results

| Policy | Planning P1 (pu) | Day-Ahead AC max phase-line loading (pu) | Actual AC max phase-line loading (pu) |
|---|---:|---:|---:|
| B0 | 0.8487691403696187 | 0.8487691403696187 | 0.9187894369215509 |
| B1 | 0.8473104038318897 | 0.8488178297477951 | 0.9249467613822655 |
| B2 | 0.8284125998911473 | 0.8355810352862253 | 0.9076065509538066 |
| B3 | 0.8257385970774200 | 0.8366269795479181 | 0.9029293071261447 |

All final Day-Ahead and Actual policies passed their stored exact AC validation. These are distinct metric scopes; planning P1 is not an Actual loading result. B1 and B3 A1 used 14,400-second continuous search budgets and retained feasible incumbents without a global optimality certificate. B3 total algorithm runtime is 38,208.3665755 seconds including reused B1; incremental runtime is 23,156.030071099987 seconds.

B2 Actual passed 96/96 convergence and control settling plus independent clean replay and battery/identity checks. Its final voltage range is 0.9600945905864189–1.0496804416457592 pu; transformer phase-current and winding-kVA maxima are 0.8346641970517626 and 0.8451283826692875 pu. One QSAFE intervention was needed. Four unnecessary readiness-based departure shifts were removed: the corrected 23-move trajectory requires zero departure shifts, zero missed nonzero P/Q commands and zero availability-curtailed energy. IEEE123 read-only regression covered 124 policy-days/95 moves with zero recorded behavioral differences.

## Frozen case

- 4,912 parsed buses, 8,639 OpenDSS nodes, 3,703 line elements and 1,226 transformer elements; 4,911 unique graph corridors. The nominal IEEE8500 name is not the parsed bus count.
- 12 AIDC sites, four MESS vehicles, 24 MESS service locations and 36 dedicated PCC transformers.
- Source 1.0400 pu, all regulator Vreg 123.5 V, alpha8500 0.50, CAPBank3 OFF; controlled capacitor logic and original ratings preserved.
- This is a declared voltage-control compatibility adaptation, not an unmodified canonical operating-point reproduction.

## Contents and provenance

- `evidence/`: final scope-specific authority, physical acceptance, regression and mobility comparison records.
- `frozen_code/`: byte-identical implementation snapshots, including electrical adapters, production orchestration, Actual replay and extraction. These retain original absolute workspace references and external V41R4 dependencies. They are provenance snapshots, not a newly installed portable runtime or instructions to rerun campaigns.
- `paper_csv/`: 11 paper-facing CSVs, audit, manifest and compact upload ZIP. Missing fields remain NA; runtime and metric limitations are documented in the audit.
- `export/`: full raw archive index/SHA and recorded export verification. The 26,437,106,617-byte tar.gz remains at the user-requested external location rather than in Git. It contains 23,709 source files and preserves historical failures and diagnostics separately from final authority.
- `SOURCE_COPY_MANIFEST.json`: SHA256, source path and size for each copied file. `.gitattributes` prevents Git newline conversion of frozen evidence.

Raw archive SHA256: `9c5519cd182c803b75c305267ed44d617d696f8a8f7c91614897bd52e30ada6e`.

The previously failed primary B2 DA decision and excluded AC-feasible diagnostic candidate are not promoted. Final B2 DA comes from the accepted frozen physical-restoration sequence. The lower-objective MF trial is not substituted for final accepted B3.

## Verification

Run `python -B science/ieee8500_2025_05_21/verify_evidence.py` from the repository root. This checks all copied hashes, CSV package integrity, final physical acceptance and two synthetic movement-boundary cases. It does not execute OpenDSS, optimization, SUMO or any scientific replay. The source results were generated and validated earlier; this PR does not regenerate them or edit existing V41R4 code/results.

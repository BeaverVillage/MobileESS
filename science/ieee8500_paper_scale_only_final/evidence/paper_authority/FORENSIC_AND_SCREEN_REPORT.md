# IEEE8500 paper authority and scale-only screening

## Authority

- Source: 2025-05-01 paper Table X production; original six-MESS PCC mapping.
- Raw archive SHA-256: `ed1d8316ce12725f5456f0f1a76440ced7f5257baf2f334f965df5775c45173e` (12665757241 bytes).
- Seven selected archive members, including B0–B3 Actual AC summaries, mapping freeze, PCC inventory and final result, are byte-identical to the paper files on disk.
- Historical inherited-source manifest: 32 records SHA verified; no missing or mismatched file.
- Table X source Actual rho: B0=0.85374621, B1=0.85259836, B2=0.84452399, B3=0.84207084.
- Paper PCC overlay SHA-256: `843e9ef83ab200f23ef17d51b3820fb1b504380be419ac0f2519d0ab49104243`; re-sited overlay SHA-256: `74ebf9959568c5fd7cbe6e32a77be4b5facecbacf62378277bd92f4dc150a1a1`.
- Paper canonical 36-PCC mapping SHA-256: `c5c0278add07309d612f616eab0cc3b31cf4a39b61cd179daae5bf75fbac9efa`; re-sited: `968e3cd0c1ee398bbf76821b39125f685ec99466aabb098c4eb8bda030681725`.
- Native feeder source and regulator/capacitor/PV files are individually hashed in `FORENSIC_AUTHORITY.json`.

## Station → electrical PCC comparison

| Station | Paper host | Re-sited host | Changed |
|---|---|---|---|
| STA01 | `m1142810` (3φ) | `sx3101194c` (1φ) | YES |
| STA02 | `m1166366` (3φ) | `m1166366` (3φ) | no |
| STA03 | `l3030197` (3φ) | `m1009763` (3φ) | YES |
| STA04 | `m1089115` (3φ) | `m1089115` (3φ) | no |
| STA05 | `l2990826` (3φ) | `l2990826` (3φ) | no |
| STA06 | `m1069310` (3φ) | `sx3141411c` (1φ) | YES |
| STA07 | `m1009763` (3φ) | `m1009763` (3φ) | no |
| STA08 | `e182732` (3φ) | `sx3027670b` (1φ) | YES |
| STA09 | `m1026855` (3φ) | `m1026855` (3φ) | no |
| STA10 | `e182746` (3φ) | `n1144668` (3φ) | YES |
| STA11 | `r18241` (3φ) | `r18241` (3φ) | no |
| STA12 | `m1027043` (3φ) | `sx2767340c` (1φ) | YES |
| AIDC01 | `l3234149` (3φ) | `l3234149` (3φ) | no |
| AIDC02 | `e182733` (3φ) | `e182733` (3φ) | no |
| AIDC03 | `m1027055` (3φ) | `m1027055` (3φ) | no |
| AIDC04 | `m1069411` (3φ) | `m1069411` (3φ) | no |
| AIDC05 | `l2688693` (3φ) | `l2688693` (3φ) | no |
| AIDC06 | `m1142814` (3φ) | `m1142814` (3φ) | no |
| AIDC07 | `m1026690` (3φ) | `m1026690` (3φ) | no |
| AIDC08 | `l3123452` (3φ) | `l3123452` (3φ) | no |
| AIDC09 | `l2728247` (3φ) | `l2728247` (3φ) | no |
| AIDC10 | `l2973833` (3φ) | `l2973833` (3φ) | no |
| AIDC11 | `m1047763` (3φ) | `m1047763` (3φ) | no |
| AIDC12 | `e192258` (3φ) | `e192258` (3φ) | no |

AIDC load PCC difference: AIDC02 `d6023352-1_int` (paper) → `e184626` (re-sited). The other 11 AIDC load hosts are equal.

## Stage A

The requested 25 BG/AIDC points were all exact 96-slot AC PASS; none reached the 0.87–0.90 band (maximum 0.8188618622). Adjacent BG refinement found:

| BG | AIDC | B0 exact rho | Vmin | Vmax | Critical slot | AC |
|---:|---:|---:|---:|---:|---:|---|
| 0.515 | 2.20 | 0.873892199 | 0.956034 | 1.041485 | 75 | PASS |
| 0.520 | 2.20 | 0.883408519 | 0.961475 | 1.041582 | 75 | PASS |
| 0.525 | 2.20 | 0.892791557 | 0.960255 | 1.041782 | 75 | PASS |

## Stage B: fixed paper DA schedule diagnostic

MESS P/S/E limits scale uniformly; efficiency, route, mobility energy and station/PCC identities do not change. This diagnostic proportionally scales the frozen paper P/Q. It does not certify a newly optimized policy or Actual.

| BG | AIDC | MESS | B0 | B1 | B2 | B3 | Vmin | Vmax | AC | Natural order |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0.515 | 2.20 | 1.0 | 0.873892 | 0.871159 | 0.863646 | 0.864492 | 0.952966 | 1.049728 | PASS | no |
| 0.515 | 2.20 | 1.5 | 0.873892 | 0.871159 | 0.864434 | 0.882231 | 0.928392 | 1.061151 | FAIL | no |
| 0.515 | 2.20 | 2.0 | 0.873892 | 0.871159 | 0.867850 | 0.915805 | 0.899620 | 1.071256 | FAIL | no |
| 0.520 | 2.20 | 1.0 | 0.883409 | 0.880637 | 0.872888 | 0.874530 | 0.952081 | 1.049352 | PASS | no |
| 0.520 | 2.20 | 1.5 | 0.883409 | 0.880637 | 0.871877 | 0.889659 | 0.927581 | 1.060687 | FAIL | no |
| 0.520 | 2.20 | 2.0 | 0.883409 | 0.880637 | 0.877377 | 0.915076 | 0.898730 | 1.068878 | FAIL | no |
| 0.525 | 2.20 | 1.0 | 0.892792 | 0.889891 | 0.882148 | 0.878711 | 0.951465 | 1.048977 | PASS | YES |
| 0.525 | 2.20 | 1.5 | 0.892792 | 0.889891 | 0.881430 | 0.897393 | 0.926524 | 1.060401 | FAIL | no |
| 0.525 | 2.20 | 2.0 | 0.892792 | 0.889891 | 0.887271 | 0.915552 | 0.897828 | 1.068318 | FAIL | no |

**Selected for one full production:** BG=0.525, AIDC=2.20, MESS=1.0. The frozen-schedule diagnostic has B0−B3=0.0140804653 and B2−B3=0.0034372629. The MESS 1.5/2.0 proportional-dispatch failures are voltage failures of that diagnostic dispatch, not a proof of optimization infeasibility.

The paper B3 Actual had a 0.0013131923 kWh MESS06 Emin shortfall. Any new production result with any SOC/energy violation must fail the physically clean gate; the historical exception is not imported as an allowance.

## Status

```ini
PAPER_CONFIG_RESTORED = TRUE
RESITED_PCC_USED = FALSE
FEEDER_MODIFIED = FALSE
SCALE_ONLY_MODIFICATION = TRUE
FULL_PRODUCTION_COMPLETE = FALSE
```

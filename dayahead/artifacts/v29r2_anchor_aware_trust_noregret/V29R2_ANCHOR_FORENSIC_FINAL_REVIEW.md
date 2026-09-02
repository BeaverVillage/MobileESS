# V29R2 pre-April anchor-physics forensic

RESULT CLASSIFICATION: `V29R2_ANCHOR_SOURCE_CORRECT_MIXED_STRESS`

- Source/materialization hashes: PASS (90 days, 2,250 GFS leads, 13,500 messages)
- F3 frozen V29R1 Fresh-summary reproduction: PASS; maximum field error `0.000e+00`
- Native-anchor NPZ vs frozen-state replay diagnostic: voltage `1.414e-05` pu, current `5.669e-02` A
- Electrical construction audit: `PASS`; deterministic defect found: `False`
- Violation population: 26/26 exact frozen days
- Non-violation controls: 2025-01-11, 2025-01-15, 2025-01-19, 2025-02-05, 2025-02-14, 2025-03-01, 2025-03-03, 2025-03-05, 2025-03-13, 2025-03-16
- Component accounting maximum error: `0.000e+00`

The F0--F3 experiment preserved the exact feeder, source scaling, PF, PCC, ratings,
native D1 tap/cap acquisition, and frozen-state replay semantics.  The frozen D1 anchor
contains MESS P=Q=0, so F2 is exactly F0 and F3 is exactly F1.  No altered-control
experiment was promoted to authority.

Proceed beyond Stage A: `True`.

# V31 V30 Safety/Headroom Forensic

Result: **V31_MIXED_AIDC_DELIVERABILITY_LIMITATION_DIAGNOSED**

This namespace is diagnostic only. It does not change V30 production science,
the four official B0/B1/B2/B3 cases, the Stage-1 or Stage-2 objectives, the
physical model, or the current production no-regret margin.

`D_CUR`, `D_PAIR`, and `D_ZERO` are all `NON_AUTHORITY_DIAGNOSTIC_ONLY`.

The Jan-Mar source retained exact aggregate maximum-absolute candidate errors
but not signed slot-line-phase residual arrays. The anchor predictor is exactly
the Fresh anchor, so the auditable paired diagnostic uses its exact zero anchor
error and the retained one-sided candidate bound. Correlation is undefined
because anchor error variance is zero; no signed cancellation was fabricated.

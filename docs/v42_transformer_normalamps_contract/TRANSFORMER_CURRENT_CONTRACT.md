# V42 common physical security successor

All B0/B1/B2/B3 use four independent physical constraints:
- Actual voltage: 0.95–1.05 pu (Planning stage-specific voltage bands are unchanged).
- Line phase current: existing source-backed Line NormAmps; existing thermal polygons unchanged.
- Transformer phase current: parent-terminal abs(I_A) <= compiled OpenDSS NormAmps.
- Transformer apparent power: unchanged source-backed winding kVA rating.

Current uses first-winding NormAmps only because every oriented transformer parent is terminal 1; otherwise STOP. Missing/nonfinite/nonpositive NormalAmps means STOP. CTPrim, taps, RegControl settings and synthetic line-rating files never supply a transformer-current denominator. Compiled defaults are source-backed by exact DSS graph and engine version, not generated replacement limits.

Planning affine constants and gradients are denormalized using the exact archived rating_a then renormalized by NormalAmps. Only transformer-current columns change. Native and compressed transformer_current <= 1 rows consume these bound coefficients. Line current columns, all voltage/flow/branch-limit arrays and transformer-kVA rows remain unchanged. Coefficient/current-authority hashes change; mismatching or unbound real IEEE123 rows fail the current-authority gate. Small synthetic row-geometry fixtures do not claim a compiled physical authority.

Actual source().branch_measurement routes to v42_thermal.measurement and uses the same authority SHA; the old external measurement is retained under legacy_branch_measurement for explicit historical auditing only. New Fresh AC receipts and May Planning freezes carry the current contract/SHA. Reclassification validates all four constraints from immutable raw arrays, not prior current_pu labels. Old evidence is preserved and is not relabeled in place.

Old M1 UB/LB/gap certificates are historical and SUPERSEDED for this changed scientific model. require_certificate rejects missing or unequal current authority/schema. A separate successor M1 solve is required; no full M1 solve is run here. P1/P2, voltage margins, line limits, transformer kVA, controllers, capacitors, P/Q, workloads, Runtime/CC4 and capacity queue are unchanged.

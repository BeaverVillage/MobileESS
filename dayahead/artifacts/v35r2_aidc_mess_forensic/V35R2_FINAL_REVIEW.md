# V35R2 final review — user-capped Apr01 rerun

Primary classification: **V35R2_MESS_MOBILITY_UNRESOLVED**.

The common current defect was repaired with `ANCHOR_GRADIENT_MATCHED_16_FACE_APPARENT_POWER_EPIGRAPH_V1`. On Apr01, line-current MAE fell from 0.003392230 to 0.000887559 pu and MESS benefit direction agreed: B2-B0 Planning -0.055786717, Fresh -0.035452644. No movement was forced.

The user explicitly capped repaired execution at Apr01. Therefore all 80 case-days remain scientifically invalidated, 4 were rerun, and 76 are deferred. The Apr01 B2/B3 schedules still have Fresh voltage violations (72 and 73 rows), MOVE remained zero, no destination net-move MIP audit was completed, and the Apr01-20 AC correction was not rebuilt.

## Apr01 AIDC finding

- Planning/Fresh rho deltas: -3.47362341e-06 / -2.91876588e-06.
- Critical-slot flexible IT fraction: B0 0.0890%, B1 0.7938%.
- Shifted workload at the binding slot: 0.138018 of 95.063852 node-hours (0.1452%).
- Provisional Apr01 interpretation: flexible-fraction/timing limited. Full Apr01-20 classification remains `AIDC_EFFECT_UNRESOLVED`.

## Apr01 MESS finding

- Natural MOVE count across B2 and B3: 0.
- B2 P/Q usage: 19506.809 kW-slot / 53724.237 kvar-slot.
- B3 P/Q usage: 21933.019 kW-slot / 55678.949 kvar-slot.
- Service mapping is electrically diverse (24 unique PCCs, 24 distinct fingerprints); it was not changed.
- Initial depots were changed by a frozen road-topology-only rule to STA01/STA12/STA08/STA06.

## Stop condition

Apr21 and May were not opened. No push or merge was performed. The repaired Apr01-20 authority is **not** ready for prospective Apr21 validation.

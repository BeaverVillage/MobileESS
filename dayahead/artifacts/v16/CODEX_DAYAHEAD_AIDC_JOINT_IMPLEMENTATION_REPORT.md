# CODEX Day-Ahead AIDC Joint V16 G5/G6 Freeze Report

## Status

G5/G6 passed. The Proposed AIDC RC-MQT production model is frozen after April-only selection and exactly one Aug19-Apr30 refit. The May primary campaign and June replication were not started.

## Frozen mapping authority

All feeder/PV/AIDC-PCC/Mobile-ESS-PCC sources were located and independently re-hashed. The six frozen digests match exactly; no replacement mapping or fitting was performed. See `FROZEN_MAPPING_AUTHORITY.json`.

## Selected model

- candidate: C02
- lookback: 1344 slots
- d_model / encoder layers / heads: 64 / 2 / 4
- dropout / learning rate: 0.2 / 0.0003
- production seed / refit count: 20260828 / 1
- weights SHA-256: 30603de0f1cf19e84d2280970aa8a74e6aff2b63cfa11d00200e161860bfc4bc
- final weight/config fingerprint: 309d9019c8ff97cce92953755b96100717d00f7fa6cfb5311caf8797c14d43e3

## Scientific access firewall

- April validation days: 30, exactly 96 slots each.
- May/June loader access count: 0.
- May/June forecast rows: 0.
- Ex-post D1 eligibility field access count: 0.
- Post-hoc calibration: NONE_V1.

## Stop point

Stopped after G5/G6 production freeze. C7 authority readiness is PASS, but no May forecast, B0-B3 campaign, integrated scientific solve, G13 QSTS, G14 result campaign, or June replication was run.

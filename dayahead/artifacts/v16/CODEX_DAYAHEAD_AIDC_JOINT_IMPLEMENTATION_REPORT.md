# CODEX Day-Ahead AIDC Joint V16 C7/C8/C9 Pre-production Report

## Status

G5/G6 remains frozen and C7/C8/C9 pre-production integration passed on the April-only, explicitly non-scientific engineering fixture. The May primary campaign and June replication were not started.

## Checkpoint

The 25-path G5/G6 freeze was committed before C7 work at `9e772de327148ef8dfa4aad397bcaa623d443119`.

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

## C7/C8/C9 result

- reference B0/B2 byte-identical SHA-256: `49696732b774feeb3687b2dc4377eedd512ecb7e625e7cd3c23f1b3c32205bba`
- residual P/G minima are nonnegative; terminal service-parity residual is zero
- monolithic objective: `0.5253623480754915` (optimal)
- Standard Single-Cut BD: objective `0.5253623480754914`, 2 iterations, 2 cuts, gap 0
- CL-MC-BD: objective `0.5253623480754914`, 2 iterations, 6 cuts, gap 0
- G11: PASS; G12: PASS_NON_SCIENTIFIC_PREPRODUCTION

## Corrected final-April gate order and current stop point

The earlier reduced-star result remains engineering-only evidence. The authoritative order is now `April full IEEE123 integration -> final G12 -> G13 -> G14 -> C12`; G13 is a prerequisite for C12, not a post-C12 activity.

The exact full IEEE123 source release passed, including native controls and the frozen nonuniform 48-Rack capacity weights. C7 then failed closed at `FAIL_REFERENCE_DELTA_DECOMPOSITION`: the fixed Rack-ID-priority reference schedule makes the frozen GPU residual negative in 96 Rack/slot cells (minimum `-14.359713515786275`). No clipping, refitting, or replacement spatialization was applied. Consequently final G12, G13, G14, and C12 were not run, and no production freeze token was minted.

No May forecast, May reference schedule, May B0-B3 campaign, or June replication was created. May and June loader access counts remain zero.

# V29R1 Jan--Mar causal electrical source-authority recovery

RESULT CLASSIFICATION: `V29R1_JANMAR_TRUST_SOURCE_AUTHORITY_BLOCKED`

## 1. Is the blocker missing raw data or only an April-only materializer?

Both. The production materializer is April-only, but generalization alone is insufficient:
required local GFS coverage is 0/90 and both AEMO forecast categories are only 30/90.

## 2. Exact April source categories

All 13 names were read directly from the verified April `2025-04-02` source-day manifest:
`['kestrel_realized_h100_workload', 'gfs_d1_weather', 'noaa_melbourne_observed_weather', 'causal_grid_demand_forecast_vintage', 'realized_grid_demand', 'causal_rooftop_pv_forecast_vintage', 'realized_rooftop_pv', 'traffic_forecast', 'realized_traffic_replay', 'travel_time_input', 'travel_energy_input', 'mess_route_location_availability', 'daily_initial_state_authority']`.

## 3. Which categories are required for trust certification?

`['gfs_d1_weather', 'causal_grid_demand_forecast_vintage', 'causal_rooftop_pv_forecast_vintage']`. They supply C1 weather and the production feeder demand/PV background.
Actual, PI, Kestrel realized jobs, traffic, and MESS-support categories are not required for
this AIDC physics certificate; no reduced electrical/thermal substitute was introduced.

## 4. Jan--Mar raw coverage by category

Required coverage is GFS 0/90, demand forecast
30/90, and rooftop-PV
forecast 30/90. Full details
for all 13 categories are in the CSV/JSON coverage artifacts.

## 5. Jan--Mar causal coverage by category

GFS has 0 causal local days. Production AEMO parsing reconstructs 2025-03-02 through
2025-03-31 only. All used/missing records retain `future_actual_used=false`.

## 6. Missing date ranges

GFS is missing 2025-01-01 through 2025-03-31. Demand/PV forecasts are missing
2025-01-01 through 2025-03-01; Mar-1 specifically requires the February archive.

## 7. Any external downloads required?

Yes: NOAA GFS D-1 inputs for all 90 days and AEMO December 2024, January 2025, and
February 2025 monthly demand/PV forecast archives. No download was authorized or performed.

## 8. Jan--Mar materialized day count

0. The gate failed before cache creation; the April production cache was not altered.

## 9. April/Jan--Mar contract equivalence

Status `NOT_EVALUATED_REQUIRED_RAW_AUTHORITY_INCOMPLETE`. The April schema and required Jan--Mar contract
are frozen, but byte/schema equivalence cannot be tested before legal materialization.

## 10. Causality audit

Future-Actual, NOAA-for-GFS, realized-demand-for-forecast, realized-PV-for-forecast, and
April substitution counts are all zero.

## 11. Tests

12/14 audit/pre-materialization gates passed; 2 materialization-dependent
tests were not run and no failed test was hidden.

## 12. Preservation audit

Status `PASS`; protected mismatch count is
0 and April cache remained unchanged.

## 13. Artifact SHA

All non-circular artifacts are inventoried by SHA-256.

## 14. Final Git status

Recorded after commit in the task handoff. No push or merge is performed.

## 15. Can V29R1 Stage-2 trust certification now resume?

No. Required causal source authority is not 90/90.

V29R1 trust certification CANNOT resume because the Jan–Mar causal electrical source authority is NOT READY.

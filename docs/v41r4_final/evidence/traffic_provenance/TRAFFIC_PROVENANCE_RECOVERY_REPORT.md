# V41R4 Traffic production provenance recovery

**FINAL_TRAFFIC_PROVENANCE_RECOVERY: PASS**

`V41R4_TRAFFIC_FULL_LINK_PROVENANCE_RECOVERY_PASS`

The exact PR #19 frozen Traffic predictor is bound to the final V41R4 May inputs for **31/31 days and 62/62 B2/B3 policy-days**. `VALIDATION_ONLY_RERUN_REQUIRED = NO`. All scientific reexecution counts and external result contamination counts are zero.

## Recovered chain

1. The final raw archive's retained May `M1_RESULT.json` preserves `external_search_files` records for each external `M1_IDENTITY.json`. All 62 external files were found at their exact referenced paths and matched the archived file SHA and size. Their canonical identity hashes also verified.
2. These execution identities name the daily shared `TRAFFIC_FORECAST.npz` and `ROUTE_TABLE.json.gz`, with file hashes and separate canonical hashes. All 31 forecasts and route caches matched both hashes. Every route-cache row binds the expected forecast canonical SHA and route graph SHA.
3. Each forecast's stored generation metadata identifies model ID, parameter SHA, data SHA, graph SHA, normalization SHA, issue cutoff and output axes. The complete stored arrays and metadata reproduce the expected canonical bundle hash; this is a byte/serialization audit, with no prediction calls.
4. The existing `CURRENT_TRANSITIVE_INPUT_INVENTORY.json` binds those same daily file/canonical identities to the frozen checkpoint, model authority and Safe ETA calibration file hashes. All 31 records reference the same three authority files, and their actual bytes match the recorded SHA and size.
5. The checkpoint bytes match PR #19. Its stored parameter dictionary hashes to the production forecast `model_sha`, and its effective graph smoothing is **0.0**. The seasonal checkpoint tensor is `[7,288,509]`; all forecast link axes equal its 509-link axis. The source default 0.08 is not the loaded parameter.

There is no reliance on a current source statement alone. The previously missing archived-to-external receipt edge is now present and verified. No new forecast-generation run or historical receipt was synthesized.

## Exact identities

| Identity | Verified value |
|---|---|
| Production model | `DA-RQSTG-DIRECT-288-V1` |
| Checkpoint SHA256 | `3da2ced5322dd2bf6d02a665043ce182db60cc82b671d9ac92d7eebd3963520b` |
| Model/parameter SHA | `93a30f54be207f6579a51af32ab6f84fbbb2608ffead3da6332886847a6163e6` |
| Data SHA | `c2e532212eba796b652bdd283a8127c2343b9305146d387975f4c69c2a848183` |
| Graph SHA | `658fb2e56867a50597e9a21899748d8171439deda852e7db4f3339a99f71dd3d` |
| Normalization SHA | `1572bb955df254e71ef0dc81b2264885f676f9cfad854f497155c795c2d417c2` |
| Safe ETA calibration file SHA256 | `353f124bdda33b1fd408f4f810b762f433bbe25d8c5c13b191fe1b0d6e36ff99` |
| Model authority file SHA256 | `7544a33649acc8b790871e22da37c3be78644f5e184ac3ce8a56578e2c035854` |
| Transitive inventory file SHA256 | `ba220f2280ff5e8cd8b6b9d3a3396ff9aa9fc41d0abeb51533b032d94ab5fa94` |
| Effective graph_smoothing_weight | 0.0 |

The data SHA is an exact PR19 aggregate match in all 31 stored forecast metadata records. It identifies the frozen model's data authority; this audit does not read external optimization outcomes into paper results.

## Paths and May coverage

The execution root is `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance`, established by the archive's embedded paths and PR42 source snapshot. Its current Git HEAD is `53cf2ff8386a8fe0562454cfeec4f0dd8ec186e3`. The workspace has pre-existing modifications; its current HEAD alone was not treated as proof of execution.

The V41 `SOURCE_REPO` points to `C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt`. Its recovered inventory is `C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\artifacts\v40h_production_integrity\CURRENT_TRANSITIVE_INPUT_INVENTORY.json`. Shared forecasts and route tables are under `dayahead/cache/v37_may_locked_final/traffic/shared/traffic/YYYY-MM-DD/` in that root. The checkpoint is `C:\codex_mobileess_workspace\MobileESS_v35r3e_r1_beam\dayahead\artifacts\v33m3_causal_dayahead_traffic\V33M3_FINAL_MODEL.npz`.

`TRAFFIC_PRODUCTION_DAY_BINDINGS.csv` has all 62 final policy-day rows and distinct file/canonical hashes. `TRAFFIC_PROVENANCE_CHAIN.csv` records referenced hashes versus actual hashes, `SEARCHED_PROVENANCE_LOCATIONS.csv` records exact-file/root/Git checks, and `EMBEDDED_PROVENANCE_PATHS.csv` records the relevant archive file, field, original path and expected hash. Irrelevant solver-cache leaf paths are omitted from the Traffic path table.

All 31 forecasts have `[288,509]` Q10/Q50/Q90 arrays, model ID and four authority SHAs matching PR19, D-1 18:00 fixed-AEST issue times, D-1 17:55 maximum input times, `causality_pass=true`, and zero future Actual reads. These are stored causal receipts; this audit did not replay the generator's data reads.

## Final command fingerprint

All **95 final committed departures** exactly match their day's route-cache Q10, Q50, Q90, Safe ETA and ordered route-link list, keyed by origin service, destination service and departure slot. No tolerance was used for this comparison. `VERIFIED_DETAILS.json` preserves final archive SHA, archived M1 SHA, external M1 receipt and per-departure path hash. The earlier Safe ETA residual comparison had floating subtraction error up to 1.9895196601282805e-13 seconds; direct stored-value comparison here is exact.

The final May31 B2 restoration command is checked against the retained May route input, so restoration P/Q changes do not substitute an earlier final output. The 95 provenance departures remain distinct from the **72 deduplicated operational observations** in the existing ML table.

## Metric attribution and preservation

The PR19 held-out validation can now be attributed to the exact V41R4 production predictor:

| Metric | Value |
|---|---:|
| Q50 MAE | 28.778100967407227 s |
| Q50 WAPE | 4.140258207917213% |
| Q90 empirical coverage | 0.8831677945135705 |
| Quantile crossings | 0 |

These are the original held-out dates 2024-01-16, 2024-02-14 and 2024-03-15, N=439,776 link-slot targets. They are **production-bound prior held-out validation**, not May full-link error measurements. No performance metric was recomputed. Target semantics remain observation-anchored calibrated simulation rather than native observed five-minute accuracy.

The existing selected-route results stay 52.6455134707414 s ETA MAE, 0.9444444444444444 Safe ETA coverage, and 142.59338453682616 s mean margin, N=72. All eleven corrected paper CSVs remain byte-identical, including their historical four NOT_AVAILABLE cells. This provenance-only delivery does not create a replacement paper export. Runtime/H4, physical results and terminal/deadline interpretation are unchanged.

## Git and audit scope

PR19, PR39, PR40, PR41 and the pre-audit PR42 HEAD were inspected by exact commit. Their ten prior authority documents and seven core source/adapter files all match PR19 bytes. `GIT_PROVENANCE_EVIDENCE.json` records the individual hashes. The inventory is an existing external receipt, not a file tracked at PR42; its SHA-bound daily inputs agree with the execution identities recorded in the final archive.

The previous archive-only PARTIAL report remains a valid historical result for its narrower scope. This expanded, explicitly authorized provenance recovery closes its missing links. The compressed archive was not rescanned or altered; the previously verified mirror was used only after each consumed archive member passed its recorded SHA.

Training, inference (including validation-only inference), SUMO, SCATS processing, Safe ETA recalibration, Dijkstra, MESS/Gurobi/OpenDSS, Actual replay, AIDC optimization and policy reruns: **0 each**. Only Traffic identity evidence from external workspaces is used. PR42 receives small audit evidence; no model or forecast binary is copied.

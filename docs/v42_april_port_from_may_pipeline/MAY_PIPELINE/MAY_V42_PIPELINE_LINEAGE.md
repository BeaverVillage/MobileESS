# May current-V42 construction lineage and April port

The GPU field in the May native bundle was a direct raw-request attribute inherited through historical reference/state tables. The upstream V37 producer excluded jobs whose request fields were missing or invalid. It did not restore missing GPU requests through a version join, immutable submission reconciliation, or source-backed node-to-GPU derivation. Consequently May input completeness does not establish complete authority for the current April population. Current April preserves those rows and current frozen Runtime.

This audit reads construction code and input provenance metadata. May workload values, coefficients, voltage trajectories, Actual outputs, policy results, and calibration outcomes are not donors. No May scientific run is performed. Persisted SHA references below identify lineage; a persisted input hash is not an assertion that its outcome arrays were opened.

## Exact boundary

`c0783fadbbca282f2ce580c45fe82feaed71584c` is the PR121 base. The operational chain remains Planning → immutable freeze → D-Day → Fresh OpenDSS. The extra DA AC curve is offline calibration only. The new reusable builder is `v42_april_port/builder.py::build_v42_day_input_bundle`, with schema `V42_DAY_INPUT_BUNDLE_V1`.

## Stage trace

### 1. RAW_WORKLOAD_SOURCE

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v37\aidc_materializer.py::load_state_source` (line 150; SHA `64dfd70b9b898cc3c0b870ed0770bb042831a90a64090bc0f55ba7017f1f1022`).

Authority: id; submit_time; start_time; end_time; gpus_requested; nodes_req; processors_req; memory_req; wallclock_req; partition; qos; account_hash. Derived: source_member; wallclock_seconds.

Units: {"gpus_requested": "requested GPU count, may be null", "nodes_req": "requested nodes", "wallclock_seconds": "seconds feature/old rule only"}. Resolution: Scheduler events, not regularly sampled. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: April March/April raw projection only; generic builder retains missing rows. Old member<=May cutoff not scientific authority.

### 2. CANONICAL_JOB_IDENTITY

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v37\aidc_materializer.py::load_state_source` (line 150; SHA `64dfd70b9b898cc3c0b870ed0770bb042831a90a64090bc0f55ba7017f1f1022`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41\data.py::normalize` (line 43; SHA `796fccf3179be61a1ed4f315e41dfc1142f6993de807a9503e3c9b0eed9dd8f4`).

Authority: raw id; submit_time. Derived: job_uid=str(raw.id); job_id=str(raw.id).

Units: {"job_uid": "opaque full source UID; raw numeric job_id is not the key"}. Resolution: one row per UID/submission. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: Exact UID plus normalized aware submission; reject duplicate or conflicting matches, never fuzzy/neighbor/May joins.

### 3. D1_KNOWN_POPULATION

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v37\aidc_materializer.py::snapshot_at_issue` (line 211; SHA `64dfd70b9b898cc3c0b870ed0770bb042831a90a64090bc0f55ba7017f1f1022`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_may01\prepare.py::job_ledger` (line 68; SHA `4f299616c023c508cc03ae065bfabf6241aec8c1729fee6c1a64f87951dfcf44`).

Authority: submit_time<=issue; observed start<=issue if RUNNING; completion event before/at issue. Derived: state_at_issue; known_running_start; operating_day.

Units: {"state": "RUNNING/PENDING", "known_running_start": "aware timestamp"}. Resolution: event snapshot at issue. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: Use current April snapshot; future starts/ends not inference fields. Retain every source-known row regardless of GPU completeness.

### 4. GPU_REQUEST_AND_GANG

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v37\aidc_materializer.py::_submission_complete` (line 113; SHA `64dfd70b9b898cc3c0b870ed0770bb042831a90a64090bc0f55ba7017f1f1022`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v37\aidc_materializer.py::_jobs_and_ledger` (line 417; SHA `64dfd70b9b898cc3c0b870ed0770bb042831a90a64090bc0f55ba7017f1f1022`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40d_actual\inputs.py::frozen_jobs` (line 45; SHA `d37f290f01952edc51a69cd8a603038bfe8b7e396dd5d44ea626613372f0b1ee`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41\common.py::build` (line 17; SHA `e21bde3188d1a246dbebfb50262c7722782ff2fa69b7e9b331ff2fba8a9d8a75`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_may01\prepare.py::job_ledger` (line 68; SHA `4f299616c023c508cc03ae065bfabf6241aec8c1729fee6c1a64f87951dfcf44`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native_inputs.py::main` (line 15; SHA `bf32fa885007f31265b09fd1511ea3c6543927a8efd5883cace9be8245e9a999`).

Authority: raw gpus_requested. Derived: requested_gpus; requested_GPU; GPU_gang=int(requested_GPU).

Units: {"GPU_gang": "whole indivisible GPU count"}. Resolution: job attribute. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: Port exact direct raw mapping; supersede historical exclusion of missing request rows. No request-version reconciliation, immutable submission certification, node-count derivation, or GPU imputation was implemented in this producer.

### 5. RUNTIME_AND_SERVICE

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native_inputs.py::memory_mib` (line 9; SHA `bf32fa885007f31265b09fd1511ea3c6543927a8efd5883cace9be8245e9a999`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native_inputs.py::main` (line 15; SHA `bf32fa885007f31265b09fd1511ea3c6543927a8efd5883cace9be8245e9a999`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\runtime.py::FrozenQ50` (line 15; SHA `86f578f315c39dd0c4e858df5d0ee04a79f16bc2c3d033af4beac7fe9ebd5e2a`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\state.py::planning_remaining` (line 19; SHA `0a7723650697869d4c7023a53d2ae9a8444c9859ccf1b11acf17338472ef0e36`).

Authority: frozen V10::T3_ISOTONIC_ROLLING14_calibrated; submission request features only; observed causal elapsed RUNNING. Derived: Q50_total_seconds; nominal_remaining_seconds=max(Q50-elapsed,0); service_slots=ceil(remaining/900).

Units: {"Q50": "seconds", "service_slots": "900 second slots"}. Resolution: one frozen inference per submitted job. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours; provider available_at<=event; max calibration completion strictly before provider availability.

April: Keep current FrozenQ50; supersede historical RollingQ90/requested_remaining/requested_walltime service. Requested walltime stays ML feature only.

### 6. STATE_AND_RESIDUAL_SERVICE

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\state.py::planning_remaining` (line 19; SHA `0a7723650697869d4c7023a53d2ae9a8444c9859ccf1b11acf17338472ef0e36`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\state.py::EpisodeLedger` (line 29; SHA `0a7723650697869d4c7023a53d2ae9a8444c9859ccf1b11acf17338472ef0e36`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native.py::canonical_jobs` (line 11; SHA `6fddb5938544aef952f86cc72e836a46c657ed66a6a594f5d842346900beebba`).

Authority: observed RUNNING/PENDING; known_running_start; physical site if sourced. Derived: hard RUNNING gang occupancy; nominal remaining; overrun_uncertainty; control-boundary release only after observed completion.

Units: {"elapsed": "seconds", "physical_GPU": "GPU count"}. Resolution: 900 second controls plus causal state events. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours; Actual observed events only at event time.

April: Q50 expiry does not imply physical completion; keep expired RUNNING hard occupancy until source-authorized causal release.

### 7. SITE_RACK_COMPATIBILITY

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41r2\reference.py::materialize` (line 12; SHA `9b981c854575a6fe4777e52908be85d2f5edd927c655b8c417b57302c040c075`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_may01\prepare.py::job_ledger` (line 68; SHA `4f299616c023c508cc03ae065bfabf6241aec8c1729fee6c1a64f87951dfcf44`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native.py::canonical_jobs` (line 11; SHA `6fddb5938544aef952f86cc72e836a46c657ed66a6a594f5d842346900beebba`).

Authority: source physical RUNNING site when available; frozen rack compatibility limits. Derived: compatible_sites satisfying gang<=site cap and <=some rack compatibility ceiling.

Units: {"site": "AIDC01..AIDC12", "rack ceiling": "GPU; not additive facility capacity"}. Resolution: job/site plus fixed 900 second execution segments. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: Do not copy historical May sites/reference start. PR121 common scheduler uses physical source site first; documented deterministic grid-blind fallback for missing site.

### 8. FACILITY_CAPACITY

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native.py::canonical_jobs` (line 11; SHA `6fddb5938544aef952f86cc72e836a46c657ed66a6a594f5d842346900beebba`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_temporal\native.py::native_jobs` (line 38; SHA `9e93c03217bad5dff2c318a91d760c85d875a05b6b42cc5d5464107000546212`).

Authority: current V42 site vector [80,40,80,40,100,80,40,80,40,80,40,80]; gang splitting false. Derived: site occupancy; whole-gang compatibility envelope.

Units: {"site capacity": "GPU; sum 780", "rack aggregate contribution": "0"}. Resolution: 120 issue-origin slots; 96 operating day slots. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: Retain current V42 780 GPU case-study vector and non-additive racks; old 624 GPU authorities are superseded.

### 9. AIDC_IT_POWER

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_temporal\native.py::load_power` (line 64; SHA `9e93c03217bad5dff2c318a91d760c85d875a05b6b42cc5d5464107000546212`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_temporal\native.py::grid_binding` (line 84; SHA `9e93c03217bad5dff2c318a91d760c85d875a05b6b42cc5d5464107000546212`).

Authority: source constants IDLE_W_PER_GPU and CENTER_SWING_W_PER_GPU; site capacity; occupied/nominal GPU. Derived: P_IT_kw=idle_kw_per_GPU*capacity+swing_kw_per_GPU*active_GPU.

Units: {"P_IT": "kW", "energy": "kWh=sum kW*0.25h"}. Resolution: 96 x 12 site slots. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: Current power conversion reparameterized by day/weather/capacity; do not read or copy May IT/PCC arrays. Reserve headroom is not electrical load.

### 10. AIDC_PCC_POWER

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_temporal\native.py::load_power` (line 64; SHA `9e93c03217bad5dff2c318a91d760c85d875a05b6b42cc5d5464107000546212`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\c1_affine.py::endpoint_secant` (line 125; SHA `912c870a2c062431cac60f2157f3b4399ad824119facdafbd7ac3f1788c40c13`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\c1_affine.py::exact_c1_pcc_kw` (line 68; SHA `912c870a2c062431cac60f2157f3b4399ad824119facdafbd7ac3f1788c40c13`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40d_actual\power_replay.py::power_from_execution` (line 12; SHA `cbdcb9196f02d434d80f53d951bae7e43bc68ad44c5f05d3f419e5502fd0aaf2`).

Authority: C1 quasistatic parameters; t_wb_c; rh_pct; source PF. Derived: Planning endpoint secant P_PCC=slope*P_IT+intercept_kw; Actual exact C1(P_IT,realized weather); Q_PCC=P_PCC*tan(acos(PF)).

Units: {"P_PCC": "kW positive consumption", "Q_PCC": "kvar positive load"}. Resolution: 96 x 12 site slots. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours for forecast weather; realized weather only Actual.

April: Current C1 semantics retained. Forecast and realized weather paths passed explicitly; no constant arbitrary PUE substitution.

### 11. LOAD_PV_WEATHER

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\source_cache.py::day_root` (line 30; SHA `20dd3c1848ff3a86bff2b19c967f819f219fb32c386eb448af21623dfe3e73a0`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40d_actual\exogenous.py::load` (line 9; SHA `5e46ec34e152da8e6c90b8074b3cf8e577db29c119e3c86a0107ecb9925499a3`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\tools\audit_v40d_actual_replay.py::aemo_audit` (line 164; SHA `99558057f12dc7e9f80372a7459210640ed89d22dfb679404cfa329aed2278e0`).

Authority: aemo_forecast demand_mw_96/pv_mw_96/timestamps_96; gfs_d1_weather t_wb_c/rh_pct; realized AEMO VIC1 TOTALDEMAND/POWER; NOAA observed weather. Derived: 5 minute dispatch sampled at exact quarter-hour ends; 30 minute measured PV repeated twice, energy conserved; observed hourly weather interpolated to quarter-hour starts.

Units: {"raw regional load/PV": "MW", "weather": "Celsius, percent"}. Resolution: 96 quarter-hour intervals; raw AEMO demand5min/PV30min/weather hourly. Cutoff: Forecast issue<=D1 cutoff; actual files only Actual; interval-end date semantics may end next-day00:00.

April: Use each April date raw forecast/realized inputs and current raw provenance; same unit/axis semantics; never forecast-to-actual substitute.

### 12. CC4_COMMON_FORECAST

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_may01\prepare.py::main` (line 178; SHA `4f299616c023c508cc03ae065bfabf6241aec8c1729fee6c1a64f87951dfcf44`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\workload.py::ForecastBook` (line 42; SHA `10320df9beaa0df89fd0d80b763595ee95fb57eb82f5a3d53ed9373d4517daed`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\workload.py::profile` (line 30; SHA `10320df9beaa0df89fd0d80b763595ee95fb57eb82f5a3d53ed9373d4517daed`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_temporal\native.py::grid_binding` (line 84; SHA `9e93c03217bad5dff2c318a91d760c85d875a05b6b42cc5d5464107000546212`).

Authority: common frozen C0 Q50/Q90 lifetime GPUh by target submission hour; pre-May execution-lag kernel. Derived: nominal_GPU convolution; uncertainty headroom=max(Q90-Q50,0); causal explicit submission depletes only its same cohort.

Units: {"C0_Q50/C0_Q90": "GPUh per target hour", "nominal_GPU": "GPU count"}. Resolution: 24 hourly cohorts -> 96+ quarter-hour lag slots. Cutoff: Only target day/index/issue metadata projected; no actual labels; no individual future UID before submission.

April: Retain common ML in B0; April day-index binding required; no May C0 value donation. Anonymous forecast stays aggregate and cannot become reference job schedule.

### 13. GRID_NETWORK_AND_PLANNING_INPUT

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\v41r4_electrical.py::configure` (line 10; SHA `68306d036e7e364f2b208320e1db58ab906b0c721e5194c77e52377de263294c`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41\electrical.py::identity` (line 41; SHA `d9bae02cf0c983cbe032ddd990633cf1b23d6b19c6ebc19325fd76894678fb97`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40i\electrical.py::generate_outputs` (line 182; SHA `dc8df57722410a14a0e30592fe35918cb4dcb4c4b0b0afdfcb189c60c6c591e3`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40e\electrical.py::upstream` (line 41; SHA `e8f2afc6a94c563d518be1ba72e004977bb0fa91ebc5bb54b575b138aff3262e`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_may01\prepare.py::native_coefficients` (line 158; SHA `4f299616c023c508cc03ae065bfabf6241aec8c1729fee6c1a64f87951dfcf44`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_native\grid.py::add_grid` (line 30; SHA `1d5c353c1e767cae54520f04ad101e34a95da3d1976d9b449e366400fe78112d`).

Authority: IEEE123 topology/PCC/branch ratings; April forecast load/PV; same frozen reference P/Q; alpha_BG from current binding. Derived: bus-phase background P/Q/PV targets; per-day planning voltage/current/PQ coefficients; 60 control axes (12 AIDC P,24 MESS P/Q controls plus mapping axes).

Units: {"planning voltage": "squared pu in affine rows; output pu after sqrt", "controls": "kW/kvar", "branch rating": "A or kVA"}. Resolution: 96 slots x native node/branch phases. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: Rebuild/bind April coefficients from raw current inputs after workload gate. Never copy May coefficient arrays or native tap/cap trajectories. Primary B0 band0.95-1.05.

### 14. PLANNING_BUNDLE_AND_FREEZE

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_may01\prepare.py::main` (line 178; SHA `4f299616c023c508cc03ae065bfabf6241aec8c1729fee6c1a64f87951dfcf44`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native_inputs.py::main` (line 15; SHA `bf32fa885007f31265b09fd1511ea3c6543927a8efd5883cace9be8245e9a999`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\native.py::canonical_jobs` (line 11; SHA `6fddb5938544aef952f86cc72e836a46c657ed66a6a594f5d842346900beebba`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_native\planning.py::freeze_day_ahead_plan` (line 84; SHA `5ea952c76d015df66f11eedeb9f86d5a41248d5e876e4a126cf61e72f3d701be`).

Authority: known population; current runtime/gpu/capacity/reference; forecast inputs; frozen causal unknown-arrival policy; input authority hashes. Derived: detached canonical immutable plan; DAYAHEAD_PLAN_SHA; POLICY_SHA; GRID_SHA.

Units: {"plan": "JSON canonical payload with kW/kvar,slots,GPU,seconds"}. Resolution: one freeze per day. Cutoff: D-1 18:00 fixed AEST UTC+10; issue(day)=day 00:00 AEST minus six hours.

April: New builder schema V42_DAY_INPUT_BUNDLE_V1; reference only after bundle PASS; B0 flex off/MESSzero. DA FreshAC is offline diagnostic, never operational gate.

### 15. ACTUAL_REALIZED_POPULATION

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\tools\audit_v40d_actual_replay.py::workload_audit` (line 221; SHA `99558057f12dc7e9f80372a7459210640ed89d22dfb679404cfa329aed2278e0`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40d_actual\inputs.py::observations` (line 94; SHA `d37f290f01952edc51a69cd8a603038bfe8b7e396dd5d44ea626613372f0b1ee`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40d_actual\job_replay.py::replay_jobs` (line 67; SHA `28a5b91b1d9dc6753aea7688c41a7ed67e9b8197edfa36ff6d1ed5ab1bdf4009`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_final\state.py::EpisodeLedger` (line 29; SHA `0a7723650697869d4c7023a53d2ae9a8444c9859ccf1b11acf17338472ef0e36`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_native\actual.py::unknown_arrival` (line 33; SHA `70b042aecaa89fc287d919534f90af8f55b12b3a688ead20be9ec3620bf165b9`).

Authority: historical source matches frozen known UID set to raw start/end/gpus_requested; current observed submissions/state events. Derived: historical known-only Actual population (does not add unknown arrivals); current causal explicit arrival state plus same immutable GPU request.

Units: {"UID": "opaque full raw id", "arrival/start/end": "aware timestamps", "GPU_gang": "integer request"}. Resolution: events appearing causally; 900 second controls. Cutoff: Actual only after freeze, each submission/start/completion observed at or before event time.

April: Supersede historical known-only Actual and end-start duration-driven schedule reconstruction. April includes full post-issue arrivals and observed known state; runtime remains currentQ50. No future identities enter Planning.

### 16. ACTUAL_PHYSICAL_BUNDLE

Code: `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_native\actual.py::ActualBackend` (line 69; SHA `70b042aecaa89fc287d919534f90af8f55b12b3a688ead20be9ec3620bf165b9`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_native\actual.py::run_dday_actual` (line 79; SHA `70b042aecaa89fc287d919534f90af8f55b12b3a688ead20be9ec3620bf165b9`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v40d_actual\grid_replay.py::replay` (line 10; SHA `26ef0f44d7693a51bcd6de3685b25fb8e77590d56f14813c3ceeda62b0d638f1`).

Authority: FrozenDayAheadPlan; realized_inputs load,pv,aidc_state; same immutable request; current causal physical events. Derived: physical schedule/load/pv/aidc_state/execution_controls; physical_arrays_sha; realized_inputs_sha.

Units: {"physical inputs": "kW/kvar, aware events, GPU"}. Resolution: 96 site/node slots plus event state. Cutoff: Post-freeze only; zero full reopt/P repair/Q repair/schedule repair.

April: Current repository defines Protocol and immutable orchestration, not a concrete native ActualBackend. April producer/adapter cannot be science-ready while GPU gate fails.

### 17. OPENDSS_INPUT

Code: `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\opendss_mapping.py::FeederAssets` (line 23; SHA `7e25e9befd8f80dba8cf1bc8cdba574ad1d77083c3b100430bea63abdfe9af89`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\opendss_mapping.py::compile_clean_engine` (line 87; SHA `7e25e9befd8f80dba8cf1bc8cdba574ad1d77083c3b100430bea63abdfe9af89`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\opendss_mapping.py::apply_trajectory_slot` (line 123; SHA `7e25e9befd8f80dba8cf1bc8cdba574ad1d77083c3b100430bea63abdfe9af89`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v28r2\opendss_backend.py::run_fresh_opendss` (line 90; SHA `55ad4be7175088ea24dbb611313635736f182f4d945f6f9b416b2ddec2c29956`); `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41r3\native_actual.py::native_actual` (line 9; SHA `d22e5cb4d8c4aeed1b76e18b6725794086fe80868d31853554471ffc80e607a8`); `C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\v42_april_port_from_may_pr\v42_native\actual.py::require_fresh_ac` (line 48; SHA `70b042aecaa89fc287d919534f90af8f55b12b3a688ead20be9ec3620bf165b9`).

Authority: IEEE123 native master SHA; runtime electrical adapter; AIDC01..12 dedicated Load.IDC_IDC01..12 consumption; same frozen schedule; forecast or actual background separately. Derived: independent NewContext compiled feeder; node-phase voltages and line/transformer checks; Actual sequential regulator states after D00.

Units: {"voltage": "pu", "P": "kW", "Q": "kvar", "current": "A and pu", "transformer loading": "kVA pu"}. Resolution: Fresh engine, 96 SolveSnap calls per trajectory. Cutoff: DA diagnostic same forecast/frozen schedule; D-Day Actual realized causal inputs; no repair.

April: Construction code only traced, no May optimization/OpenDSS/output arrays read or run; April paths require fresh day-specific generation.

## Concrete limits and supersession

The PR121 tree has `ActualBackend` as a protocol and `run_dday_actual` as immutable orchestration. Its test adapters validate control flow; they do not create a complete native physical producer. The historical V40D source observes frozen known UIDs. The later V41 consumer calls `v41.actual_dispatch.replay_jobs`, which keeps their sites but inserts contention delays using observed runtime; these known decisions alone drive site IT/PCC and grid replay. A separate `v41.actual.realized_workload` scans full D-Day submission IDs for positive-GPU/valid-duration GPUh/H4 scoring after grid replay. That aggregate score does not reconstruct individual unknown-arrival site/IT/PCC. Neither its missing-row filter nor the physical dispatcher is a complete current-V42 unknown-arrival authority or permissible schedule repair.

The historical chain is fully located, including its exclusion and unresolved native adapter boundaries. `lineage_forensic_complete=true` means the source/code trace is complete. It does not mean `scientific_bundle_PASS=true`. Current April GPU rows stay unresolved where exact raw request is null, and original request-version history remains explicitly unverified.

The old reference’s requested-duration/Q90 service, unassigned historical site eligibility, missing-GPU drop, and known-only Actual population are superseded. CurrentQ50, all-row retention, current780GPU capacity/non-additive compatibility, the PR121 common grid-blind scheduler, and full causal April arrivals apply. The May01 electrical wrapper `v41r4_electrical.configure` provides date-binding topology and final-scale metadata; April never adopts its stored coefficients, P/Q arrays, taps/caps, or voltage results.

The adjacent JSON records exact source hashes, per-stage artifacts, units and cutoff. The CSV supplies field-by-field actions and distinguishes raw-source availability from native adapter readiness.

## Historical Actual consumer closure

- `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41\actual.py::replay_jobs` line 21, SHA `82ad9b01a57fcbca33e9778a8741665626ca763025fa150470e4354551a70fe6`.
- `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41\actual.py::realized_workload` line 138, SHA `82ad9b01a57fcbca33e9778a8741665626ca763025fa150470e4354551a70fe6`.
- `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41\actual_dispatch.py::replay_jobs` line 18, SHA `27c4a59e5e237cee45ed4e26ed03eab8368b5e18afea552963cd3377264e82d9`.
- `C:\codex_mobileess_workspace\MobileESS_v41r3_scale_rebalance\dayahead\v41\execution.py::actual` line 328, SHA `abc1f40740063662aa9e6436e8c9e352a921ff9945da43eb4a35b16e4d7ccc9c`.

`v41.execution.actual` invokes same-site `actual_dispatch.replay_jobs` for known frozen decisions and builds PCC before OpenDSS. After that, `realized_workload` independently constructs the arriving GPUh/H4 score by positive-request/valid-observed-service filtering. No code in this closure places those scored unknown identities into the physical AIDC occupancy/PCC arrays. Current April keeps every observed physical job and cannot inherit that separation as a workload drop. Code was inspected; none of these producers or May data payloads was executed/opened.

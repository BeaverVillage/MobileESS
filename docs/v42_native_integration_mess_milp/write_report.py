"""Assemble the review from measured audits; never execute a native campaign."""
from pathlib import Path
import csv,json,math,xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent


def read(name):return json.loads((HERE/name).read_text(encoding='utf-8'))
def dump(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def md(name,value):(HERE/name).write_text(value.strip()+'\n',encoding='utf-8')


def main():
    rec=read('EPISODE_RESOURCE_RECONCILIATION.json');profiles=read('BOUNDED_COMPUTATIONAL_PROFILES.json')
    comparison=list(csv.DictReader((HERE/'MISOCP_VS_MILP_BOUNDED_COMPARISON.csv').open(encoding='utf-8')))
    rho={r['mode']:float(r['rho']) for r in comparison}
    tests=sum(int(e.attrib['tests']) for e in ET.parse(HERE/'TEST_RESULTS.xml').getroot().iter('testsuite'))
    gates={
        'reference_resources':{'status':'UNRESOLVED_GLOBAL_EPISODE_AUTHORITY','evidence':'PR79 321 conflicting intervals; Apr01 readiness alone excludes nonphysical/unassigned rows and is not full native activation'},
        'native_grid':{'status':'ADAPTER_IMPLEMENTED_FINAL_BINDING_NOT_ASSEMBLED','evidence':'V40A equations recovered; final native controls/coefficient identity not frozen'},
        'runtime_where_required':{'status':'UNPROMOTED','evidence':'No approved persisted pre-April total-runtime provider for unknown arrivals'},
        'CC4_where_required':{'status':'CURRENT_BASELINE_PRESERVED_NOT_BOUND_TO_FINAL_NATIVE_KERNEL','evidence':'Same-hour Q50/Q90 interface and P2 adapter implemented; current frozen forecast is not promoted into a new electrical readiness certificate'},
        'final_kernel_anchor':{'status':'STALE_ANCHOR_REJECTED','evidence':'Apr01 regeneration_002 reference predates final episode/service authority and uses zero-MESS baseline'},
        'service_windows':{'status':'SOURCE_SELECTION_UNRESOLVED','evidence':'D24 closure implemented; PR90 final TS rule selection remains NONE. New allowed starts cannot be inferred from duration or QoS'},
        'security_margin':{'status':'NOT_FROZEN','evidence':'V42_VOLTAGE_SECURITY_MARGIN_CONTRACT.json says AUTHORITY_INSUFFICIENT_NOT_FROZEN; no new margin invented'},
        'MESS_initial_state':{'status':'FINAL_BUNDLE_NOT_BOUND','evidence':'Historical authorities exist; coherent selected-day final MESS initial/terminal bundle is not assembled and frozen'},
        'traffic_routes':{'status':'FINAL_BUNDLE_NOT_BOUND','evidence':'Source-backed RouteArc interface implemented; selected-day travel forecast route receipt not bound to final state'},
    }
    dump('NATIVE_GATE_EVIDENCE.json',gates)
    md('README.md',f"""
# V42 native adapters and MESS MILP

Stacked on Draft PR #90, base `87be27b68829afc2fb1e915c0ae26f3cbd787ccb`.
The implementation advances the native physical architecture, but **native scientific activation remains BLOCKED**. No native day or Fresh OpenDSS solve was run; native timing/gap cells are null. The preregistered day remains 2025-04-01, at most one day and 600 external wall seconds per block.

`v42_native` now provides complete-option AIDC MILP, full-service/tail accounting, joint MESS route/P/Q/SOC MILP, all-face grid row binding, uncertainty-envelope P2, provider protocols, bounded fixed-discrete Actual P/Q repair, and supervised A1→M1→A2→M2 coordination. A concrete frozen native backend/data bundle is still required. Synthetic workers exercise the solvers and warm starts independently; they are not a coupled native electrical canary.

Validation: {tests} tests pass (including 39 unchanged PR90 tests); MESS production constructor has zero quadratic/SOS/general constraints and linear objectives. The bounded fixture retains travel energy, transit P/Q zero, SOC and terminal energy. Its old-circle-only comparison is conservative, not exact equivalence. All {read('INPUT_PRESERVATION.json')['files']} protected source/evidence files retain their hashes.

Read `FINAL_REVIEW_KO.md` for all 50 requested answers, `FINAL_FLAGS.json` for scope-qualified flags, `NATIVE_GATE_EVIDENCE.json` for unresolved authority versus unfinished final binding, and `PR79_RESOURCE_CONFLICT_ROOT_CAUSE.md` for the attempted reconciliation.

Reproduce from the repository root with Python, numpy, pandas, pytest and a licensed gurobipy installation:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONUTF8='1'
python -m pytest tests/test_v42_native.py tests/test_v42_job_capability.py -q --junitxml=docs/v42_native_integration_mess_milp/TEST_RESULTS.xml
python docs/v42_native_integration_mess_milp/audit.py
python docs/v42_native_integration_mess_milp/write_report.py
python docs/v42_native_integration_mess_milp/verify_delivery.py
```

The source audit requires the historical local artifacts listed in SOURCE_MANIFEST; they are read-only and are not copied or fabricated when absent. Unit tests need no historical dataset. `verify_delivery.py --write-manifest` refreshes the delivery manifest deliberately; normal verification does not rewrite it. No command above launches native/May/full IEEE campaigns or retrains ML.
""")
    md('NATIVE_SOURCE_AUTHORITY_AUDIT.md',"""
# Native source and authority audit

Authority is not established by a filename alone. SOURCE_MANIFEST.json records exact local file paths and hashes; the sources below were read before implementation. Earlier branches remain unmerged. This successor changes only its own package/tests/docs and local attributes.

| Subject | Inspected source | Recovery and limitation |
|---|---|---|
| PR90 | `v42_job_capability.py`, `docs/v42_job_capability_joint_flexibility` at 87be27b6 | Three masks, eight complete option classes, whole-gang/WAN/checkpoint rules reused unchanged. No final TS rule was frozen; synthetic prior ServiceBoundary is replaced only through explicit new contract adapter. |
| PR79 | `v42_reference_episode_pr/v42_reference_episode.py`, canonical ledger and conflict details | Stable continuing site identities and observed RUNNING replacement recovered; resource conflicts actively joined to source transitions. No branch merge, no invented restart or mapping. |
| PR75 | `v42_job_capability_joint_flexibility/EXISTING_FLEXIBILITY_IMPLEMENTATION_AUDIT.md`, R0 reproduction and inherited source manifest | Original gate/domain/witness denominators remain distinct; old D24 rule is not the new service contract. Stored 28.760644% / 10.433886% / 3.453156% shares are prior evidence, not new campaign results. |
| Latest generic V42 | `v42_integrated_pr/v42/canonical.py`, `checkpoint_planning.py`, `blocks.py` | Backend-driven A1→M1→A2→M2, same-domain refinement, full-tail GPU/WAN and reserve objective. The original tree also required a native backend/preflight; it was not an already frozen full native application. |
| Latest MESS | `v42_integrated_pr/v42/joint_mobility.py` | Joint route-flow/P/Q/SOC, exact PCS circle AND inner16. Remove only redundant cone; preserve connection/energy/terminal equations. |
| Older MESS | `v42_integrated_pr/v42/mobility.py` | Circle-only; replacing it with inner16 is a conservative subset, never exact equivalence to the circle. |
| Grid | `C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v40a/grid.py` | Non-transformer phase-line rho; voltage squared, transformer current and kVA hard rows; kW/kvar 60-control convention. New generic coefficient binder requires explicit frozen identity. No native coefficient bundle certified by synthetic grid tests. |
| Fresh AC | same historical tree `dayahead/v41/execution.py` and `dayahead/v28r2/opendss_backend.py` | Fresh OpenDSS, corrected physical mapping/readback, convergence/voltage/line/transformer validation. New coordinator requires a matching real receipt; validator tests do not invoke OpenDSS. |
| Checkpoint/WAN | `dayahead/v41r1/migration.py`, `migration_admission.py`, `terminal.py`, `dayahead/v40g/domain.py`, PR90 checkpoint generator | Modeled payload/prestaging/rack/path assumptions, one migration/episode, 900 s controls, 1800 s physical checkpoint phase from elapsed; not measured Kestrel capability. |
| Snapshots | `dayahead/v37/aidc_materializer.py`, PR79 causal ledger | Causal observed membership and requested-remaining baseline are historical inputs; independent snapshots do not prove counterfactual sequential execution. |
| Runtime/CC4 | `v42_integrated_pr/v42/runtime_provider_contract.py`, `envelope.py`, prior runtime forensic | No approved April unknown total-runtime model; preserve existing CC4 baseline. Protocols/envelope now implemented; no trained/new model promoted. |
| Response | `response_kernel.py`, `response_prefix_policy.py`, `policy_eligibility.py`, `docs/v42_prefix_policy/V42_FINAL_REVIEW_KO.md` | Prefix/full-service distinction and oversize firewall retained. Prior April02 prefix run: 392 candidates all rejected by frozen trust before numerical scoring; this is prior evidence, not rerun. No native active-policy pass. |
| Kernel/security | `V42_RESPONSE_KERNEL_LOCAL/regeneration_002/2025-04-01/{CAUSAL_REFERENCE,INPUT_FREEZE}.json`, `docs/v42_final/V42_VOLTAGE_SECURITY_MARGIN_CONTRACT.json` | Historical topology/weather/grid sources exist, but final service/reference/PQ anchor not matched; zero-MESS kernel stale. Security contract explicitly not frozen. |
| Actual correction | `ieee123_per_mess_pr/pfr/slow_fast.py`, V28/V28r2 Actual docs, V34 correction code | Earlier local repair disabled/zero; V34 correction is static AC calibration. No existing authorized continuous Actual P/Q repair relabeled as complete. New bounded LP is explicitly a proposal requiring Fresh AC. |
| Supervision | latest generic `contracts.py`, `supervision.py`, `stage_worker.py` | Copied source provenance in REUSED_SOURCE_LOG, modified namespace and hard cap to 600 s; added unvalidated diagnostic journal and removed unused legacy feature switches. Windows process-tree termination retained. |

See NATIVE_GATE_EVIDENCE.json: some gates lack authority, while other gates have source equations but lack final assembled and frozen native bindings. Neither is reported as a successful native experiment. No May record was evaluated or used for fitting; inherited historical file bytes were only hashed/read for authority and preservation.
""")
    md('V42_CONTINUOUS_SERVICE_CONTRACT.md',"""
# V42_CONTINUOUS_SERVICE_INDEPENDENT_SNAPSHOT_V1

D24/H=96 is an electrical evaluation boundary, never a job completion deadline. This normative contract implements the current user instruction; it does not promote a new runtime predictor or an unselected temporal eligibility rule.

An admitted job has exact authorized compute seconds W, integer gang G and complete compute segments. Allocation reserves ceil(W/900) full gang slots. Exact compute W and unused final reservation seconds remain separate; rounding resource reservation upward is not additional compute. Sum of segment lengths equals allocated slots, segments cannot overlap, and prefix compute + post-H compute equals W. Transfer/restart gaps are not compute. All tail GPU/resource constraints are retained. No GPU clipping, splitting, service dropping or artificial midnight completion.

Electrical support is [start,min(end,H)); no post-H electrical-security claim. Full-service feasibility, electrical support and post-H carry-out are distinct quantities. `NativeServiceBoundary` requires source hashes for exact duration and finite authorized start window. Its completion bound is a representation ceiling covering all retained tails, not D24. It cannot authorize delay from QoS/requested walltime by itself. PR90 option construction still enforces a checkpoint, complete WAN transfer/restart and useful destination compute before the control boundary for migration.

Reconciliation keeps previous counterfactual plan history. A same-site causal RUNNING observation replaces the old plan in an independent day's current view; this does not delete previously executed service. An expired PENDING counterfactual start remains unresolved, without requeue or start reset. Completion release requires an observed COMPLETED state plus a matching causal episode/source receipt. Current RUNNING cannot be released by an old completion receipt.

Use the next day's authoritative snapshot independently when causal sequential execution cannot be demonstrated. No fabricated D+1 state, no stacking old RUNNING reservation on top of current remaining service, and no claim of sequential policy validation. PR79 already used this RUNNING replacement structure; semantic closure alone does not eliminate its resource conflicts.

Structural service/tail semantics are ready and tested. End-to-end native reference placement, selected temporal windows and production duration providers remain gated separately.
""")
    md('PR79_RESOURCE_CONFLICT_ROOT_CAUSE.md',f"""
# PR79 reconciliation attempt

Read-only join of all 242,842 source job-days, not a chosen favorable date. `EPISODE_RESOURCE_RECONCILIATION.json` hashes the local 26,586-row conflict/source join. State-pair keys in that JSON are **(current state, prior state)**.

- Duplicate (day,episode) rows: {rec['duplicate_episode_day_rows']}.
- Conflicting site/time segments: {rec['conflict_site_time_segments']}; contribution rows: {rec['episode_segment_rows']}.
- PENDING→PENDING: 18,838; PENDING→RUNNING: 7,512; RUNNING→RUNNING: 236 contribution rows.
- New-placement overlap rows: 0. Continuing invalid state is detected before new admission.
- Expired PENDING reservation job-days: 28,025.
- PENDING→RUNNING transitions: 16,266; 4,670 have comparable old assigned start. Observed start is later in 3,234 and earlier in 1,436; none matches exactly. 4,711 conflict contribution rows have a later observed start than the prior counterfactual start.

Source inspection rejects A (stale RUNNING reservation stacked with current execution) and B (duplicate logical episode) as an implemented double-count bug. PR79 rebuilds current intervals and replaces RUNNING remaining service at the preserved site. The demonstrated cause is mismatch between counterfactual planned start/reservation and later causal execution inside synthetic site mapping. This is an inconsistency under the current native representation, not evidence that raw Kestrel scheduling violated its physical cluster.

C: no causal requeue/restart receipt resolves expired PENDING starts. D: requested-duration reservations may be conservative, but future realized runtime cannot authorize shortening them; no approved unknown runtime provider is available. E/F: continuing occupancy still exceeds current assigned-site capacity. No supported completion/requeue/mapping transaction was found that removes those conflicts legally. Diagnosis is not a claim that every segment has a unique physical causal explanation.

Reconciliation code closes independent-day ledger semantics and refuses unsupported releases. Actual physical conflicts resolved: **0**. No site/GPU/service changes, drops, invented completion or requeue. Apr01 has 664 rows, 582 capacity-feasible rows and 82 other/nonphysical rows; its stored day-ready flag is true, but that alone does not establish final native service/kernel/security/provider authority. No alternative easier date was substituted.

Required next evidence: causal execution/requeue/completion mapping or a separately validated reference allocation authority preserving all obligations, plus approved duration/start-window authorities. Oversize jobs remain out of domain; no legacy >100-GPU virtual capacity, clipping or gang splitting is promoted.
""")
    dump('RUNTIME_CC4_INTERFACE_STATUS.json',dict(RUNTIME_PROVIDER_STATUS='UNPROMOTED',RUNTIME_PROVIDER_READY=False,
        runtime_interface=['predict_total(job,event_time)','predict_remaining(job,elapsed_seconds,event_time)'],
        outputs=['q50_seconds','q90_seconds','model_version','provenance'],causal_feature_whitelist=True,
        requires=['persisted_model_and_preprocessing_hash','training_cutoff','frozen_at','optimizer_use_allowed','causal_per_feature_observed_at'],
        absent_provider_behavior='OBSERVED_JOB_RECORDED_PHYSICAL_WORKLOAD_UNRESOLVED_NO_ACTION_NO_FIX_COERCION',
        APRIL_UNKNOWN_TOTAL_RUNTIME_MODEL_AVAILABLE=False,RUNTIME_MODEL_RETRAIN_REQUIRED=True,RUNTIME_MODEL_RETRAIN_ALLOWED_IN_THIS_TASK=False,
        DDAY_UNKNOWN_ML_RUNTIME_BOUND=False,FUTURE_ACTUAL_RUNTIME_DECISION_READS=0,
        external_dependency='A causally trained, pre-April frozen and persisted total-runtime model for newly submitted jobs, callable at submission time without refitting.',
        CC4_PROVIDER_STATUS='CURRENT_FROZEN_BASELINE_PRESERVED_FINAL_NATIVE_BINDING_PENDING',CC4_PROVIDER_READY=False,
        CC4_INTERFACE_IMPLEMENTED=True,CC4_NEW_MODEL_PROMOTED=False,CC4_semantics='SAME_HOUR_Q50_NOMINAL_Q90_UNCERTAINTY_NO_BACKLOG_SHIFT',
        SEMANTIC_ML_MERGED=False,ML_retraining=False,ML_branch_waited=False,ML_branch_merged=False))
    dump('AIDC_NATIVE_BINDING_AUDIT.json',dict(native_solver_adapter_implemented=True,native_population_bound=False,
        native_activation=False,reason='Reference/resource/start-window/grid/provider gates remain',
        masks=['can_timeshift','can_prestart_place','can_checkpoint_migrate'],FLEX='OR',FIX='ALL_FALSE_ONLY',unknown_is_FIX=False,
        classes=['STAY','SHIFT_ONLY','PREPLACE_ONLY','SHIFT_PREPLACE','MIGRATE','SHIFT_MIGRATE','PREPLACE_MIGRATE','SHIFT_PREPLACE_MIGRATE'],
        joint_complete_options=True,shift_migrate_structurally_supported=True,full_tail_resource_rows=True,
        exact_seconds_required=True,FIX_binary_count=0,prescreen='INFEASIBILITY_OR_IDENTICAL_DUPLICATE_ONLY',
        grid_top_K=False,physical_units_unchanged=True,checkpoint_physical_seconds=1800,checkpoint_control_seconds=900,
        carry_in_phase_source='CAUSAL_ELAPSED_SECONDS',phase_reset=False,arbitrary_modeled_start=False,
        migrations_per_episode_max=1,measured_Kestrel_checkpoint_claim=False,native_joint_combination_promoted=False))
    md('MESS_MILP_FORMULATION.md',f"""
# MESS formulation and conservative conversion

Time-network binary arc x selects a stay or an authorized route with departure, arrival and connection time. Flow conservation gives one continuous path per MESS. Reachability removes only source-unreachable arcs; no favorable-site screening. Each route keeps its source authority hash and full travel energy. Charge/discharge direction remains binary. All units are kW, kvar, kVA, kWh and hours.

At each connected site/time, for f=0,...,15 and theta_f=2*pi*f/16:

`cos(theta_f)*P + sin(theta_f)*Q <= S*cos(pi/16)*x_connected`.

P=Pdis-Pch. Physical Pch/Pdis bounds and Q bounds couple to connection. Opposite polygon normals force P=Q=0 at x=0. No unconstrained transit injection or oversized big-M. SOC obeys `E[t+1]=E[t]+0.25*(eta_c*Pch-Pdis/eta_d)-route_energy[t]`, with unchanged initial/terminal energy and SOC bounds. Route/connection, P, Q and SOC are joint decisions in M1 and M2.

**Proof.** Adjacent supporting lines intersect at angle theta_f+pi/16 and radius S*x. Thus every polygon vertex lies on the radius-S*x circle; convexity puts the entire polygon inside that circle. For any direction, radial support lies between S*x*cos(pi/16) and S*x. At x=0 the only point is the origin. Even for 0<=x<=1, norm squared <=S²*x²<=S²*x, so the quadratic row is redundant in the existing inner16 intersection, including its relaxation.

Worst radial conservatism against circle-only is 1-cos(pi/16)={100*(1-math.cos(math.pi/16)):.9f}%. No outer polygon and no face-count sensitivity sweep. Latest `joint_mobility.py` had circle AND polygon; its feasible set is unchanged by removing the redundant circle. Historical `mobility.py` had circle only; this conversion deliberately restricts it. Do not conflate those two comparisons.

AST audit finds one generated quadratic PCS family in each of those two source implementations, no quadratic objective. The primary constructor checks `NumQConstrs=0`, quadratic objective terms=0, SOS=0 and general constraints=0 at every objective level; a hidden quadratic grid callback is rejected. Diagnostic circle modes are explicit and cannot silently become production.

Identical synthetic fixture (2 sites, 1 MESS, 8 slots, two declared route arcs): old intersection rho={rho['LEGACY_BOTH']:.12f}, circle-only rho={rho['CIRCLE_ONLY_DIAGNOSTIC']:.12f}, new MILP rho={rho['MILP']:.12f}. MILP minus circle-only = {rho['MILP']-rho['CIRCLE_ONLY_DIAGNOSTIC']:.12g}; intersection difference = {rho['MILP']-rho['LEGACY_BOTH']:.12g} within solver numerical tolerance. Identical route domains, exact circle feasibility, full travel energy and terminal SOC pass. P/Q trajectories need not be unique; full P/Q/SOC differences are reported in the comparison CSV. This is not a native-day equivalence or runtime speedup result.
""")
    md('OBJECTIVE_NATIVE_BINDING.md',"""
# Objective and native row binding

Level 1 minimizes rho_max of non-transformer phase-line loading. `grid.add_grid` preserves the inherited anchored all-face affine current approximation and upper bound rho<=1; voltage squared, transformer current and transformer kVA are separate hard rows. The inherited modeled per-MESS transformer domination rule is retained, not generalized. All coefficients/control units and topology/mapping/service/PQ identity must be bound before use. Synthetic coefficient tests verify the anchor and independent hard voltage/current/kVA rejection; they are not Fresh AC.

Level 2 is uncertainty reserve shortfall only. `envelope.bind` keeps aggregate CC4 Q50 in the same hour, Q90-Q50 as an envelope, hard known GPU and nominal allocation, reserve variables and mandatory nominal/incremental electrical readiness callback. It introduces no unknown-job service deadline, shifting or backlog. The callback must bind all incremental security rows; a claimed hash alone is not a scientific validation. Final selected-day CC4/grid readiness is not yet certified, so P2 hard feasibility remains false.

After rho/P2, A-block lex levels are migration count, total absolute shift slots, pre-start relocation count, stable option tie. M-block levels are movement kWh, movement count, stable route tie. Earlier higher objective levels are locked within a shared deadline. The numerical rho lock tolerance 1e-7 is a solver tolerance inherited from the generic comparison convention, not a frozen event-policy trust/security epsilon. No missing security margin is filled with that value. A weighted index tie can have collisions; it is a reproducibility aid with fixed seed/thread, not a uniqueness proof or scientific objective.

A1→M1→A2→M2 is retained with explicit state handoff. A2 starts from mapped A1 values; M2 starts from mapped M1 values. M2 no-regret compares candidate and M1 under the same fixed A2 state. No monolithic AIDC+MESS model. Final backend composition and matching Fresh OpenDSS must pass before an operating schedule is accepted.
""")
    dump('P2_RESERVE_STATUS.json',dict(P2_RETAINED=True,P2_HARD_FEASIBILITY_PROVEN=False,
        slack_scope='CC4_Q90_MINUS_Q50_UNCERTAINTY_RESERVE_ONLY',known_admitted_service_slack=False,
        same_hour_nominal=True,aggregate_backlog_shift=False,native_electrical_readiness_bound=False,
        unit_test='Known=7, nominal=1, cap=8, spread=3 each hour => reserve shortfall 72, known service remains hard',
        reason='Universal native uncertainty absorbability not proved; deleting P2 would hide shortage'))
    md('EVENT_ACTUAL_CONTROL_CONTRACT.md',"""
# Causal event and Actual boundary

Optimization passes A1/M1/A2/M2 are distinct from the paper registry:

- M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE
- M2_FIXED30_MOBILE
- M3_EVENT30_NO_LOCAL_REPAIR_MOBILE
- M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION

Observe current state only; test events on 30-minute boundaries of the 900-second control grid. Threshold must be supplied from a frozen policy authority; no fitted/default threshold is promoted here. M2 paper policy fires on every eligible boundary, others use the supplied observed-deviation trigger. M3 rejects local repair. M4's native dispatcher must additionally freeze location; no four-policy runner or campaign is claimed from a name registry.

Unknown arrival observes submission features, checks causal runtime provider, then calls a frozen site-only policy. Temporal shift and migration remain disabled for unknown jobs. No online global A1/M1/A2/M2 call. Missing provider records the observed job as unresolved and returns no action; it neither drops physical workload nor fabricates FIX/reference service. Spatial action can be proposed only with source-backed placement/capacity/full-service certificates; no native provider means production handler readiness is false.

KernelAnchor requires exact service/reference/PQ/grid identities. Prior April prefix evidence failed active scoring; do not reuse its old zero-MESS kernel or call a protocol test an active-policy pass. Regeneration must follow final service/reference/PQ/grid freeze. Unknown temporal/migration authority stays missing, existing known-job R0/checkpoint semantics remain unchanged. No future actual runtime/end data, policy fitting, new May evaluation or trust widening.

Accepted Actual output requires fresh exact OpenDSS convergence, hard voltage/line current/transformer current and kVA checks, with matching schedule and grid hash. `require_fresh_ac` is a validation boundary, not an OpenDSS producer. The historical native producer is identified in the source audit; it was not run against an unbound model.
""")
    md('LOCAL_REPAIR_PQ_CONTRACT.md',"""
# Bounded continuous P/Q proposal

New LP adapter consumes an explicitly authorized frozen suffix of at most 16 control slots and a shared at-most-10-second in-process deadline. The production caller must place it under external execution supervision as well; this function alone cannot guarantee wall time across a stalled solver/API call. No production Actual wrapper is asserted ready.

Location/connection, charge direction, route energy, job schedules and migrations are fixed. Only P/Q and the resulting energy trajectory change inside supplied delta-P/delta-Q reserves. Transit has P=Q=0. Inner16 PCS, physical power bounds, exact efficiency/quarter-hour energy balance, SOC limits, observed initial energy and frozen terminal energy remain hard. Future compensating P is permitted only within the supplied frozen reserve suffix, never by reading future Actual state.

Optimize electrical rho first, lock it, then minimize absolute P change and finally Q change: Q-first intervention preference at equal electrical quality, no arbitrary P/Q weight. A P change recomputes every SOC boundary through terminal equality. M3 paper policy forbids this repair. No new route or discrete MILP in Actual; the adapter checks integer variable count=0.

Output is PROPOSAL_REQUIRES_FRESH_AC, never an automatically executed dispatch. Native current-state adapter, margin/trigger/reserve authorities and Fresh validation remain required. Unit tests demonstrate P/Q changes with compensating SOC on synthetic data only.
""")
    flags=dict(V42_CONTINUOUS_SERVICE_READY=True,V42_CARRY_OVER_READY=True,
        SERVICE_READY_SCOPE='IMPLEMENTED_FULL_SERVICE_LEDGER_AND_INDEPENDENT_CAUSAL_SNAPSHOT_MODE_ONLY',
        SEQUENTIAL_CARRY_OVER_READY=False,PR79_RESOURCE_CONFLICT_RESOLVED=False,V42_REFERENCE_PLACEMENT_READY=False,
        AIDC_CAPABILITY_MODEL_BOUND_NATIVE=False,AIDC_NATIVE_SOLVER_ADAPTER_IMPLEMENTED=True,AIDC_JOINT_START_SITE_MIGRATION_READY=False,
        MESS_ORIGINAL_FORMULATION='MISOCP',MESS_FINAL_FORMULATION='MILP',MESS_FORMULATION_SCOPE='IMPLEMENTED_CONSTRUCTOR_AND_SYNTHETIC_PHYSICAL_VALIDATION_NOT_NATIVE_DAY',
        MESS_QUADRATIC_CONSTRAINT_COUNT=0,PCS_POLYGON_FACES=16,PCS_POLYGON_IS_INNER_SAFE=True,
        MESS_P_AND_Q_JOINT=True,MESS_ROUTE_MOVEMENT_PQ_SOC_JOINT=True,PRIMARY_OBJECTIVE='MAX_LINE_LOADING',
        P2_RESERVE_OBJECTIVE_RETAINED=True,P2_HARD_FEASIBILITY_PROVEN=False,
        SECONDARY_INTERVENTION_OBJECTIVE=['MIGRATION_COUNT','SHIFT_MAGNITUDE','PRESTART_RELOCATION','MESS_MOVEMENT','DETERMINISTIC_TIE'],
        A1_M1_A2_M2_RETAINED=True,AIDC_OPTION_REDUCTION_PERCENT=None,SYNTHETIC_AIDC_OPTION_REDUCTION_PERCENT=40.,
        WARM_START_A1_TO_A2_USED=False,WARM_START_M1_TO_M2_USED=False,WARM_START_FLAG_SCOPE='NATIVE_DAY_NOT_RUN',
        SYNTHETIC_WARM_START_A1_TO_A2_ACCEPTED=True,SYNTHETIC_WARM_START_M1_TO_M2_ACCEPTED=True,
        FRESH_AC_CANARY_PASS=False,V42_NATIVE_BLOCK_RUNTIME_FEASIBLE=False,V42_PHYSICAL_OPTIMIZER_READY=False,
        CL_MC_BD_TRIGGERED=False,RUNTIME_PROVIDER_READY=False,CC4_PROVIDER_READY=False,
        SEMANTIC_ML_MERGED=False,FULL_IEEE123_ROUND_RUN=False,IEEE8500_FULL_RUN=False,FLEX_SENSITIVITY_RUN=False,
        NEW_MAY_POLICY_EVALUATION=False,UNKNOWN_ARRIVAL_TEMPORAL_ACTIONABLE=False,UNKNOWN_ARRIVAL_MIGRATION_ACTIONABLE=False,
        UNKNOWN_TEMPORAL_MIGRATION_AUTHORITY_MISSING=True,FUTURE_ACTUAL_RUNTIME_DECISION_READS=0)
    for stage in ('A1','M1','A2','M2'):
        for suffix in ('RUNTIME_SECONDS','FINAL_GAP','BINARY_COUNT'):flags[stage+'_'+suffix]=None
    dump('FINAL_FLAGS.json',flags)
    dump('FINAL_VERDICT.json',dict(status='PARTIAL_NATIVE_ARCHITECTURE_IMPLEMENTED_SCIENTIFIC_ACTIVATION_BLOCKED',
        native_canary_status='NOT_RUN_SOURCE_GATE_FAILED',fresh_AC_status='NOT_RUN_NO_ACCEPTED_NATIVE_CANARY',
        tests_passed=tests,ML_dependency_waited=False,known_blocker_merely_repeated=False,
        completed=['PR79 causal transition/source reconciliation','continuous exact service/tail contract','native AIDC and grid row adapters',
            'MESS cone removal with conservative proof and bounded comparison','provider and P2 envelope interfaces',
            'bounded Actual P/Q proposal and receipt gate','external 600s stage supervision and warm-start diagnostics'],
        remaining=list(gates),before_IEEE123_1ROUND=['resolve reference/resources/start-window authority','assemble and freeze final native backend/grid/MESS/route/provider bundle',
            'regenerate matching response kernel and pass active-policy gate','one preregistered native day under 600s per block','Fresh exact AC'],
        native_speedup_claimed=False,post_H_electrical_security_claimed=False))
    timings='; '.join(f"{s} {profiles[s]['supervisor']['total_wall_seconds']:.6f}s" for s in ('A1','M1','A2','M2'))
    first='; '.join(f"{s} {profiles[s]['receipt']['first_incumbent_seconds']:.6f}s" for s in ('A1','M1','A2','M2'))
    answers=[
        '최신 local generic V42 canonical/checkpoint_planning/blocks/joint_mobility, V40A grid, V41 Fresh OpenDSS 및 PR90/79/75를 SHA로 추적했다. NATIVE_SOURCE_AUTHORITY_AUDIT 참조.',
        'PR90의 3개 독립 mask·8개 complete option·GPU/rack/WAN/checkpoint 검사를 새 Gurobi AIDC adapter에 연결했다. native population 실행/승격은 아직 하지 않았다.',
        '중복 episode 0개. counterfactual 계획 start와 나중 causal 실행 start가 일치하지 않는 continuing occupancy가 현재 synthetic site capacity와 충돌한다. 321구간/26,586기여행을 source join했다.',
        'NO. 물리적 conflict 해결 0개. 이미 PR79가 RUNNING 현재 remaining으로 교체하므로 stale 중복 삭제로 고칠 수 없었다. 임의 이동·축소·requeue 없이 fail closed.',
        'NO. D24는 전기 평가 경계이며 job deadline이 아니다.',
        'exact compute seconds와 ceil(seconds/900) gang reservation을 분리하고 prefix+tail=전체 service를 검증한다. transfer/restart는 compute가 아니다.',
        'NO. tail GPU/resource ledger를 전부 유지한다. post-H 전기 안전성은 주장하지 않는다.',
        'YES. continuing site 일치 검사를 유지한다. 다른 사이트로 바꾸어 자원 충돌을 숨기지 않는다.',
        'YES, adapter complete option 안에서 start/site/migration이 공동 결정된다. 실제 native cohort binding은 아직 false다.',
        '구조적으로 지원한다. 그러나 source-backed start window와 native physical validation 전에는 새 조합의 운영 승격을 하지 않는다.',
        '합성 완전 option domain의 compute·gang·WAN·checkpoint·transfer/restart·tail invariants는 PASS. native joint-combination 검증은 미실행이다.',
        'NO. 제출 시 runtime interface와 frozen site policy만 호출한다. 없는 runtime은 unresolved 처리하고 global MILP 호출은 0이다.',
        'UNPROMOTED. provider interface는 구현했지만 production readiness=false. requested walltime을 realized runtime으로 대체하지 않는다.',
        'NO. future Actual runtime decision reads=0. 과거 source hash/forensic 열람은 새 planning/policy evaluation이 아니다.',
        'connection binary와 함께 P²+Q²<=S²x quadratic PCS를 가지고 있어서 MISOCP였다.',
        '최신 joint_mobility와 구형 mobility 각각 하나의 반복 PCS quadratic family. quadratic objective 없음. 생성 모델도 전수 구조 검사한다.',
        '최신 inner16와 공존하던 중복 exact PCS circle만 제거했다. 구형 circle-only 대비는 보수적인 부분집합 변환이다.',
        'cos(2πf/16)P+sin(2πf/16)Q<=S cos(π/16)x_connected, f=0..15.',
        'YES. 인접 face 교점 반지름이 Sx이고 convex hull이 circle 내부. x=0은 원점. 완화 x∈[0,1]에서도 circle row가 함의된다.',
        f'최악 방사방향 용량 손실 {100*(1-math.cos(math.pi/16)):.6f}%. face sweep은 하지 않았다.',
        'YES, 구현한 primary MESS constructor 및 bounded generated model에서 0. native day 모델 생성은 source gate로 미실행.',
        'YES, linear objective/constraints, QConstr=0, quadratic objective=0, SOS=0, general constraints=0 검사를 통과한다. 이것이 native campaign 준비 완료를 뜻하지 않는다.',
        'YES. M1/M2에서 Pch/Pdis 및 Q를 이동·SOC와 공동 결정한다.',
        'YES. stay connection bound와 inner polygon이 disconnected/transit P/Q=0을 강제한다.',
        'YES. 0.25h·충방전효율·initial/terminal SOC를 적용한다. Actual P 보정도 전체 suffix SOC를 다시 계산한다.',
        'YES. route departure의 source-backed travel kWh를 SOC에서 차감한다. bounded fixture는 0.1kWh 이동을 보존했다.',
        'YES. time-expanded route/stay flow binary, 출발/연결시점은 source arc를 따른다. stationary battery로 바꾸지 않았다.',
        f"합성 동일 fixture: MILP−circle-only Δrho={rho['MILP']-rho['CIRCLE_ONLY_DIAGNOSTIC']:.12g}; MILP−기존 circle+inner16={rho['MILP']-rho['LEGACY_BOTH']:.12g}. native objective 차이는 미측정.",
        'YES, bounded 모든 선택 P/Q의 exact circle ratio<=1을 독립 검사했다. 원 내부 증명과 CSV가 있다.',
        '미실행. OpenDSS 설치와 receipt rejection unit test는 Fresh AC PASS가 아니다. FRESH_AC_CANARY_PASS=false.',
        'YES. coordinator가 A1→M1→A2→M2와 A1/A2, M1/M2 state handoff, fixed-A2 M2 no-regret를 유지한다. frozen native backend는 미완성.',
        '합성 pre-lex 모델: A1/A2 binary24, integer0, continuous1, linear47, NZ340; M1/M2 binary23, integer0, continuous49, linear377, NZ1093. 모두 Q/SOS/general0. native 수치는 null.',
        'native 네 block 모두 NOT_RUN/null. 합성 OS-supervised wall: '+timings+'. 합성 속도를 native 성능으로 대체하지 않는다.',
        'native first incumbent=null. 합성 callback: '+first+'. root/presolve는 callback 관측치이며 별도 LP 시간으로 추정하지 않는다.',
        'native gap=null. 합성 네 block 각 objective 최종 gap=0. timeout/null을 0으로 채우지 않는다.',
        '중복 PCS cone 제거, FIX constant, exact-safe complete-option prescreen, reachable route/PQ column 제거, indexed resource/flow assembly, objective-level model 재사용과 MIP start. 4h native 대비 speedup은 입증하지 않았다.',
        '합성 A1/A2 raw40→retained24, 40% 감소. native cohort 감소율은 미측정/null. 원인별 CSV 제공.',
        'YES. singleton option은 상수1이고 별도 binary를 만들지 않는다.',
        '검사한 hard resource/service/checkpoint/WAN 불가능성과 동일 option 중복만 제거한다. grid benefit top-K·favorable site·campaign 결과 기반 제거 없음.',
        '합성 A2 25개/M2 72개 시작값 적용, solver Loaded user MIP start 로그로 수락 확인. native 사용=false, node 감소율 미측정.',
        'MAX_LINE_LOADING: non-transformer phase-line rho 최대값 최소화. transformer/voltage는 hard constraint.',
        'P2 유지. uncertainty reserve가 항상 hard feasible임을 증명하지 못했다. known admitted compute에는 slack이 없다.',
        'A: migration count→shift magnitude→pre-start relocation→tie. M: movement energy→movement count→tie. rho/P2 lock 이후 수행한다.',
        'NO. deterministic tie는 구현상 반복성 보조이며 과학적 목적이나 unique-solution 증명이 아니다.',
        'NO. IEEE123 1/2/3ROUND, IEEE8500, May 신규 평가 모두 미실행.',
        'NO. FLEX sensitivity 및 PCS face-count sweep 미실행.',
        'NO. ML branch 대기/merge/retrain 없음. semantic ML OFF. provider 부재와 physical adapter 작업을 분리했다.',
        'NO. native grid bottleneck 측정이 없어서 CL-MC-BD trigger=false.',
        'reference/resources 및 causal start/duration authority 해결, final native backend/grid/MESS/route/provider freeze, matching kernel 재생성·active-policy gate, 600s/block 단일 native canary와 Fresh AC가 남았다.',
        f'PARTIAL_NATIVE_ARCHITECTURE_IMPLEMENTED_SCIENTIFIC_ACTIVATION_BLOCKED. service/tail 독립 snapshot semantics와 MILP adapter는 구현·검증({tests} tests PASS). native optimizer/runtime readiness=false, PR79 unresolved, Fresh AC=false. source binding이 확보되기 전 full campaign 금지.'
    ]
    assert len(answers)==50
    md('FINAL_REVIEW_KO.md','# V42 native integration 최종 검토\n\n구현/합성 검증과 실제 native 운용 검증을 구분한다. 모든 번호는 요청한 50개 질문과 같은 순서다.\n\n'+'\n\n'.join(f'{i}. {a}' for i,a in enumerate(answers,1)))
    md('PR_DESCRIPTION.md',f"""
V42's latest joint MESS block imposed both an exact PCS circle and an inner 16-face polygon. This stacked successor to #90 removes the redundant quadratic rows while retaining route decisions, joint P/Q, transit connection, travel energy, SOC and terminal energy. It adds native solver adapters for PR90 joint AIDC options, exact service/tail accounting, grid/P2 binding, strict unpromoted providers, and bounded Actual P/Q proposals with Fresh AC acceptance gates.

PR79 source reconciliation finds 321 conflicting continuing-resource intervals and no duplicate episode-day records. The conflicts cannot be legally repaired by deleting a stale reservation, moving jobs or shortening service. Final native reference/windows/kernel/security/provider bindings remain blocked. The preregistered Apr01 native canary and Fresh AC were therefore **not run**; native performance fields are null.

Validation: {tests} tests pass. The same bounded synthetic MESS instance passes both circle and polygon physics with zero quadratic/general/SOS rows in the MILP; A2/M2 warm starts are observed accepted under external supervision. No native speedup claim. No ML training/merge, May evaluation, full IEEE campaign or sensitivity sweep.

Review: `docs/v42_native_integration_mess_milp/FINAL_REVIEW_KO.md`, `FINAL_FLAGS.json`, `NATIVE_GATE_EVIDENCE.json` and the reproducible source/measurement audits. This PR remains draft until native authority and Fresh AC gates are satisfied.
""")


if __name__=='__main__':main()

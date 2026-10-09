"""Prepare original-source linkage without importing or constructing a solver.

These adapters expose content-addressed input descriptors and source API plans.
They do not impersonate a production backend: A2 fixed-MESS construction and
stage-correct M2 construction remain explicit integration requirements. Native
entry points always deny before source inspection, import, build or invocation.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import ast
import hashlib
import json

from .contracts import StageRequest, canonical, digest, require, require_sha
from .policy import gap_target, require_production_authorization


@dataclass(frozen=True)
class SourceApiSpec:
    """Pinned source location and AST signature, deliberately not a callable."""

    file: str
    symbol: str
    signature: str
    source_sha256: str
    stages: tuple
    role: str
    invocation_status: str = "DEFERRED_RESOURCE_PROTECTION"

    def __post_init__(self):
        require(not Path(self.file).is_absolute() and ".." not in Path(self.file).parts,
                "REPOSITORY_RELATIVE_SOURCE_REQUIRED")
        require_sha(self.source_sha256)
        object.__setattr__(self, "stages", tuple(self.stages))

    def to_dict(self):
        return asdict(self)


# Catalog entries contain only source metadata. No importlib, module import or
# caller-supplied loader can resolve them into executable source in preparation.
SOURCE_APIS = (
    SourceApiSpec('v42_a_stage_domain_v2/domain.py', 'physical_domain', '(job, bound, resources, gen=None, hard_release=None)', '1b93465a1564a514a27bf01e4cf193f569f1a292edb4ade3d6796bb6e109f8d6', ('A1', 'A2'), 'Complete original STAY and migration physical domain'),
    SourceApiSpec('v42_a_stage_domain_v2/domain.py', 'contains', '(job, bound, resources, domain, option)', '1b93465a1564a514a27bf01e4cf193f569f1a292edb4ade3d6796bb6e109f8d6', ('A1', 'A2'), 'Original hard-valid option membership'),
    SourceApiSpec('v42_a_stage_canary/phase.py', 'run', '(native, state, day, certified_zero_point=None)', 'a4b59e2e802a3f42c922481666eb1f6f244477d5016454208bd2c5f112b6875a', ('A1', 'A2'), 'Phase I zero and P1 closure algorithm'),
    SourceApiSpec('v42_a_stage_canary/pricing.py', 'full_pricing', '(native, original, master, raw, descriptor, data, domains, ledger, axes, global_variables, global_rows, local_rows, owned, round_folder, *, zero=False)', '429b75f242696ba0a06f78e818ee6c3cd13bfe9f004f6b48e51fe0d4fd368e40', ('A1', 'A2'), 'Complete local block pricing and original global exact bound'),
    SourceApiSpec('v42_a_stage_practical/integer_model.py', 'restore_types', '(state, global_types)', '44e31914aadc70fca841564daeaf1a8470a3f729d8077cda826da252ad4e8aaf', ('A1', 'A2'), 'Restore original native integer types and preserve rows'),
    SourceApiSpec('v42_a_stage_acceptance/native.py', 'Native.solve', '(self, snapshot, folder, component)', 'cf725c1ecfff6d5d8744b13e30ca24e0bb8e056c1a195e3af0858a43204daf82', ('A1', 'A2'), 'Native snapshot solver adapter'),
    SourceApiSpec('v42_a_stage_acceptance/physical.py', 'Physical.verify', '(self, x)', '856f823a8d80b6f6fe4994eef55e26bb1655e23e47905ee34f3a550f5ec99695', ('A1', 'A2'), 'Original A rows and job/GPU/grid physical replay'),
    SourceApiSpec('v42_pr134_sc/snapshot.py', 'certify', '(descriptor, data, x, row_certificate, coefficients)', 'fb0eaa65db86f13fa2bcdad0424ffe5126b1510f1084470c41e9f50b0cb3f921', ('A1', 'A2'), 'Original individual job and grid source replay'),
    SourceApiSpec('v42_may_recovery_v5/a_stage.py', 'prepare', '(request, progress=None)', '63306b9775a787e2ab10fb11703bbec99c7914e5bf683ef337ac87d63c8a1a63', ('A1', 'A2'), 'Fresh date original state, complete-domain roster and source routing'),
    SourceApiSpec('v42_may_recovery_v5/a_stage.py', 'run', '(request, budget, progress=None)', '63306b9775a787e2ab10fb11703bbec99c7914e5bf683ef337ac87d63c8a1a63', ('A1', 'A2'), 'Source-routed P1-only A phase/pricing/integer orchestration'),
    SourceApiSpec('v42_may_recovery_v5/a_stage.py', '_planning', '(state, verification, power, output)', '63306b9775a787e2ab10fb11703bbec99c7914e5bf683ef337ac87d63c8a1a63', ('A1', 'A2'), 'Original AIDC PCC/IT/GPU materializer'),
    SourceApiSpec('v42_native/aidc.py', 'solve', '(stage, deadline, jobs, boundaries, resources, grid_builder, incumbent=None, *, seconds_authority=None, progress=None, day=None)', '8321137f3d04cec19c7bf063ac3fb71b4c3dc973a936ec520b938ee03cb6a264', ('A1', 'A2'), 'Complete-option A builder and GPU/grid callback'),
    SourceApiSpec('v42_may_campaign_native90/m_model.py', 'build_case', '(payload, request, progress=None)', '758fbb11c07c52ac10895da63bf3bd6049dd5d94cb19e6b606589f25b5889dde', ('M1', 'M2'), 'Same-day fixed AIDC payload to original full/compact/C3A source model'),
    SourceApiSpec('v42_may_campaign_native90/m_model.py', 'verify_case', '(case)', '758fbb11c07c52ac10895da63bf3bd6049dd5d94cb19e6b606589f25b5889dde', ('M1', 'M2'), 'Original matrix/box/objective/transport state integrity'),
    SourceApiSpec('v42_may_campaign_native90/m_model.py', 'verify_transport', '(compact, presolve)', '758fbb11c07c52ac10895da63bf3bd6049dd5d94cb19e6b606589f25b5889dde', ('M1', 'M2'), 'Independent exact FULL/Compact/presolve transport proof'),
    SourceApiSpec('v42_may_campaign_native90/m_stage.py', 'run', '(request, budget, progress)', '12f2a75996c4ec17654fda2205fbf139dfc702fb03923b22c4551bea9f2133b4', ('M1', 'M2'), 'P1-only 3 percent anytime primal-dual orchestration'),
    SourceApiSpec('v42_m1_hybrid/blocks.py', 'build_blocks', '(case)', '9c9ee88e31af36f51cfcec71816c718e60de02774efec88019375bc6dba2282d', ('M1', 'M2'), 'Original unit trajectory and coupling decomposition'),
    SourceApiSpec('v42_m1_hybrid/pricing.py', 'make_prices', '(case, decomp, full_dual)', 'b5d907fac13080484c7dc36c87cf78661d1c2b74793739f991985d3f32c5b5a3', ('M1', 'M2'), 'Signed original multirow coupling prices'),
    SourceApiSpec('v42_m1_hybrid/pricing.py', 'run_pricing', "(case, decomp, prices, ledger, output, *, seconds_per_unit=120, lp_seconds=90, mode='MILP_AND_LP')", 'b5d907fac13080484c7dc36c87cf78661d1c2b74793739f991985d3f32c5b5a3', ('M1', 'M2'), 'Full 96-slot local trajectory MILP/LP pricing'),
    SourceApiSpec('v42_m1_hybrid/pricing.py', 'run_lp_prices', '(case, decomp, prices, ledger, output, *, lp_seconds=60)', 'b5d907fac13080484c7dc36c87cf78661d1c2b74793739f991985d3f32c5b5a3', ('M1', 'M2'), 'Local complete-domain LP trajectory pricing'),
    SourceApiSpec('v42_m1_hybrid/dw.py', 'run', '(case, decomp, columns, ledger, output, *, seconds=30)', '111f49ab1e63a7b4ec90a413a3d1b116e0561a7cc407bd301ad1c38bbdc5f88f', ('M1', 'M2'), 'Restricted master with original row dual transport'),
    SourceApiSpec('v42_m1_hybrid/verify.py', 'verify_decomposition', '(case, decomposition)', '889193e86fc75b9fda94cecbcc4de36b223da52abae65e18885a7cc6fffe9a48', ('M1', 'M2'), 'Independent original decomposition coverage'),
    SourceApiSpec('v42_m1_hybrid/verify.py', 'verify_global_lagrangian_bound', '(case, decomposition, coupling_dual, unit_duals, *, nonunit_dual=None)', '889193e86fc75b9fda94cecbcc4de36b223da52abae65e18885a7cc6fffe9a48', ('M1', 'M2'), 'Original full-domain global exact dual bound'),
    SourceApiSpec('v42_m1_hybrid/verify.py', 'verify_rmp_pricing_lower_bounds', '(case, decomposition, full_rmp_dual, unit_duals, convexity_duals)', '889193e86fc75b9fda94cecbcc4de36b223da52abae65e18885a7cc6fffe9a48', ('M1', 'M2'), 'Independent RMP missing-column lower-bound admission'),
    SourceApiSpec('v42_m1_anytime/core.py', 'schedule_choice', '(history, iteration, wall)', '78a00beaf605125f6b996b49ef662402d6ab3f6d27d8bfe275e0b606a62caf17', ('M1', 'M2'), 'Existing primal-dual adaptive scheduler'),
    SourceApiSpec('v42_m1_anytime/algorithms.py', 'ub_trial', '(case, point, method, ordinal, ledger, frontier, path, limit, grid, *, context=None)', '1ba142fa2baea50c7f4acf6412d9fe9b6e21d9a731b2be06e24b31ac49ccc25c', ('M1', 'M2'), 'Original-row primal route/mode/P/Q/SOC neighborhood'),
    SourceApiSpec('v42_m1_anytime/algorithms.py', 'lp_round', "(case, decomp, dual, ledger, frontier, path, method, kind='LP_ONLY', *, context=None)", '1ba142fa2baea50c7f4acf6412d9fe9b6e21d9a731b2be06e24b31ac49ccc25c', ('M1', 'M2'), 'Complete-domain exact lower-bound pricing round'),
    SourceApiSpec('v42_m1_anytime/algorithms.py', 'feedback_master', '(case, decomp, point, ledger, path, *, context=None)', '1ba142fa2baea50c7f4acf6412d9fe9b6e21d9a731b2be06e24b31ac49ccc25c', ('M1', 'M2'), 'Current strict-UB trajectory to original restricted master'),
    SourceApiSpec('v42_m1_research/check_lb.py', 'check_rational_dual_certificate', '(A, d, multipliers, *, lower=None, upper=None, source_rows=None, case_sha=None)', '6c87483c677e015c966da3b5f76277968ed7a3412166a081b807bb60b65570d8', ('M1', 'M2'), 'Independent exact original-row global dual certificate'),
    SourceApiSpec('v42_m1_research/check_ub.py', 'validate_candidate', '(case, point)', '92ebe7d05225b91921ce910638ea4325279962f6efee2cbfb3503e87aab34b6e', ('M1', 'M2'), 'Original rows, exact integrality and physics candidate admission'),
    SourceApiSpec('v42_m1_research/check_ub.py', 'physical_replay', '(case, original_point)', '92ebe7d05225b91921ce910638ea4325279962f6efee2cbfb3503e87aab34b6e', ('M1', 'M2'), 'Unchanged original route/SOC/PCS and charge-mode validator'),
    SourceApiSpec('v42_m1_hybrid/final_verify.py', '_strict_ub', '(case, path, evidence)', '2fdd456498ca3e14b7f036258176da825e65dbdaf6739390082370313f07023e', ('M1', 'M2'), 'Raw point exact original UB and physical admission'),
    SourceApiSpec('v42_native/mess.py', 'solve', "(stage, deadline, sites, initial_sites, routes, battery, horizon, grid_builder, incumbent=None, *, mode='MILP', diagnostic=False, progress=None, strengthening_hook=None)", '547f5d7aec0572c65b96b9e61382176e269af7d93937fe71ca2a57de265217ec', ('M1', 'M2'), 'Original route flow/Pch/Pdis/Q/SOC/PCS builder'),
    SourceApiSpec('v42_native/mess.py', 'validate', '(result, sites, routes, battery, horizon, tolerance=1e-05)', '547f5d7aec0572c65b96b9e61382176e269af7d93937fe71ca2a57de265217ec', ('M1', 'M2'), 'Original route continuity, energy, PCS and connection replay'),
    SourceApiSpec('v42_integrated/contract.py', 'physical_authority', '()', '5b120d3ef9647ab8189baeb33abbe83e4a374845083ed39bcf066e66879c8e17', ('A1', 'M1', 'A2', 'M2'), 'Original NormalAmps and zero-margin voltage authority scope'),
    SourceApiSpec('v42_integrated/contract.py', 'all_transformer_rows', '(builder, binding_rows=None)', '5b120d3ef9647ab8189baeb33abbe83e4a374845083ed39bcf066e66879c8e17', ('A1', 'M1', 'A2', 'M2'), 'Original complete 120 transformer phase-current rows'),
    SourceApiSpec('v42_may_campaign_native90/budget.py', 'DateBudget.native_optimize', "(self, model, callback=None, *, component='P1', track='A', label='', requested_seconds=None)", '6626d770f9259df1a7f9aa7bc736ceaae43fbff9cc732b4579080533a083f4f8', ('A1', 'M1', 'A2', 'M2'), 'Measured native-only runtime accounting reference'),
    SourceApiSpec('v42_native/planning.py', 'freeze_day_ahead_plan', '(final_plan, output, *, grid_sha)', '8ae74c945abf935e89f2830d8580b4835e54884415cee78a6d1f783e8e3d99ae', ('A1', 'M1', 'A2', 'M2'), 'Existing immutable day-ahead source plan freeze'),
    SourceApiSpec('v42_native/actual.py', 'run_dday_actual', '(frozen_day_ahead_plan, realized_inputs, backend: ActualBackend, output, *, local_p_repair=False, local_q_repair=False, full_reoptimization=False)', 'a830c6f31a74bdb686514ff0f6d721712fd0ae9e9bca1b4df0435188b1a28a9a', ('A1', 'M1', 'A2', 'M2'), 'Existing frozen controls Actual and single Fresh AC path'),
)


def _definition(tree, symbol):
    scope = tree
    for part in symbol.split("."):
        matches = [node for node in scope.body
                   if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == part]
        require(len(matches) == 1, "SOURCE_API_DEFINITION_REQUIRED:" + symbol)
        scope = matches[0]
    require(isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)),
            "SOURCE_CALL_SIGNATURE_REQUIRED:" + symbol)
    return scope


def inspect_source_api(spec, source_root=None):
    """Read a single small Python source and parse AST; never execute its code."""
    require(isinstance(spec, SourceApiSpec), "TYPED_SOURCE_SPEC_REQUIRED")
    root = Path(source_root or Path(__file__).resolve().parents[1]).resolve()
    source = (root / spec.file).resolve()
    require(source.is_relative_to(root), "SOURCE_ESCAPE_FORBIDDEN")
    raw = source.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == spec.source_sha256,
            "SOURCE_API_SHA_DRIFT:" + spec.file)
    tree = ast.parse(raw.decode("utf-8-sig"), filename=spec.file)
    definition = _definition(tree, spec.symbol)
    observed = "(" + ast.unparse(definition.args) + ")"
    require(observed == spec.signature, "SOURCE_API_SIGNATURE_DRIFT:" + spec.symbol)
    return dict(spec.to_dict(), line=definition.lineno,
                status="STATIC_SIGNATURE_PASS", source_executed=False,
                native_calls=0, model_builds=0, physical_domain_builds=0)


def inspect_source_links(stage=None, source_root=None):
    if stage is not None:
        gap_target(stage)
    specs = [spec for spec in SOURCE_APIS if stage is None or stage in spec.stages]
    return tuple(inspect_source_api(spec, source_root) for spec in specs)


@dataclass(frozen=True)
class PreparedSourceBinding:
    stage: str
    authority_sha: str
    request_sha: str
    fixed_input_sha: str
    payload_json: str
    api_specs: tuple
    unresolved_interfaces: tuple
    status: str = "STATIC_INPUT_DESCRIPTOR_COMPLETE_SOURCE_INVOCATION_DEFERRED"

    def __post_init__(self):
        gap_target(self.stage)
        for name in ("authority_sha", "request_sha", "fixed_input_sha"):
            require_sha(getattr(self, name))
        payload = json.loads(self.payload_json)
        require(payload["stage"] == self.stage
                and payload["authority_sha"] == self.authority_sha
                and payload["request_sha"] == self.request_sha
                and payload["fixed_input_sha"] == self.fixed_input_sha,
                "SOURCE_BINDING_IDENTITY_DRIFT")
        object.__setattr__(self, "payload_json", canonical(payload))
        object.__setattr__(self, "api_specs", tuple(self.api_specs))
        object.__setattr__(self, "unresolved_interfaces", tuple(self.unresolved_interfaces))
        require(all(isinstance(spec, SourceApiSpec) for spec in self.api_specs),
                "SOURCE_BINDING_TYPED_APIS_REQUIRED")

    @property
    def sha(self):
        return digest(self.to_dict())

    def payload(self):
        # A fresh detached dict cannot mutate the sealed request descriptor.
        return json.loads(self.payload_json)

    def to_dict(self):
        return dict(stage=self.stage, authority_sha=self.authority_sha,
                    request_sha=self.request_sha, fixed_input_sha=self.fixed_input_sha,
                    payload=self.payload(), api_specs=[spec.to_dict() for spec in self.api_specs],
                    unresolved_interfaces=list(self.unresolved_interfaces), status=self.status)


COMMON_GAPS = (
    "Resolve original same-day source bundle, electrical coefficients and route/PCS authority by SHA; do not load a historical case.",
    "Create and independently certify the original stage-specific model only after separate production authorization.",
    "Bind original global LB/UB and integer/physical replay to this request, fixed_input_sha and decision_sha; static linkage is not a scientific certificate.",
)
A2_GAPS = (
    "Recovery A prepare uses F2-CRA with MESS disabled; a B3 source-bound grid callback must substitute every fixed M1 route/location/Pch/Pdis/Q/SOC decision while retaining all original A rows and complete pricing blocks.",
    "Recovery _planning rejects non-AIDC controls and emits zero MESS arrays; adapt A2 materialization and original physical replay to the exact fixed M1 control packet.",
    "A2 full-domain bounds and integer recovery must be regenerated for the fixed M1 plan; A1 or historical closure/bounds are not transferable.",
)
M_GAPS = (
    "Bypass the B2 FCFS generate_b2 producer only via an explicitly admitted A1/A2 source payload; preserve the original job option schema and causal forecast authority.",
    "Authority is a SHA contract, not a full native bundle. The same-day original bundle, power coefficients and known_gpu materialization must be supplied and independently checked; do not infer them from the interface arrays.",
    "Original build_case consumes PCC_P_kw and computes the established Q relation through its source grid path; verify the independently supplied PCC_Q_kvar against that unchanged authority before construction.",
    "The existing m_model/m_stage runners hardcode arm B2 and stage M1; implement isolated B3 stage/output/provenance routing without changing active B1/B2 files.",
)
M2_GAPS = (
    "Route ConstructionDeadline.stage, native.solve stage, GridAuthority stage and voltage authority to M2; the existing M1 builder cannot be relabeled after construction.",
    "M1 is only a warm-start candidate. Revalidate its raw integer/physical point under the new fixed A2 anchor and reconstruct the new case axis before admission.",
)


def _slot_major(rows):
    """Axis permutation only; numerical values remain untouched."""
    return [list(column) for column in zip(*rows)]


def _aidc_input(request):
    aidc = request.fixed_aidc
    return dict(
        authority_sha=request.authority.sha,
        decision_sha=aidc.sha,
        complete_immutable_decision=aidc.to_dict(),
        planning_fields=dict(sites=list(request.authority.pcc_ids),
                             time_axis=list(request.authority.slots),
                             PCC_P_kw=_slot_major(aidc.pcc_p),
                             PCC_Q_kvar=_slot_major(aidc.pcc_q),
                             IT_kw=_slot_major(aidc.it_power)),
        native_fixed_controls={"aidc_load_kw[" + site + "]": list(aidc.pcc_p[index])
                               for index, site in enumerate(request.authority.pcc_ids)},
        source_job_actions=json.loads(aidc.jobs_json),
        source_gpu_runtime_state=json.loads(aidc.gpu_runtime_json),
        source_complete_variables=json.loads(aidc.variables_json),
        GPU_known_gpu_mapping_status="ORIGINAL_MATERIALIZER_REQUIRED",
        AIDC_decision_variables=0,
        allowed_to_change=False,
    )


def _mess_input(request):
    mess = request.fixed_mess
    return dict(
        authority_sha=request.authority.sha,
        decision_sha=mess.sha,
        complete_immutable_decision=mess.to_dict(),
        unit_ids=list(request.authority.mess_ids),
        time_axis=list(request.authority.slots),
        SOC_time_axis=list(range(97)),
        unit_slot_source_families=dict(routes=[list(row) for row in mess.routes],
                                       location=_slot_major(mess.location),
                                       Pch_kw=_slot_major(mess.charge_p),
                                       Pdis_kw=_slot_major(mess.discharge_p),
                                       Q_kvar=_slot_major(mess.q),
                                       SOC_kwh=_slot_major(mess.soc),
                                       move_energy_kwh=_slot_major(mess.move_energy)),
        source_initial_final_state=json.loads(mess.initial_final_json),
        source_complete_variables=json.loads(mess.variables_json),
        native_site_expansion_status="ORIGINAL_ROUTE_AND_CHARGER_MAPPING_REQUIRED",
        MESS_decision_variables=0,
        allowed_to_change=False,
    )


def _verification_plan(stage):
    """Name original verifier interfaces without accepting any producer flag."""
    if stage.startswith("A"):
        roles = {
            "complete_domain": (("v42_a_stage_domain_v2/domain.py", "physical_domain"),),
            "complete_pricing_and_global_LB": (("v42_a_stage_canary/pricing.py", "full_pricing"),),
            "original_integer_type_restore": (("v42_a_stage_practical/integer_model.py", "restore_types"),),
            "original_integer_job_grid_replay_and_UB": (
                ("v42_a_stage_acceptance/physical.py", "Physical.verify"),
                ("v42_pr134_sc/snapshot.py", "certify")),
        }
    else:
        roles = {
            "original_FULL_compact_C3A_transport": (
                ("v42_may_campaign_native90/m_model.py", "verify_transport"),
                ("v42_may_campaign_native90/m_model.py", "verify_case")),
            "global_exact_LB": (("v42_m1_research/check_lb.py", "check_rational_dual_certificate"),
                                ("v42_m1_hybrid/verify.py", "verify_global_lagrangian_bound")),
            "RMP_missing_column_LB": (("v42_m1_hybrid/verify.py", "verify_rmp_pricing_lower_bounds"),),
            "original_integer_physical_UB": (("v42_m1_hybrid/final_verify.py", "_strict_ub"),
                                             ("v42_m1_research/check_ub.py", "validate_candidate")),
            "original_route_SOC_PCS_charge_mode_replay": (
                ("v42_m1_research/check_ub.py", "physical_replay"),
                ("v42_native/mess.py", "validate")),
        }
    catalog = {(spec.file, spec.symbol): spec for spec in SOURCE_APIS}
    return dict(status="ORIGINAL_VERIFIER_LINKS_PREPARED_NOT_INVOKED",
                source_apis={role: [catalog[key].to_dict() for key in keys]
                             for role, keys in roles.items()},
                required_packet_bindings=["stage", "authority_sha", "fixed_input_sha",
                                          "decision_sha", "original_model_sha", "verifier_source_sha"],
                original_verifiers_called=False, scientific_certified=False,
                accept_producer_PASS_without_independent_source_replay=False)


def prepare_source_binding(request):
    """Prepare A1/M1/A2/M2 input maps using only the immutable small interface.

    No source loading, model/domain construction, pricing or physical replay
    happens here. Legacy unknown-job, Q and GPU arithmetic is never recreated.
    """
    require(isinstance(request, StageRequest), "TYPED_STAGE_REQUEST_REQUIRED")
    target = gap_target(request.stage)
    aidc = _aidc_input(request) if request.fixed_aidc is not None else None
    mess = _mess_input(request) if request.fixed_mess is not None else None
    gaps = COMMON_GAPS
    if request.stage == "A2":
        gaps += A2_GAPS
    if request.stage.startswith("M"):
        gaps += M_GAPS
    if request.stage == "M2":
        gaps += M2_GAPS
    warm = request.warm_start
    warm_start = None
    if warm is not None:
        warm_start = dict(contract_eligibility_claim=warm.eligible,
                          contract_feasibility_claim=warm.feasibility_verified,
                          evidence_kind="MOCK", actual_feasibility_status="NOT_RUN",
                          authority_sha=warm.authority_sha, fixed_aidc_sha=warm.fixed_aidc_sha,
                          candidate_mess_sha=warm.mess.sha, reason=warm.reason,
                          selected_for_future_native=False,
                          decision=warm.mess.to_dict() if warm.eligible else None,
                          raw_point_native_admission_status="ORIGINAL_VERIFIER_BRIDGE_NOT_IMPLEMENTED",
                          historical_certificate_transferred=False)
    payload = dict(schema="V42_B3_SOURCE_BINDING_PREPARATION_V1", stage=request.stage,
                   authority=request.authority.to_dict(), authority_sha=request.authority.sha,
                   request_sha=request.request_sha, fixed_input_sha=request.fixed_input_sha,
                   objective="min rho_max", exact_gap_target=str(target), Threads=1,
                   P2_calls=0, native_limit_seconds=5400,
                   fixed_aidc=aidc, fixed_mess=mess, warm_start=warm_start,
                   optimized_families=(["AIDC_job_time", "AIDC_migration", "GPU", "Rack", "WAN", "QoS"]
                                       if request.stage.startswith("A") else
                                       ["movement", "route", "location", "Pch", "Pdis", "P", "Q", "SOC", "charge_mode"]),
                   optimized_source_variable_families=(
                       ["original_job_schedule", "original_STAY_integer_histogram", "original_individual_migration"]
                       if request.stage.startswith("A") else ["arc", "charge_mode", "Pch", "Pdis", "Q", "SOC"]),
                   interface_shapes={"AIDC_PCC_IT": [12, 96], "MESS_PQ_location_move_energy": [4, 96],
                                     "MESS_SOC": [4, 97], "source_PCC_IT": [96, 12]},
                   verification_plan=_verification_plan(request.stage),
                   MESS_optimization_off=request.stage == "A1",
                   source_payload_ready_for_native_build=False,
                   preparation_only=True, native_calls=0, model_builds=0,
                   pricing_calls=0, physical_domain_builds=0, OpenDSS_calls=0)
    return PreparedSourceBinding(request.stage, request.authority.sha, request.request_sha,
                                 request.fixed_input_sha, canonical(payload),
                                 tuple(spec for spec in SOURCE_APIS if request.stage in spec.stages),
                                 gaps)


class NativeStageAdapter:
    """Source-linked production placeholder with a pre-import unconditional gate."""

    def prepare(self, request):
        return prepare_source_binding(request)

    def execute(self, request, budget):
        require_production_authorization(action="NATIVE_STAGE_ADAPTER")
        # Even replacing the policy function cannot introduce a solver import.
        raise PermissionError("B3_NATIVE_ADAPTER_IMPLEMENTATION_REQUIRES_SEPARATE_REVIEW")

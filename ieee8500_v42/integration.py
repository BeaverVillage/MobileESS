"""Isolated IEEE8500 admission contracts and additional PCC constraints.

This module neither imports a solver nor dispatches an existing campaign.
The hook appends rows to the original ``StrengtheningContext``; original
route, mode, battery, grid, objective and exact-transport rows stay present.
Explicitly SHA-bound simulation-design ports are admitted for research only.
These additional rows still require real FULL/Compact/C3A equivalence and
the independent original physical replay before any production execution.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path


ARMS = ("B0", "B1", "B2", "B3")
ARM_STAGES = {"B0": (), "B1": ("A1",), "B2": ("M1",),
              "B3": ("A1", "M1", "A2", "M2")}
GATES = (
    "single_frozen_scenario", "original_branch_conductor_identity",
    "all_bus_voltage_and_transformer_winding_authority",
    "orientation_preserving_mapping", "lv_pcc_and_device_eligibility",
    "source_causal_job_gpu_rack_wan_qos_capacity",
    "certified_96_slot_affine_control_domain", "feeder_grid_source_hooks",
    "six_vehicle_axis_and_original_transport_equivalence",
    "original_and_added_location_constraints_replay",
    "independent_planning_actual_fresh_feeder_hooks",
    "all_96_slots_real_ac_physical_feasibility",
)
FACES = 16
DAY = "2025-05-01"
ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FOLDER = ROOT / "docs/ieee8500_v42_single_case/integration_contracts"
DESIGN_PATH = ROOT / "docs/ieee8500_v42_single_case/LV_PORT_SIMULATION_DESIGN.json"
SIMULATION_SCHEMA = "IEEE8500_V42_USER_AUTHORIZED_SIMULATION_DESIGN_V1"


def digest(document):
    raw = json.dumps(document, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def verify_source_identity(root, manifest):
    """Read-only, byte-exact verification; never rewrites source line endings."""
    root = Path(root).resolve()
    records = manifest.get("files", {})
    if not records or len(manifest.get("v42_git_sha", "")) != 40:
        raise ValueError("PINNED_V42_SOURCE_MANIFEST_REQUIRED")
    for relative, expected in records.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or file_sha(path) != expected:
            raise ValueError("ORIGINAL_SOURCE_IDENTITY_DRIFT:" + relative)
    return {"PASS": True, "source_files_verified": len(records),
            "v42_git_sha": manifest["v42_git_sha"],
            "source_manifest_sha": digest(manifest), "native_calls": 0,
            "evidence_kind": "BYTE_IDENTITY_ONLY"}


def comparison_plan(scenario, *, gate_receipts=None):
    """Prepare identical-condition arm requests without executing any stage.

    Gate evidence is inspected from saved, hashed real receipts. No Boolean
    permit or environment variable enables solver execution in this release.
    An AC screening candidate is never promoted into a selected configuration.
    """
    frozen = json.loads(json.dumps(scenario, allow_nan=False))
    sha = digest(frozen)
    receipts = gate_receipts or {}
    completed, unresolved = {}, []
    for gate in GATES:
        receipt = receipts.get(gate)
        if receipt is None:
            unresolved.append(gate)
            continue
        path = Path(receipt["path"])
        if file_sha(path) != receipt["sha256"]:
            raise ValueError("INTEGRATION_GATE_ARTIFACT_DRIFT:" + gate)
        evidence = json.loads(path.read_text(encoding="utf-8-sig"))
        if (evidence.get("PASS") is not True or evidence.get("gate") != gate
                or evidence.get("scenario_sha") != sha
                or evidence.get("evidence_kind") not in
                ("REAL_OPENDSS", "INDEPENDENT_EXACT_SOURCE_VERIFICATION")
                or not _sha256(evidence.get("verifier_source_sha"))):
            unresolved.append(gate)
        else:
            completed[gate] = dict(receipt)
    if (frozen.get("status") != "SELECTED_AND_FROZEN"
            or frozen.get("day") != DAY):
        if "single_frozen_scenario" not in unresolved:
            unresolved.append("single_frozen_scenario")
    arms = []
    for arm in ARMS:
        stages = []
        for stage in ARM_STAGES[arm]:
            stages.append({"stage": stage, "gap_target": .005 if stage[0] == "A" else .03,
                           "native_runtime_limit_seconds": 5400, "Threads": 1,
                           "P2_calls": 0, "budget_basis": "MEASURED_NATIVE_RUNTIME_ONLY",
                           "independent_ledger": True, "bound_or_model_transfer": False})
        arms.append({"arm": arm, "scenario_sha": sha,
                     "aidc_flexibility": arm in ("B1", "B3"),
                     "mess_flexibility": arm in ("B2", "B3"), "stages": stages,
                     "native_execution_status": "NOT_RUN",
                     "planning_actual_fresh_status": "NOT_RUN"})
    return {"schema": "IEEE8500_V42_COMPARISON_ADMISSION_V1", "day": DAY,
            "scenario_sha": sha, "arms": arms, "completed_gates": completed,
            "unresolved_gates": unresolved, "production_ready": False,
            "production_execution": "UNAVAILABLE_PENDING_CERTIFIED_PORT_AND_SEPARATE_APPROVAL",
            "objective": "min max(line conductor current / original NormalAmps)",
            "voltage_band_pu": [.95, 1.05], "joint_global_optimality_claim": False,
            "native_calls": 0, "full_model_builds": 0}


def execute_production(*args, **kwargs):
    """A separate approved execution implementation is intentionally required."""
    raise PermissionError("IEEE8500_V42_CERTIFIED_PRODUCTION_PORT_NOT_AVAILABLE")


@dataclass(frozen=True)
class LocationPort:
    site: str
    bus: str
    nodes: tuple
    connection: str
    p_charge_kw: float
    p_discharge_kw: float
    pcs_kva: float
    eligible_units: tuple
    available_slots: tuple
    physical_evidence_sha: str
    certified: bool = False
    authority_kind: str = "UNVERIFIED"
    simulation_design_sha: str = ""
    simulation_authority_sha: str = ""
    field_certified: bool | None = None
    q_abs_kvar: float | None = None
    physical_evidence_path: str = ""

    @property
    def field_certificate_claim(self):
        # Legacy fixtures retain their old structural certified field. It never
        # substitutes for the actual certificate-chain check in Production.
        return self.certified if self.field_certified is None else self.field_certified

    @property
    def reactive_limit_kvar(self):
        return self.pcs_kva if self.q_abs_kvar is None else self.q_abs_kvar

    def validate(self, horizon=96, *, execution_scope="RESEARCH", simulation_authority=None):
        if execution_scope not in ("RESEARCH", "PRODUCTION"):
            raise ValueError("EXPLICIT_RESEARCH_OR_PRODUCTION_SCOPE_REQUIRED")
        if (not isinstance(self.site, str) or not self.site
                or not isinstance(self.bus, str) or not self.bus
                or type(self.certified) is not bool or self.connection not in
                ("THREE_PHASE_MV", "SPLIT_PHASE_240V", "SINGLE_PHASE_120V")
                or not self.nodes or len(set(self.nodes)) != len(self.nodes)
                or self.authority_kind not in ("UNVERIFIED", "FIELD_CERTIFIED", "SIMULATION_DESIGN")
                or (self.field_certified is not None and type(self.field_certified) is not bool)
                or (self.field_certified is not None and self.field_certified != self.certified)
                or (self.authority_kind != "SIMULATION_DESIGN" and not _sha256(self.physical_evidence_sha))):
            raise ValueError("SOURCE_PCC_CONNECTION_AUTHORITY_REQUIRED")
        expected = {"THREE_PHASE_MV": 3, "SPLIT_PHASE_240V": 2,
                    "SINGLE_PHASE_120V": 1}[self.connection]
        if len(self.nodes) != expected or any(type(n) is not int or n <= 0 for n in self.nodes):
            raise ValueError("PCC_PHASE_NODE_COUNT_REQUIRED")
        limits = (self.p_charge_kw, self.p_discharge_kw, self.pcs_kva)
        if (any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in limits)
                or max(self.p_charge_kw, self.p_discharge_kw) > self.pcs_kva
                or type(self.reactive_limit_kvar) not in (int, float)
                or not math.isfinite(self.reactive_limit_kvar)
                or not 0 <= self.reactive_limit_kvar <= self.pcs_kva
                or any(not isinstance(unit, str) or not unit for unit in self.eligible_units)
                or len(set(self.eligible_units)) != len(self.eligible_units)
                or len(set(self.available_slots)) != len(self.available_slots)
                or any(type(t) is not int or not 0 <= t < horizon for t in self.available_slots)):
            raise ValueError("FINITE_ORIGINAL_PCC_LIMITS_AND_AVAILABILITY_REQUIRED")
        if self.authority_kind == "SIMULATION_DESIGN":
            if execution_scope != "RESEARCH" or self.certified or self.field_certificate_claim:
                raise ValueError("SIMULATION_DESIGN_RESEARCH_ONLY_NOT_FIELD_CERTIFIED")
            _verify_simulation_design(self, simulation_authority)
        elif not self.certified and any(limits):
            raise ValueError("UNCERTIFIED_PORT_MUST_HAVE_ZERO_PQ_LIMITS")
        if execution_scope == "PRODUCTION":
            _verify_actual_field_certificates(self)
        return True


def _verify_simulation_design(port, authority_path=None):
    authority_path = Path(authority_path or CONTRACT_FOLDER / "RESEARCH_SIMULATION_AUTHORITY.json")
    if (not authority_path.is_file() or not _sha256(port.simulation_design_sha)
            or not _sha256(port.simulation_authority_sha)
            or file_sha(authority_path) != port.simulation_authority_sha):
        raise ValueError("SHA_BOUND_SIMULATION_DESIGN_AUTHORITY_REQUIRED")
    authority = json.loads(authority_path.read_text(encoding="utf-8-sig"))
    if (authority.get("schema") != SIMULATION_SCHEMA or authority.get("scope") != "RESEARCH_ONLY"
            or authority.get("user_authorized") is not True or authority.get("production_authorized") is not False
            or authority.get("authority_source") != "EXPLICIT_USER_AUTHORIZATION_FOR_SIMULATION_LV_PORT_DESIGN"):
        raise ValueError("EXPLICIT_USER_RESEARCH_DESIGN_AUTHORITY_REQUIRED")
    record = authority.get("design_file", {})
    path = Path(record.get("path", ""))
    if not path.is_absolute():
        path = authority_path.parent / path
    if (not path.is_file() or file_sha(path) != port.simulation_design_sha
            or record.get("sha256") != port.simulation_design_sha
            or path.resolve() != DESIGN_PATH.resolve()):
        raise ValueError("SIMULATION_DESIGN_SOURCE_SHA_DRIFT")
    design = json.loads(path.read_text(encoding="utf-8-sig"))
    if (design.get("status") != "AUTHORIZED_SIMULATION_INTERFACE_DESIGN_NOT_INSTALLED_HARDWARE"
            or design.get("production_eligible") is not False
            or design.get("field_installation_certified") is not False
            or port.connection != "SPLIT_PHASE_240V" or tuple(port.nodes) != (1, 2)
            or port.p_charge_kw > min(5., design["P_import_max_kw"])
            or port.p_discharge_kw > min(5., design["P_export_max_kw"])
            or port.pcs_kva > min(6., design["S_max_kva"])
            or port.q_abs_kvar is None or port.q_abs_kvar > min(3., design["Q_abs_max_kvar"])):
        raise ValueError("AUTHORIZED_SIMULATION_SPLIT240_5KW_3KVAR_6KVA_ENVELOPE_REQUIRED")
    return authority


def _verify_actual_field_certificates(port):
    """A Boolean field is not a Production equipment certificate chain."""
    required = {"installed_device", "grid_interconnection", "protection_and_earthing",
                "anti_islanding_grid_profile", "vehicle_dc_dc_BMS", "physical_access"}
    path = Path(port.physical_evidence_path)
    if (not port.certified or not port.field_certificate_claim or not path.is_file()
            or file_sha(path) != port.physical_evidence_sha):
        raise ValueError("ACTUAL_FIELD_CERTIFICATES_REQUIRED_FOR_PRODUCTION")
    evidence = json.loads(path.read_text(encoding="utf-8-sig"))
    records = evidence.get("certificates", {})
    if (evidence.get("evidence_kind") != "ACTUAL_INSTALLED_FIELD_CERTIFICATE_CHAIN"
            or evidence.get("site") != port.site or evidence.get("bus") != port.bus
            or required - records.keys()):
        raise ValueError("COMPLETE_ACTUAL_FIELD_CERTIFICATE_CHAIN_REQUIRED")
    for key in required:
        record = records[key]; certificate = Path(record.get("path", ""))
        if not certificate.is_absolute():
            certificate = path.parent / certificate
        if (not certificate.is_file() or not _sha256(record.get("sha256"))
                or file_sha(certificate) != record["sha256"]):
            raise ValueError("ACTUAL_FIELD_CERTIFICATE_SHA_DRIFT:" + key)


def _ports_by_site(ports, horizon, execution_scope="RESEARCH", simulation_authority=None):
    result = {}
    for port in ports:
        port.validate(horizon, execution_scope=execution_scope, simulation_authority=simulation_authority)
        if port.site in result:
            raise ValueError("ONE_PORT_AUTHORITY_PER_SERVICE_SITE_REQUIRED")
        result[port.site] = port
    return result


def make_location_strengthening_hook(ports, *, quicksum, execution_scope="RESEARCH", simulation_authority=None):
    """Append physical location limits through the original source hook API.

    ``quicksum`` must be the original solver expression constructor. No new
    variables/objectives are introduced. Units at an unauthorized port retain
    route access with zero P/Q. A verified SIMULATION_DESIGN admits positive
    research limits only. Aggregate charge/discharge and the same inner
    16 PCS faces impose conservative shared-port ratings across all vehicles.
    """
    ports = tuple(ports)

    def append(model, context):
        roster = _ports_by_site(ports, context.horizon, execution_scope, simulation_authority)
        sites, units = tuple(context.sites), tuple(context.initial_sites)
        if set(roster) != set(sites) or len(units) != 6:
            raise ValueError("ALL_24_SITE_AND_SIX_VEHICLE_PORT_AXES_REQUIRED")
        if len(sites) != 24 or any(set(p.eligible_units) - set(units) for p in ports):
            raise ValueError("PORT_ELIGIBILITY_OUTSIDE_ORIGINAL_UNIT_AXIS")
        model.update()
        original_variables, original_rows = model.NumVars, model.NumConstrs
        count = 0
        for site in sites:
            port = roster[site]
            for t in range(context.horizon):
                for unit in units:
                    key = unit, site, t
                    connected = context.x[unit, context.stay[site, t]]
                    authorized = port.certified or (execution_scope == "RESEARCH" and port.authority_kind == "SIMULATION_DESIGN")
                    eligible = int(authorized and unit in port.eligible_units
                                   and t in port.available_slots)
                    ch, dis, q = context.charge[key], context.discharge[key], context.reactive[key]
                    label = f"ieee8500_port[{unit},{site},{t}]"
                    model.addConstr(ch <= port.p_charge_kw * eligible * connected, name=label + ":ch")
                    model.addConstr(dis <= port.p_discharge_kw * eligible * connected, name=label + ":dis")
                    model.addConstr(q <= port.reactive_limit_kvar * eligible * connected, name=label + ":q_upper")
                    model.addConstr(q >= -port.reactive_limit_kvar * eligible * connected, name=label + ":q_lower")
                    count += 4
                    for f in range(FACES):
                        angle = 2 * math.pi * f / FACES
                        face = math.cos(angle) * (dis - ch) + math.sin(angle) * q
                        model.addConstr(face <= port.pcs_kva * math.cos(math.pi / FACES)
                                        * eligible * connected, name=label + f":pcs{f}")
                        count += 1
                aggregate_ch = quicksum(context.charge[unit, site, t] for unit in units)
                aggregate_dis = quicksum(context.discharge[unit, site, t] for unit in units)
                aggregate_q = quicksum(context.reactive[unit, site, t] for unit in units)
                label = f"ieee8500_shared_port[{site},{t}]"
                model.addConstr(aggregate_ch <= port.p_charge_kw, name=label + ":ch")
                model.addConstr(aggregate_dis <= port.p_discharge_kw, name=label + ":dis")
                count += 2
                if port.q_abs_kvar is not None:
                    model.addConstr(aggregate_q <= port.q_abs_kvar, name=label + ":q_upper")
                    model.addConstr(aggregate_q >= -port.q_abs_kvar, name=label + ":q_lower")
                    count += 2
                for f in range(FACES):
                    angle = 2 * math.pi * f / FACES
                    face = math.cos(angle) * (aggregate_dis - aggregate_ch) + math.sin(angle) * aggregate_q
                    model.addConstr(face <= port.pcs_kva * math.cos(math.pi / FACES),
                                    name=label + f":pcs{f}")
                    count += 1
        model.update()
        if model.NumVars != original_variables or model.NumConstrs != original_rows + count:
            raise ValueError("APPEND_ONLY_PCC_ROW_CONSTRUCTION_DRIFT")
        return {"appended_rows": count, "new_variables": 0,
                "original_rows_retained": True, "original_unit_PCS_rows_retained": True,
                "port_authority_sha": digest([asdict(p) for p in ports]),
                "execution_scope": execution_scope,
                "simulation_design_port_count": sum(p.authority_kind == "SIMULATION_DESIGN" for p in ports),
                "LV_auxiliary_efficiency_SOC_adapter": "UNVERIFIED",
                "real_full_model_equivalence": "NOT_TESTED"}
    return append


def validate_location_limits(values, locations, ports, unit_ids, *, horizon=96, tolerance=1e-5,
                             execution_scope="RESEARCH", simulation_authority=None):
    """Independent numerical replay of additional PCC rows, without solver use.

    The caller must separately run the unchanged source route/SOC/grid replay.
    ``locations`` is slot-major and must come from its verified route replay.
    All original Pch/Pdis/Q site variables are required; absent values fail.
    """
    ports = tuple(ports)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("FINITE_NONNEGATIVE_REPLAY_TOLERANCE_REQUIRED")
    roster = _ports_by_site(ports, horizon, execution_scope, simulation_authority)
    units = tuple(unit_ids)
    if len(units) != 6 or len(set(units)) != 6 or len(roster) != 24:
        raise ValueError("ALL_24_SITE_AND_SIX_VEHICLE_REPLAY_AXES_REQUIRED")
    if (len(locations) != horizon or any(len(row) != 6 for row in locations)
            or any(set(p.eligible_units) - set(units) for p in ports)):
        raise ValueError("SOURCE_VERIFIED_LOCATION_AND_UNIT_AXES_REQUIRED")
    violations, maximum = [], 0.
    for site, port in roster.items():
        for t in range(horizon):
            total_ch = total_dis = total_q = 0.
            for j, unit in enumerate(units):
                row = tuple(values[f"{prefix}[{unit},{site},{t}]"] for prefix in ("Pch", "Pdis", "Q"))
                if any(type(v) not in (int, float) or not math.isfinite(v) for v in row):
                    raise ValueError("FINITE_COMPLETE_ORIGINAL_SITE_VARIABLES_REQUIRED")
                ch, dis, q = row
                connected = locations[t][j] == site
                authorized = port.certified or (execution_scope == "RESEARCH" and port.authority_kind == "SIMULATION_DESIGN")
                eligible = authorized and unit in port.eligible_units and t in port.available_slots
                scale = int(connected and eligible)
                errors = [-ch, -dis, ch - port.p_charge_kw * scale,
                          dis - port.p_discharge_kw * scale, abs(q) - port.reactive_limit_kvar * scale]
                errors.extend(math.cos(2 * math.pi * f / FACES) * (dis - ch)
                              + math.sin(2 * math.pi * f / FACES) * q
                              - port.pcs_kva * math.cos(math.pi / FACES) * scale
                              for f in range(FACES))
                error = max(0., *errors)
                maximum = max(maximum, error)
                if error > tolerance:
                    violations.append({"kind": "VEHICLE_PORT", "unit": unit, "site": site,
                                       "slot": t, "violation_kw_or_kvar": error})
                total_ch += ch; total_dis += dis; total_q += q
            errors = [total_ch - port.p_charge_kw, total_dis - port.p_discharge_kw]
            if port.q_abs_kvar is not None:
                errors.append(abs(total_q) - port.q_abs_kvar)
            errors.extend(math.cos(2 * math.pi * f / FACES) * (total_dis - total_ch)
                          + math.sin(2 * math.pi * f / FACES) * total_q
                          - port.pcs_kva * math.cos(math.pi / FACES) for f in range(FACES))
            error = max(0., *errors)
            maximum = max(maximum, error)
            if error > tolerance:
                violations.append({"kind": "SHARED_PORT", "site": site, "slot": t,
                                   "violation_kw_or_kvar": error})
    return {"PASS": not violations, "violations": violations,
            "maximum_violation_kw_or_kvar": maximum,
            "port_authority_sha": digest([asdict(p) for p in ports]),
            "evidence_kind": "ADDITIONAL_ROW_NUMERICAL_REPLAY_ONLY",
            "execution_scope": execution_scope,
            "simulation_design_port_count": sum(p.authority_kind == "SIMULATION_DESIGN" for p in ports),
            "field_certification_verified": execution_scope == "PRODUCTION",
            "original_route_soc_and_grid_replay_required": True,
            "real_opendss_verified": False, "native_calls": 0}


def research_port_contract(ports, *, horizon=96, simulation_authority=None):
    """Admit the declared interface ceiling, without admitting an AC operation."""
    ports = tuple(ports)
    roster = _ports_by_site(ports, horizon, "RESEARCH", simulation_authority)
    return {"schema": "IEEE8500_RESEARCH_PORT_LIMIT_ADMISSION_V1",
            "execution_scope": "RESEARCH_ONLY", "research_design_admitted": True,
            "ports": [asdict(p) for p in roster.values()],
            "port_authority_sha": digest([asdict(p) for p in ports]),
            "simulation_design_port_count": sum(p.authority_kind == "SIMULATION_DESIGN" for p in ports),
            "field_certification_verified": False, "production_ready": False,
            "operational_AC_feasibility": "NOT_CERTIFIED_BY_INTERFACE_DESIGN_ADMISSION",
            "actual_six_unit_native_and_SOC_adapter": "UNVERIFIED",
            "original_route_access_SOC_grid_and_PCS_rows_required": True,
            "Native_calls": 0, "full_model_builds": 0}


def build_research_fleet_configuration(base_path=None, design_path=None):
    """Preserve original six initial sites and energy fractions; scale ratings1.5."""
    base_path = Path(base_path or ROOT / "ieee8500_v42/data/research_case/PAPER_FLEET_BASE_AUTHORITY.json")
    design_path = Path(design_path or DESIGN_PATH)
    base = json.loads(base_path.read_text(encoding="utf-8-sig"))
    design = json.loads(design_path.read_text(encoding="utf-8-sig"))
    units = tuple(f"MESS{i:02d}" for i in range(1, 7))
    initial = base["initial_locations"]
    expected_initial = dict(zip(units, ("STA01", "STA12", "STA08", "STA06", "STA03", "STA10")))
    if (tuple(base["fleet_ids"]) != units or set(initial) != set(units)
            or initial != expected_initial
            or base["B2_initial_locations"] != initial or base["B3_initial_locations"] != initial
            or any(initial[u] not in {f"STA{i:02d}" for i in range(1, 13)} for u in units)):
        raise ValueError("PRESERVED_ORIGINAL_SIX_INITIAL_STA_AUTHORITY_REQUIRED")
    physical = base["physical"]
    if (physical["active_power_limit_kw"] != 300. or physical["pcs_kva"] != 400.
            or physical["capacity_kwh"] != 1200. or physical["charge_efficiency"] != .95
            or physical["discharge_efficiency"] != .95 or design["study_auxiliary_conversion_efficiency"] != .90
            or tuple(physical[k] for k in ("energy_min_kwh", "energy_max_kwh", "initial_energy_kwh", "terminal_energy_kwh")) != (440., 1080., 760., 760.)):
        raise ValueError("ORIGINAL_RATING_FRACTIONS_AND_EFFICIENCY_AUTHORITY_REQUIRED")
    scaled = dict(physical)
    for key in ("active_power_limit_kw", "pcs_kva", "capacity_kwh", "energy_min_kwh", "energy_max_kwh",
                "initial_energy_kwh", "terminal_energy_kwh"):
        scaled[key] = 1.5 * physical[key]
    native_path = ROOT / "ieee8500_v42/data/workload_flexibility/NATIVE_INPUT.json"
    native = json.loads(native_path.read_text(encoding="utf-8-sig"))
    return {"schema": "IEEE8500_SIX_UNIT_RESEARCH_FLEET_CONFIGURATION_V1", "day": DAY,
            "status": "RESEARCH_CONFIGURATION_ONLY_ACTUAL_NATIVE_ADAPTER_UNVERIFIED",
            "fleet_ids": list(units), "initial_locations": initial,
            "B2_initial_locations": dict(initial), "B3_initial_locations": dict(initial),
            "rating_scale": 1.5, "rating_authority": "USER450KW_600KVA_1800KWH_WITH_ORIGINAL_ENERGY_FRACTIONS",
            "physical": scaled, "initial_total_energy_kwh": 6 * scaled["initial_energy_kwh"],
            "nominal_total_capacity_kwh": 6 * scaled["capacity_kwh"],
            "original_main_PCS_charge_efficiency": .95, "original_main_PCS_discharge_efficiency": .95,
            "LV_auxiliary_interface_efficiency_assumption": .90,
            "LV_AC_to_battery_charge_efficiency": .95 * .90,
            "LV_battery_to_AC_discharge_efficiency": .95 * .90,
            "AC_port_to_battery_SOC_equation": "deltaE=hours*(eta_main*eta_LV*Pch_AC-Pdis_AC/(eta_main*eta_LV))-original_route_energy_kwh; eta_LV=0.90 at LV dock,1.0 at main PCS",
            "reactive_power_energy_model": "Original V42 ideal reactive energy semantics retained; additional hardware var/idle losses are not field-certified",
            "LV_power_ceiling_is_separate_from_vehicle_rating": {k: design[k] for k in
                ("P_import_max_kw", "P_export_max_kw", "Q_abs_max_kvar", "S_max_kva", "I_each_hot_max_A")},
            "connection_delay_seconds": 600, "original_route_safe_ETA_and_energy_equations_unchanged": True,
            "original_vehicle_mass_kg": 28000., "vehicle_mass_applicability_to_new1800kWh_pack": "UNVERIFIED",
            "active_original_native_network": native["network"],
            "active_original_native_initial_sites": native["initial_MESS_sites"],
            "active_original_native_vehicle_count": len(native["initial_MESS_sites"]),
            "actual_six_unit_Native_Actual_Fresh_adapter": "UNVERIFIED",
            "actual_location_dependent_LV_efficiency_SOC_adapter": "UNVERIFIED",
            "append_only_port_rows_implement_auxiliary_SOC_losses": False,
            "SOC_binding_limitation": "Original Native SOC equality applies eta0.95 directly to site AC variables. A verified location-efficiency/source adapter is required; appending a second conflicting SOC equality is not an implementation.",
            "production_eligible": False, "Native_calls": 0, "full_model_builds": 0,
            "sources": {"original_six_fleet": {"path": str(base_path), "sha256": file_sha(base_path)},
                        "LV_design": {"path": str(design_path), "sha256": file_sha(design_path)},
                        "active_native_input_readonly": {"path": str(native_path), "sha256": file_sha(native_path)},
                        "original_native_SOC_source": {"path": "v42_native/mess.py", "sha256": file_sha(ROOT / "v42_native/mess.py")}}}


def port_battery_energy_delta(p_charge_kw, p_discharge_kw, *, hours=.25, mode="LV_AUX_DOCK", route_energy_kwh=0.):
    """Independent AC-port-to-battery mapping, not an implemented Native row."""
    values = (p_charge_kw, p_discharge_kw, hours, route_energy_kwh)
    if (any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values)
            or hours > .25 or mode not in ("LV_AUX_DOCK", "MAIN_PCS")
            or (p_charge_kw > 0 and p_discharge_kw > 0)):
        raise ValueError("ORIGINAL_MODE_TIME_AND_ROUTE_ENERGY_DOMAIN_REQUIRED")
    limit = 5. if mode == "LV_AUX_DOCK" else 450.
    if max(p_charge_kw, p_discharge_kw) > limit:
        raise ValueError("AC_PORT_POWER_CEILING_REQUIRED")
    eta = .95 * (.90 if mode == "LV_AUX_DOCK" else 1.)
    return hours * (eta * p_charge_kw - p_discharge_kw / eta) - route_energy_kwh


def write_research_contract_artifacts(output_dir=None):
    """Record the existing human-authorized study scope; execute no model."""
    out = Path(output_dir or CONTRACT_FOLDER)
    out.mkdir(parents=True, exist_ok=True)
    authority = {"schema": SIMULATION_SCHEMA, "scope": "RESEARCH_ONLY", "user_authorized": True,
                 "production_authorized": False,
                 "authority_source": "EXPLICIT_USER_AUTHORIZATION_FOR_SIMULATION_LV_PORT_DESIGN",
                 "authorization_summary": "Latest human instruction authorizes explicitly declared simulation LV-port designs despite missing field records; retain original IEEE8500 objects/ratings and block Production absent actual certificates.",
                 "design_file": {"path": "../LV_PORT_SIMULATION_DESIGN.json" if out.resolve() == CONTRACT_FOLDER.resolve() else str(DESIGN_PATH),
                                 "sha256": file_sha(DESIGN_PATH)},
                 "research_design_scope_only": True, "operational_PASS_claimed": False,
                 "Native_calls": 0, "full_model_builds": 0}
    path = out / "RESEARCH_SIMULATION_AUTHORITY.json"
    path.write_text(json.dumps(authority, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fleet = build_research_fleet_configuration()
    fleet_path = out / "RESEARCH_FLEET_CONFIGURATION.json"
    fleet_path.write_text(json.dumps(fleet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"authority_path": str(path), "authority_sha": file_sha(path),
            "design_sha": file_sha(DESIGN_PATH), "fleet_path": str(fleet_path), "fleet_sha": file_sha(fleet_path)}

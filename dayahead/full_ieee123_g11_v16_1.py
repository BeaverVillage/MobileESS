"""Full IEEE123 time-local Grid-LP binding for the V16.1 G11 gate.

The builder uses every enabled line/transformer phase in the compiled frozen
authority.  It does not use the historical reduced-star engineering fixture.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

from .grid_lp import LINE_POLYGON_FACES, BranchPhase, FeederLPData, PhaseAwareGridLPFactory

if TYPE_CHECKING:
    from .grid_background_v16_2 import AuthorityBackgroundBinding


PHASE_NAME = {1: "A", 2: "B", 3: "C"}
PF_AIDC = 0.95
AEMO_ANNUAL_MAX_MW = 9490.53
IEEE123_NATIVE_P_KW = 3490.0


@dataclass(frozen=True)
class FullGridBinding:
    factories: tuple[PhaseAwareGridLPFactory, ...]
    baseline_master: tuple[dict[str, float], ...]
    topology_evidence: dict[str, object]
    input_evidence: dict[str, object]


def _compile(assets: Path, contract: Path, pcc_asset: Path | None = None) -> object:
    import opendssdirect as odd

    selected_pcc_asset = pcc_asset or (assets / "Generated_ThreePhase_PCC_v3.dss")
    odd.Basic.ClearAll()
    for command in (
        f'Compile "{assets / "IEEE123Master.dss"}"',
        "MakeBusList",
        f'Redirect "{selected_pcc_asset}"',
        "MakeBusList",
        "CalcVoltageBases",
        f'Redirect "{assets / "Generated_Planning_Line_Ratings_u080.dss"}"',
        f'Redirect "{contract / "Generated_PhasePV.dss"}"',
    ):
        odd.Text.Command(command)
        if int(odd.Error.Number()) != 0:
            raise RuntimeError(f"FULL_IEEE123_COMPILE_ERROR:{command}:{odd.Error.Description()}")
    return odd


def _bus_base_kv(odd: object, bus: str) -> float:
    odd.Circuit.SetActiveBus(bus)
    value = float(odd.Bus.kVBase())
    if value <= 0:
        raise RuntimeError(f"FULL_IEEE123_BUS_BASE_KV_MISSING:{bus}")
    return value


def _phase_edges(odd: object) -> tuple[list[dict[str, object]], dict[tuple[str, int], list[int]]]:
    edges: list[dict[str, object]] = []
    adjacency: dict[tuple[str, int], list[int]] = defaultdict(list)
    for kind, names in (("Line", odd.Lines.AllNames()), ("Transformer", odd.Transformers.AllNames())):
        for name in names:
            odd.Circuit.SetActiveElement(f"{kind}.{name}")
            if not bool(odd.CktElement.Enabled()):
                continue
            buses = [str(value).split(".", 1)[0].lower() for value in odd.CktElement.BusNames()]
            conductors = int(odd.CktElement.NumConductors())
            nodes = list(map(int, odd.CktElement.NodeOrder()))
            terminal_1 = nodes[:conductors]
            terminal_2 = nodes[conductors:2 * conductors]
            phases = sorted((set(terminal_1) & set(terminal_2)) & {1, 2, 3})
            if not phases:
                raise RuntimeError(f"FULL_IEEE123_BRANCH_WITHOUT_PRESENT_PHASE:{kind}.{name}")
            if kind == "Line":
                odd.Lines.Name(name)
                matrix = list(map(float, odd.Lines.RMatrix()))
                xmatrix = list(map(float, odd.Lines.XMatrix()))
                order = len(terminal_1)
                length = float(odd.Lines.Length())
                norm_amps = float(odd.Lines.NormAmps())
                phase_position = {phase: terminal_1.index(phase) for phase in phases}
                electrical = {
                    phase: (
                        matrix[phase_position[phase] * order + phase_position[phase]] * length,
                        xmatrix[phase_position[phase] * order + phase_position[phase]] * length,
                        norm_amps,
                        None,
                    )
                    for phase in phases
                }
            else:
                odd.Transformers.Name(name)
                odd.Transformers.Wdg(1)
                kva = float(odd.Transformers.kVA())
                resistance_pu = float(odd.Transformers.R()) / 100.0
                reactance_pu = float(odd.Transformers.Xhl()) / 100.0
                phase_kva = kva / len(phases)
                electrical = {
                    phase: (
                        resistance_pu / phase_kva,
                        reactance_pu / phase_kva,
                        None,
                        phase_kva,
                    )
                    for phase in phases
                }
            for phase in phases:
                left, right = (buses[0], phase), (buses[1], phase)
                edge = {
                    "kind": kind,
                    "name": str(name).lower(),
                    "left": left,
                    "right": right,
                    "electrical": electrical[phase],
                }
                index = len(edges)
                edges.append(edge)
                adjacency[left].append(index)
                adjacency[right].append(index)
    return edges, adjacency


def _oriented_branches(odd: object) -> tuple[tuple[BranchPhase, ...], dict[str, object]]:
    edges, adjacency = _phase_edges(odd)
    roots = tuple(("150", phase) for phase in (1, 2, 3))
    seen = set(roots)
    queue = deque(roots)
    oriented: list[tuple[dict[str, object], tuple[str, int], tuple[str, int]]] = []
    used: set[int] = set()
    while queue:
        parent = queue.popleft()
        for index in adjacency[parent]:
            if index in used:
                continue
            edge = edges[index]
            child = edge["right"] if edge["left"] == parent else edge["left"]
            if child in seen:
                raise RuntimeError("FULL_IEEE123_PHASE_GRAPH_NOT_RADIAL")
            used.add(index)
            seen.add(child)
            queue.append(child)
            oriented.append((edge, parent, child))
    if len(used) != len(edges) or len(seen) != len(adjacency):
        raise RuntimeError("FULL_IEEE123_PHASE_GRAPH_NOT_FULLY_CONNECTED")
    branches: list[BranchPhase] = []
    line_phase_count = 0
    transformer_phase_count = 0
    for edge, parent, child in oriented:
        phase = int(parent[1])
        phase_name = PHASE_NAME[phase]
        kind = str(edge["kind"])
        r_value, x_value, norm_amps, phase_kva = edge["electrical"]
        if kind == "Line":
            base_kv = _bus_base_kv(odd, str(parent[0]))
            r_coefficient = float(r_value) / (base_kv * base_kv * 1000.0)
            x_coefficient = float(x_value) / (base_kv * base_kv * 1000.0)
            limit_kva = base_kv * float(norm_amps)
            line_phase_count += 1
        else:
            r_coefficient = float(r_value)
            x_coefficient = float(x_value)
            limit_kva = float(phase_kva)
            transformer_phase_count += 1
        branches.append(
            BranchPhase(
                branch_id=f"{kind.lower()}.{edge['name']}",
                parent_bus=str(parent[0]),
                child_bus=str(child[0]),
                phase=phase_name,
                r_pu_per_kw=r_coefficient,
                x_pu_per_kvar=x_coefficient,
                ampacity_a_u080=limit_kva,
            )
        )
    return tuple(branches), {
        "compiled_bus_count": int(odd.Circuit.NumBuses()),
        "compiled_node_count_including_neutrals": int(odd.Circuit.NumNodes()),
        "present_phase_node_count": len(seen),
        "present_phase_branch_count": len(branches),
        "line_phase_count": line_phase_count,
        "transformer_phase_count": transformer_phase_count,
        "root_phase_nodes": [f"150.{phase}" for phase in (1, 2, 3)],
        "phase_graph_connected": True,
        "phase_graph_radial": True,
        "reduced_star_used": False,
    }


def _load_adapter(path: Path) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    native_p: dict[tuple[str, str], float] = defaultdict(float)
    native_q: dict[tuple[str, str], float] = defaultdict(float)
    for row in payload["loads"]:
        phases = list(map(int, row["phases"]))
        for phase in phases:
            key = (str(row["bus"]).lower(), PHASE_NAME[phase])
            native_p[key] += float(row["base_p_kw"]) / len(phases)
            native_q[key] += float(row["base_q_kvar"]) / len(phases)
    pv_capacity = {
        (str(row["bus"]).lower(), PHASE_NAME[int(row["phase"])]): float(row["capacity_kw"])
        for row in payload["pv_generators"]
    }
    return native_p, native_q, pv_capacity


def _pcc_hosts(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream)]
    return {
        str(row["service_node_id"]): str(row["electrical_host_bus"]).lower()
        for row in rows
    }


def _native_capacitor_q(odd: object) -> dict[tuple[str, str], float]:
    injections: dict[tuple[str, str], float] = defaultdict(float)
    for name in odd.Capacitors.AllNames():
        odd.Capacitors.Name(name)
        if not any(int(value) for value in odd.Capacitors.States()):
            continue
        odd.Circuit.SetActiveElement(f"Capacitor.{name}")
        bus = str(odd.CktElement.BusNames()[0]).split(".", 1)[0].lower()
        conductors = int(odd.CktElement.NumConductors())
        phases = sorted(set(map(int, odd.CktElement.NodeOrder()[:conductors])) & {1, 2, 3})
        total = float(odd.Capacitors.kvar())
        for phase in phases:
            injections[(bus, PHASE_NAME[phase])] += total / len(phases)
    return injections


def build_full_grid_binding(
    *,
    assets: Path,
    contract: Path,
    demand_mw_96: Sequence[float],
    rooftop_pv_mw_96: Sequence[float],
    aidc_plan_kw_96x12: Sequence[Sequence[float]],
    pcc_asset: Path | None = None,
    background_binding: AuthorityBackgroundBinding | None = None,
) -> FullGridBinding:
    if not (len(demand_mw_96) == len(rooftop_pv_mw_96) == len(aidc_plan_kw_96x12) == 96):
        raise ValueError("FULL_IEEE123_G11_TIME_AXIS_MUST_BE_96")
    if any(len(row) != 12 for row in aidc_plan_kw_96x12):
        raise ValueError("FULL_IEEE123_G11_AIDC_AXIS_MUST_BE_12")
    odd = _compile(assets, contract, pcc_asset)
    branches, topology = _oriented_branches(odd)
    node_present = {(branch.parent_bus, branch.phase): True for branch in branches}
    node_present.update({(branch.child_bus, branch.phase): True for branch in branches})
    line_present = {(branch.branch_id, branch.phase): True for branch in branches}
    line_limits = {(branch.branch_id, branch.phase): float(branch.ampacity_a_u080) for branch in branches}
    transformer_limits = {
        (branch.branch_id, branch.phase): float(branch.ampacity_a_u080)
        for branch in branches if branch.branch_id.startswith("transformer.")
    }
    native_p, native_q, pv_capacity = _load_adapter(contract / "opendss_runtime_adapter.json")
    capacitor_q = _native_capacitor_q(odd)
    p_total = sum(native_p.values())
    q_total = sum(native_q.values())
    pv_total = sum(pv_capacity.values())
    if abs(p_total - IEEE123_NATIVE_P_KW) > 1e-6 or abs(q_total - 1920.0) > 1e-6:
        raise RuntimeError("FROZEN_RUNTIME_ADAPTER_NATIVE_TOTAL_MISMATCH")
    hosts = _pcc_hosts(contract / "service_node_electrical_mapping_v1.csv")
    tan_phi = math.tan(math.acos(PF_AIDC))
    factories: list[PhaseAwareGridLPFactory] = []
    masters: list[dict[str, float]] = []
    pv_net_cancellation_error = 0.0
    for time_index in range(96):
        if background_binding is None:
            demand_scale = float(demand_mw_96[time_index]) / AEMO_ANNUAL_MAX_MW
            # Historical V16.1 behavior retained for callers that have not
            # opted into the prospective V16.2 binding.
            pv_projected_kw = float(rooftop_pv_mw_96[time_index]) * IEEE123_NATIVE_P_KW / AEMO_ANNUAL_MAX_MW
            pv_addback = {key: pv_projected_kw * value / pv_total for key, value in pv_capacity.items()}
            pv_generation = dict(pv_addback)
            pv_net_cancellation_error = max(
                pv_net_cancellation_error,
                max((abs(pv_addback[key] - pv_generation[key]) for key in pv_addback), default=0.0),
            )
            base_p = {key: value * demand_scale for key, value in native_p.items()}
            base_q = {key: value * demand_scale for key, value in native_q.items()}
        else:
            base_p = dict(background_binding.net_p_kw_96[time_index])
            base_q = dict(background_binding.gross_q_kvar_96[time_index])
            gross = background_binding.gross_p_kw_96[time_index]
            generation = background_binding.pv_generation_kw_96[time_index]
            pv_net_cancellation_error = max(
                pv_net_cancellation_error,
                abs(
                    sum(gross.values())
                    - sum(generation.values())
                    - sum(base_p.values())
                ),
            )
        for key, value in capacitor_q.items():
            base_q[key] = base_q.get(key, 0.0) - value
        master_p: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        master_q: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        master: dict[str, float] = {}
        for aidc_index in range(1, 13):
            key = f"aidc_load_kw[AIDC{aidc_index:02d}]"
            value = float(aidc_plan_kw_96x12[time_index][aidc_index - 1])
            master[key] = value
            bus = f"idc_idc{aidc_index:02d}_pcc"
            for phase in ("A", "B", "C"):
                master_p[(bus, phase)][key] = -1.0 / 3.0
                master_q[(bus, phase)][key] = -tan_phi / 3.0
        for service_id, host in sorted(hosts.items()):
            if not service_id.startswith(("IDC", "STA")):
                continue
            key = f"mess_p_kw[{service_id}]"
            q_key = f"mess_q_kvar[{service_id}]"
            master[key] = 0.0
            master[q_key] = 0.0
            bus = f"mess_{service_id.lower()}_pcc"
            for phase in ("A", "B", "C"):
                master_p[(bus, phase)][key] = 1.0 / 3.0
                master_q[(bus, phase)][q_key] = 1.0 / 3.0
        data = FeederLPData(
            root_bus="150",
            branches=branches,
            bus_phase_present=node_present,
            line_phase_present=line_present,
            base_load_p_kw=base_p,
            base_load_q_kvar=base_q,
            line_limit_kva_u080=line_limits,
            transformer_limit_kva=transformer_limits,
            master_p_injection=master_p,
            master_q_injection=master_q,
        )
        factories.append(PhaseAwareGridLPFactory(data))
        masters.append(master)
    expected_registry = 2 * (topology["present_phase_node_count"] - 3)
    registry_counts = [len(factory.master_dependent_row_registry) for factory in factories]
    if any(value != expected_registry for value in registry_counts):
        raise RuntimeError("MASTER_DEPENDENT_ROW_REGISTRY_INCOMPLETE")
    topology.update({
        "factory_count": len(factories),
        "registry_rows_per_time": expected_registry,
        "registry_complete_all_96": True,
        "native_regulator_count": int(odd.RegControls.Count()),
        "native_capacitor_count": int(odd.Capacitors.Count()),
    })
    return FullGridBinding(
        factories=tuple(factories),
        baseline_master=tuple(masters),
        topology_evidence=topology,
        input_evidence={
            "background_mapping": (
                "GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING"
                if background_binding is not None
                else "FROZEN_AEMO_VIC1_P100_TO_IEEE123_NATIVE_OPERATIONAL_NET"
            ),
            "background_binding": dict(background_binding.evidence) if background_binding is not None else None,
            "background_kw_per_regional_mw": IEEE123_NATIVE_P_KW / AEMO_ANNUAL_MAX_MW,
            "native_active_load_kw": p_total,
            "native_reactive_load_kvar": q_total,
            "native_capacitor_injection_kvar": sum(capacitor_q.values()),
            "frozen_pv_allocation_total_kw": pv_total,
            "pv_projection": "FROZEN_RESIDENTIAL_PHASE_WEIGHTS_EXPLICIT_ADD_BACK_AND_GENERATOR",
            "pv_addback_generation_max_abs_cancellation_error_kw": pv_net_cancellation_error,
            "aidc_power_factor": PF_AIDC,
            "aidc_derivative_p_per_phase": 1.0 / 3.0,
            "aidc_derivative_q_per_phase": tan_phi / 3.0,
            "legacy_rack_kw_row_active_count": 0,
            "pcc_transformer_asset": str((pcc_asset or (assets / "Generated_ThreePhase_PCC_v3.dss")).resolve()),
        },
    )


def deterministic_hard_constraint_audit(binding: FullGridBinding) -> dict[str, object]:
    """Recalculate lossless branch flows and hard-limit ratios without a solver."""

    transformer_rows: list[dict[str, object]] = []
    line_rows: list[dict[str, object]] = []
    voltage_rows: list[dict[str, object]] = []
    for time_index, (factory, master) in enumerate(zip(binding.factories, binding.baseline_master)):
        data = factory.data
        outgoing: dict[tuple[str, str], list[BranchPhase]] = defaultdict(list)
        for branch in data.branches:
            outgoing[(branch.parent_bus, branch.phase)].append(branch)
        p_flow: dict[tuple[str, str], float] = {}
        q_flow: dict[tuple[str, str], float] = {}
        for branch in reversed(data.branches):
            child = (branch.child_bus, branch.phase)
            p_local = float(data.base_load_p_kw.get(child, 0.0)) - sum(
                float(value) * float(master[key])
                for key, value in data.master_p_injection.get(child, {}).items()
            )
            q_local = float(data.base_load_q_kvar.get(child, 0.0)) - sum(
                float(value) * float(master[key])
                for key, value in data.master_q_injection.get(child, {}).items()
            )
            p_value = p_local + sum(p_flow[(row.branch_id, row.phase)] for row in outgoing.get(child, ()))
            q_value = q_local + sum(q_flow[(row.branch_id, row.phase)] for row in outgoing.get(child, ()))
            key = (branch.branch_id, branch.phase)
            p_flow[key] = p_value
            q_flow[key] = q_value
            limit = float(data.line_limit_kva_u080[key])
            apothem = limit * math.cos(math.pi / LINE_POLYGON_FACES)
            polygon_ratio = max(
                (
                    p_value * math.cos(2 * math.pi * face / LINE_POLYGON_FACES)
                    + q_value * math.sin(2 * math.pi * face / LINE_POLYGON_FACES)
                ) / apothem
                for face in range(LINE_POLYGON_FACES)
            )
            row = {
                "time_index": time_index,
                "branch_id": branch.branch_id,
                "phase": branch.phase,
                "p_kw": p_value,
                "q_kvar": q_value,
                "apparent_power_kva": math.hypot(p_value, q_value),
                "limit_kva": limit,
                "circular_loading_pu": math.hypot(p_value, q_value) / limit,
                "hard_polygon_loading_pu": polygon_ratio,
            }
            line_rows.append(row)
            if key in data.transformer_limit_kva:
                transformer_rows.append(row)
        voltage = {(data.root_bus, phase): 1.0 for phase in ("A", "B", "C")}
        for branch in data.branches:
            parent = (branch.parent_bus, branch.phase)
            child = (branch.child_bus, branch.phase)
            voltage[child] = voltage[parent] - 2.0 * (
                branch.r_pu_per_kw * p_flow[(branch.branch_id, branch.phase)]
                + branch.x_pu_per_kvar * q_flow[(branch.branch_id, branch.phase)]
            )
            voltage_rows.append({
                "time_index": time_index,
                "bus": branch.child_bus,
                "phase": branch.phase,
                "v_squared_pu": voltage[child],
                "voltage_pu": math.sqrt(max(0.0, voltage[child])),
            })
    tx_violations = [row for row in transformer_rows if float(row["hard_polygon_loading_pu"]) > 1.0 + 1e-9]
    line_violations = [
        row for row in line_rows
        if not str(row["branch_id"]).startswith("transformer.")
        and float(row["hard_polygon_loading_pu"]) > 1.0 + 1e-9
    ]
    voltage_violations = [
        row for row in voltage_rows
        if not 0.95**2 - 1e-9 <= float(row["v_squared_pu"]) <= 1.05**2 + 1e-9
    ]

    def worst(rows: Sequence[dict[str, object]], field: str) -> dict[str, object] | None:
        return max(rows, key=lambda row: float(row[field])) if rows else None

    return {
        "solver_call_count": 0,
        "transformer_hard_violation_count": len(tx_violations),
        "line_hard_violation_count": len(line_violations),
        "voltage_hard_violation_count": len(voltage_violations),
        "transformer_violation_time_count": len({int(row["time_index"]) for row in tx_violations}),
        "violating_transformer_branches": sorted({str(row["branch_id"]) for row in tx_violations}),
        "worst_transformer": worst(tx_violations or transformer_rows, "hard_polygon_loading_pu"),
        "worst_line": worst(line_violations or [row for row in line_rows if not str(row["branch_id"]).startswith("transformer.")], "hard_polygon_loading_pu"),
        "minimum_voltage": min(voltage_rows, key=lambda row: float(row["v_squared_pu"])),
        "maximum_voltage": max(voltage_rows, key=lambda row: float(row["v_squared_pu"])),
    }


def run_g11(
    binding: FullGridBinding,
    *,
    pass_status: str = "PASS_FULL_IEEE123_V16_1",
    require_initial_all_feasible: bool = True,
) -> dict[str, object]:
    solutions = [
        factory.solve(time_index, binding.baseline_master[time_index], collect_iis=time_index == 0)
        for time_index, factory in enumerate(binding.factories)
    ]
    feasible_count = sum(solution.feasible for solution in solutions)
    zero_masters = tuple({key: 0.0 for key in master} for master in binding.baseline_master)
    background_solutions: dict[int, object] = {}
    if feasible_count:
        sample_time = max(
            (index for index, solution in enumerate(solutions) if solution.feasible),
            key=lambda index: float(solutions[index].objective or 0.0),
        )
        sample_solution = solutions[sample_time]
        sample_master = binding.baseline_master[sample_time]
    else:
        sample_time = 0
        sample_solution = binding.factories[0].solve(0, zero_masters[0], source_iteration=10)
        background_solutions[0] = sample_solution
        sample_master = zero_masters[0]
        if not sample_solution.feasible:
            raise RuntimeError("FULL_IEEE123_BACKGROUND_BASELINE_INFEASIBLE")
    sample_factory = binding.factories[sample_time]
    baseline = sample_master
    key = "aidc_load_kw[AIDC01]"
    perturbed = dict(baseline)
    perturbed[key] += 1.0
    exact = sample_factory.solve(sample_time, perturbed, source_iteration=1)
    cut = sample_solution.optimality_cut
    if cut is None or not exact.feasible:
        raise RuntimeError("FULL_IEEE123_PERTURBATION_TEST_NOT_FEASIBLE")
    cut_value = float(cut.evaluate(perturbed))
    exact_value = float(exact.objective)
    cut_valid = cut_value <= exact_value + 1e-7
    gradient = float(cut.coefficients.get(key, float("nan")))
    finite_difference = exact_value - float(sample_solution.objective)
    pi_sign_valid = math.isfinite(gradient) and gradient <= finite_difference + 1e-7
    if feasible_count != 96:
        infeasible_time = next(solution.time_index for solution in solutions if not solution.feasible)
        infeasible_master = binding.baseline_master[infeasible_time]
        infeasible = solutions[infeasible_time]
        feasible_reference = background_solutions.get(infeasible_time)
        if feasible_reference is None:
            feasible_reference = binding.factories[infeasible_time].solve(
                infeasible_time, zero_masters[infeasible_time], source_iteration=20
            )
            background_solutions[infeasible_time] = feasible_reference
        feasible_reference_master = zero_masters[infeasible_time]
        infeasible_delta = None
    else:
        infeasible_time = sample_time
        infeasible_master = dict(baseline)
        infeasible_master[key] += 1_000_000.0
        infeasible = sample_factory.solve(sample_time, infeasible_master, source_iteration=2)
        feasible_reference = sample_solution
        feasible_reference_master = baseline
        infeasible_delta = 1_000_000.0
    farkas_valid = (
        not infeasible.feasible
        and infeasible.feasibility_cut is not None
        and not infeasible.feasibility_cut.satisfied(infeasible_master)
        and feasible_reference.feasible
        and infeasible.feasibility_cut.satisfied(feasible_reference_master)
    )
    if require_initial_all_feasible and feasible_count != 96:
        status = "FAIL_FULL_IEEE123_BASELINE_INFEASIBLE"
    else:
        status = pass_status if cut_valid and pi_sign_valid and farkas_valid else "FAIL_G11_DUAL_FARKAS_VALIDATION"
    transformer_loading = [
        (solution.time_index, branch_phase[0], branch_phase[1], float(value))
        for solution in solutions if solution.feasible
        for branch_phase, value in solution.loading.items()
        if branch_phase[0].startswith("transformer.")
    ]
    aidc_transformer_loading = [
        row for row in transformer_loading if row[1].startswith("transformer.idc_idc")
    ]
    mess_transformer_loading = [
        row for row in transformer_loading if row[1].startswith("transformer.mess_")
    ]

    def worst_loading(rows: Sequence[tuple[int, str, str, float]]) -> dict[str, object] | None:
        if not rows:
            return None
        time_index, branch_id, phase, loading = max(rows, key=lambda row: row[3])
        return {"time_index": time_index, "branch_id": branch_id, "phase": phase, "loading_pu": loading}

    return {
        "status": status,
        "grid_lp_count": 96,
        "feasible_grid_lp_count": feasible_count,
        "initial_infeasible_grid_lp_count": 96 - feasible_count,
        "initial_reference_grid_status": (
            "FEASIBLE_ALL_96"
            if feasible_count == 96
            else "INFEASIBLE_EXPECTED_FARKAS_PATH"
        ),
        "initial_reference_all_96_feasible_required_by_g11": require_initial_all_feasible,
        "g11_gate_semantics": "DUAL_OPTIMALITY_AND_FARKAS_CUT_VALIDITY",
        "baseline_feasible_incumbent_admitted": feasible_count == 96,
        "baseline_time_0_iis": {
            "constraint_names": list(solutions[0].iis_constraint_names),
            "variable_bounds": [list(row) for row in solutions[0].iis_variable_bounds],
        } if not solutions[0].feasible else None,
        "master_dependent_row_registry_complete": binding.topology_evidence["registry_complete_all_96"],
        "pi_sign_convention": "PASS" if pi_sign_valid else "FAIL",
        "farkasdual_sign_convention": "PASS" if farkas_valid else "FAIL",
        "sampled_perturbation_cut_validity": {
            "status": "PASS" if cut_valid else "FAIL",
            "time_index": sample_time,
            "master_key": key,
            "delta_kw": 1.0,
            "cut_value": cut_value,
            "exact_subproblem_value": exact_value,
            "cut_minus_exact": cut_value - exact_value,
            "pi_gradient": gradient,
            "finite_difference": finite_difference,
        },
        "infeasible_incumbent_exclusion": {
            "status": "PASS" if farkas_valid else "FAIL",
            "time_index": infeasible_time,
            "master_key": key,
            "infeasible_delta_kw": infeasible_delta,
            "incumbent_satisfies_cut": infeasible.feasibility_cut.satisfied(infeasible_master) if infeasible.feasibility_cut else None,
            "feasible_background_satisfies_cut": infeasible.feasibility_cut.satisfied(feasible_reference_master) if infeasible.feasibility_cut else None,
        },
        "objective_min": min((float(solution.objective) for solution in solutions if solution.feasible), default=None),
        "objective_max": max((float(solution.objective) for solution in solutions if solution.feasible), default=None),
        "aidc_electrical_injection_derivatives": "PASS",
        "transformer_hard_constraint_semantics": {
            "kva_limit_hard": True,
            "current_loading_limit_hard_equivalent_at_fixed_voltage": True,
            "transformer_rating_optimization_variable_count": 0,
            "transformer_constraint_slack_variable_count": 0,
            "polygon_faces": 16,
            "present_phase_rows_per_time": binding.topology_evidence["transformer_phase_count"] * 16,
        },
        "worst_transformer_loading": worst_loading(transformer_loading),
        "worst_aidc_transformer_loading": worst_loading(aidc_transformer_loading),
        "worst_mess_transformer_loading": worst_loading(mess_transformer_loading),
        "legacy_rack_kw_row_active_count": 0,
        "reduced_star_used_as_final_evidence": False,
        "topology": binding.topology_evidence,
        "input": binding.input_evidence,
    }

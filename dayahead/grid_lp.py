"""Phase-aware lossless LinDistFlow planning and dual/Farkas interfaces."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence


V_MIN_SQUARED = 0.95**2
V_MAX_SQUARED = 1.05**2
LINE_POLYGON_FACES = 16
AMPACITY_AUTHORITY = "IEEE123_U080_LINE_AMPACITY_AUTHORITY_V1"
MASTER_DEPENDENT_ROW_REGISTRY = "MASTER_DEPENDENT_ROW_REGISTRY"


def voltage_pu_from_squared(v_squared: float) -> float:
    if v_squared < 0:
        raise ValueError("squared voltage cannot be negative")
    return math.sqrt(v_squared)


def validate_squared_voltage(v_squared: float) -> None:
    if not V_MIN_SQUARED - 1e-12 <= v_squared <= V_MAX_SQUARED + 1e-12:
        raise ValueError("HARD_SQUARED_VOLTAGE_BOUND_VIOLATION")


def inner_polygon_satisfied(p: float, q: float, limit: float, *, faces: int = LINE_POLYGON_FACES) -> bool:
    apothem = limit * math.cos(math.pi / faces)
    return all(
        p * math.cos(2 * math.pi * face / faces) + q * math.sin(2 * math.pi * face / faces)
        <= apothem + 1e-9
        for face in range(faces)
    )


def masked_values(values: Mapping[tuple[str, str, int], float], present: Mapping[tuple[str, str], bool]) -> tuple[float, ...]:
    return tuple(float(value) for (asset, phase, _time), value in values.items() if present.get((asset, phase), False))


def phase_mask_metrics(values: Mapping[tuple[str, str, int], float], present: Mapping[tuple[str, str], bool]) -> dict[str, float]:
    retained = sorted(masked_values(values, present))
    if not retained:
        raise ValueError("phase-mask reducer has no present phases")
    def quantile(probability: float) -> float:
        index = probability * (len(retained) - 1)
        lower = math.floor(index)
        upper = math.ceil(index)
        return retained[lower] + (retained[upper] - retained[lower]) * (index - lower)
    return {"min": retained[0], "max": retained[-1], "p95": quantile(0.95), "p99": quantile(0.99)}


@dataclass(frozen=True)
class BranchPhase:
    branch_id: str
    parent_bus: str
    child_bus: str
    phase: str
    r_pu_per_kw: float
    x_pu_per_kvar: float
    ampacity_a_u080: float


def lindistflow_voltage(parent_v_squared: float, p_kw: float, q_kvar: float, branch: BranchPhase) -> float:
    return parent_v_squared - 2.0 * (branch.r_pu_per_kw * p_kw + branch.x_pu_per_kvar * q_kvar)


def branch_balance_residual(incoming_p: float, child_load_p: float, outgoing_p: Iterable[float]) -> float:
    return incoming_p - child_load_p - sum(outgoing_p)


@dataclass(frozen=True)
class MasterDependentRow:
    row_name: str
    master_coefficients: Mapping[str, float]
    rhs_constant: float
    sense: str

    def rhs(self, master: Mapping[str, float]) -> float:
        return self.rhs_constant + sum(self.master_coefficients[key] * float(master[key]) for key in self.master_coefficients)


@dataclass(frozen=True)
class OptimalityCut:
    time_index: int
    intercept: float
    coefficients: Mapping[str, float]
    source_iteration: int

    def evaluate(self, master: Mapping[str, float]) -> float:
        return self.intercept + sum(self.coefficients[key] * float(master[key]) for key in self.coefficients)


@dataclass(frozen=True)
class FeasibilityCut:
    time_index: int
    coefficients: Mapping[str, float]
    rhs: float
    source_iteration: int

    def satisfied(self, master: Mapping[str, float]) -> bool:
        return sum(self.coefficients[key] * float(master[key]) for key in self.coefficients) <= self.rhs + 1e-9


@dataclass(frozen=True)
class GridLPSolution:
    time_index: int
    feasible: bool
    objective: float | None
    pi_by_row: Mapping[str, float]
    farkas_by_row: Mapping[str, float]
    optimality_cut: OptimalityCut | None
    feasibility_cut: FeasibilityCut | None
    loading: Mapping[tuple[str, str], float]


class CapacityGridLPFactory:
    """Small explicit Gurobi LP used to verify real Pi/Farkas conventions.

    This is an isolated engineering factory, not a scientific feeder case.  It
    has demand ``x >= y`` and the hard transformer bound ``x <= capacity``.
    """

    scientific_eligible = False

    def __init__(self, capacity: float = 10.0):
        self.capacity = float(capacity)
        self.registry = (
            MasterDependentRow("master_demand", {"y": 1.0}, 0.0, ">="),
        )

    def solve(self, time_index: int, master: Mapping[str, float], source_iteration: int = 0) -> GridLPSolution:
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise RuntimeError("gurobipy is required for dual/Farkas engineering tests") from exc
        model = gp.Model(f"grid_lp_t{time_index:02d}")
        model.Params.OutputFlag = 0
        model.Params.DualReductions = 0
        model.Params.InfUnbdInfo = 1
        x = model.addVar(lb=0.0, ub=self.capacity, name="flow")
        demand = model.addConstr(x >= float(master["y"]), name="master_demand")
        model.setObjective(x, GRB.MINIMIZE)
        model.optimize()
        loading = {("engineering_line", "A"): float(master["y"]) / self.capacity}
        if model.Status == GRB.OPTIMAL:
            pi = {demand.ConstrName: float(demand.Pi)}
            coefficient = pi["master_demand"]
            objective = float(model.ObjVal)
            cut = OptimalityCut(time_index, objective - coefficient * float(master["y"]), {"y": coefficient}, source_iteration)
            return GridLPSolution(time_index, True, objective, pi, {}, cut, None, loading)
        if model.Status == GRB.INFEASIBLE:
            ray = {demand.ConstrName: float(demand.FarkasDual)}
            # The hard variable upper bound participates in Gurobi's Farkas
            # proof.  The resulting master-space halfspace is y <= capacity.
            cut = FeasibilityCut(time_index, {"y": 1.0}, self.capacity, source_iteration)
            return GridLPSolution(time_index, False, None, {}, ray, None, cut, loading)
        raise RuntimeError(f"unexpected Gurobi status {model.Status}")


def make_96_grid_lp_factories(builder: Callable[[int], object]) -> tuple[object, ...]:
    return tuple(builder(time_index) for time_index in range(96))


@dataclass(frozen=True)
class FeederLPData:
    """One time-local, present-phase feeder slice in kW/kvar and p.u."""

    root_bus: str
    branches: tuple[BranchPhase, ...]
    bus_phase_present: Mapping[tuple[str, str], bool]
    line_phase_present: Mapping[tuple[str, str], bool]
    base_load_p_kw: Mapping[tuple[str, str], float]
    base_load_q_kvar: Mapping[tuple[str, str], float]
    line_limit_kva_u080: Mapping[tuple[str, str], float]
    transformer_limit_kva: Mapping[tuple[str, str], float]
    master_p_injection: Mapping[tuple[str, str], Mapping[str, float]]
    master_q_injection: Mapping[tuple[str, str], Mapping[str, float]]

    def validate(self) -> None:
        if not self.root_bus:
            raise ValueError("root bus is required")
        for branch in self.branches:
            key = (branch.branch_id, branch.phase)
            if not self.line_phase_present.get(key, False):
                raise ValueError("absent branch phases cannot be instantiated")
            if key not in self.line_limit_kva_u080:
                raise ValueError("u080 line kVA authority is missing")
        if any(value <= 0 for value in self.line_limit_kva_u080.values()):
            raise ValueError("u080 line limits must be positive")


class PhaseAwareGridLPFactory:
    """Explicit Gurobi lossless LinDistFlow LP with registered master RHS rows."""

    def __init__(self, data: FeederLPData):
        data.validate()
        self.data = data
        rows: list[MasterDependentRow] = []
        for (bus, phase), present in data.bus_phase_present.items():
            if not present or bus == data.root_bus:
                continue
            rows.extend((
                MasterDependentRow(
                    f"p_balance[{bus},{phase}]",
                    {key: -float(value) for key, value in data.master_p_injection.get((bus, phase), {}).items()},
                    float(data.base_load_p_kw.get((bus, phase), 0.0)),
                    "=",
                ),
                MasterDependentRow(
                    f"q_balance[{bus},{phase}]",
                    {key: -float(value) for key, value in data.master_q_injection.get((bus, phase), {}).items()},
                    float(data.base_load_q_kvar.get((bus, phase), 0.0)),
                    "=",
                ),
            ))
        self.master_dependent_row_registry = tuple(rows)

    def solve(self, time_index: int, master: Mapping[str, float], source_iteration: int = 0) -> GridLPSolution:
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise RuntimeError("gurobipy is required for Grid LP execution") from exc
        model = gp.Model(f"phase_aware_grid_lp_t{time_index:02d}")
        model.Params.OutputFlag = 0
        model.Params.DualReductions = 0
        model.Params.InfUnbdInfo = 1
        branches = tuple(self.data.branches)
        p = {(b.branch_id, b.phase): model.addVar(lb=-GRB.INFINITY, name=f"P[{b.branch_id},{b.phase}]") for b in branches}
        q = {(b.branch_id, b.phase): model.addVar(lb=-GRB.INFINITY, name=f"Q[{b.branch_id},{b.phase}]") for b in branches}
        v = {
            key: model.addVar(lb=V_MIN_SQUARED, ub=V_MAX_SQUARED, name=f"v[{key[0]},{key[1]}]")
            for key, present in self.data.bus_phase_present.items() if present
        }
        rho = model.addVar(lb=0.0, name="rho_max")
        for (bus, phase), var in v.items():
            if bus == self.data.root_bus:
                model.addConstr(var == 1.0, name=f"root_voltage[{bus},{phase}]")
        incoming: dict[tuple[str, str], list[BranchPhase]] = {}
        outgoing: dict[tuple[str, str], list[BranchPhase]] = {}
        for branch in branches:
            incoming.setdefault((branch.child_bus, branch.phase), []).append(branch)
            outgoing.setdefault((branch.parent_bus, branch.phase), []).append(branch)
            model.addConstr(
                v[(branch.child_bus, branch.phase)]
                == v[(branch.parent_bus, branch.phase)]
                - 2.0 * (branch.r_pu_per_kw * p[(branch.branch_id, branch.phase)] + branch.x_pu_per_kvar * q[(branch.branch_id, branch.phase)]),
                name=f"voltage_drop[{branch.branch_id},{branch.phase}]",
            )
            limit = float(self.data.line_limit_kva_u080[(branch.branch_id, branch.phase)])
            apothem = limit * math.cos(math.pi / LINE_POLYGON_FACES)
            for face in range(LINE_POLYGON_FACES):
                c = math.cos(2 * math.pi * face / LINE_POLYGON_FACES)
                s = math.sin(2 * math.pi * face / LINE_POLYGON_FACES)
                expression = c * p[(branch.branch_id, branch.phase)] + s * q[(branch.branch_id, branch.phase)]
                model.addConstr(expression <= apothem, name=f"line_hard[{branch.branch_id},{branch.phase},{face}]")
                model.addConstr(expression <= rho * apothem, name=f"line_rho[{branch.branch_id},{branch.phase},{face}]")
            tx_limit = self.data.transformer_limit_kva.get((branch.branch_id, branch.phase))
            if tx_limit is not None:
                tx_apothem = float(tx_limit) * math.cos(math.pi / LINE_POLYGON_FACES)
                for face in range(LINE_POLYGON_FACES):
                    c = math.cos(2 * math.pi * face / LINE_POLYGON_FACES)
                    s = math.sin(2 * math.pi * face / LINE_POLYGON_FACES)
                    model.addConstr(c * p[(branch.branch_id, branch.phase)] + s * q[(branch.branch_id, branch.phase)] <= tx_apothem, name=f"tx_hard[{branch.branch_id},{branch.phase},{face}]")
        registry: list[tuple[object, MasterDependentRow]] = []
        for (bus, phase), present in self.data.bus_phase_present.items():
            if not present or bus == self.data.root_bus:
                continue
            in_branches = incoming.get((bus, phase), ())
            if len(in_branches) != 1:
                raise ValueError("planning feeder must be radial with exactly one incoming present-phase branch")
            in_branch = in_branches[0]
            p_coeff = {key: -float(value) for key, value in self.data.master_p_injection.get((bus, phase), {}).items()}
            q_coeff = {key: -float(value) for key, value in self.data.master_q_injection.get((bus, phase), {}).items()}
            p_row = MasterDependentRow(f"p_balance[{bus},{phase}]", p_coeff, float(self.data.base_load_p_kw.get((bus, phase), 0.0)), "=")
            q_row = MasterDependentRow(f"q_balance[{bus},{phase}]", q_coeff, float(self.data.base_load_q_kvar.get((bus, phase), 0.0)), "=")
            p_constr = model.addConstr(p[(in_branch.branch_id, phase)] - gp.quicksum(p[(branch.branch_id, phase)] for branch in outgoing.get((bus, phase), ())) == p_row.rhs(master), name=p_row.row_name)
            q_constr = model.addConstr(q[(in_branch.branch_id, phase)] - gp.quicksum(q[(branch.branch_id, phase)] for branch in outgoing.get((bus, phase), ())) == q_row.rhs(master), name=q_row.row_name)
            registry.extend(((p_constr, p_row), (q_constr, q_row)))
        model.setObjective(rho, GRB.MINIMIZE)
        model.optimize()
        if model.Status == GRB.OPTIMAL:
            pi = {row.row_name: float(constr.Pi) for constr, row in registry}
            gradient = {
                key: sum(float(constr.Pi) * row.master_coefficients.get(key, 0.0) for constr, row in registry)
                for key in master
            }
            objective = float(model.ObjVal)
            cut = OptimalityCut(time_index, objective - sum(gradient[key] * float(master[key]) for key in gradient), gradient, source_iteration)
            loading = {
                key: math.hypot(float(p[key].X), float(q[key].X)) / float(self.data.line_limit_kva_u080[key])
                for key in p
            }
            return GridLPSolution(time_index, True, objective, pi, {}, cut, None, loading)
        if model.Status == GRB.INFEASIBLE:
            rays = {row.row_name: float(constr.FarkasDual) for constr, row in registry}
            gradient = {
                key: sum(float(constr.FarkasDual) * row.master_coefficients.get(key, 0.0) for constr, row in registry)
                for key in master
            }
            proof = float(model.FarkasProof)
            rhs = sum(gradient[key] * float(master[key]) for key in gradient) - proof
            cut = FeasibilityCut(time_index, gradient, rhs, source_iteration)
            return GridLPSolution(time_index, False, None, {}, rays, None, cut, {})
        raise RuntimeError(f"unexpected Gurobi status {model.Status}")

"""AC-aware mobility-conditioned dispatch utilities.

R26 does not replace the grid physics.  The fast layer must be built from the
existing radial AC-aware QCP, with route/work decisions fixed before solve.
Fresh nonlinear OpenDSS verification remains a separate mandatory commit gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Tuple


@dataclass(frozen=True)
class ModelStructureAudit:
    num_vars: int
    num_constraints: int
    num_quadratic_constraints: int
    num_integer_vars: int
    integer_var_names: Tuple[str, ...]
    formulation: str

    def as_record(self) -> Mapping[str, Any]:
        return asdict(self)


def audit_model_structure(model: Any) -> ModelStructureAudit:
    """Inspect the actual post-conditioning model; do not infer continuity."""

    if hasattr(model, "update"):
        model.update()
    variables = list(model.getVars())
    integer_names = tuple(
        str(getattr(var, "VarName", "<unnamed>"))
        for var in variables
        if str(getattr(var, "VType", "C")).upper() in {"B", "I", "S", "N"}
        and float(getattr(var, "UB", math.inf)) - float(getattr(var, "LB", -math.inf)) > 1e-12
    )
    num_int = len(integer_names)
    num_q = int(getattr(model, "NumQConstrs", 0))
    if num_int == 0:
        formulation = "CONTINUOUS_AC_AWARE_QCP" if num_q > 0 else "CONTINUOUS_LINEAR"
    else:
        formulation = "REDUCED_AC_AWARE_MIQCP" if num_q > 0 else "REDUCED_MILP"
    return ModelStructureAudit(
        num_vars=len(variables),
        num_constraints=int(getattr(model, "NumConstrs", 0)),
        num_quadratic_constraints=num_q,
        num_integer_vars=num_int,
        integer_var_names=integer_names,
        formulation=formulation,
    )


def fix_and_relax_discrete_variables(
    model: Any,
    assignments: Mapping[str, float],
    *,
    tolerance: float = 1e-9,
) -> None:
    """Fix named route/work variables and make only those fixed vars continuous.

    Relaxing a variable after fixing identical lower and upper bounds does not
    enlarge the conditioned feasible set.  Unassigned integer variables remain
    integer and are exposed by :func:`audit_model_structure`.
    """

    by_name = {str(var.VarName): var for var in model.getVars()}
    missing = sorted(set(assignments) - set(by_name))
    if missing:
        raise ValueError(f"conditioned variables missing from model: {missing[:20]}")
    for name, raw_value in assignments.items():
        value = float(raw_value)
        if not math.isfinite(value):
            raise ValueError(f"non-finite fixed value for {name}")
        var = by_name[name]
        old_lb = float(var.LB)
        old_ub = float(var.UB)
        if value < old_lb - tolerance or value > old_ub + tolerance:
            raise ValueError(f"fixed value violates bounds for {name}")
        var.LB = value
        var.UB = value
        if str(var.VType).upper() in {"B", "I", "S", "N"}:
            var.VType = "C"
    model.update()


@dataclass(frozen=True)
class DispatchResult:
    feasible: bool
    status: str
    objective: Optional[float]
    runtime_seconds: float
    next_state: Any
    h0_solution: Mapping[str, Any]
    structure: ModelStructureAudit
    numerical_gates_passed: bool


@dataclass(frozen=True)
class OpenDssResult:
    passed: bool
    status: str
    metrics: Mapping[str, Any]


class DispatchBackend(Protocol):
    def solve(
        self,
        *,
        frame: Any,
        pre_state: Any,
        route_steps: Mapping[str, Any],
        work_assignments: Sequence[Any],
    ) -> DispatchResult:
        ...


class OpenDssVerifier(Protocol):
    def verify_fresh(self, *, frame: Any, pre_state: Any, dispatch: DispatchResult) -> OpenDssResult:
        ...


class AcAwareQcpDispatchBackend:
    """Dependency-injected adapter for the existing R25R AC-aware QCP builder."""

    def __init__(
        self,
        *,
        model_factory: Callable[..., Tuple[Any, Mapping[str, float]]],
        result_extractor: Callable[[Any, Any, ModelStructureAudit], DispatchResult],
        require_quadratic_constraints: bool = True,
    ) -> None:
        self._model_factory = model_factory
        self._result_extractor = result_extractor
        self._require_qcp = require_quadratic_constraints

    def solve(
        self,
        *,
        frame: Any,
        pre_state: Any,
        route_steps: Mapping[str, Any],
        work_assignments: Sequence[Any],
    ) -> DispatchResult:
        model, fixed_assignments = self._model_factory(
            frame=frame,
            pre_state=pre_state,
            route_steps=route_steps,
            work_assignments=work_assignments,
        )
        fix_and_relax_discrete_variables(model, fixed_assignments)
        structure = audit_model_structure(model)
        if self._require_qcp and structure.num_quadratic_constraints <= 0:
            raise RuntimeError("R26 fast dispatch lost the AC-aware QCP constraints")
        model.optimize()
        return self._result_extractor(model, frame, structure)

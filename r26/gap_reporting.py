"""Honest offline gap reporting helpers.

The restricted-master native bound is diagnostic only.  A scientific global
gap can only be formed from a feasible incumbent and an independently supplied
exact all-column lower bound.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Callable, Mapping, Optional


def minimization_relative_gap(incumbent: float, lower_bound: float) -> float:
    """Return ``max(0, (U-L)/abs(U))`` for a minimization problem.

    The zero-incumbent case is handled explicitly rather than hidden behind a
    numerical epsilon: equal zero values have zero gap and every other bound
    relation has infinite relative gap.
    """

    if not (math.isfinite(incumbent) and math.isfinite(lower_bound)):
        return math.inf
    if lower_bound > incumbent:
        raise ValueError("lower bound cannot exceed the feasible incumbent")
    if incumbent == 0.0:
        return 0.0 if lower_bound == 0.0 else math.inf
    return max(0.0, (incumbent - lower_bound) / abs(incumbent))


@dataclass(frozen=True)
class IncumbentTarget:
    """Auditable incumbent threshold implied by an exact lower bound."""

    lower_bound: float
    target_gap: float
    threshold: float
    branch: str

    def accepts(self, incumbent: float, *, atol: float = 1e-12) -> bool:
        if not math.isfinite(incumbent):
            return False
        try:
            return minimization_relative_gap(incumbent, self.lower_bound) <= (
                self.target_gap + atol
            )
        except ValueError:
            return False


def incumbent_required_for_gap(lower_bound: float, target_gap: float) -> IncumbentTarget:
    """Derive the feasible-incumbent target for a minimization certificate.

    For negative objectives, ``U <= L/(1+g)``.  For positive objectives,
    ``U <= L/(1-g)``.  The branches are deliberately explicit because applying
    the common negative-objective formula to a positive cost is incorrect.
    """

    if not math.isfinite(lower_bound):
        raise ValueError("lower_bound must be finite")
    if not (0.0 <= target_gap < 1.0):
        raise ValueError("target_gap must satisfy 0 <= target_gap < 1")
    if lower_bound < 0.0:
        threshold = lower_bound / (1.0 + target_gap)
        branch = "NEGATIVE_OBJECTIVE"
    elif lower_bound > 0.0:
        threshold = lower_bound / (1.0 - target_gap)
        branch = "POSITIVE_OBJECTIVE"
    else:
        threshold = 0.0
        branch = "ZERO_OBJECTIVE"
    return IncumbentTarget(lower_bound, target_gap, threshold, branch)


@dataclass(frozen=True)
class ScientificGapSnapshot:
    """One progress record with diagnostic and authoritative fields separated."""

    current_incumbent: Optional[float]
    restricted_master_obj_bound: Optional[float]
    rmp_native_gap: Optional[float]
    global_lower_bound: Optional[float]
    global_certified_gap: Optional[float]
    incumbent_required_for_3pct: Optional[float]
    target_gap: float = 0.03
    globally_certified: bool = False
    global_bound_authority: str = "EXACT_ALL_COLUMN_LOWER_BOUND"
    restricted_bound_authority: str = "DIAGNOSTIC_ONLY_NOT_GLOBAL"

    @classmethod
    def create(
        cls,
        *,
        incumbent: Optional[float],
        restricted_obj_bound: Optional[float],
        restricted_native_gap: Optional[float],
        exact_global_lower_bound: Optional[float],
        target_gap: float = 0.03,
    ) -> "ScientificGapSnapshot":
        finite_u = incumbent is not None and math.isfinite(incumbent)
        finite_l = exact_global_lower_bound is not None and math.isfinite(exact_global_lower_bound)
        gap: Optional[float] = None
        threshold: Optional[float] = None
        certified = False
        if finite_l:
            target = incumbent_required_for_gap(float(exact_global_lower_bound), target_gap)
            threshold = target.threshold
            if finite_u:
                gap = minimization_relative_gap(float(incumbent), float(exact_global_lower_bound))
                certified = gap <= target_gap + 1e-12
        return cls(
            current_incumbent=float(incumbent) if finite_u else None,
            restricted_master_obj_bound=(
                float(restricted_obj_bound)
                if restricted_obj_bound is not None and math.isfinite(restricted_obj_bound)
                else None
            ),
            rmp_native_gap=(
                float(restricted_native_gap)
                if restricted_native_gap is not None and math.isfinite(restricted_native_gap)
                else None
            ),
            global_lower_bound=float(exact_global_lower_bound) if finite_l else None,
            global_certified_gap=gap,
            incumbent_required_for_3pct=threshold if target_gap == 0.03 else None,
            target_gap=target_gap,
            globally_certified=certified,
        )

    def as_record(self) -> Mapping[str, Any]:
        return asdict(self)

    def progress_line(self) -> str:
        def fmt(value: Optional[float], percent: bool = False) -> str:
            if value is None:
                return "NA"
            return f"{100.0 * value:.3f}%" if percent else f"{value:.6f}"

        return (
            f"CURRENT_INCUMBENT={fmt(self.current_incumbent)} "
            f"RMP_NATIVE_GAP={fmt(self.rmp_native_gap, True)} "
            f"GLOBAL_LOWER_BOUND={fmt(self.global_lower_bound)} "
            f"GLOBAL_CERTIFIED_GAP={fmt(self.global_certified_gap, True)} "
            f"INCUMBENT_REQUIRED_FOR_3PCT={fmt(self.incumbent_required_for_3pct)} "
            f"CERTIFIED={str(self.globally_certified).lower()}"
        )


def make_global_certificate_callback(
    *,
    exact_global_lower_bound: float,
    target_gap: float = 0.03,
    on_snapshot: Optional[Callable[[ScientificGapSnapshot], None]] = None,
) -> Callable[[Any, int], None]:
    """Build a Gurobi-compatible MIPSOL callback with safe stop semantics.

    This callback may terminate incumbent search once the *external exact*
    lower bound and the new feasible MIPSOL incumbent satisfy the scientific
    target.  It never reads the restricted model's ObjBound as a global bound,
    and termination itself is not treated as a certificate.
    """

    incumbent_required_for_gap(exact_global_lower_bound, target_gap)

    def callback(model: Any, where: int) -> None:
        grb = getattr(model, "_r26_grb", None)
        if grb is None:
            try:
                from gurobipy import GRB as grb  # type: ignore
            except ImportError:
                return
        if where != grb.Callback.MIPSOL:
            return
        incumbent = float(model.cbGet(grb.Callback.MIPSOL_OBJ))
        native_bound: Optional[float]
        native_gap: Optional[float]
        try:
            native_bound = float(model.cbGet(grb.Callback.MIPSOL_OBJBND))
        except Exception:
            native_bound = None
        try:
            native_gap = minimization_relative_gap(incumbent, native_bound) if native_bound is not None else None
        except ValueError:
            native_gap = None
        snapshot = ScientificGapSnapshot.create(
            incumbent=incumbent,
            restricted_obj_bound=native_bound,
            restricted_native_gap=native_gap,
            exact_global_lower_bound=exact_global_lower_bound,
            target_gap=target_gap,
        )
        if on_snapshot is not None:
            on_snapshot(snapshot)
        if snapshot.globally_certified:
            model.terminate()

    return callback

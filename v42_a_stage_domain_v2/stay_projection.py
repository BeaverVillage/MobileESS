"""Exact fixed-duration class histograms, with an explicit LP-scope gate.

No native model or optimizer is imported by the matrix-free API.  This module
does not replace mixed individual event-flow relaxations: their LP projection
is different, even on the zero-migration face (see ``lp_counterexample``).
The safe native helper preserves the already accepted ``factor.stay`` model.
Physical authorization of ``starts`` belongs to the V2 domain authority.
"""
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction

from v42_job_capability import Option


HISTOGRAM_REFERENCE = "FIXED_DURATION_HISTOGRAM"
RETAIN_EVENT_FLOW = "RETAIN_EXISTING_EVENT_FLOW_AND_LAZY_SUPPORT"


def exact(value):
    """Preserve the exact value, including an inherited binary64 coefficient."""
    return value if isinstance(value, Fraction) else Fraction(value)


@dataclass(frozen=True)
class StayIncidence:
    class_id: str
    cardinality: int
    service_slots: int
    gpu: int
    reference_start: int
    reference_site: str
    starts: tuple

    def __post_init__(self):
        for value in (self.cardinality, self.service_slots, self.gpu):
            if type(value) is not int or value <= 0:
                raise ValueError("POSITIVE_INTEGER_CLASS_SERVICE_GPU_REQUIRED")
        if type(self.reference_start) is not int:
            raise ValueError("INTEGER_REFERENCE_REQUIRED")
        if tuple(sorted(set(self.starts))) != self.starts:
            raise ValueError("CANONICAL_DISTINCT_STAY_SUPPORT_REQUIRED")
        if any(not isinstance(site, str) or type(start) is not int
               for site, start in self.starts):
            raise ValueError("INTEGER_SITE_START_SUPPORT_REQUIRED")

    @property
    def finishes(self):
        return tuple((site, start + self.service_slots)
                     for site, start in self.starts)

    @property
    def states(self):
        return tuple(sorted({(site, t) for site, start in self.starts
                             for t in range(start, start + self.service_slots)}))

    def objective_column(self, key):
        if key not in self.starts:
            raise ValueError("STAY_KEY_OUTSIDE_SUPPORT")
        site, start = key
        return dict(migration_count=0,
                    shift_magnitude=abs(start - self.reference_start),
                    prestart_relocation=int(site != self.reference_site),
                    inherited_signed_shift=start - self.reference_start)

    def scientific_column(self, key, *, runtime_provider=None,
                          grid_gpu_rows=None):
        """Direct incidence using caller-supplied, unchanged authority values.

        ``runtime_provider(site,end)`` returns the frozen Runtime vector.
        ``grid_gpu_rows[row][site,t]`` is a signed coefficient per known GPU.
        CC4 forecast variables/values stay in the original global equations:
        a known-job column has no direct CC4 forecast coefficient.  Its known
        GPU and Runtime interfaces are identical and thus preserve every CC4
        reserve/headroom equation that consumes those interfaces.
        """
        if key not in self.starts:
            raise ValueError("STAY_KEY_OUTSIDE_SUPPORT")
        site, start = key
        end = start + self.service_slots
        out = {("class_exact_cardinality", self.class_id): Fraction(1),
               ("completion", site, end): Fraction(1)}
        for t in range(start, end):
            out["known_GPU", site, t] = Fraction(self.gpu)
        if runtime_provider is not None:
            values = runtime_provider(site, end)
            values = values.items() if hasattr(values, "items") else values
            for target, value in values:
                target = tuple(target) if isinstance(target, (list, tuple)) else (target,)
                row = ("Runtime",) + target
                out[row] = out.get(row, Fraction(0)) + exact(value)
        for row, coefficients in (grid_gpu_rows or {}).items():
            value = sum((exact(coefficients.get((site, t), 0)) * self.gpu
                         for t in range(start, end)), Fraction(0))
            if value:
                target = tuple(row) if isinstance(row, (list, tuple)) else (row,)
                out[("grid",) + target] = value
        return out

    def structural_census(self):
        """Exact local counts; unchanged global rows/Runtime auxiliaries excluded."""
        starts, states = len(self.starts), len(self.states)
        return dict(
            kind="EXACT_LOCAL_STRUCTURAL_COUNT",
            compact=dict(binary=starts if self.cardinality == 1 else 0,
                         integer=starts if self.cardinality > 1 else 0,
                         continuous=0, local_rows=0, local_nnz=0,
                         external_class_exact_cardinality_rows=1,
                         external_class_cardinality_stay_nnz=starts),
            extended_histogram=dict(
                binary=2 * starts if self.cardinality == 1 else 0,
                integer=2 * starts if self.cardinality > 1 else 0,
                continuous=states, local_rows=starts + states,
                local_nnz=2 * starts + states + self.service_slots * starts),
            already_projected_factor_stay_delta=dict(
                binary=0, integer=0, continuous=0, rows=0, nnz=0),
            global_matrix_size="REQUIRES_GLOBAL_BINDING_CENSUS_NOT_INFERRED")


def incidence(job, starts, cardinality, class_id=""):
    """Build a deterministic coefficient interface; never deletes a candidate."""
    keys = tuple(sorted(set(starts)))
    return StayIncidence(class_id, cardinality, job.service_slots, job.gpu,
                         job.reference_start, job.reference_site, keys)


def representation_gate(cardinality, *, has_migration, fixed=False):
    if fixed:
        return dict(adopt=False, reference="FIXED_HISTORY",
                    reason="FIXED_RUNNING_OR_SINGLE_OPTION_HISTORY_RETAINED")
    if cardinality > 1 or not has_migration:
        return dict(adopt=True, reference=HISTOGRAM_REFERENCE,
                    reason="ALREADY_ACCEPTED_FIXED_DURATION_HISTOGRAM")
    return dict(adopt=False, reference=RETAIN_EVENT_FLOW,
                reason="SINGLETON_MIXED_EVENT_FLOW_LP_COUNTEREXAMPLE")


def lift_counts(spec, counts, *, migration_count=0, integral=False):
    """Unique exact lift to accepted fixed-duration finish/occupancy variables."""
    if set(counts) - set(spec.starts):
        raise ValueError("STAY_KEY_OUTSIDE_SUPPORT")
    y = {key: exact(counts.get(key, 0)) for key in spec.starts}
    migration = exact(migration_count)
    if migration < 0 or any(value < 0 or value > spec.cardinality
                            for value in y.values()):
        raise ValueError("CLASS_COUNT_BOUNDS")
    if sum(y.values(), Fraction(0)) + migration != spec.cardinality:
        raise ValueError("CLASS_EXACT_CARDINALITY")
    if integral and any(value.denominator != 1 for value in (*y.values(), migration)):
        raise ValueError("FRACTIONAL_CLASS_COUNT")
    out = dict(y=y, q={}, w={}, f0={}, f1={}, r0={}, h={}, r1={})
    for (site, start), value in y.items():
        out["f0"][site, start + spec.service_slots] = value
    for site, t in spec.states:
        out["r0"][site, t] = sum((value for (k, s), value in y.items()
                                 if k == site and s <= t < s + spec.service_slots),
                                Fraction(0))
    # Nonnegative migration count and exact cardinality make each auxiliary
    # upper bound redundant, over both real and integer y.
    if any(value > spec.cardinality for value in out["r0"].values()):
        raise AssertionError("REDUNDANT_STATE_BOUND_PROOF_FAILED")
    return out


def project_extended(spec, extended, *, migration_count=0, integral=False):
    """Independent exact identity check for an extended histogram point."""
    want = lift_counts(spec, extended["y"], migration_count=migration_count,
                       integral=integral)
    for family in ("f0", "r0"):
        got = extended.get(family, {})
        for key in set(got) | set(want[family]):
            if exact(got.get(key, 0)) != want[family].get(key, 0):
                raise ValueError("FIXED_DURATION_PROJECTION_IDENTITY:" + family)
    return want["y"]


def reconstruct_counts(spec, counts, *, migration_count=0):
    point = lift_counts(spec, counts, migration_count=migration_count, integral=True)
    return tuple(Option(start, site, ((site, start, start + spec.service_slots),))
                 for (site, start), value in point["y"].items()
                 for _ in range(int(value)))


def add_stay_unit(model, job, graph, cardinality, *, starts=None,
                  reference_representation=HISTOGRAM_REFERENCE):
    """Native API compatible with factor.stay(..., f0=True, state=True).

    The caller retains the original class_exact_cardinality equation and all
    optional migration lanes.  This helper never adds or changes an objective,
    global row, scientific class, migration authority, or solver call.
    """
    gate = representation_gate(cardinality, has_migration=bool(graph.events["w"]),
                               fixed=bool(graph.fixed))
    if not gate["adopt"] or reference_representation != HISTOGRAM_REFERENCE:
        raise ValueError("STAY_COMPACT_LP_PROJECTION_UNPROVEN_RETAIN_EXISTING_REPRESENTATION")
    import gurobipy as gp
    spec = incidence(job, graph.events["y"] if starts is None else starts, cardinality)
    typ = gp.GRB.BINARY if cardinality == 1 else gp.GRB.INTEGER
    y = {key: model.addVar(lb=0, ub=cardinality, vtype=typ,
                          name=f"Y[{job.uid},{i}]")
         for i, key in enumerate(spec.starts)}
    out = dict(y=y, q={}, w={}, f0={}, f1={}, r0={}, h={}, r1={})
    for (site, start), value in y.items():
        out["f0"][site, start + spec.service_slots] = value
    for site, t in spec.states:
        out["r0"][site, t] = gp.quicksum(value for (k, s), value in y.items()
                                          if k == site and s <= t < s + spec.service_slots)
    return out


def lp_counterexample():
    """Exact event-flow LP point disproving unrestricted singleton projection.

    All migration variables can be zero in a mixed event-flow model.  These
    source states obey one_start, source_exit, every source balance, full_service,
    useful_destination_service, and [0,1] variable bounds.  However they are
    absent from the fixed-duration histogram projection for service D=3.
    D=3 admits a proper pending-job checkpoint after two source slots, so this
    face is also present in a physically authorized mixed migration graph.
    """
    half = Fraction(1, 2)
    y = {("A", 0): Fraction(0), ("A", 1): Fraction(1), ("A", 2): Fraction(0)}
    f0 = {("A", 3): half, ("A", 4): Fraction(0), ("A", 5): half}
    r0 = {("A", 0): Fraction(0), ("A", 1): Fraction(1),
          ("A", 2): Fraction(1), ("A", 3): half, ("A", 4): half}
    residuals = {"one_start": sum(y.values()) - 1,
                 "source_exit": sum(f0.values()) - 1,
                 "full_service": sum(r0.values()) - 3,
                 "useful_destination_service": Fraction(0)}
    for t in range(6):
        residuals[f"r0_balance[{t}]"] = (r0.get(("A", t), 0)
            - r0.get(("A", t - 1), 0) - y.get(("A", t), 0) + f0.get(("A", t), 0))
    return dict(service_slots=3, cardinality=1, starts=tuple(y),
                point=dict(y=y, f0=f0, r0=r0), residuals=residuals,
                event_flow_rows_exact_pass=all(value == 0 for value in residuals.values()),
                bounds_exact_pass=all(0 <= value <= 1
                                     for family in (y, f0, r0) for value in family.values()),
                fixed_duration_finish_identity_pass=False,
                fixed_duration_occupancy_identity_pass=False,
                global_all_classes_compact_adoption=False,
                optimizer_calls=0)

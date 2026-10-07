"""Exact locked-stage rebuild and migration-zero LP projection.

Every reduction is proved against an actual linear matrix, not a historical
objective value or date.  Mixed singleton source flow variables are retained:
changing their finish/occupancy LP projection is deliberately prohibited.
This module never calls a production optimizer.
"""
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math

import numpy as np
import scipy.sparse as sp


COMPONENTS = ("rho", "migration_count", "shift_magnitude", "prestart_relocation")
INTEGER_COMPONENTS = frozenset(COMPONENTS[1:])


def rational(value):
    return value if isinstance(value, Fraction) else Fraction(value)


@dataclass(frozen=True)
class Objective:
    name: str
    terms: tuple  # (column index, exact coefficient)
    constant: object = 0

    def coefficients(self):
        out = {}
        for column, value in self.terms:
            if type(column) is not int or column < 0:
                raise ValueError("OBJECTIVE_COLUMN_AXIS")
            out[column] = out.get(column, Fraction(0)) + rational(value)
        return {column: value for column, value in sorted(out.items()) if value}


@dataclass(frozen=True)
class LinearSnapshot:
    matrix: object
    lower: object
    upper: object
    senses: object
    rhs: object
    vtypes: object
    objectives: tuple

    def require(self):
        rows, columns = self.matrix.shape
        if not sp.isspmatrix_csr(self.matrix) or not self.matrix.has_canonical_format:
            raise ValueError("CANONICAL_CSR_LINEAR_STAGE_REQUIRED")
        if any(len(value) != columns for value in (self.lower, self.upper, self.vtypes)):
            raise ValueError("STAGE_COLUMN_AXIS")
        if len(self.senses) != rows or len(self.rhs) != rows:
            raise ValueError("STAGE_ROW_AXIS")
        if any(sense not in ("=", "<", ">") for sense in self.senses):
            raise ValueError("LINEAR_ROW_SENSE")
        if any(vtype not in ("B", "I", "C") for vtype in self.vtypes):
            raise ValueError("LINEAR_VARIABLE_TYPE")
        if np.any(np.isnan(np.asarray(self.lower))) or np.any(np.isnan(np.asarray(self.upper))):
            raise ValueError("NONFINITE_STAGE_BOUND")
        if not np.all(np.isfinite(self.matrix.data)) or not np.all(np.isfinite(self.rhs)):
            raise ValueError("NONFINITE_STAGE_COEFFICIENT")
        if np.any(np.asarray(self.lower) > np.asarray(self.upper)):
            raise ValueError("INCONSISTENT_STAGE_BOUNDS")
        names = [objective.name for objective in self.objectives]
        if len(set(names)) != len(names):
            raise ValueError("DUPLICATE_OBJECTIVE_AXIS")
        for objective in self.objectives:
            if any(column >= columns for column in objective.coefficients()):
                raise ValueError("OBJECTIVE_COLUMN_AXIS")
        return self

    def objective(self, name):
        matches = [objective for objective in self.objectives if objective.name == name]
        if len(matches) != 1:
            raise ValueError("EXACT_OBJECTIVE_REQUIRED:" + name)
        return matches[0]

    def fingerprint(self):
        self.require()
        matrix = self.matrix
        digest = hashlib.sha256()
        digest.update(str(matrix.shape).encode())
        for value in (matrix.indptr, matrix.indices, matrix.data,
                      self.lower, self.upper, self.senses, self.rhs, self.vtypes):
            array = np.asarray(value)
            digest.update(str((array.shape, array.dtype.str)).encode())
            digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
        for objective in self.objectives:
            digest.update(repr((objective.name, tuple(objective.coefficients().items()),
                                rational(objective.constant))).encode())
        return digest.hexdigest()


def integer_objective_proof(snapshot, component):
    """Integer coefficients on integer variables imply an integer objective."""
    snapshot.require()
    if component not in INTEGER_COMPONENTS:
        raise ValueError("CONTINUOUS_OBJECTIVE_HAS_NO_INTEGER_CERTIFICATE")
    objective = snapshot.objective(component)
    coefficients = objective.coefficients()
    constant = rational(objective.constant)
    if constant.denominator != 1:
        raise ValueError("OBJECTIVE_CONSTANT_NOT_INTEGER")
    if any(value.denominator != 1 or snapshot.vtypes[column] not in ("I", "B")
           for column, value in coefficients.items()):
        raise ValueError("OBJECTIVE_INTEGRALITY_NOT_PROVEN")
    return dict(PASS=True, component=component, exact_constant=str(constant),
                terms=len(coefficients), proof="Integer affine combination of integer variables",
                absolute_value_auxiliaries=0, rho_integer_certificate_allowed=False,
                snapshot_sha256=snapshot.fingerprint())


def integer_optimality_certificate(component, incumbent, valid_lower_bound, *,
                                  bound_independently_validated=False,
                                  primal_independently_validated=False,
                                  integrality_proven=False, bound_tolerance=1e-6,
                                  integer_tolerance=1e-5):
    """Repository convention: ceil(valid LB - 1e-6) >= integer incumbent.

    The caller supplies current-stage independently replayed primal/bound
    evidence. A certificate is scoped to that matrix/domain, never to omitted
    integer columns. Historical objective values are not accepted as evidence.
    """
    if component not in INTEGER_COMPONENTS:
        raise ValueError("CONTINUOUS_OBJECTIVE_HAS_NO_INTEGER_CERTIFICATE")
    if bound_tolerance != 1e-6 or integer_tolerance != 1e-5:
        raise ValueError("FROZEN_INTEGER_CERTIFICATE_CONVENTION_REQUIRED")
    usable = (incumbent is not None and valid_lower_bound is not None
              and math.isfinite(float(incumbent)) and math.isfinite(float(valid_lower_bound)))
    integer = round(float(incumbent)) if usable else None
    integral = bool(usable and abs(float(incumbent) - integer) <= integer_tolerance)
    bound_integer = math.ceil(float(valid_lower_bound) - bound_tolerance) if usable else None
    consistent = bool(usable and float(valid_lower_bound) <= float(incumbent) + integer_tolerance)
    passed = bool(bound_independently_validated and primal_independently_validated
                  and integrality_proven and integral and consistent and bound_integer >= integer)
    return dict(PASS=passed, component=component, incumbent_integer=integer,
                valid_lower_bound=valid_lower_bound, safe_integer_lower_bound=bound_integer,
                bound_tolerance=bound_tolerance, integer_tolerance=integer_tolerance,
                independent_bound=bound_independently_validated,
                independent_primal=primal_independently_validated,
                objective_integrality_proven=integrality_proven,
                scope="CURRENT_LOCKED_ACTIVE_MATRIX_ONLY",
                integer_domain_closure_proven=False)


def add_integer_shift_variable(model, expression):
    """Optional exact Z_shift definition after independent coefficient checks.

    Integer nonnegative y with known nonnegative integer magnitude coefficients
    makes the defining variable redundant over integer schedules. Its relaxed
    lower bound is also redundant, so the LP projection stays identical.
    """
    import gurobipy as gp
    model.update()
    expression = gp.LinExpr(expression)
    constant = Fraction(expression.getConstant())
    terms = {}
    for i in range(expression.size()):
        variable = expression.getVar(i)
        terms.setdefault(variable.index, [variable, Fraction(0)])[1] += Fraction(expression.getCoeff(i))
    if (constant.denominator != 1 or constant < 0 or any(
            coefficient.denominator != 1 or coefficient < 0
            or variable.VType not in (gp.GRB.INTEGER, gp.GRB.BINARY) or variable.LB < 0
            for variable, coefficient in terms.values() if coefficient)):
        raise ValueError("NONNEGATIVE_INTEGER_SHIFT_EXPRESSION_REQUIRED")
    z = model.addVar(lb=0, vtype=gp.GRB.INTEGER, name="Z_shift_exact_integer")
    model.addConstr(z == expression, name="exact_integer_shift_definition")
    return z, dict(PASS=True, integer_valued=True, unique_lift=True,
                   same_integer_projection=True, same_LP_projection=True,
                   same_shift_objective=True, original_terms=sum(bool(coefficient) for _, coefficient in terms.values()),
                   variables_added=1, rows_added=1,
                   proof="Nonnegative integer affine expression; Z equals that expression exactly.",
                   optimization_calls=0)


@dataclass(frozen=True)
class LexLock:
    component: str
    value: object
    independently_verified: bool
    current_run_evidence_hash: str
    epsilon: object = 0


def rebuild_locked_snapshot(snapshot, locks):
    """Fresh exact matrix plus ordered current-run prior objective locks."""
    snapshot.require()
    locks = tuple(locks)
    if tuple(lock.component for lock in locks) != COMPONENTS[:len(locks)]:
        raise ValueError("EXACT_LEX_PREFIX_REQUIRED")
    matrix, rhs, senses = snapshot.matrix.tocsr(copy=True), list(snapshot.rhs), list(snapshot.senses)
    lock_rows = {}
    for lock in locks:
        if not lock.independently_verified or len(lock.current_run_evidence_hash) != 64:
            raise ValueError("NEW_RUN_PROVEN_LOCK_REQUIRED")
        objective = snapshot.objective(lock.component)
        coefficients = objective.coefficients()
        if lock.component in INTEGER_COMPONENTS:
            integer_objective_proof(snapshot, lock.component)
            if rational(lock.value).denominator != 1 or rational(lock.epsilon) != 0:
                raise ValueError("EXACT_INTEGER_LOCK_REQUIRED")
            sense = "="
        else:
            # rho follows the repository's continuous prior-lock convention.
            if rational(lock.epsilon) != Fraction(1e-7):
                raise ValueError("RHO_LEX_LOCK_EPSILON_AUTHORITY")
            sense = "<"
        values = []
        for value in coefficients.values():
            converted = float(value)
            if Fraction(converted) != value:
                raise ValueError("NONEXACT_LEX_COEFFICIENT_PROJECTION")
            values.append(converted)
        row = sp.csr_matrix((values, ([0] * len(values), list(coefficients))), shape=(1, matrix.shape[1]))
        lock_rows[lock.component] = matrix.shape[0]
        matrix = sp.vstack((matrix, row), format="csr")
        target = rational(lock.value) + rational(lock.epsilon) - rational(objective.constant)
        converted = float(target)
        if Fraction(converted) != target:
            # Preserve the exact binary64 RHS used by native Gurobi arithmetic:
            # continuous rho has an intentional floating epsilon addition.
            if lock.component != "rho":
                raise ValueError("NONEXACT_INTEGER_LEX_RHS")
            converted = float(lock.value) + float(lock.epsilon) - float(objective.constant)
        rhs.append(converted)
        senses.append(sense)
    rebuilt = LinearSnapshot(matrix, np.array(snapshot.lower, copy=True), np.array(snapshot.upper, copy=True),
                             np.asarray(senses), np.asarray(rhs), np.array(snapshot.vtypes, copy=True),
                             snapshot.objectives).require()
    return rebuilt, dict(PASS=True, same_original_matrix_coefficients=True,
                         same_original_bounds_types=True, same_objectives=True,
                         lock_rows=lock_rows, locks=[lock.component for lock in locks],
                         original_snapshot_sha256=snapshot.fingerprint(),
                         rebuilt_snapshot_sha256=rebuilt.fingerprint(),
                         proof="Original rows unchanged; exact ordered current-run locks appended",
                         optimization_calls=0)


@dataclass(frozen=True)
class ZeroProjectionProof:
    original_hash: str
    migration_lock_row: int
    bound_zero_columns: tuple
    migration_zero_columns: tuple
    forcing_steps: tuple  # (row, columns forced to zero)
    removed_columns: tuple
    removed_rows: tuple

    def verify(self, snapshot):
        snapshot.require()
        if snapshot.fingerprint() != self.original_hash:
            raise ValueError("ZERO_PROJECTION_SOURCE_HASH_DRIFT")
        matrix = snapshot.matrix.tocsr(copy=True)
        matrix.sum_duplicates(); matrix.eliminate_zeros(); matrix.sort_indices()
        objective = snapshot.objective("migration_count")
        terms = objective.coefficients()
        lock = _row_terms(matrix, self.migration_lock_row)
        if (snapshot.senses[self.migration_lock_row] != "=" or snapshot.rhs[self.migration_lock_row] != 0
                or rational(objective.constant) != 0 or lock != terms
                or any(value <= 0 or snapshot.lower[column] < 0 for column, value in terms.items())):
            raise ValueError("ACTUAL_NONNEGATIVE_MIGRATION_ZERO_LOCK_REQUIRED")
        if tuple(terms) != self.migration_zero_columns:
            raise ValueError("MIGRATION_ZERO_SEED_AXIS")
        zeros = set(self.bound_zero_columns)
        if any(snapshot.lower[column] != 0 or snapshot.upper[column] != 0 for column in zeros):
            raise ValueError("FIXED_ZERO_BOUND_PROOF")
        zeros.update(terms)
        for row, forced in self.forcing_steps:
            remaining = {column: value for column, value in _row_terms(matrix, row).items() if column not in zeros}
            if (tuple(remaining) != forced or not _nonnegative_zero_row(snapshot, row, remaining)):
                raise ValueError("NONNEGATIVE_ZERO_PROPAGATION_PROOF")
            zeros.update(forced)
        if tuple(sorted(zeros)) != self.removed_columns:
            raise ValueError("ZERO_PROJECTION_REMOVED_AXIS")
        for row in self.removed_rows:
            if any(column not in zeros for column in _row_terms(matrix, row)):
                raise ValueError("NONEMPTY_REMOVED_ROW")
            if not _empty_row_feasible(snapshot.senses[row], snapshot.rhs[row]):
                raise ValueError("INCONSISTENT_REMOVED_ZERO_ROW")
        return dict(PASS=True, same_LP_projection=True, same_integer_projection=True,
                    exact_zero_lift=True, original_columns=matrix.shape[1],
                    removed_columns=len(zeros), removed_rows=len(self.removed_rows),
                    propagation_rows=len(self.forcing_steps),
                    singleton_source_finish_occupancy_replaced_by_histogram=False,
                    historical_lock_used=False, optimization_calls=0)


def _row_terms(matrix, row):
    start, end = matrix.indptr[row:row + 2]
    return {int(column): Fraction(float(value))
            for column, value in zip(matrix.indices[start:end], matrix.data[start:end]) if value}


def _nonnegative_zero_row(snapshot, row, remaining):
    if not remaining or snapshot.rhs[row] != 0 or any(snapshot.lower[column] < 0 for column in remaining):
        return False
    sense = snapshot.senses[row]
    return ((sense in ("=", "<") and all(value > 0 for value in remaining.values()))
            or (sense in ("=", ">") and all(value < 0 for value in remaining.values())))


def _empty_row_feasible(sense, rhs):
    return rhs == 0 if sense == "=" else rhs >= 0 if sense == "<" else rhs <= 0


def project_migration_zero(snapshot, *, migration_lock_row):
    """Remove only columns independently proved zero under the actual lock.

    Exact LP-preserving fallback: mixed singleton y/f0/r0 are not replaced by
    histogram identities. Unsupported zero implications simply retain columns.
    The returned mapping lifts every projected point with exact zeros.
    """
    snapshot.require()
    matrix = snapshot.matrix.tocsr(copy=True)
    matrix.sum_duplicates(); matrix.eliminate_zeros(); matrix.sort_indices()
    terms = snapshot.objective("migration_count").coefficients()
    if (not 0 <= migration_lock_row < matrix.shape[0]
            or snapshot.senses[migration_lock_row] != "=" or snapshot.rhs[migration_lock_row] != 0
            or rational(snapshot.objective("migration_count").constant) != 0
            or _row_terms(matrix, migration_lock_row) != terms
            or any(value <= 0 or snapshot.lower[column] < 0 for column, value in terms.items())):
        raise ValueError("ACTUAL_NONNEGATIVE_MIGRATION_ZERO_LOCK_REQUIRED")
    bounds = tuple(int(column) for column in np.flatnonzero(
        (np.asarray(snapshot.lower) == 0) & (np.asarray(snapshot.upper) == 0)))
    zeros = set(bounds) | set(terms)
    columns = matrix.tocsc()
    pending, queued, steps = deque(), set(), []

    def enqueue(column):
        for row in columns.indices[columns.indptr[column]:columns.indptr[column + 1]]:
            row = int(row)
            if row not in queued:
                pending.append(row); queued.add(row)

    for column in sorted(zeros):
        enqueue(column)
    while pending:
        row = pending.popleft(); queued.remove(row)
        remaining = {column: value for column, value in _row_terms(matrix, row).items() if column not in zeros}
        if _nonnegative_zero_row(snapshot, row, remaining):
            forced = tuple(remaining)
            steps.append((row, forced))
            zeros.update(forced)
            for column in forced:
                enqueue(column)
    removed = tuple(sorted(zeros))
    keep_mask = np.ones(matrix.shape[1], dtype=bool)
    keep_mask[np.asarray(removed, dtype=np.int64)] = False
    keep_columns = np.flatnonzero(keep_mask)
    projected = matrix[:, keep_columns].tocsr()
    empty = np.flatnonzero(np.diff(projected.indptr) == 0)
    for row in empty:
        if not _empty_row_feasible(snapshot.senses[row], snapshot.rhs[row]):
            raise ValueError("LOCKED_MODEL_ZERO_ROW_INCONSISTENT")
    keep_rows = np.ones(matrix.shape[0], dtype=bool); keep_rows[empty] = False
    mapping = np.full(matrix.shape[1], -1, dtype=np.int64)
    mapping[keep_columns] = np.arange(len(keep_columns))
    objectives = tuple(Objective(objective.name,
        tuple((int(mapping[column]), value) for column, value in objective.coefficients().items()
              if mapping[column] >= 0), objective.constant) for objective in snapshot.objectives)
    result = LinearSnapshot(projected[keep_rows], np.asarray(snapshot.lower)[keep_columns],
                            np.asarray(snapshot.upper)[keep_columns], np.asarray(snapshot.senses)[keep_rows],
                            np.asarray(snapshot.rhs)[keep_rows], np.asarray(snapshot.vtypes)[keep_columns],
                            objectives).require()
    proof = ZeroProjectionProof(snapshot.fingerprint(), int(migration_lock_row), bounds, tuple(terms),
                                tuple(steps), removed, tuple(int(row) for row in empty))
    proof.verify(snapshot)
    return result, mapping, proof


def lift_zero_projection(projected_point, mapping):
    point = np.zeros(len(mapping), dtype=float)
    keep = np.asarray(mapping) >= 0
    point[keep] = np.asarray(projected_point)[np.asarray(mapping)[keep]]
    return point


def exact_gpu_count_rounding(columns, residual_capacity):
    """Valid count/clique inequality for overlapping whole-gang STAY counts.

    ``columns`` supplies (variable, per-job GPU), each for an integer count
    whose jobs occupy the same physical site/time. Other occupancy is
    nonnegative. Therefore min(GPU) * sum(counts) <= residual capacity and an
    integer sum obeys the exact floor. Caller verifies occupancy incidence.
    """
    columns = tuple(columns)
    if (type(residual_capacity) is not int or residual_capacity < 0 or not columns
            or any(type(gpu) is not int or gpu <= 0 for _, gpu in columns)
            or len({column for column, _ in columns}) != len(columns)):
        raise ValueError("INTEGER_GANG_CAPACITY_INCIDENCE_REQUIRED")
    minimum = min(gpu for _, gpu in columns)
    return dict(coefficients=tuple((column, 1) for column, _ in columns),
                upper=residual_capacity // minimum,
                minimum_gpu=minimum, residual_capacity=residual_capacity,
                valid_for_all_integer_schedules=True,
                proof="Every selected whole gang contributes >= minimum_gpu at this site/time; integer count rounds capacity down.",
                scientific_capacity_changed=False)

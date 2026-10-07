"""Exact LP certificates and bounded activation over original native rows.

No optimizer is imported or called.  A physical schedule is a useful pricing
witness, but it does not span the mixed source-flow LP (fractional finishes
included).  Consequently physical-option scans NEVER close the native LP.

The finite matrix bridge below checks every actual primitive native column,
including bounds and added local rows.  Its certificate applies to that exact
extension.  Connecting the extension to the entire scientific domain is a
separate producer proof; a caller-supplied completeness flag cannot supply it.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
import hashlib
import json
import math
import re

import numpy as np
import scipy.sparse as sp

from .domain import contains, digest
from .lexstage import LinearSnapshot, Objective, rational


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _finite(value):
    # Gurobi represents infinity as +/-1e100 in exported attributes.
    return math.isfinite(float(value)) and abs(float(value)) < 1e100


def _vector(values, length, name):
    if len(values) != length:
        raise ValueError(name + "_AXIS")
    return tuple(rational(float(value)) if isinstance(value, np.floating)
                 else rational(value) for value in values)


def _transpose_exact(matrix, weights):
    values = [Fraction(0) for _ in range(matrix.shape[1])]
    for row, weight in enumerate(weights):
        if not weight:
            continue
        for cursor in range(matrix.indptr[row], matrix.indptr[row + 1]):
            values[int(matrix.indices[cursor])] += weight * rational(float(matrix.data[cursor]))
    return tuple(values)


def _box_minimum(coefficients, lower, upper):
    total, unbounded = Fraction(0), []
    for column, coefficient in enumerate(coefficients):
        if not coefficient:
            continue
        bound = lower[column] if coefficient > 0 else upper[column]
        if not _finite(bound):
            unbounded.append(column)
        else:
            total += coefficient * rational(float(bound))
    return (None if unbounded else total), unbounded


def verify_primal(snapshot, point):
    """Exact binary64-rational LP replay; integer variables are relaxed here."""
    snapshot.require()
    point = _vector(point, snapshot.matrix.shape[1], "PRIMAL")
    violations = []
    for column, value in enumerate(point):
        if (_finite(snapshot.lower[column]) and value < rational(float(snapshot.lower[column]))
                or _finite(snapshot.upper[column]) and value > rational(float(snapshot.upper[column]))):
            violations.append(("bound", column))
    for row, sense in enumerate(snapshot.senses):
        activity = sum((rational(float(snapshot.matrix.data[cursor])) * point[int(snapshot.matrix.indices[cursor])]
                        for cursor in range(snapshot.matrix.indptr[row], snapshot.matrix.indptr[row + 1])), Fraction(0))
        rhs = rational(float(snapshot.rhs[row]))
        if (sense == "=" and activity != rhs or sense == "<" and activity > rhs
                or sense == ">" and activity < rhs):
            violations.append(("row", row))
    return dict(PASS=not violations, exact=True, violations=violations,
                snapshot_sha256=snapshot.fingerprint(), point_sha256=_hash(point),
                integers_relaxed=True, rounded_or_clipped=False)


def verify_dual(snapshot, row_multipliers, objective_name, point=None):
    """Certify min-LP lower bound including every finite variable bound.

For <= rows Pi<=0; for >= rows Pi>=0.  Residual c-A'Pi need not be zero:
its exact minimum over each variable's ORIGINAL box is part of the bound.
"""
    snapshot.require()
    weights = _vector(row_multipliers, snapshot.matrix.shape[0], "DUAL")
    bad_signs = [row for row, (sense, weight) in enumerate(zip(snapshot.senses, weights))
                 if sense == "<" and weight > 0 or sense == ">" and weight < 0]
    objective = snapshot.objective(objective_name)
    coefficients = objective.coefficients()
    weighted = _transpose_exact(snapshot.matrix, weights)
    residuals = tuple(coefficients.get(column, Fraction(0)) - value
                      for column, value in enumerate(weighted))
    minimum, unbounded = _box_minimum(residuals, snapshot.lower, snapshot.upper)
    rhs = sum((weight * rational(float(value)) for weight, value in zip(weights, snapshot.rhs)), Fraction(0))
    lower_bound = None if minimum is None else rational(objective.constant) + rhs + minimum
    primal = None if point is None else verify_primal(snapshot, point)
    primal_objective = None if point is None else rational(objective.constant) + sum(
        (value * rational(point[column]) for column, value in coefficients.items()), Fraction(0))
    exact_optimal = bool(not bad_signs and not unbounded and primal and primal['PASS']
                         and primal_objective == lower_bound)
    return dict(PASS=not bad_signs and not unbounded, mode="EXACT_NATIVE_DUAL_BOUND",
                snapshot_sha256=snapshot.fingerprint(), multipliers_sha256=_hash(weights),
                objective_name=objective_name, lower_bound=None if lower_bound is None else str(lower_bound),
                residuals=tuple(map(str, residuals)), invalid_row_signs=bad_signs,
                unbounded_residual_columns=unbounded, primal=primal,
                primal_objective=None if primal_objective is None else str(primal_objective),
                exact_LP_optimum=exact_optimal, tolerance_ignored_terms=0,
                LP_PRICING_CLOSED=False, INTEGER_DOMAIN_CLOSURE_PROVEN=False)


def verify_farkas(snapshot, row_multipliers):
    """Check weighted A x <= weighted b against the ORIGINAL bound box.

<= rows require lambda>=0; >= rows lambda<=0.  A strictly positive
min(lambda A x)-lambda b is an exact infeasibility contradiction.
"""
    snapshot.require()
    weights = _vector(row_multipliers, snapshot.matrix.shape[0], "FARKAS")
    bad_signs = [row for row, (sense, weight) in enumerate(zip(snapshot.senses, weights))
                 if sense == "<" and weight < 0 or sense == ">" and weight > 0]
    coefficients = _transpose_exact(snapshot.matrix, weights)
    minimum, unbounded = _box_minimum(coefficients, snapshot.lower, snapshot.upper)
    rhs = sum((weight * rational(float(value)) for weight, value in zip(weights, snapshot.rhs)), Fraction(0))
    margin = None if minimum is None else minimum - rhs
    return dict(PASS=bool(not bad_signs and not unbounded and margin is not None and margin > 0),
                mode="EXACT_NATIVE_FARKAS", snapshot_sha256=snapshot.fingerprint(),
                multipliers_sha256=_hash(weights), minimum=None if minimum is None else str(minimum),
                weighted_rhs=str(rhs), contradiction_margin=None if margin is None else str(margin),
                invalid_row_signs=bad_signs, unbounded_columns=unbounded,
                primitive_coefficients=tuple(map(str, coefficients)), tolerance_ignored_terms=0,
                SCIENTIFIC_DOMAIN_INFEASIBLE=False)


@dataclass(frozen=True)
class NativeExtension:
    """Explicit index injection into an actual ORIGINAL native extension.

Maps are old-index -> extended-index, not row names: native row names can
repeat.  Every new primitive column belongs to an activation block.  A block
can include local state/finish variables and rows beyond one physical option.
"""
    active: LinearSnapshot
    extended: LinearSnapshot
    row_map: tuple
    column_map: tuple
    column_blocks: tuple  # (new extended column index, stable activation block id)

    def verify(self):
        a, b = self.active.require(), self.extended.require()
        rows, columns = a.matrix.shape
        if (len(self.row_map) != rows or len(self.column_map) != columns
                or len(set(self.row_map)) != rows or len(set(self.column_map)) != columns
                or any(type(i) is not int or not 0 <= i < b.matrix.shape[0] for i in self.row_map)
                or any(type(i) is not int or not 0 <= i < b.matrix.shape[1] for i in self.column_map)):
            raise ValueError("EXACT_NATIVE_INDEX_INJECTION_REQUIRED")
        if any(a.senses[i] != b.senses[j] or rational(float(a.rhs[i])) != rational(float(b.rhs[j]))
               for i, j in enumerate(self.row_map)):
            raise ValueError("SHARED_ORIGINAL_ROW_DRIFT")
        for old, new in enumerate(self.column_map):
            if (a.lower[old] != b.lower[new] or a.upper[old] != b.upper[new]
                    or a.vtypes[old] != b.vtypes[new]):
                raise ValueError("SHARED_ORIGINAL_COLUMN_BOUND_OR_TYPE_DRIFT")
        submatrix = b.matrix[list(self.row_map)][:, list(self.column_map)].tocsr()
        difference = a.matrix - submatrix
        difference.eliminate_zeros()
        if difference.nnz:
            raise ValueError("SHARED_ORIGINAL_PRIMITIVE_COEFFICIENT_DRIFT")
        if {o.name for o in a.objectives} != {o.name for o in b.objectives}:
            raise ValueError("ORIGINAL_OBJECTIVE_AXIS_DRIFT")
        for objective in a.objectives:
            full = b.objective(objective.name)
            oldcoeff, newcoeff = objective.coefficients(), full.coefficients()
            if (rational(objective.constant) != rational(full.constant)
                    or any(oldcoeff.get(old, 0) != newcoeff.get(new, 0)
                           for old, new in enumerate(self.column_map))):
                raise ValueError("SHARED_ORIGINAL_OBJECTIVE_DRIFT")
        new_columns = tuple(sorted(set(range(b.matrix.shape[1])) - set(self.column_map)))
        blocks = dict(self.column_blocks)
        if (len(blocks) != len(self.column_blocks) or set(blocks) != set(new_columns)
                or any(type(key) is not int or type(value) is not str or not value for key, value in self.column_blocks)):
            raise ValueError("EVERY_NEW_NATIVE_PRIMITIVE_REQUIRES_ACTIVATION_BLOCK")
        new_rows = tuple(sorted(set(range(b.matrix.shape[0])) - set(self.row_map)))
        return dict(PASS=True, active_snapshot_sha256=a.fingerprint(),
                    extension_snapshot_sha256=b.fingerprint(), new_rows=new_rows,
                    new_columns=new_columns, native_primitive_coverage=len(new_columns),
                    scientific_full_domain_coverage_verified=False,
                    coverage_scope="FINITE_ACTUAL_NATIVE_EXTENSION")


def price_native_extension(extension, row_multipliers, *, mode, objective_name="rho", point=None):
    """Extend actual native dual/ray by zero on new rows, price ALL primitives.

Even a successful finite extension certificate is not promoted to closure of
the scientific domain.  That requires a verified full-native producer, not
enumeration of physical paths or a supplied 'complete' boolean.
"""
    structural = extension.verify()
    weights = _vector(row_multipliers, extension.active.matrix.shape[0], "ROW_MULTIPLIER")
    fullweights = [Fraction(0)] * extension.extended.matrix.shape[0]
    for old, new in enumerate(extension.row_map):
        fullweights[new] = weights[old]
    if mode == "feasibility":
        active = verify_farkas(extension.active, weights)
        full = verify_farkas(extension.extended, fullweights)
        prices = _transpose_exact(extension.extended.matrix, fullweights)
    elif mode == "optimality":
        active = verify_dual(extension.active, weights, objective_name, point)
        lifted = None
        if point is not None:
            lifted = [Fraction(0)] * extension.extended.matrix.shape[1]
            for old, new in enumerate(extension.column_map):
                lifted[new] = rational(point[old])
        full = verify_dual(extension.extended, fullweights, objective_name, lifted)
        prices = tuple(map(Fraction, full['residuals']))
    else:
        raise ValueError("EXACT_FEASIBILITY_OR_OPTIMALITY_MODE_REQUIRED")
    if not active['PASS']:
        raise ValueError("RESTRICTED_NATIVE_CERTIFICATE_NOT_INDEPENDENTLY_VALID")
    blocks, negative = dict(extension.column_blocks), []
    for column in structural['new_columns']:
        price = prices[column]
        minimum, unbounded = _box_minimum((price,), (extension.extended.lower[column],),
                                          (extension.extended.upper[column],))
        zero_in_box = extension.extended.lower[column] <= 0 <= extension.extended.upper[column]
        if not zero_in_box:
            raise ValueError("NEW_PRIMITIVE_ZERO_LIFT_BOUND_UNSUPPORTED")
        if minimum is None or minimum < 0:
            negative.append(dict(column=column, block_id=blocks[column], price=str(price),
                                 box_minimum=None if minimum is None else str(minimum),
                                 bounded=not unbounded))
    negative.sort(key=lambda row: (Fraction(row['price']), row['block_id'], row['column']))
    return dict(structural=structural, active_certificate=active, extension_certificate=full,
                candidates_scanned=len(structural['new_columns']), negative_native_primitives=negative,
                candidate_blocks=sorted({row['block_id'] for row in negative}),
                finite_extension_infeasible=bool(mode == 'feasibility' and full['PASS']),
                finite_extension_LP_closed=bool(mode == 'optimality' and full['exact_LP_optimum']),
                LP_PRICING_CLOSED=False, INTEGER_DOMAIN_CLOSURE_PROVEN=False,
                FULL_DOMAIN_ACCEPTED=False,
                classification="FINITE_NATIVE_EXTENSION_CERTIFICATE_ONLY")


@dataclass(frozen=True)
class NativeLocalBlock:
    """One complete ORIGINAL local LP block, including fractional finishes.

The coupling matrix rows use explicit original global row indices.  Columns
must be exactly the same actual primitive coordinates as the local snapshot.
The caller's producer must separately prove scientific-domain completeness.
"""
    class_id: str
    snapshot: LinearSnapshot
    coupling: object  # CSR: global coupling row x actual local primitive
    global_rows: tuple
    objective_name: str

    def require(self):
        self.snapshot.require()
        if (not sp.isspmatrix_csr(self.coupling) or not self.coupling.has_canonical_format
                or self.coupling.shape != (len(self.global_rows), self.snapshot.matrix.shape[1])
                or len(set(self.global_rows)) != len(self.global_rows)
                or any(type(row) is not int or row < 0 for row in self.global_rows)
                or not np.all(np.isfinite(self.coupling.data))):
            raise ValueError("ORIGINAL_LOCAL_NATIVE_COUPLING_AXIS_REQUIRED")
        self.snapshot.objective(self.objective_name)
        return self


def local_pricing_snapshot(block, global_row_multipliers):
    """Exact local oracle objective c_local-B'Pi, no path LP substitution."""
    block.require()
    weights = tuple(rational(global_row_multipliers[row]) for row in block.global_rows)
    coupling = _transpose_exact(block.coupling, weights)
    original = block.snapshot.objective(block.objective_name)
    coefficients = original.coefficients()
    objective = Objective("native_local_pricing", tuple(
        (column, coefficients.get(column, Fraction(0)) - value)
        for column, value in enumerate(coupling)), original.constant)
    return replace(block.snapshot, objectives=(objective,)).require()


def verify_local_pricing(block, global_row_multipliers, local_row_multipliers, point=None):
    """Independently certify the full native local oracle lower bound.

This covers every fractional native direction of the PROVIDED local block.
The producer, scientific class registry, and global residual certificate must
still be verified before a block collection can close the full scientific LP.
"""
    snapshot = local_pricing_snapshot(block, global_row_multipliers)
    certificate = verify_dual(snapshot, local_row_multipliers, "native_local_pricing", point)
    return dict(class_id=block.class_id, certificate=certificate,
                original_local_snapshot_sha256=block.snapshot.fingerprint(),
                local_pricing_snapshot_sha256=snapshot.fingerprint(),
                actual_native_primitive_columns=block.snapshot.matrix.shape[1],
                fractional_finish_directions_included=True,
                scientific_full_local_domain_producer_verified=False,
                LP_PRICING_CLOSED=False, INTEGER_DOMAIN_CLOSURE_PROVEN=False)


def verify_local_farkas(block, global_ray, local_dual, point=None):
    """Certify min(lambda B z) over the PROVIDED original local LP block.

These lower bounds can prove a full weighted-row contradiction only after
every full-native class block/global box and original coupling are covered.
"""
    block.require()
    weights=tuple(rational(global_ray[row]) for row in block.global_rows)
    coefficients=_transpose_exact(block.coupling,weights)
    objective=Objective('native_local_farkas',tuple(enumerate(coefficients)))
    snapshot=replace(block.snapshot,objectives=(objective,)).require()
    return dict(class_id=block.class_id,certificate=verify_dual(snapshot,local_dual,
        'native_local_farkas',point),actual_native_primitive_columns=block.snapshot.matrix.shape[1],
        original_local_snapshot_sha256=block.snapshot.fingerprint(),
        scientific_full_local_domain_producer_verified=False,
        SCIENTIFIC_DOMAIN_INFEASIBLE=False,LP_PRICING_CLOSED=False)


@dataclass(frozen=True)
class CouplingRows:
    """Explicit ORIGINAL row indices captured at native model construction.

Keys are ('GPU', site, slot), ('RUNTIME', site, slot), ('WAN', link, slot),
('ACTIVE', '', slot). Duplicate native row names are never used as identity.
"""
    rows: tuple
    snapshot_sha256: str
    byte_scale: float = 1.

    def require(self, snapshot):
        if snapshot.fingerprint() != self.snapshot_sha256:
            raise ValueError("COUPLING_ROWS_NATIVE_MATRIX_DRIFT")
        mapping = dict(self.rows)
        if (len(mapping) != len(self.rows) or len(set(mapping.values())) != len(mapping)
                or any(type(row) is not int or not 0 <= row < snapshot.matrix.shape[0]
                       or len(key) != 3 or key[0] not in ('GPU', 'RUNTIME', 'WAN', 'ACTIVE')
                       for key, row in self.rows)):
            raise ValueError("EXPLICIT_UNIQUE_NATIVE_COUPLING_ROWS_REQUIRED")
        if self.byte_scale <= 0 or self.byte_scale != 2. ** round(math.log2(self.byte_scale)):
            raise ValueError("EXACT_POWER_OF_TWO_WAN_SCALE_REQUIRED")
        for key, row in self.rows:
            expected = '=' if key[0] in ('GPU', 'RUNTIME') else '<'
            if snapshot.senses[row] != expected:
                raise ValueError("ORIGINAL_COUPLING_ROW_SENSE_DRIFT")
        return mapping


def physical_option_coefficients(option, job, raw, bundle, coupling_rows):
    """Unchanged native physical coupling values; Runtime preserves order."""
    coefficients = {}
    for site, start, end in option.segments:
        for slot in range(start, end):
            key = ('GPU', site, slot)
            if key not in coupling_rows:
                raise ValueError("MISSING_ORIGINAL_GPU_COUPLING_ROW")
            coefficients[key] = coefficients.get(key, Fraction(0)) - job.gpu
    site, _, end = option.segments[-1]
    adjusted = int(raw['risk_nominal_completion_issue_slot'] + end - raw['reference_end'])
    kernel = bundle['runtime_survival_kernel']
    for slot in range(24, 120):
        lag = slot - adjusted
        if 0 <= lag < len(kernel):
            key = ('RUNTIME', site, slot)
            if key not in coupling_rows:
                raise ValueError("MISSING_ORIGINAL_RUNTIME_COUPLING_ROW")
            # Identical binary64 operation order to risk_exposure then gamma.
            value = bundle['runtime_reserve_gamma'] * (job.gpu * float(kernel[lag]))
            coefficients[key] = -Fraction(value)
    if option.migrated:
        for link, slot, amount in option.wan:
            key = ('WAN', link, slot)
            if key not in coupling_rows:
                raise ValueError("MISSING_ORIGINAL_WAN_COUPLING_ROW")
            coefficients[key] = coefficients.get(key, Fraction(0)) + Fraction(amount)
        for slot in range(option.transfer_start, option.transfer_end):
            key = ('ACTIVE', '', slot)
            if key not in coupling_rows:
                raise ValueError("MISSING_ORIGINAL_ACTIVE_COUPLING_ROW")
            coefficients[key] = Fraction(1)
    return coefficients


def score_physical_option(option, job, bound, resources, domain, raw, bundle,
                          coupling, snapshot, row_multipliers, *, class_id,
                          mode, objective_name='rho', normalization_price=0):
    """Useful ORIGINAL coupling pricing witness, explicitly NOT LP closure.

The normalization potential must come from the original active block dual.
For mixed-flow classes a negative physical witness can guide activation;
nonnegative witnesses cannot exclude omitted fractional native directions.
"""
    if not contains(job, bound, resources, domain, option):
        raise ValueError("ONLY_FULL_ATTRIBUTE_HARD_VALID_OPTIONS_MAY_BE_PRICED")
    rows = coupling.require(snapshot)
    weights = _vector(row_multipliers, snapshot.matrix.shape[0], "ROW_MULTIPLIER")
    values = physical_option_coefficients(option, job, raw, bundle, rows)
    weighted = sum((weights[rows[key]] * (value / Fraction(coupling.byte_scale)
                   if key[0] == 'WAN' else value) for key, value in values.items()), Fraction(0))
    objectives = dict(rho=0, migration_count=int(option.migrated),
                      shift_magnitude=abs(option.start - job.reference_start),
                      prestart_relocation=int(option.initial_site != job.reference_site))
    if mode == 'feasibility':
        price = weighted + rational(normalization_price)
    elif mode == 'optimality' and objective_name in objectives:
        price = Fraction(objectives[objective_name]) - weighted - rational(normalization_price)
    else:
        raise ValueError("ORIGINAL_OBJECTIVE_AND_PRICING_MODE_REQUIRED")
    candidate_id = digest((class_id, option))
    return dict(candidate_id=candidate_id, class_id=class_id, option=option,
                price=str(price), negative=price < 0, mode=mode,
                objective_name=objective_name, original_snapshot_sha256=coupling.snapshot_sha256,
                coupling_row_coefficients=tuple((rows[key], str(value / Fraction(coupling.byte_scale)
                    if key[0] == 'WAN' else value)) for key, value in sorted(values.items())),
                scientifically_hard_valid=True, permanent_cut=False,
                classification='HARD_VALID_PHYSICAL_COUPLING_PRICING_WITNESS',
                exact_native_primitive_reduced_cost=False,
                native_fractional_direction_coverage_verified=False,
                LP_PRICING_CLOSED=False, INTEGER_DOMAIN_CLOSURE_PROVEN=False)


def select_batch(scores, *, batch_size, negative_threshold=0):
    """Deterministic bounded top-K, without deleting any unselected option."""
    if type(batch_size) is not int or batch_size < 1 or rational(negative_threshold) > 0:
        raise ValueError("PREREGISTERED_POSITIVE_BATCH_AND_NONPOSITIVE_THRESHOLD_REQUIRED")
    scores = list(scores)
    ids = [score['candidate_id'] for score in scores]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_PRICING_CANDIDATE_ID")
    negative = sorted((score for score in scores if Fraction(score['price']) < rational(negative_threshold)),
                      key=lambda score: (Fraction(score['price']), score['class_id'], score['candidate_id']))
    selected = negative[:batch_size]
    prices = sorted(Fraction(score['price']) for score in selected)
    median = None if not prices else prices[len(prices)//2] if len(prices) % 2 else (
        prices[len(prices)//2-1] + prices[len(prices)//2]) / 2
    return dict(selected=selected, candidates_scanned=len(scores),
                negative_price_candidates=len(negative), candidates_activated=len(selected),
                minimum_price=None if not scores else str(min(Fraction(score['price']) for score in scores)),
                median_activated_price=None if median is None else str(median),
                skipped_small_negative=sum(rational(negative_threshold) <= Fraction(score['price']) < 0 for score in scores),
                LP_PRICING_CLOSED=False, omitted_candidates_remain_scientific=True)


def require_milp_pricing_gate(receipt):
    """Section 13: finite/path scans and unproven closures cannot launch MIP."""
    if not (receipt.get('LP_PRICING_CLOSED') is True
            and receipt.get('ACTIVE_DOMAIN_FEASIBLE') is True
            and receipt.get('native_full_direction_coverage_verified') is True
            and receipt.get('independent_full_native_producer_verified') is True
            and len(receipt.get('full_native_certificate_sha256', '')) == 64):
        raise PermissionError("MILP_BLOCKED_UNTIL_INDEPENDENT_FULL_NATIVE_LP_PRICING_CLOSURE")
    return True


def _native_coupling(backend):
    rows = []
    for (family, key), row in backend.row_keys.items():
        if family == 'ACTIVE':
            canonical = ('ACTIVE', '', key)
        else:
            canonical = ('RUNTIME' if family == 'Runtime' else family, *key)
        rows.append((canonical, int(row)))
    from v42_sparse.config import settings
    scale = 2. ** 20 if settings('F2-CRA')['scale_wan'] else 1.
    return CouplingRows(tuple(sorted(rows)), backend.current.fingerprint(), scale)


def _normalization_rows(backend, column_matrix, class_id):
    """Find normalization by actual primitive support/RHS, never row names."""
    snapshot = backend.current
    units = [unit for unit in backend.descriptor['units'] if unit['class_key'] == class_id]
    counts = [unit for unit in units if not unit['optional']]
    if len(counts) != 1:
        return (), False, None
    unit = counts[0]
    support = {}
    for expression in unit['v']['y'].values():
        if expression[0] != 'v':
            return (), False, None
        support[int(expression[1])] = Fraction(1)
    if unit['stay_count']:
        for lane in units:
            if lane['optional']:
                selected = lane['v'].get('migration_selected', {}).get('selected')
                if selected is None or selected[0] != 'v':
                    return (), False, None
                support[int(selected[1])] = Fraction(1)
        rhs = len(backend.data[7]['classes'][class_id])
    else:
        rhs = 1
    if not support:
        return (), False, None
    first = min(support)
    possible = column_matrix.indices[column_matrix.indptr[first]:column_matrix.indptr[first+1]]
    matches = []
    for row in possible:
        row = int(row)
        if snapshot.senses[row] != '=' or rational(float(snapshot.rhs[row])) != rhs:
            continue
        actual = {int(snapshot.matrix.indices[cursor]): rational(float(snapshot.matrix.data[cursor]))
                  for cursor in range(snapshot.matrix.indptr[row], snapshot.matrix.indptr[row+1])
                  if snapshot.matrix.data[cursor]}
        if actual == support:
            matches.append(row)
    return tuple(matches), bool(matches), unit


def _histogram_identity(backend, pool, unit, normalization, coupling, rows, column_matrix):
    """Independently match an existing direct Y column to native coefficients.

Mixed event-flow starts have local balance coefficients and therefore fail
this identity. New optional-lane directions created during activation remain
outside this individual STAY-column identity and outside closure coverage.
"""
    if unit is None or pool.retained_mixed_flow or not normalization:
        return False
    items = unit['v']['y']
    if not items:
        return False
    (site, start), expression = next(iter(sorted(items.items())))
    if expression[0] != 'v' or (start, site) not in pool.active:
        return False
    option = pool.option((start, site))
    coefficients = physical_option_coefficients(option, pool.job,
        backend.data[4][pool.representative], backend.data[0], rows)
    predicted = {rows[key]: value / Fraction(coupling.byte_scale) if key[0] == 'WAN' else value
                 for key, value in coefficients.items() if value}
    for row in normalization:
        predicted[row] = Fraction(1)
    column = int(expression[1])
    actual = {int(column_matrix.indices[cursor]): rational(float(column_matrix.data[cursor]))
              for cursor in range(column_matrix.indptr[column], column_matrix.indptr[column+1])
              if column_matrix.data[cursor]}
    if actual != predicted:
        return False
    for name, coefficient in dict(rho=0, migration_count=0,
        shift_magnitude=abs(start-pool.job.reference_start),
        prestart_relocation=int(site!=pool.job.reference_site)).items():
        if backend.current.objective(name).coefficients().get(column, 0) != coefficient:
            return False
    return True


def _migration_prefix(pool, limit, offset):
    """Jump into compact block/tau indices; never enumerate a huge skipped pool."""
    domain = pool.physical_domain
    total = pool.physical_count
    if not total or not limit:
        return
    limit = min(limit, total)
    offset %= total
    # At most two deterministic intervals provide wraparound; skip counts via
    # block lengths rather than constructing preceding physical Option objects.
    intervals = ((offset, min(total, offset+limit)), (0, max(0, offset+limit-total)))
    for begin, finish in intervals:
        if begin >= finish:
            continue
        cursor = 0
        for start, source, cp, physical, dest, gpu, taus in domain.blocks:
            end = cursor + len(taus)
            lo, hi = max(begin, cursor)-cursor, min(finish, end)-cursor
            if lo < hi:
                for tau in taus[lo:hi]:
                    key = (start, source, cp, physical, dest, tau)
                    if key not in pool.active_keys:
                        transfer = domain.cache.transfer(source, dest, gpu, tau)
                        from v42_job_capability import Option
                        yield Option(start, source, ((source,start,cp),
                            (dest,transfer.restart,transfer.restart+domain.duration-(cp-start))),
                            cp,physical,dest,tau,transfer.end,transfer.restart,transfer.wan)
            cursor = end
            if cursor >= finish:
                break


def score_active_pools(backend, build, mode, iteration):
    """Production adapter: exact coupling scores, deterministic bounded batches.

All inactive STAY are scanned. Migration uses the preregistered bounded
compact prefix. Existing direct histogram columns are independently matched;
singleton mixed and migration options remain witnesses, not LP certificates.
"""
    mode = mode.lower() if isinstance(mode,str) else mode
    if mode not in ('feasibility', 'optimality') or type(iteration) is not int or iteration < 0:
        raise ValueError('NATIVE_LP_PRICING_MODE_AND_ITERATION_REQUIRED')
    snapshot = backend.current.require()
    multipliers = tuple(build.model.getAttr('FarkasDual' if mode=='feasibility' else 'Pi'))
    weights = _vector(multipliers, snapshot.matrix.shape[0], 'NATIVE_ROW_MULTIPLIER')
    current_evidence = (verify_farkas(snapshot, weights) if mode=='feasibility'
                        else verify_dual(snapshot, weights, 'rho'))
    # The independent verifier covers every column, but the receipt should not
    # serialize a second enormous inactive/active primitive vector.
    for vector_key in ('residuals','primitive_coefficients'):
        values=current_evidence.pop(vector_key,None)
        if values is not None:
            current_evidence[vector_key+'_sha256']=_hash(values)
            current_evidence[vector_key+'_count']=len(values)
    coupling = _native_coupling(backend)
    rows = coupling.require(snapshot)
    columns = snapshot.matrix.tocsc()
    pools = backend.ledger['stay_pools']
    normalizers, identities, potentials = {}, {}, {}
    for class_id, pool in sorted(pools.items()):
        normalizers[class_id], _, unit = _normalization_rows(backend, columns, class_id)
        identities[class_id] = _histogram_identity(backend,pool,unit,normalizers[class_id],coupling,rows,columns)
        potentials[class_id] = sum((weights[row] for row in normalizers[class_id]), Fraction(0))
    # Exact GPU dual prefix sums avoid a repeated occupancy loop per STAY.
    gpu_prefix = {}
    for site in backend.data[3].capacities:
        slots = sorted(key[2] for key in rows if key[0]=='GPU' and key[1]==site)
        if slots and slots == list(range(slots[-1]+1)):
            prefix=[Fraction(0)]
            for slot in slots:
                prefix.append(prefix[-1]+weights[rows['GPU',site,slot]])
            gpu_prefix[site]=prefix
    runtime_cache = {}
    def runtime_weight(pool, site, end):
        key = pool.class_id,site,end
        if key not in runtime_cache:
            raw = backend.data[4][pool.representative]
            adjusted = int(raw['risk_nominal_completion_issue_slot']+end-raw['reference_end'])
            bundle=backend.data[0];kernel=bundle['runtime_survival_kernel'];value=Fraction(0)
            for slot in range(24,120):
                lag=slot-adjusted
                if 0<=lag<len(kernel):
                    row=rows['RUNTIME',site,slot]
                    if weights[row]:
                        coefficient=bundle['runtime_reserve_gamma']*(pool.job.gpu*float(kernel[lag]))
                        value -= weights[row]*Fraction(coefficient)
            runtime_cache[key]=value
        return runtime_cache[key]
    scores=[];stay_scanned=0
    for class_id,pool in sorted(pools.items()):
        for start,site in pool.keys():
            option=pool.option((start,site));end=start+pool.job.service_slots
            if site not in gpu_prefix or start<0 or end>=len(gpu_prefix[site]):
                raise ValueError('COMPLETE_ORIGINAL_GPU_PREFIX_REQUIRED')
            weighted=-pool.job.gpu*(gpu_prefix[site][end]-gpu_prefix[site][start])+runtime_weight(pool,site,end)
            price=weighted+potentials[class_id] if mode=='feasibility' else -weighted-potentials[class_id]
            scores.append(dict(candidate_id=digest((class_id,option)),class_id=class_id,option=option,
                price=str(price),kind='STAY',negative=price<0,
                exact_native_primitive_reduced_cost=identities[class_id],
                normalization_rows=normalizers[class_id],
                classification='VERIFIED_DIRECT_HISTOGRAM_STAY_COLUMN' if identities[class_id]
                    else 'HARD_VALID_PHYSICAL_COUPLING_PRICING_WITNESS'))
            stay_scanned+=1
    policy=backend.policy
    migration_limit=int(policy.get('pricing',{}).get('migration_scan_limit',policy.get('migration_scan_limit',4096)))
    migration_scanned=0
    migration_pools=backend.ledger['migration_pools']
    eligible=[key for key,pool in sorted(migration_pools.items()) if pool.inactive_count]
    if eligible:
        quota=max(1,math.ceil(migration_limit/len(eligible)))
        for class_id in eligible:
            if migration_scanned>=migration_limit:
                break
            pool=pools[class_id];mpool=migration_pools[class_id]
            for option in _migration_prefix(mpool,min(quota,migration_limit-migration_scanned),iteration*quota):
                values=physical_option_coefficients(option,pool.job,backend.data[4][pool.representative],backend.data[0],rows)
                weighted=sum((weights[rows[key]]*(value/Fraction(coupling.byte_scale) if key[0]=='WAN' else value)
                              for key,value in values.items()),Fraction(0))
                price=weighted+potentials[class_id] if mode=='feasibility' else -weighted-potentials[class_id]
                scores.append(dict(candidate_id=digest((class_id,option)),class_id=class_id,option=option,
                    price=str(price),kind='MIGRATION',negative=price<0,
                    exact_native_primitive_reduced_cost=False,normalization_rows=normalizers[class_id],
                    classification='HARD_VALID_PHYSICAL_COUPLING_PRICING_WITNESS'))
                migration_scanned+=1
    batch_policy=policy.get('batch',{})
    initial=int(batch_policy.get('initial',64));minimum=int(batch_policy.get('minimum',32));maximum=int(batch_policy.get('maximum',256))
    previous=getattr(backend,'_fast_previous_pricing_density',None)
    size=getattr(backend,'_fast_previous_batch_size',initial)
    if previous is not None:
        if previous>rational(batch_policy.get('high_density_threshold',.5)):
            size=min(maximum,size*2)
        elif previous<rational(batch_policy.get('low_density_threshold',.1)):
            size=max(minimum,size//2)
    batch=select_batch(scores,batch_size=size)
    backend._fast_previous_batch_size=size
    backend._fast_previous_pricing_density=Fraction(batch['negative_price_candidates'],max(1,len(scores)))
    max_iterations=int(policy.get('max_pricing_iterations',4))
    eligible_activation=not(mode=='feasibility' and not current_evidence['PASS']) and iteration<max_iterations-1
    selected=batch['selected'] if eligible_activation else []
    selections={}
    for score in selected:
        selections.setdefault(score['class_id'],[]).append(score['option'])
    selections={key:tuple(value) for key,value in sorted(selections.items())}
    physical_inactive_migration=sum(pool.inactive_count for pool in migration_pools.values())
    certificate=dict(PASS=True,score_arithmetic_exact=True,
        original_snapshot_sha256=coupling.snapshot_sha256,
        lp_snapshot_sha256=coupling.snapshot_sha256,
        native_row_multipliers_sha256=_hash(weights),native_certificate=current_evidence,
        exhaustive_inactive_STAY_scanned=stay_scanned==sum(pool.inactive_count for pool in pools.values()),
        migration_candidates_scanned=migration_scanned,migration_candidates_unscanned=max(0,physical_inactive_migration-migration_scanned),
        exhaustive_migration_scanned=migration_scanned==physical_inactive_migration,
        verified_histogram_class_columns=sum(identities.values()),
        actual_histogram_column_identities=identities,
        mixed_fractional_finish_native_direction_coverage=False,
        native_full_direction_coverage_verified=False,independent_full_native_producer_verified=False,
        LP_PRICING_CLOSED=False,INTEGER_DOMAIN_CLOSURE_PROVEN=False,FULL_DOMAIN_ACCEPTED=False,
        infeasibility_is_restricted_only=True,
        limitation='Physical option witnesses do not span singleton mixed native LP directions; bounded migration scan is incomplete.')
    native_prices=[Fraction(score['price']) for score in scores if score['exact_native_primitive_reduced_cost']]
    activated_native_prices=sorted(Fraction(score['price']) for score in selected
                                   if score['exact_native_primitive_reduced_cost'])
    native_median=(None if not activated_native_prices else
        activated_native_prices[len(activated_native_prices)//2] if len(activated_native_prices)%2 else
        (activated_native_prices[len(activated_native_prices)//2-1]+activated_native_prices[len(activated_native_prices)//2])/2)
    trace=dict(candidates_scanned=len(scores),inactive_STAY_scanned=stay_scanned,
        migration_candidates_scanned=migration_scanned,improving_candidates=batch['negative_price_candidates'],
        improving_candidates_semantics='negative native histogram columns plus negative coupling ranking witnesses; latter do not guarantee native LP improvement',
        negative_verified_native_histogram_columns=sum(price<0 for price in native_prices),
        candidates_activated=len(selected),minimum_reduced_cost=None if not native_prices else str(min(native_prices)),
        median_activated_reduced_cost=None if native_median is None else str(native_median),
        minimum_coupling_pricing_score=batch['minimum_price'],
        median_activated_coupling_pricing_score=batch['median_activated_price'] if selected else None,
        reduced_cost_metric_scope='independently matched direct native histogram STAY columns only',
        batch_size=size,rows_added=None,cols_added=None,nnz_added=None,
        last_iteration_activation_prohibited=iteration>=max_iterations-1,
        skipped_small_negative=batch['skipped_small_negative'],native_full_direction_coverage_verified=False)
    return dict(selections=selections,candidates_activated=len(selected),selected_scores=selected,
        certificate=certificate,trace=trace,iteration=iteration,mode=mode,
        classification='CERTIFIABLE_PHYSICAL_ACTIVATION_NATIVE_LP_CLOSURE_UNRESOLVED',
        LP_PRICING_CLOSED=False,native_full_direction_coverage_verified=False)


def verify_active_pool_scores(backend, build, pricing, mode):
    """Independent selected-option coefficient replay against current native axes."""
    mode=mode.lower() if isinstance(mode,str) else mode
    snapshot=backend.current;coupling=_native_coupling(backend);rows=coupling.require(snapshot)
    multipliers=tuple(build.model.getAttr('FarkasDual' if mode=='feasibility' else 'Pi'))
    weights=_vector(multipliers,snapshot.matrix.shape[0],'NATIVE_ROW_MULTIPLIER')
    certificate=pricing['certificate'];errors=[]
    if (str(pricing.get('mode')).lower()!=mode or certificate['lp_snapshot_sha256']!=coupling.snapshot_sha256
            or certificate['native_row_multipliers_sha256']!=_hash(weights)):
        errors.append('NATIVE_MATRIX_OR_MULTIPLIER_IDENTITY_DRIFT')
    selected=pricing.get('selected_scores',[])
    columns=snapshot.matrix.tocsc();normalizers={};identities={}
    for class_id in sorted({score['class_id'] for score in selected}):
        pool=backend.ledger['stay_pools'][class_id]
        normalizers[class_id],_,unit=_normalization_rows(backend,columns,class_id)
        identities[class_id]=_histogram_identity(backend,pool,unit,normalizers[class_id],coupling,rows,columns)
    expected={}
    for score in selected:
        class_id=score['class_id'];pool=backend.ledger['stay_pools'][class_id]
        option=score['option'];job=pool.job;uid=pool.representative
        if tuple(score['normalization_rows'])!=normalizers[class_id]:
            errors.append('ORIGINAL_NATIVE_NORMALIZATION_REPLAY_MISMATCH')
        if not contains(job,backend.data[2][uid],backend.data[3],backend.domains[uid],option):
            errors.append('ACTIVATION_NOT_FULL_ATTRIBUTE_HARD_VALID');continue
        if (not option.migrated and (option.start,option.initial_site) in pool.active
                or option.migrated and (option.start,option.initial_site,option.checkpoint,
                    option.physical_checkpoint_seconds,option.destination,option.transfer_start)
                    in backend.ledger['migration_pools'][class_id].active_keys):
            errors.append('ACTIVATION_ALREADY_ACTIVE')
        values=physical_option_coefficients(option,job,backend.data[4][uid],backend.data[0],rows)
        # Independent inherited Runtime producer, preserving binary64 bits.
        from v42_final.reserve import risk_exposure
        site,_,end=option.segments[-1];raw=backend.data[4][uid];bundle=backend.data[0]
        adjusted=int(raw['risk_nominal_completion_issue_slot']+end-raw['reference_end'])
        independent={('RUNTIME',site,slot):-Fraction(bundle['runtime_reserve_gamma']*value)
            for (site,slot),value in risk_exposure(job.gpu,adjusted,site,
                bundle['runtime_survival_kernel'],range(24,120)).items()}
        if independent!={key:value for key,value in values.items() if key[0]=='RUNTIME'}:
            errors.append('INHERITED_RUNTIME_COEFFICIENT_BITWISE_DRIFT')
        weighted=sum((weights[rows[key]]*(value/Fraction(coupling.byte_scale) if key[0]=='WAN' else value)
                      for key,value in values.items()),Fraction(0))
        potential=sum((weights[row] for row in score['normalization_rows']),Fraction(0))
        price=weighted+potential if mode=='feasibility' else -weighted-potential
        if str(price)!=score['price'] or price>=0 or digest((class_id,option))!=score['candidate_id']:
            errors.append('ORIGINAL_ROW_PRICE_REPLAY_MISMATCH')
        if score['exact_native_primitive_reduced_cost']!=(not option.migrated and identities[class_id]):
            errors.append('NATIVE_PRIMITIVE_REPRESENTATION_IDENTITY_DRIFT')
        expected.setdefault(class_id,[]).append(option)
    expected={key:tuple(value) for key,value in sorted(expected.items())}
    if expected!=pricing.get('selections') or len(selected)!=pricing.get('candidates_activated'):
        errors.append('ACTIVATION_BATCH_IDENTITY_DRIFT')
    return dict(PASS=not errors,activated_candidates_hard_valid=not errors,
        independently_verified=True,errors=errors,lp_snapshot_sha256=coupling.snapshot_sha256,
        pricing_verification_sha256=_hash((certificate,tuple(score['candidate_id'] for score in selected))),
        candidate_coefficients_replayed=len(selected),native_full_direction_coverage_verified=False,
        LP_PRICING_CLOSED=False,INTEGER_DOMAIN_CLOSURE_PROVEN=False,FULL_DOMAIN_ACCEPTED=False)


def parse_baseline_log(log_text, pass_result=None):
    """Read-only native log metrics; different clocks retain their semantics."""
    def match(pattern, casts):
        found = list(re.finditer(pattern, log_text, re.MULTILINE))
        return None if not found else tuple(cast(value) for cast, value in zip(casts, found[-1].groups()))
    raw = match(r'Optimize a model with (\d+) rows, (\d+) columns and (\d+) nonzeros', (int,int,int))
    presolved = match(r'^Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros', (int,int,int))
    root = match(r'^Root relaxation presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros', (int,int,int))
    ordering = match(r'^Ordering time: ([\d.]+)s', (float,))
    factor = match(r'^\s*Factor NZ\s*:\s*([\d.eE+]+) \(roughly ([\d.]+) GB of memory\)', (float,float))
    barrier = match(r'^Barrier performed (\d+) iterations in ([\d.]+) seconds \(([\d.]+) work units\)', (int,float,float))
    root_time = match(r'^Root relaxation: ([^,]+), \d+ iterations, ([\d.]+) seconds \(([\d.]+) work units\)', (str,float,float))
    explored = match(r'^Explored (\d+) nodes .* in ([\d.]+) seconds \(([\d.]+) work units\)', (int,float,float))
    iterations = []
    for line in log_text.splitlines():
        found = re.match(r'^\s*(\d+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+(\d+)s\s*$',line)
        if found:
            iteration, primal, dual, pres, dres, compl, elapsed = found.groups()
            iterations.append(dict(iteration=int(iteration), primal=float(primal), dual=float(dual),
                primal_residual=float(pres), dual_residual=float(dres), complementarity=float(compl),
                log_elapsed_seconds=int(elapsed)))
    timed_out = bool(root_time and root_time[0] == 'time limit')
    result = dict(classification='COMPLETE_STAY_ALL_ACTIVE_ROOT_TIMEOUT' if timed_out else 'BASELINE_NATIVE_STATUS_REQUIRES_REVIEW',
        raw_rows=None if raw is None else raw[0],raw_columns=None if raw is None else raw[1],raw_nnz=None if raw is None else raw[2],
        presolved=None if presolved is None else dict(zip(('rows','columns','nnz'),presolved)),
        root_relaxation_presolved=None if root is None else dict(zip(('rows','columns','nnz'),root)),
        ordering_seconds=None if ordering is None else ordering[0],
        factor_nnz_rounded_from_log=None if factor is None else factor[0],
        factor_memory_GB_approximate=None if factor is None else factor[1],
        barrier_iterations=None if barrier is None else barrier[0],
        barrier_summary_seconds=None if barrier is None else barrier[1],
        barrier_summary_work=None if barrier is None else barrier[2],
        root_relaxation_summary_status=None if root_time is None else root_time[0],
        root_relaxation_summary_seconds=None if root_time is None else root_time[1],
        root_relaxation_summary_work=None if root_time is None else root_time[2],
        explored_summary_seconds=None if explored is None else explored[1],
        explored_summary_work=None if explored is None else explored[2],
        barrier_log_iterations=iterations,root_completed=False if timed_out else None,
        infeasible=False if timed_out else None,scientific_domain_fail=False if timed_out else None,
        crossover_seconds=None, first_incumbent_seconds=None,
        clock_semantics='Each native log summary and Runtime receipt retained separately; no subtraction defines a new timer.',
        optimizer_calls=0)
    if pass_result is not None:
        result.update(native_Runtime_seconds=pass_result.get('native_seconds'),
                      native_Work=pass_result.get('Work'),native_status=pass_result.get('status'),
                      native_incumbent=pass_result.get('objective'),
                      active_domain_bound=pass_result.get('active_domain_global_bound'))
    return result

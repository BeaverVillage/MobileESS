"""Proved whole-gang count rounding on actual known-GPU binding rows.

Only accepted histogram scopes participate. The source matrix, descriptor and
integer incidence are checked before a cut is formed. Mixed singleton flow
starts are deliberately excluded. This changes the LP relaxation, while
preserving every integer feasible schedule and all scientific objective values.
"""
from fractions import Fraction
import hashlib
import json

import numpy as np
import scipy.sparse as sp

from .lexstage import LinearSnapshot, exact_gpu_count_rounding


def _integer(value):
    exact = Fraction(float(value))
    return int(exact) if exact.denominator == 1 else None


def _payload_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _require_zero_map(original, current, mapping):
    original.require(); current.require()
    mapping = np.asarray(mapping)
    if (mapping.dtype.kind not in "iu" or mapping.ndim != 1
            or len(mapping) != original.matrix.shape[1] or np.any(mapping < -1)
            or sorted(int(value) for value in mapping if value >= 0) != list(range(current.matrix.shape[1]))):
        raise ValueError("EXACT_ZERO_COLUMN_MAP_REQUIRED_FOR_STRENGTHENING")
    retained = np.flatnonzero(mapping >= 0)
    for old, new in ((original.lower, current.lower), (original.upper, current.upper),
                     (original.vtypes, current.vtypes)):
        if not np.array_equal(old[retained], new[mapping[retained]]):
            raise ValueError("UNCHANGED_RETAINED_COLUMN_BOUNDS_TYPES_REQUIRED")
    if tuple(o.name for o in original.objectives) != tuple(o.name for o in current.objectives):
        raise ValueError("UNCHANGED_PROJECTED_SCIENTIFIC_OBJECTIVES_REQUIRED")
    for old, new in zip(original.objectives, current.objectives):
        expected = {int(mapping[column]): coefficient for column, coefficient in old.coefficients().items()
                    if mapping[column] >= 0}
        if expected != new.coefficients() or old.constant != new.constant:
            raise ValueError("UNCHANGED_PROJECTED_SCIENTIFIC_OBJECTIVES_REQUIRED")
    return mapping


def _binding_matches(original, current, original_row, current_row, mapping):
    """Check the actual capacity equation survives on current column axes."""
    if (not 0 <= current_row < current.matrix.shape[0] or current.senses[current_row] != "="
            or current.rhs[current_row] != original.rhs[original_row]):
        return False
    lo, hi = original.matrix.indptr[original_row:original_row + 2]
    expected = sorted((int(mapping[column]), float(value))
                      for column, value in zip(original.matrix.indices[lo:hi], original.matrix.data[lo:hi])
                      if mapping[column] >= 0)
    lo, hi = current.matrix.indptr[current_row:current_row + 2]
    actual = list(zip(current.matrix.indices[lo:hi], current.matrix.data[lo:hi]))
    return actual == expected


def strengthen_histogram_capacity(original, current, descriptor, data, mapping):
    """Return an augmented snapshot and complete independently checkable proof.

    mapping is the exact retained-column/zero-deletion map from original to
    current coordinates. Rows refer to the original native matrix. Capacity is
    the original known-variable upper bound; fixed occupancy is the actual
    original binding RHS, which includes all immutable fixed-history constants.
    """
    mapping = _require_zero_map(original, current, mapping)
    _, jobs, _, resources, _, graphs, _, _ = data
    eligible, excluded_units = {}, []
    for unit in descriptor["units"]:
        uid = unit["uid"]; job = jobs[uid]
        if (unit.get("optional") or unit.get("retained_mixed_flow")
                or not (unit.get("stay_count") or not graphs[uid].events["w"])):
            excluded_units.append(unit.get("id", uid)); continue
        if (not isinstance(job.gpu, int) or isinstance(job.gpu, bool) or job.gpu <= 0
                or not isinstance(job.service_slots, int) or isinstance(job.service_slots, bool)
                or job.service_slots <= 0):
            raise ValueError("POSITIVE_INTEGER_WHOLE_GANG_GPU_AND_DURATION_REQUIRED")
        for (site, start), encoded in unit["v"]["y"].items():
            if encoded[0] != "v":
                continue  # Immutable fixed histories are already in row RHS.
            column = int(encoded[1])
            if (not 0 <= column < original.matrix.shape[1]
                    or original.vtypes[column] not in ("B", "I") or original.lower[column] < 0):
                raise ValueError("INTEGER_HISTOGRAM_START_COLUMN_REQUIRED")
            effect = (site, int(start), job.service_slots, job.gpu)
            if column in eligible and eligible[column] != effect:
                raise ValueError("AMBIGUOUS_HISTOGRAM_COLUMN_INCIDENCE")
            eligible[column] = effect
    axes = []
    for key, encoded in sorted(descriptor["known"].items()):
        if encoded[0] != "v":
            raise ValueError("ORIGINAL_KNOWN_GPU_VARIABLE_AXIS_REQUIRED")
        if not 0 <= int(encoded[1]) < original.matrix.shape[1]:
            raise ValueError("ORIGINAL_KNOWN_GPU_VARIABLE_AXIS_REQUIRED")
        if mapping[int(encoded[1])] >= 0:
            axes.append((key, int(encoded[1])))
    if len({column for _, column in axes}) != len(axes):
        raise ValueError("AMBIGUOUS_KNOWN_GPU_AXIS")
    # Slice known columns before CSC conversion: do not copy the entire huge
    # migration matrix merely to discover a few physical binding rows.
    selected = original.matrix[:, [column for _, column in axes]].tocsc()
    current_selected = current.matrix[:, [int(mapping[column]) for _, column in axes]].tocsc()
    cuts, ambiguity = {}, []
    matrix = original.matrix
    for axis, ((site, slot), known) in enumerate(axes):
        capacity = _integer(original.upper[known])
        if capacity is None or capacity != resources.capacities.get(site) or original.lower[known] < 0:
            raise ValueError("UNCHANGED_KNOWN_GPU_CAPACITY_REQUIRED")
        candidates = []
        for row in selected.indices[selected.indptr[axis]:selected.indptr[axis + 1]]:
            row = int(row)
            if original.senses[row] != "=":
                continue
            lo, hi = matrix.indptr[row:row + 2]
            columns, values = matrix.indices[lo:hi], matrix.data[lo:hi]
            known_values = values[columns == known]
            other = columns != known
            fixed = _integer(original.rhs[row])
            if (len(known_values) != 1 or known_values[0] != 1 or fixed is None or not 0 <= fixed <= capacity
                    or np.any(values[other] > 0) or np.any(original.lower[columns[other]] < 0)):
                continue
            group = []
            for column, value in zip(columns, values):
                column = int(column)
                effect = eligible.get(column)
                if effect is None or mapping[column] < 0:
                    continue
                location, start, duration, gpu = effect
                if location != site or not start <= slot < start + duration:
                    raise ValueError("ACTUAL_GPU_BINDING_HISTOGRAM_INCIDENCE_DRIFT")
                if value != -gpu:
                    raise ValueError("ACTUAL_GPU_BINDING_COEFFICIENT_DRIFT")
                group.append((column, gpu))
            if group:
                candidates.append((row, fixed, group))
        if len(candidates) > 1:
            ambiguity.append(dict(site=site, slot=slot, reason="AMBIGUOUS_NATIVE_GPU_BINDING_ROW_KEEP_WITHOUT_CUT"))
            continue
        if not candidates:
            continue
        row, fixed, group = candidates[0]
        matches = [int(current_row) for current_row in
                   current_selected.indices[current_selected.indptr[axis]:current_selected.indptr[axis + 1]]
                   if _binding_matches(original, current, row, int(current_row), mapping)]
        if not matches:
            raise ValueError("ACTUAL_CURRENT_GPU_BINDING_ROW_REQUIRED")
        current_row = min(matches)
        residual = capacity - fixed
        for threshold in sorted({gpu for _, gpu in group}):
            columns = tuple(sorted(((column, gpu) for column, gpu in group if gpu >= threshold),
                                   key=lambda item: int(mapping[item[0]])))
            if residual % threshold == 0:
                continue  # Fractional RHS rounding gives no stronger LP bound.
            cut = exact_gpu_count_rounding(columns, residual)
            if sum(float(original.upper[column]) for column, _ in columns) <= cut["upper"]:
                continue
            projected_columns = tuple(int(mapping[column]) for column, _ in columns)
            key = projected_columns
            proof = dict(site=site, slot=int(slot), original_binding_row=row,
                         current_binding_row=current_row,
                         known_column=known, unchanged_capacity=capacity,
                         actual_fixed_occupancy_RHS=fixed, residual_capacity=residual,
                         minimum_gpu=threshold, original_columns=list(column for column, _ in columns),
                         GPU_per_column=list(gpu for _, gpu in columns),
                         projected_columns=list(projected_columns), upper=cut["upper"])
            if key not in cuts or cut["upper"] < cuts[key]["upper"]:
                cuts[key] = proof
    ordered = sorted(cuts.values(), key=lambda cut: (cut["projected_columns"], cut["upper"]))
    rows, columns, values = [], [], []
    for row, cut in enumerate(ordered):
        for column in cut["projected_columns"]:
            rows.append(row); columns.append(column); values.append(1.)
    addition = sp.csr_matrix((values, (rows, columns)), shape=(len(ordered), current.matrix.shape[1]))
    augmented = LinearSnapshot(sp.vstack((current.matrix, addition), format="csr"),
                               current.lower, current.upper,
                               np.r_[current.senses, np.full(len(ordered), "<")],
                               np.r_[current.rhs, [cut["upper"] for cut in ordered]],
                               current.vtypes, current.objectives).require()
    receipt = dict(PASS=True, adopted_family="EXACT_WHOLE_GANG_INTEGER_COUNT_CAPACITY_ROUNDING",
                   original_snapshot_sha256=original.fingerprint(),
                   input_locked_snapshot_sha256=current.fingerprint(),
                   strengthened_snapshot_sha256=augmented.fingerprint(),
                   unchanged_scientific_capacities=True, same_integer_feasible_schedules=True,
                   same_integer_schedule_P1_P2_values=True, LP_relaxation_strengthened=bool(ordered),
                   strict_current_LP_bound_improvement_proven=False,
                   same_LP_projection_asserted=False, histogram_scopes_only=True,
                   mixed_singleton_flow_units_excluded=excluded_units,
                   cuts_added=len(ordered), cut_nnz=addition.nnz,
                   cuts=ordered, cut_payload_sha256=_payload_hash(ordered),
                   ambiguous_rows_without_cuts=ambiguity,
                   proof="Known_GPU=sum(nonnegative occupancy)+actual fixed RHS <= unchanged capacity. Every selected integer histogram count contributes at least minimum_gpu, so its integer sum is bounded by floor(residual/minimum_gpu).",
                   optimization_calls=0)
    verify_histogram_capacity_strengthening(original, current, augmented, descriptor, data, mapping, receipt)
    return augmented, receipt


def verify_histogram_capacity_strengthening(original, current, augmented, descriptor, data, mapping, receipt):
    """Independent row/sign/type/incidence check of every adopted inequality."""
    mapping = _require_zero_map(original, current, mapping)
    augmented.require()
    if (receipt["original_snapshot_sha256"] != original.fingerprint()
            or receipt["input_locked_snapshot_sha256"] != current.fingerprint()
            or receipt["strengthened_snapshot_sha256"] != augmented.fingerprint()
            or receipt["cut_payload_sha256"] != _payload_hash(receipt["cuts"])):
        raise ValueError("STRENGTHENING_SOURCE_OR_PROOF_HASH_DRIFT")
    safe = {}
    _, jobs, _, resources, _, graphs, _, _ = data
    for unit in descriptor["units"]:
        uid = unit["uid"]; job = jobs[uid]
        if (unit.get("optional") or unit.get("retained_mixed_flow")
                or not (unit.get("stay_count") or not graphs[uid].events["w"])):
            continue
        for (site, start), encoded in unit["v"]["y"].items():
            if encoded[0] == "v":
                column = int(encoded[1]); effect = (site, int(start), job.service_slots, job.gpu)
                if column in safe and safe[column] != effect:
                    raise ValueError("AMBIGUOUS_HISTOGRAM_COLUMN_INCIDENCE")
                safe[column] = effect
    if augmented.matrix.shape[0] != current.matrix.shape[0] + len(receipt["cuts"]):
        raise ValueError("STRENGTHENING_APPENDED_ROW_AXIS")
    if ((augmented.matrix[:current.matrix.shape[0]] - current.matrix).nnz
            or not np.array_equal(augmented.rhs[:len(current.rhs)], current.rhs)
            or not np.array_equal(augmented.senses[:len(current.senses)], current.senses)
            or not np.array_equal(augmented.lower, current.lower)
            or not np.array_equal(augmented.upper, current.upper)
            or not np.array_equal(augmented.vtypes, current.vtypes)
            or augmented.objectives != current.objectives):
        raise ValueError("ORIGINAL_LOCKED_SCIENTIFIC_ROWS_CHANGED")
    for number, cut in enumerate(receipt["cuts"]):
        row, known = cut["original_binding_row"], cut["known_column"]
        sizes = {len(cut[key]) for key in ("original_columns", "GPU_per_column", "projected_columns")}
        if (len(sizes) != 1 or not next(iter(sizes))
                or len(set(cut["original_columns"])) != len(cut["original_columns"])
                or cut["projected_columns"] != sorted(set(cut["projected_columns"]))
                or any(not isinstance(gpu, int) or isinstance(gpu, bool) or gpu <= 0 for gpu in cut["GPU_per_column"])
                or not 0 <= row < original.matrix.shape[0] or not 0 <= known < len(mapping)
                or mapping[known] < 0
                or not _binding_matches(original, current, row, cut["current_binding_row"], mapping)):
            raise ValueError("ACTUAL_CURRENT_GPU_BINDING_ROW_OR_COUNT_AXES_REQUIRED")
        lo, hi = original.matrix.indptr[row:row + 2]
        vector = dict(zip(original.matrix.indices[lo:hi], original.matrix.data[lo:hi]))
        expected_known = descriptor["known"][cut["site"], cut["slot"]]
        if (expected_known != ("v", known) or vector.get(known) != 1
                or original.senses[row] != "=" or _integer(original.rhs[row]) != cut["actual_fixed_occupancy_RHS"]
                or _integer(original.upper[known]) != cut["unchanged_capacity"]
                or resources.capacities[cut["site"]] != cut["unchanged_capacity"]
                or any(value > 0 or original.lower[column] < 0 for column, value in vector.items() if column != known)):
            raise ValueError("EXACT_NATIVE_KNOWN_GPU_BOUND_PROOF")
        for column, gpu, projected in zip(cut["original_columns"], cut["GPU_per_column"], cut["projected_columns"]):
            site, start, duration, actual_gpu = safe[column]
            if (site != cut["site"] or not start <= cut["slot"] < start + duration
                    or gpu != actual_gpu or vector.get(column) != -gpu or mapping[column] != projected
                    or original.vtypes[column] not in ("B", "I") or original.lower[column] < 0):
                raise ValueError("EXACT_INTEGER_HISTOGRAM_OCCUPANCY_PROOF")
        expected_upper = (cut["unchanged_capacity"] - cut["actual_fixed_occupancy_RHS"]) // min(cut["GPU_per_column"])
        target = current.matrix.shape[0] + number
        lo, hi = augmented.matrix.indptr[target:target + 2]
        if (cut["upper"] != expected_upper or augmented.rhs[target] != expected_upper
                or augmented.senses[target] != "<"
                or list(augmented.matrix.indices[lo:hi]) != cut["projected_columns"]
                or not np.all(augmented.matrix.data[lo:hi] == 1)):
            raise ValueError("EXACT_COUNT_ROUNDING_INEQUALITY_PROOF")
    return dict(PASS=True, independently_verified_cuts=len(receipt["cuts"]),
                same_integer_feasible_schedules=True, same_LP_projection_asserted=False)

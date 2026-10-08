"""Exact zero-column and byte-identical row compression of a locked model."""
from dataclasses import dataclass, replace
import hashlib
import numpy as np
from v42_a_stage_domain_v2.lexstage import Objective
from .proofs import shift_count_bounds


@dataclass
class Compression:
    original: object
    compact: object
    kept_columns: object
    kept_rows: object
    fixed_zero: object
    upper_proofs: list
    removed_rows: list

    def forward(self, original_point):
        x = np.asarray(original_point)
        if x.shape != (self.original.matrix.shape[1],):
            raise ValueError('ORIGINAL_POINT_AXIS')
        if np.any(x[self.fixed_zero] != 0):
            raise ValueError('ORIGINAL_POINT_NOT_EXACT_PROVEN_ZERO')
        return x[self.kept_columns].copy()

    def inverse(self, compact_point):
        x = np.asarray(compact_point)
        if x.shape != (len(self.kept_columns),):
            raise ValueError('COMPACT_POINT_AXIS')
        restored = np.zeros(self.original.matrix.shape[1], dtype=x.dtype)
        restored[self.kept_columns] = x
        return restored


def compress(snapshot, shift_row, *, expected_shift=74, duplicate_rows=True):
    snapshot.require()
    if snapshot.senses[shift_row] != '=' or snapshot.rhs[shift_row] != expected_shift:
        raise ValueError('EXACT_ORIGINAL_SHIFT_LOCK_REQUIRED')
    row = snapshot.matrix.getrow(shift_row)
    bounds, proofs = shift_count_bounds(dict(zip(row.indices, row.data)), snapshot.rhs[shift_row],
        snapshot.lower, snapshot.upper, snapshot.vtypes)
    upper = snapshot.upper.copy()
    for j, bound in bounds.items():
        upper[j] = bound
    zero = np.flatnonzero((snapshot.lower == 0) & (upper == 0))
    keep = np.flatnonzero(~((snapshot.lower == 0) & (upper == 0)))
    mapping = np.full(snapshot.matrix.shape[1], -1, dtype=np.int64)
    mapping[keep] = np.arange(len(keep))
    A = snapshot.matrix[:, keep].tocsr()
    selected, removed, seen = [], [], {}
    for i in range(A.shape[0]):
        first, last = A.indptr[i:i+2]
        sense, rhs = snapshot.senses[i], snapshot.rhs[i]
        if first == last and (sense == '=' and rhs == 0 or sense == '<' and rhs >= 0 or sense == '>' and rhs <= 0):
            removed.append(dict(row=i, kind='EXACT_TRIVIAL_ZERO_ROW'))
            continue
        if duplicate_rows:
            indices, data = A.indices[first:last], A.data[first:last]
            key = hashlib.sha256(indices.tobytes() + data.tobytes() + str(sense).encode() + np.float64(rhs).tobytes()).digest()
            prior = seen.get(key)
            if prior is not None:
                start, end = A.indptr[prior:prior+2]
                if sense == snapshot.senses[prior] and rhs == snapshot.rhs[prior] and np.array_equal(indices, A.indices[start:end]) and np.array_equal(data, A.data[start:end]):
                    removed.append(dict(row=i, kind='IDENTICAL_ROW', witness_row=prior))
                    continue
            seen[key] = i
        selected.append(i)
    objectives = tuple(Objective(o.name, tuple((int(mapping[j]), c) for j, c in o.coefficients().items() if mapping[j] >= 0), o.constant) for o in snapshot.objectives)
    compact = replace(snapshot, matrix=A[selected].tocsr(), lower=snapshot.lower[keep].copy(), upper=upper[keep],
        vtypes=snapshot.vtypes[keep].copy(), rhs=snapshot.rhs[selected].copy(), senses=snapshot.senses[selected].copy(), objectives=objectives).require()
    return Compression(snapshot, compact, keep, np.asarray(selected, dtype=np.int64), zero, proofs, removed)

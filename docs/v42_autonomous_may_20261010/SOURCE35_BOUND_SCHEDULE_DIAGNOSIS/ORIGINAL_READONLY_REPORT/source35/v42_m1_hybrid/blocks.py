"""Exact original-CSR trajectory partition, without dropping a coefficient.

The four local domains keep the original 96-slot route/SOC/mode/PCS/PQ
constraints and literal bounds/types.  All other rows are kept in either the
nonunit block or the coupling table.  This is a decomposition, not a new cut.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import numpy as np
from scipy import sparse

UNIT_FAMILIES = frozenset(('route_flow', 'node_activity', 'charge_mode',
                           'SOC', 'Pch', 'Pdis', 'Q'))


def unit_owner(name):
    text = str(name)
    if '[' not in text or not text.endswith(']'):
        return None
    family, axis = text.split('[', 1)
    return axis[:-1].split(',', 1)[0] if family in UNIT_FAMILIES else None


def _equal(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def matrix_sha(A):
    A = A.tocsr()
    h = sha256(np.asarray(A.shape, dtype='<i8').tobytes())
    for value in (A.indptr, A.indices, A.data):
        h.update(np.asarray(value).dtype.str.encode('ascii'))
        h.update(np.ascontiguousarray(value).tobytes())
    return h.hexdigest()


@dataclass
class UnitBlock:
    unit: str
    A: object
    d: dict
    original_rows: np.ndarray
    original_columns: np.ndarray


@dataclass
class Decomposition:
    units: dict
    nonunit_block: UnitBlock
    coupling_rows: np.ndarray
    column_owner: np.ndarray
    case_sha: str
    inclusion: dict

    @property
    def nonunit_columns(self):
        return self.nonunit_block.original_columns


def _metadata(d, rows, columns):
    result = {k: np.asarray(d[k])[columns].copy()
              for k in ('names', 'lower', 'upper', 'types', 'objective')}
    result.update({k: np.asarray(d[k])[rows].copy()
                   for k in ('rhs', 'sense', 'row_names')})
    # Original ObjCon belongs to the global bound exactly once.
    result['constant'] = np.asarray(0., dtype=np.asarray(d['constant']).dtype)
    return result


def build_blocks(case):
    A, d = case.A.tocsr(), case.d
    owners = [unit_owner(n) for n in d['names']]
    units = sorted({u for u in owners if u is not None})
    if len(units) != 4:
        raise ValueError('FOUR_ORIGINAL_FLEET_UNITS_REQUIRED')
    if hasattr(case, 'graph') and set(case.graph[1]) != set(units):
        raise ValueError('ORIGINAL_GRAPH_FLEET_IDENTITY_DRIFT')
    codes = {u: k+1 for k, u in enumerate(units)}
    column_owner = np.asarray([codes.get(u, 0) for u in owners], dtype=np.int64)
    counts = np.diff(A.indptr)
    nonempty = np.flatnonzero(counts)
    low = np.zeros(A.shape[0], dtype=np.int64)
    high = np.zeros(A.shape[0], dtype=np.int64)
    if len(nonempty):
        support = column_owner[A.indices]
        low[nonempty] = np.minimum.reduceat(support, A.indptr[nonempty])
        high[nonempty] = np.maximum.reduceat(support, A.indptr[nonempty])
    blocks = {}
    for u, code in codes.items():
        rows = np.flatnonzero((low == code) & (high == code)).astype(np.int64)
        columns = np.flatnonzero(column_owner == code).astype(np.int64)
        blocks[u] = UnitBlock(u, A[rows][:, columns].tocsr(),
                              _metadata(d, rows, columns), rows, columns)
    rows = np.flatnonzero((low == 0) & (high == 0)).astype(np.int64)
    columns = np.flatnonzero(column_owner == 0).astype(np.int64)
    nonunit = UnitBlock('NONUNIT', A[rows][:, columns].tocsr(),
                        _metadata(d, rows, columns), rows, columns)
    coupling = np.flatnonzero(low != high).astype(np.int64)
    decomp = Decomposition(blocks, nonunit, coupling, column_owner,
                           case.case_sha, {})
    decomp.inclusion = verify_decomposition(case, decomp)
    return decomp


def verify_decomposition(case, decomp):
    """Check every original row/column and every local matrix nonzero."""
    A, d = case.A.tocsr(), case.d
    if decomp.case_sha != case.case_sha:
        raise ValueError('DECOMPOSITION_CASE_SHA_DRIFT')
    all_blocks = list(decomp.units.values()) + [decomp.nonunit_block]
    rows = np.concatenate([b.original_rows for b in all_blocks] + [decomp.coupling_rows])
    columns = np.concatenate([b.original_columns for b in all_blocks])
    for axis, size, label in ((rows, A.shape[0], 'ROW'), (columns, A.shape[1], 'COLUMN')):
        if axis.dtype.kind not in 'iu' or not np.array_equal(np.sort(axis), np.arange(size)):
            raise ValueError('ORIGINAL_'+label+'_PARTITION_INCOMPLETE_OR_DUPLICATE')
    nnz = 0
    for b in all_blocks:
        expected = A[b.original_rows][:, b.original_columns].tocsr()
        for key in ('indptr', 'indices', 'data'):
            if not _equal(getattr(expected, key), getattr(b.A.tocsr(), key)):
                raise ValueError('ORIGINAL_LOCAL_CSR_COEFFICIENT_DRIFT')
        # No original nonzero may disappear at column restriction.
        if expected.nnz != A[b.original_rows].nnz:
            raise ValueError('LOCAL_ROW_NONLOCAL_COEFFICIENT_DROPPED')
        for key in ('names', 'lower', 'upper', 'types', 'objective'):
            if not _equal(np.asarray(d[key])[b.original_columns], b.d[key]):
                raise ValueError('ORIGINAL_LOCAL_DOMAIN_DRIFT:'+key)
        for key in ('rhs', 'sense', 'row_names'):
            if not _equal(np.asarray(d[key])[b.original_rows], b.d[key]):
                raise ValueError('ORIGINAL_LOCAL_ROW_DRIFT:'+key)
        if float(b.d['constant']) != 0.:
            raise ValueError('GLOBAL_OBJECTIVE_CONSTANT_DUPLICATED')
        expected_owner = b.unit if b.unit != 'NONUNIT' else None
        if any(unit_owner(d['names'][j]) != expected_owner for j in b.original_columns):
            raise ValueError('UNIT_COLUMN_OWNERSHIP_DRIFT')
        nnz += b.A.nnz
    for i in decomp.coupling_rows:
        owners = {unit_owner(d['names'][j]) for j in A.indices[A.indptr[i]:A.indptr[i+1]]}
        if len(owners) < 2:
            raise ValueError('COUPLING_ROW_IS_NOT_MIXED_ORIGINAL_SUPPORT')
    nnz += A[decomp.coupling_rows].nnz
    if nnz != A.nnz:
        raise ValueError('ORIGINAL_MATRIX_NONZERO_COVERAGE_DRIFT')
    return dict(PASS=True, case_sha=case.case_sha,
        theorem='F_EQUALS_PRODUCT_OF_ORIGINAL_LOCAL_DOMAINS_INTERSECT_ORIGINAL_COUPLING',
        original_rows=A.shape[0], original_columns=A.shape[1], original_nnz=A.nnz,
        units={u:dict(rows=b.A.shape[0], columns=b.A.shape[1], nnz=b.A.nnz,
                       binary_columns=int(np.sum(b.d['types'] == 'B')))
               for u,b in decomp.units.items()},
        nonunit_rows=decomp.nonunit_block.A.shape[0],
        nonunit_columns=decomp.nonunit_block.A.shape[1],
        coupling_rows=len(decomp.coupling_rows), all_original_nonzeros_retained=True,
        all_original_bounds_types_objective_retained=True,
        full_96_slot_domain_preserved=True, original_matrix_sha256=matrix_sha(A),
        new_cut=False, integer_block_strengthening_proven=False)


def output_directory(output):
    path = Path(output).resolve()
    root = Path(__file__).resolve().parents[1]
    if root.drive.upper() != 'D:' or not path.is_relative_to(root):
        raise ValueError('HYBRID_OUTPUT_MUST_BE_INSIDE_D_V42')
    path.mkdir(parents=True, exist_ok=True)
    return path


def persist_decomposition(case, decomp, output):
    """Persist original CSR, axes and immutable row/domain/objective mapping."""
    path = output_directory(output)
    receipt = verify_decomposition(case, decomp)
    sparse.save_npz(path/'ORIGINAL_C3A_CSR.npz', case.A.tocsr())
    np.savez_compressed(path/'ORIGINAL_C3A_DOMAIN.npz', **case.d)
    axes = dict(coupling_rows=decomp.coupling_rows, column_owner=decomp.column_owner,
                NONUNIT_rows=decomp.nonunit_block.original_rows,
                NONUNIT_columns=decomp.nonunit_block.original_columns)
    for u,b in decomp.units.items():
        axes[u+'_rows'] = b.original_rows
        axes[u+'_columns'] = b.original_columns
    np.savez_compressed(path/'BLOCK_AXES.npz', **axes)
    files = {}
    for name in ('ORIGINAL_C3A_CSR.npz', 'ORIGINAL_C3A_DOMAIN.npz', 'BLOCK_AXES.npz'):
        p = path/name
        files[name] = dict(path=str(p), sha256=sha256(p.read_bytes()).hexdigest())
    receipt = dict(receipt, files=files, native_optimize_calls=0)
    (path/'DECOMPOSITION.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return receipt

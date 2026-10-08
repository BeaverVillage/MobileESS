"""Inspect a CSR lock row without loading the large original matrix."""
from pathlib import Path
import json
import time
import zipfile
import numpy as np
from .proofs import shift_count_bounds
from .isolation import OUT, STATIC, assert_write_path

BASELINE = Path(r'C:\Users\kjw39\Documents\Codex\2026-10-08\a-stage-acceptance-fourday\docs\v42_a_stage_acceptance_fourday_20261008\2025-05-10')


def stream_array_slice(archive, name, first, last):
    with archive.open(name + '.npy') as stream:
        version = np.lib.format.read_magic(stream)
        header = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
        shape, fortran, dtype = header(stream)
        if len(shape) != 1 or fortran or not 0 <= first <= last <= shape[0]:
            raise ValueError('ONE_DIMENSIONAL_SAVED_CSR_SLICE_REQUIRED')
        remaining = first * dtype.itemsize
        while remaining:
            chunk = stream.read(min(1024*1024, remaining))
            if not chunk:
                raise ValueError('TRUNCATED_ORIGINAL_CSR_MEMBER')
            remaining -= len(chunk)
        raw = stream.read((last-first) * dtype.itemsize)
        if len(raw) != (last-first) * dtype.itemsize:
            raise ValueError('TRUNCATED_ORIGINAL_CSR_SLICE')
        return np.frombuffer(raw, dtype=dtype).copy()


def read_row(path, row):
    with zipfile.ZipFile(path) as archive:
        pointers = stream_array_slice(archive, 'indptr', row, row+2)
        start, end = map(int, pointers)
        indices = stream_array_slice(archive, 'indices', start, end)
        data = stream_array_slice(archive, 'data', start, end)
        return indices, data


def run():
    start = time.perf_counter()
    folder = BASELINE / 'P2/PRESTART_RELOCATION'
    identity = json.loads((folder / 'NATIVE/MODEL_IDENTITY.json').read_text())
    locks = json.loads((folder / 'LOCK_REBUILD.json').read_text())
    row = locks['lock_rows']['shift_magnitude']
    indices, data = read_row(identity['matrix']['path'], row)
    with np.load(identity['attributes']['path']) as attrs:
        lower, upper, types = attrs['lower'], attrs['upper'], attrs['vtypes']
        rhs, sense = float(attrs['rhs'][row]), str(attrs['senses'][row])
    if rhs != 74 or sense != '=':
        raise ValueError('SAVED_ORIGINAL_SHIFT_LOCK_DRIFT')
    bounds, proofs = shift_count_bounds(dict(zip(indices, data)), rhs, lower, upper, types)
    fixed = [j for j, bound in bounds.items() if bound == 0]
    target = assert_write_path(STATIC / 'SAVED_SHIFT_IMPLICATIONS.npz')
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, columns=np.asarray(list(bounds), dtype=np.int64),
        upper=np.asarray(list(bounds.values()), dtype=np.float64), fixed_zero=np.asarray(fixed, dtype=np.int64))
    receipt = dict(PASS=True, stage='ROW_IMPLICATION_ONLY_FULL_MODEL_EQUIVALENCE_PENDING',
        baseline_identity=identity, original_shift_row=row, original_shift_rhs=rhs,
        original_shift_terms=len(indices), implied_tighter_integer_upper_bounds=len(bounds),
        implied_fixed_zero_columns=len(fixed), original_columns=identity['cols'],
        potential_remaining_columns=identity['cols']-len(fixed),
        coefficient_min=float(data.min()), coefficient_max=float(data.max()),
        all_row_coefficients_nonnegative=bool(np.all(data>=0)),
        all_row_variable_lower_bounds_nonnegative=bool(np.all(lower[indices]>=0)),
        continuous_lanes_not_integerized=True, native_optimization_calls=0,
        matrix_loaded_in_full=False, source_artifacts_modified=False,
        elapsed_seconds=time.perf_counter()-start, proof_examples=proofs[:8],
        implied_bounds_path=str(target))
    assert_write_path(OUT/'SAVED_SHIFT_IMPLICATION_ANALYSIS.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('baseline_identity','proof_examples')},ensure_ascii=False))


if __name__=='__main__':
    run()

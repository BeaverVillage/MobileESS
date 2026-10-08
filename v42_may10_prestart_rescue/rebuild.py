"""Rebuild all original class/objective interfaces without optimizing."""
from dataclasses import replace
from pathlib import Path
import gzip
import json
import pickle
import shutil
import time
import numpy as np
import scipy.sparse as sp
import gurobipy as gp
from v42_pr134_b1.common import read, record, atomic
from v42_pr134_b1.native import bind
from v42_a_stage_practical.integer_model import restore_types
from v42_a_stage_domain_v2.lexstage import LinearSnapshot
from v42_a_stage_phase1.core import primal_replay
from v42_a_stage_acceptance.schedule_audit import original_schedule_metrics
from .inspect_saved import BASELINE
from .compression import compress
from .isolation import OUT, STATIC, assert_write_path, require_large_resource_isolation


def run():
    require_large_resource_isolation()
    started = time.perf_counter()
    source = read(BASELINE / 'INITIAL_VERIFICATION.json')
    if record(source['state']['path']) != source['state']:
        raise ValueError('FROZEN_MAY10_INITIAL_STATE_DRIFT')
    with gzip.open(source['state']['path'], 'rb') as stream:
        state = pickle.load(stream)
    if state['data'][0]['day'] != '2025-05-10' or len(state['data'][7]['classes']) != 575:
        raise ValueError('EXACT_MAY10_575_CLASS_INSTANCE_REQUIRED')
    inherited = gp.Model.optimize
    def forbidden(*args, **kwargs):
        raise PermissionError('NO_OPTIMIZATION_DURING_ORIGINAL_EQUIVALENCE_REBUILD')
    gp.Model.optimize = forbidden
    try:
        bind(state['data'][0], Path('C:/v42_pr134_sc_execution_20261007/inputs/2025-05-10'), STATIC/'ORIGINAL_INTERFACE_REPLAY')
        typed, types = restore_types(state, state['global_types'])
        from v42_a_stage_canary import zero
        own_zero = OUT / 'ORIGINAL_REBUILD'
        target = assert_write_path(own_zero / '2025-05-10/BLOCK_PRICING_ORACLE_VERIFICATION.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BASELINE/'BLOCK_PRICING_ORACLE_VERIFICATION.json', target)
        zero.OUT = own_zero
        physical_state, original = zero.build(state, typed, '2025-05-10')
        expected_zero = read(BASELINE / 'FULL_ZERO_DOMAIN_VERIFICATION.json')
        if original.fingerprint() != expected_zero['snapshot_sha256']:
            raise ValueError('ALL_575_ORIGINAL_ZERO_MODEL_REBUILD_DRIFT')
        identity = read(BASELINE/'P2/PRESTART_RELOCATION/NATIVE/MODEL_IDENTITY.json')
        for name in ('matrix', 'attributes'):
            if record(identity[name]['path']) != identity[name]:
                raise ValueError('SAVED_ACTUAL_NATIVE_MODEL_BYTES_DRIFT:'+name)
        A = sp.load_npz(identity['matrix']['path']).tocsr()
        with np.load(identity['attributes']['path']) as attrs:
            boxes = {name: attrs[name].copy() for name in ('lower','upper','senses','rhs','vtypes')}
            native_objective = attrs['objective'].copy()
        objs = (original.objective('prestart_relocation'),) + tuple(o for o in original.objectives if o.name != 'prestart_relocation')
        query = LinearSnapshot(A, boxes['lower'], boxes['upper'], boxes['senses'], boxes['rhs'], boxes['vtypes'], objs).require()
        if query.fingerprint() != identity['original_snapshot_sha256']:
            raise ValueError('ALL_FOUR_ORIGINAL_OBJECTIVE_AND_QUERY_IDENTITY_DRIFT')
        expected = np.zeros(query.matrix.shape[1])
        for j,c in query.objective('prestart_relocation').coefficients().items(): expected[j] = float(c)
        if not np.array_equal(native_objective, expected):
            raise ValueError('PRESTART_NATIVE_OBJECTIVE_COEFFICIENT_DRIFT')
        end = A.indptr[original.matrix.shape[0]]
        if not (np.array_equal(A.indptr[:original.matrix.shape[0]+1],original.matrix.indptr)
            and np.array_equal(A.indices[:end],original.matrix.indices)
            and np.array_equal(A.data[:end],original.matrix.data)):
            raise ValueError('UNSTRENGTHENED_ORIGINAL_PHYSICAL_ROWS_DRIFT')
        checkpoint = read(BASELINE/'P2_CHECKPOINT.json')
        pre = next(s for s in checkpoint['stages'] if s['component'] == 'prestart_relocation')
        if record(pre['point']['path']) != pre['point']: raise ValueError('VALIDATED_UB60_POINT_DRIFT')
        with np.load(pre['point']['path']) as arrays: warm = arrays['X'].copy()
        from v42_a_stage_acceptance import physical
        physical.STATIC = STATIC / 'ORIGINAL_PHYSICAL'
        replay = physical.Physical(physical_state, original)
        verification = replay.verify(warm)
        if not verification['PASS'] or not primal_replay(query,warm)['PASS']:
            raise ValueError('ORIGINAL_UB60_REPLAY_FAILED')
        values = {'migration_count':0, 'shift_magnitude':74, 'prestart_relocation':60}
        metrics,residuals = original_schedule_metrics(physical_state['data'][1], verification['selected_jobs'], values)
        locks = read(BASELINE/'P2/PRESTART_RELOCATION/LOCK_REBUILD.json')
        reduction = compress(query, locks['lock_rows']['shift_magnitude'])
        compact_warm = reduction.forward(warm)
        restored = reduction.inverse(compact_warm)
        if not np.array_equal(restored,warm) or not primal_replay(reduction.compact,compact_warm)['PASS']:
            raise ValueError('BIDIRECTIONAL_UB60_MAPPING_NOT_EXACT')
        for path in (STATIC/'SOURCE_QUERY.npz', STATIC/'COMPRESSED_QUERY.npz'):
            assert_write_path(path)
        sp.save_npz(STATIC/'SOURCE_QUERY.npz',query.matrix)
        sp.save_npz(STATIC/'COMPRESSED_QUERY.npz',reduction.compact.matrix)
        with gzip.open(assert_write_path(STATIC/'REBUILT_CONTEXT.pkl.gz'),'wb') as stream:
            pickle.dump(dict(physical_state=physical_state,original=original,query=query,reduction=reduction,
                warm=warm,compact_warm=compact_warm,identity=identity),stream,protocol=5)
        atomic(assert_write_path(OUT/'ORIGINAL_UB60_PHYSICAL_REPLAY.json'),verification)
        atomic(assert_write_path(OUT/'COMPRESSION_VALIDATION.json'),dict(PASS=True,all_575_classes_independently_rebuilt=True,
            original_jobs=len(physical_state['data'][1]),classes=len(physical_state['data'][7]['classes']),
            original_zero_sha256=original.fingerprint(),original_query_sha256=query.fingerprint(),
            compact_sha256=reduction.compact.fingerprint(),
            original=dict(rows=A.shape[0],cols=A.shape[1],nnz=A.nnz),
            compact=dict(rows=reduction.compact.matrix.shape[0],cols=reduction.compact.matrix.shape[1],nnz=reduction.compact.matrix.nnz),
            fixed_zero_columns=len(reduction.fixed_zero),tighter_upper_bounds=len(reduction.upper_proofs),
            removed_rows=len(reduction.removed_rows),objective_constants={o.name:str(o.constant) for o in query.objectives},
            all_four_objective_coefficient_constant_identity=True,original_native_vtypes_preserved=True,
            original_continuous_finish_lanes_not_integerized=True,complete_original_integer_schedule_domain_preserved=True,
            same_original_physics_and_tolerances=True,UB60_exact_bidirectional_mapping=True,
            independent_schedule_objectives=metrics,objective_residuals=residuals,
            original_physical_PASS=True,native_optimization_calls=0,
            rebuild_elapsed_seconds=time.perf_counter()-started,source_model_identity=identity,
            context=record(STATIC/'REBUILT_CONTEXT.pkl.gz')))
        print('ORIGINAL_EQUIVALENCE_AND_COMPRESSION_PASS',query.matrix.shape,reduction.compact.matrix.shape,reduction.compact.matrix.nnz,flush=True)
    finally:
        gp.Model.optimize = inherited


if __name__ == '__main__':
    run()

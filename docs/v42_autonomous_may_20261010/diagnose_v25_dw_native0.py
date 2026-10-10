"""Saved actual three-date RMP transport proof; no solve or full Native model."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter
import hashlib
import json
import gc

import gurobipy as gp
import numpy as np
from scipy import sparse
import psutil

from v42_autonomous_b2 import dw_native
from v42_m1_hybrid.blocks import build_blocks, matrix_sha
from v42_m1_research.check_ub import matrix_replay,vector_sha


ROOT=Path(__file__).resolve().parents[2]
CAMPAIGN=Path(r'D:\v42_may_restart_20261010_02')
ORIGINAL=Path(r'D:\v42run23')


def record(path):
    path=Path(path);h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=h.hexdigest())


def load_data(path):
    with np.load(path,allow_pickle=False) as archive:
        return {k:archive[k].copy() for k in archive.files}


def day_proof(day,attempt):
    out=CAMPAIGN/'dates/B2'/day/'attempts'/attempt/'output'
    A=sparse.load_npz(out/'C3A_A.npz').tocsr();d=load_data(out/'C3A_DATA.npz')
    identity=json.loads((out/'SCIENTIFIC_CASE_IDENTITY.json').read_text())
    assert matrix_sha(A)==identity['selected_matrix_sha']
    point=load_data(out/'BEST_STRICT_UB_POINT.npz')['point']
    case=SimpleNamespace(A=A,d=d,point=point,case_sha=identity['case_sha'])
    decomp=build_blocks(case)
    source_rows=np.sort(np.concatenate((decomp.nonunit_block.original_rows,decomp.coupling_rows)))
    nonunit=decomp.nonunit_columns
    pieces=[A[source_rows][:,nonunit].tocsr()]
    objective=list(map(float,d['objective'][nonunit]));columns=[];local=[]
    for unit,block in decomp.units.items():
        path=out/'005_L2_00_MASTER'/(unit+'_MASTER_SEED_COLUMN.npz')
        saved=load_data(path);seed=saved['point'];axis=saved['original_columns']
        assert np.array_equal(axis,block.original_columns)
        assert np.array_equal(seed,point[axis])
        replay=matrix_replay(block.A,block.d,seed)
        assert replay['PASS'] and replay['integer_pattern_exact'] and replay['exact_binary_0_1']
        weighted=A[source_rows][:,axis]@seed
        pieces.append(sparse.csr_matrix(weighted.reshape(-1,1)))
        objective.append(float(block.d['objective']@seed))
        columns.append(record(path));local.append(dict(unit=unit,replay=replay))
    n=len(nonunit)
    matrix=sparse.vstack((sparse.hstack(pieces,format='csr'),
        sparse.hstack((sparse.csr_matrix((4,n)),sparse.eye(4)),format='csr')),format='csr')
    rhs=np.concatenate((d['rhs'][source_rows],np.ones(4)))
    sense=np.concatenate((d['sense'][source_rows],np.full(4,'=')))
    lower=np.concatenate((d['lower'][nonunit],np.zeros(4)))
    upper=np.concatenate((d['upper'][nonunit],np.ones(4)))
    original,scaled,scaled_rhs,exponents,receipt=dw_native.scale_rows(matrix,rhs)
    # Prove the complete sparse RMP round trip while creating Native models
    # only for affected rows. Unaffected rows are byte-identical and have no
    # coefficient in Native's omitted range.
    restored=scaled.copy()
    restored.data=np.ldexp(restored.data,-np.repeat(exponents,np.diff(restored.indptr)))
    assert dw_native._same_matrix(restored,matrix)
    affected=np.flatnonzero(exponents)
    projection=matrix[affected].tocsr()
    axes=np.unique(projection.indices)
    projection=projection[:,axes].tocsr()
    raw=gp.Model('V42_ACTUAL_RMP_OMISSION_NATIVE0_'+day);raw.Params.OutputFlag=0
    try:
        x=raw.addMVar(len(axes),lb=lower[axes],ub=upper[axes],vtype='C',obj=np.asarray(objective)[axes])
        raw.ObjCon=float(d['constant'])
        raw.addMConstr(projection,x,sense[affected],rhs[affected]);raw.update()
        delta=raw.getA()-projection;delta.eliminate_zeros()
        assert delta.nnz==receipt['tiny_nonzero_coefficients_preserved']
        assert np.all(np.abs(delta.data)<dw_native.DROP_THRESHOLD)
        assert raw.Status==gp.GRB.LOADED
        unscaled_drift=int(delta.nnz)
    finally:raw.dispose()
    model=dw_native.ExactRowModel('V42_ACTUAL_RMP_SCALED_NATIVE0_'+day)
    model.Params.OutputFlag=0
    try:
        x=model.addMVar(len(axes),lb=lower[axes],ub=upper[axes],vtype='C',obj=np.asarray(objective)[axes])
        model.ObjCon=float(d['constant'])
        rows=model.addMConstr(projection,x,sense[affected],rhs[affected]);model.update()
        assert dw_native._same_matrix(model.getA(),projection)
        assert np.array_equal(model.getAttr('RHS'),rhs[affected])
        assert model._model.Status==gp.GRB.LOADED
        native_pi=np.linspace(-.25,.25,len(affected))
        pulled=dw_native.pullback_pi(native_pi,model._exponents)
        assert np.array_equal(np.ldexp(pulled,-model._exponents),native_pi)
        # A changed non-tiny Native coefficient must still fail the strict
        # raw scaled-matrix check before any unscaled snapshot is accepted.
        row,col=int(projection.nonzero()[0][0]),int(projection.nonzero()[1][0])
        model._model.chgCoeff(rows._rows[row].item(),x[col].item(),float(model._scaled[row,col])+1.)
        model.update()
        try:model.getA()
        except ValueError as error:assert str(error)=='DW_SCALED_NATIVE_MATRIX_DRIFT'
        else:raise AssertionError('MALICIOUS_NATIVE_DRIFT_ACCEPTED')
    finally:model.dispose()
    c3=matrix_replay(A,d,point)
    assert c3['PASS'] and c3['integer_pattern_exact'] and c3['exact_binary_0_1']
    strict_path=out/'BEST_STRICT_UB_CERTIFICATE.json'
    strict=json.loads(strict_path.read_text())
    replay=strict['original_matrix_and_96_slot_physical_replay']
    assert strict['PASS'] and replay['PASS'] and replay['physical']['PASS']
    assert strict['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact'] is True
    assert replay['C3A']['integer_pattern_exact'] and replay['original_full_matrix']['integer_pattern_exact']
    assert replay['original_objective_bit_equal'] is True
    assert strict['point_vector_sha256']==vector_sha(point)
    result=dict(day=day,attempt=attempt,PASS=True,Native_optimize_calls=0,
        source_matrix=record(out/'C3A_A.npz'),source_domain=record(out/'C3A_DATA.npz'),
        saved_columns=columns,original_decomposition=decomp.inclusion,
        original_local_replays=local,current_original_C3A_replay=c3,
        existing_real_FULL_physical_exact_integer_objective_certificate=record(strict_path),
        existing_real_exact_Global_UB=strict['exact_Global_UB'],
        full_RMP_sparse_scaling=receipt,affected_rows_Native0=len(affected),
        affected_projection_columns_Native0=len(axes),
        unscaled_Native0_dropped_coefficients=unscaled_drift,
        scaled_Native0_exact_matrix_RHS_senses_domain_objective_and_constant_PASS=True,
        exact_Pi_pullback_round_trip_PASS=True,malicious_non_tiny_Native_drift_rejected=True,
        unaffected_rows_byte_identical=True,original_FULL_model_unchanged=True,
        process_RSS_bytes=psutil.Process().memory_info().rss,
        fresh_run_gap_or_production_qualification_claimed=False)
    return result


def main():
    started=perf_counter();sources={}
    for name in ('v42_m1_hybrid/dw.py','v42_m1_hybrid/blocks.py',
        'v42_m1_research/check_ub.py','v42_m1_research/check_lb.py',
        'v42_m1_hybrid/final_verify.py','v42_m1_anytime/core.py',
        'v42_m1_anytime/algorithms.py','v42_may_campaign_native90/m_stage.py',
        'v42_may_campaign_native90/m_model.py','v42_native/mess.py'):
        current,old=record(ROOT/name),record(ORIGINAL/name)
        assert current['sha256']==old['sha256']
        sources[name]=dict(current=current,frozen_v23=old,byte_identical=True)
    rows=[]
    for day,attempt in [('2025-05-01','repair_b2_v23_01_s1'),
        ('2025-05-02','repair_b2_v23_01_s3'),('2025-05-03','repair_b2_v23_01_s2')]:
        proof=day_proof(day,attempt);rows.append(proof)
        print(json.dumps(dict(day=day,PASS=True,
            dropped=proof['unscaled_Native0_dropped_coefficients'],
            scale=proof['full_RMP_sparse_scaling'],RSS=proof['process_RSS_bytes'])),flush=True)
        gc.collect()
    result=dict(schema='V42_B2_V25_SAVED_ACTUAL_RMP_NATIVE0_PROOF',PASS=True,
        UTC=datetime.now(timezone.utc).isoformat(),Native_optimize_calls=0,
        heavy_full_Native_models_built=0,original_scientific_sources=sources,
        adapter_sources={name:record(ROOT/name) for name in
            ('v42_autonomous_b2/dw_native.py','v42_autonomous_b2/worker.py')},
        dates=rows,wall_seconds=perf_counter()-started,
        no_new_production_PASS_or_gap_or_qualification_claimed=True)
    path=Path(__file__).with_name('V25_ACTUAL_THREE_DATE_DW_NATIVE0_PROOF.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(proof=record(path),PASS=True,Native_optimize_calls=0)),flush=True)


if __name__=='__main__':main()

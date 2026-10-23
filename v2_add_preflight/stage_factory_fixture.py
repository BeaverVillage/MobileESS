"""Real production K48 handler through its actual source Native0 boundary."""
import uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np
from .stage_common import *
from .prestart_native import native_zero
from .stage_gurobi_io import scope as gurobi_io
from .stage_case_cache import scope as preparation_scope


class ReadbackComplete(RuntimeError):pass
class ScoreBoundary(BaseException):pass


def certify():
    from . import stage_handlers as handler
    from .stage_reference import prepare
    from v44.frozen.v43_mess.library import load
    from v42_may_campaign_native90 import budget as source_budget
    from .stage_origin import require_m
    with measured('PRODUCTION_M1_CURRENT_CASE_NATIVE0.json') as (report,start),gurobi_io(),native_zero() as denied,preparation_scope() as preparation:
        root=WORK/('CURRENT_CASE_HANDLER_'+uuid.uuid4().hex[:8]);root.mkdir()
        payload=prepare(root/'R0');p=payload['planning']['PCC_P_kw']
        anchor=[]
        for t in range(96):
            with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:anchor.append(z['anchor'][:12])
        assert np.array_equal(p,np.asarray(anchor)),'LITERAL_SEALED_R0_REUSE_NOT_AVAILABLE'
        request=dict(day='2025-05-01',arm='B2',stage='M1',logical_stage='K48_M1',
            output=str(root/'K48_M1'),source_sha=digest(SOURCE),worker_slot=1,Threads=4,campaign_root=str(root))
        parents=dict(REFERENCE=dict(PASS=True,AIDC_reference=record(root/'R0/AIDC_REFERENCE.json')))
        k=load()['table_v_k48'];written=k._write;captured=[]
        def observer(path,value):
            written(path,value)
            if Path(path).name=='NATIVE_READBACK.json':
                captured.append(record(path));raise ReadbackComplete('BEFORE_REAL_PRODUCTION_BUDGET_SOLVE')
        with patch.object(handler,'current',lambda:dict(explicit_Native0_fixture=True)),patch.object(k,'_write',observer),patch.object(source_budget,'d_path',lambda p:Path(p)):
            try:handler.k48(request,parents)
            except ReadbackComplete:pass
        assert len(captured)==1 and read(captured[0]['path'])['PASS'] and not denied
        binary=read(root/'K48_M1/M_BINARY.json')
        assert binary['anchor']==payload['identity']
        actual=root/'K48_M1/K48_NATIVE_LEDGER.json';ledger=read(actual)
        assert ledger['measured_Native_Runtime']==0. and ledger['calls']==[] and ledger['inflight'] is None
        rejected=False
        try:require_m(dict(PASS=True,FULL_feasible=True,fixture=True))
        except ValueError:rejected=True
        assert rejected
        # Continue the real M handler with a genuine preparation-only summary
        # containing NO numerical lower bound, incumbent or accepted plan.
        manifest=read(root/'K48_M1/NATIVE0_K16/NATIVE0_MANIFEST.json')
        proof=read(root/'K48_M1/NATIVE0_K16/CURRENT_SOURCE_PROJECTION_CERTIFICATE.json')
        lower=load()['table_v_k48'].summarize_current_k48(dict(K=manifest['K'],source=manifest['source']),proof,[])
        import gc;gc.collect()
        reached=[];candidates=load()['m_candidates']
        def no_score(objective,**kw):
            # geometry.scope deliberately installs its certified compact IO
            # function after the source timing wrapper. Check the actual
            # current binding, rather than that overwritten wrapper's name.
            scope=candidates.grid_context.__globals__
            assert callable(scope.get('_compact_current_authority')) and callable(scope.get('_compact_authority_cache')),'CURRENT_CASE_GEOMETRY_IO_NOT_BOUND'
            assert np.isfinite(objective).all() and kw['A_ub'].shape[1]==len(objective)
            assert np.isfinite(kw['b_ub']).all()
            reached.append(dict(columns=len(objective),rows=kw['A_ub'].shape[0]))
            raise ScoreBoundary('BEFORE_ORIGINAL_HIGHS_SCORE_SOLVE')
        mparents={'K48_M1':dict(PASS=True,lower=lower,M_binary=record(root/'K48_M1/M_BINARY.json'),
            fixed_AIDC=payload['identity'],Native_seconds=0.,Native0_no_numeric_bound_fixture=True)}
        mrequest=dict(request,logical_stage='M1',output=str(root/'M1_NATIVE0'))
        with patch.object(handler,'current',lambda:dict(explicit_Native0_fixture=True)),patch.object(candidates,'linprog',no_score),patch.object(source_budget,'d_path',lambda p:Path(p)):
            try:mresult=handler.m(mrequest,mparents)
            except ScoreBoundary:mresult=None
        assert reached and not denied
        reuse=read(root/'M1_NATIVE0/SAME_CASE_PREPARATION_REUSE.json')
        assert reuse['reused'] and preparation.stats['stored']==preparation.stats['reused']==1
        mledger=read(root/'M1_NATIVE0/JOINT_NATIVE_LEDGER.json')
        assert mledger['measured_Native_Runtime']==0. and not mledger['calls'] and mledger['inflight'] is None
        if mresult is not None:assert mresult['PASS'] is False and mresult['MESS_plan'] is None
        report.update(PASS=True,real_production_K48_handler_current_case_factory_and_original_Native_builder_called=True,
            source_R0_PQ_bit_identical_to_sealed_complete_M1=True,new_B0_model_or_old_SHA_checks_recomputed=False,
            current_AIDC_anchor_preserved=True,Native_actual_readback=captured[0],binary=record(root/'K48_M1/M_BINARY.json'),
            real_source_budget_zero_Native_calls=record(actual),finite_M_fixture_rejected_as_production_A2_parent=True,
            real_production_M1_handler_original_adaptive_Beam_score_boundary_reached=reached,
            probe_is_not_M1_implementation_or_optimization_performance_result=True,
            preparation_only_parent_Global_LB=lower['Global_LB'],M1_Native_ledger=record(root/'M1_NATIVE0/JOINT_NATIVE_LEDGER.json'),
            actual_handler_same_case_preparation_reused=True,preparation_cache_statistics=dict(preparation.stats),
            actual_same_case_geometry_IO_binding_reinstalled=True,
            no_accepted_A1_A2_or_M1_M2_optimization_result_fabricated=True,
            explicit_Native0_fixture_authority_only=True,external_worker_locks_not_acquired=True,denied_attempts=denied)


if __name__=='__main__':certify()

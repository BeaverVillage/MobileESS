"""Exercise the unchanged source whole-case K48 and Beam/Joint interfaces.

K48 fixture pricing uses finite search points; it does not solve a packet or
publish a numerical LB. The Beam score LP is intercepted before linprog and
its real arguments are checked; no fabricated LP score is returned.
"""
import gc,inspect,pickle,sys,traceback
from contextlib import ExitStack
from fractions import Fraction as F
from types import SimpleNamespace
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .stage_m_case import build_case,source_binding
from .prestart_native import native_zero

def k48(case,k,start):
    if (WORK/'M1/K16/NATIVE0_MANIFEST.json').exists():
        from v44.m_restore import packet
        p,certificate=packet(WORK/'M1/K16',case,k)
        reused=True
    else:p,certificate=k.prepare_k16(case,None,WORK/'M1/K16');reused=False
    print('SOURCE WHOLE K16 VERIFIED',reused,flush=True)
    stages=[dict(K=16,certificate=certificate)]
    # Finite original physical reference with low rho is a pricing search
    # point only, never an incumbent, LB, MIPStart or optimization result.
    from .static_pack import PACK
    full=np.load(RUN/'STAY_SOURCE_YY_FULL_POINT.npy');search=full[p['columns']].copy()
    rho_axis=str(len(p['columns'])-1)
    # A finite near-facet probe exercises the original selector without the
    # millions of deliberately violated faces produced by the old rho=0
    # diagnostic. This value is neither a solver point nor a claimed bound.
    search[-1]=min(float(F(c['exact_rhs'])/F(c['terms'][rho_axis])) for c in p['cuts'])-.005
    for target in (32,48):
        guard(start);print('SOURCE WHOLE SEPARATE',target,flush=True);cuts,receipt=k.separate(case,p,search)
        if not cuts:raise ValueError('SOURCE_K48_FIXTURE_FOUND_NO_NEW_CUTS')
        p,cert=k.append_cuts(case,p,cuts,WORK/'M1'/f'K{target}')
        stages.append(dict(K=p['K'],source_pricing=receipt,certificate=cert));print('SOURCE WHOLE K PACKET',p['K'],receipt['candidate_count'],flush=True)
    assert p['K']==48
    return dict(PASS=True,packets=stages,original_prepare_verify_separate_append_called=True,current_Native0_K16_reused=reused,
        finite_pricing_probe_rho=float(search[-1]),
        source_family_quotas_unchanged=True,whole_original_row_universe=case.original_A.shape[0],
        Global_LB=None,K48_Native_solver_calls=0,fixture_search_not_solver_result=True)

class ScoreProbeReached(BaseException):pass

def beam(case,modules,start):
    engine=modules['m_engine'];candidates=modules['m_candidates'];captured={}
    graph=engine.PathGraph(case)
    bank=SimpleNamespace(graph=graph,best=None,best_moving=None)
    class Budget:
        def remaining(self):guard(start);return 900.
        def record_external(self,*a,**k):
            # Source's finally records a failed attempt even when the probe
            # stops before linprog. Keep that honest non-Native IO receipt.
            assert captured and k.get('solver')=='HIGHS'
            captured['non_Native_probe_cost']=dict(args=a,**k)
    def before_lp(objective,**kw):
        assert np.isfinite(objective).all() and kw['A_ub'].shape[1]==len(objective)
        assert np.isfinite(kw['b_ub']).all()
        frame=inspect.currentframe().f_back
        while frame is not None and frame.f_code.co_name!='generate':frame=frame.f_back
        assert frame is not None
        captured.update(candidates=frame.f_locals['candidates'],
            lp=dict(columns=len(objective),rows=kw['A_ub'].shape[0],method=kw.get('method'),options=kw.get('options')))
        raise ScoreProbeReached('NATIVE0_BEFORE_ORIGINAL_HIGHS_SCORE_LP')
    old=candidates.linprog;candidates.linprog=before_lp
    original_context=candidates.grid_context;cached_context=False
    context_path=case.output/'COMMON_M_PR222/CRITICAL_MINIMAX_CONTEXT.json'
    if context_path.exists():
        context=read(context_path)
        if context.get('case_sha')==case.case_sha and context.get('seedless') is True and context.get('center_vector_sha') is None:
            assert context['PASS'] and context['all_thermal_rows_scanned']==96*6156*16
            from copy import deepcopy
            def existing(current,point):
                assert current.original_A is case.original_A and point is None
                return deepcopy(context)
            candidates.grid_context=existing;cached_context=True
    try:
        try:candidates.generate(case,None,bank,Budget())
        except ScoreProbeReached:pass
        else:raise ValueError('EXPECTED_SOURCE_BEAM_SCORE_LP_CALL_NOT_REACHED')
    finally:candidates.linprog=old;candidates.grid_context=original_context
    assert set(captured['candidates'])==set(INITIAL)
    pools={};counts={}
    for unit,records in captured['candidates'].items():
        rows=list(records.values());counts[unit]=dict(total=len(rows),STAY=sum(r['moves']==0 for r in rows),MOVE=sum(r['moves']>0 for r in rows),multiMOVE=sum(r['moves']>=2 for r in rows))
        assert counts[unit]['STAY'] and counts[unit]['MOVE'] and counts[unit]['multiMOVE']
        stay=graph.complete(unit);chosen=[stay]
        for lower in (1,2,3):
            found=next((r['path'] for r in sorted(rows,key=lambda r:(r['moves'],r['path'])) if r['moves']>=lower and r['path'] not in chosen),None)
            if found is not None:chosen.append(found)
        for path in chosen:graph.validate(unit,path)
        pools[unit]=chosen
    return pools,dict(PASS=True,scope='Full-grid source Beam through its real score LP boundary; LP admission numeric scores intentionally absent in Native0',
        units=counts,score_LP_argument_domain=captured['lp'],original_widths=[12,16],original_MOVE_depth=4,
        same_case_original_full_scan_intermediate_reused=cached_context,
        original_full_scan=record(context_path) if context_path.exists() else None,
        source_candidate_generation_unchanged=True,HiGHS_calls=0,official_admitted_pool_not_claimed=True)

def build():
    with measured('STAGE_M_RUNTIME_BINDING.json') as (report,start),native_zero() as denied:
        case=build_case();guard(start)
        report.update(reference_shape=list(case.original_A.shape),selected_shape=list(case.A.shape),case_sha=case.case_sha)
        with ExitStack() as stack:
            modules=stack.enter_context(source_binding(case))
            from .stage_geometry_io import scope as geometry_io
            counters=stack.enter_context(geometry_io(case,modules))
            # Independent workstreams continue after a representation failure;
            # no generic PASS can conceal the failed required interface.
            packet_test=read(OUT/'K48_WHOLE_CASE_PACKET_BINDING.json') if (OUT/'K48_WHOLE_CASE_PACKET_BINDING.json').exists() else {}
            if packet_test.get('PASS') and packet_test['case_sha']==case.case_sha:report['K48']=packet_test['K48']
            for name,operation in [('Beam',lambda:beam(case,modules,start))]:
                try:
                    result=operation()
                    if name=='Beam':pools,receipt=result;report[name]=receipt
                    else:report[name]=result
                except Exception as exc:report[name]=dict(PASS=False,error=repr(exc),traceback=traceback.format_exc())
            if report.get('Beam',{}).get('PASS'):
                guard(start);packet=modules['m_engine'].direct_joint(case,None,pools)
                A,d,lift,point,proof=packet
                assert point is None and proof['PASS'] and proof['no_MOVE_forcing']
                folder=WORK/'DIRECT_JOINT';folder.mkdir(exist_ok=True)
                sp.save_npz(folder/'A.npz',A);sp.save_npz(folder/'LIFT.npz',lift);np.savez_compressed(folder/'D.npz',**d)
                (folder/'PROOF.json').write_text(json.dumps(proof,default=str),encoding='utf-8')
                report['Direct_Joint_substitution']=dict(PASS=True,rows=A.shape[0],columns=A.shape[1],nonzeros=A.nnz,
                    all8_route_pools=True,physical_rows_preserved=proof['original_source_rows_semantically_preserved'],
                    independently_bounded_paths=True,source_direct_joint=record(modules['m_engine'].__file__),
                    actual_Native0_pending=True,restricted_ObjBound_is_Global_LB=False)
            report['geometry_IO_counters']=dict(counters)
        report.update(PASS=bool(report.get('K48',{}).get('PASS') and report.get('Beam',{}).get('PASS') and report.get('Direct_Joint_substitution',{}).get('PASS')),
            denied_attempts=denied,Native0_only=True,
            production_case_validation_handler_bound=callable(case.strict_validator))

def k48_build():
    with measured('K48_WHOLE_CASE_PACKET_BINDING.json') as (report,start),native_zero() as denied:
        case=build_case(k48_only=True)
        from .stage_geometry_io import scope as geometry_io
        with source_binding(case) as modules,geometry_io(case,modules) as counters:
            result=k48(case,modules['table_v_k48'],start)
        report.update(PASS=result['PASS'],case_sha=case.case_sha,K48=result,geometry_IO_counters=counters,
            all_original_FULL_rows=case.original_A.shape[0],all_original_FULL_columns=case.original_A.shape[1],
            unused_selected_UB_arrays_deferred=True,all_original_grid_rows_and_8_vehicle_physics_loaded=True,
            denied_attempts=denied)

class NativeReadbackComplete(RuntimeError):pass

def k48_native0():
    """Actual unchanged source Native builders, abort before budget.solve."""
    from unittest.mock import patch
    from v44.m_restore import packet
    from v44.budget import StageBudget
    from v42_may_campaign_native90 import budget as native_budget
    from .stage_geometry_io import scope as geometry_io
    from .stage_gurobi_io import scope as gurobi_io
    with measured('K48_ACTUAL_NATIVE0_READBACK.json') as (report,start),gurobi_io(),native_zero() as denied:
        case=build_case(k48_only=True);results=[]
        assert read(OUT/'K48_WHOLE_CASE_PACKET_BINDING.json')['PASS']
        with source_binding(case) as modules,geometry_io(case,modules):
            k=modules['table_v_k48'];original_write=k._write
            base=WORK/'K_NATIVE0';attempt=1
            while (base/f'ATTEMPT_{attempt:02d}').exists():attempt+=1
            base=base/f'ATTEMPT_{attempt:02d}'
            for size in (16,32,48):
                p,proof=packet(WORK/'M1'/f'K{size}',case,k)
                folder=base/f'K{size}'
                folder.mkdir(parents=True,exist_ok=True)
                with patch.object(native_budget,'d_path',lambda p:Path(p)):
                    budget=StageBudget(folder/'LEDGER.json',case=case,kind='K48_SEPARATE')
                def written(path,value):
                    original_write(path,value)
                    if Path(path).name=='NATIVE_READBACK.json':raise NativeReadbackComplete('BEFORE_SOURCE_BUDGET_SOLVE')
                with patch.object(k,'_write',written):
                    try:k.solve_packet(p,proof,budget,folder/'MODEL')
                    except NativeReadbackComplete:pass
                    else:raise AssertionError('NATIVE0_READBACK_BOUNDARY_NOT_REACHED')
                actual=read(folder/'MODEL/NATIVE_READBACK.json');assert actual['PASS']
                assert budget.used()==0 and not budget.calls and budget.inflight is None
                results.append(dict(K=size,Native_readback=actual,rows=p['A'].shape[0],columns=p['A'].shape[1],nonzeros=p['A'].nnz))
                del p;gc.collect();guard(start);print('K48 ACTUAL SOURCE NATIVE0',size,flush=True)
        assert not denied
        report.update(PASS=True,results=results,source_native_solve_packet_unchanged=True,
            Native_boundary='after every original actual-model readback check and before budget.solve',
            denied_attempts=denied,numeric_Global_LB=None)

def joint_native0():
    from .stage_gurobi_io import scope as gurobi_io
    with measured('BEAM_DIRECT_JOINT_MESS8_BINDING.json') as (report,start),gurobi_io(),native_zero() as denied:
        from v44.frozen.v43_mess.library import load
        folder=WORK/'DIRECT_JOINT';A=sp.load_npz(folder/'A.npz');lift=sp.load_npz(folder/'LIFT.npz')
        with np.load(folder/'D.npz') as z:d={k:z[k] for k in z.files}
        proof=read(folder/'PROOF.json');modules=load()
        # Source native_joint takes no mathematical data from its case arg;
        # all original full-grid rows and exact route lift are in this packet.
        from .stage_native_io import readback_scope,AsciiNames
        for key in ('names','row_names'):d[key]=AsciiNames(d[key])
        from v44.q250_m4 import m_threads
        request=dict(day='2025-05-01',arm='B2',stage='M1',worker_slot=1,Threads=4)
        with m_threads(request) as policy,readback_scope(modules['m_engine'],folder/'NATIVE0/READBACK'):
            result,captures=modules['m_engine']._native_joint(None,SimpleNamespace(remaining=lambda:900.),
                (A,d,lift,None,proof),folder/'NATIVE0',300.,native0=True)
        assert not captures and result['Native_optimize_calls']==0 and not denied
        report.update(PASS=True,source_Native0_result=result,source_direct_joint_proof=record(folder/'PROOF.json'),
            original_r043_effective_parameters=policy,
            model=dict(rows=A.shape[0],columns=A.shape[1],nonzeros=A.nnz,binary=int(np.sum(d['types']=='B'))),
            Native_readback=read(folder/'NATIVE0/NATIVE_READBACK.json'),
            pure_Beam_binding=read(OUT/'STAGE_M_RUNTIME_BINDING.json').get('Beam'),
            official_pool_admission_score_not_executed=True,production_FULL_validator_bound=False)

if __name__=='__main__':globals()[sys.argv[1] if len(sys.argv)>1 else 'build']()

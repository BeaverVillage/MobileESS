"""Independent May date census and actual Production DW Native0 assembly.

No optimize/presolve/IIS is permitted. Run one date per process to release
the original integer model, sparse arrays and geometry caches on completion.
A2 requires an actual current M1 parent; absence is recorded, never forged.
"""
import os
for _name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_name]='1'
import argparse
from collections import Counter
from copy import deepcopy
import gc
import gzip
import json
from pathlib import Path
import pickle
import sys
from time import perf_counter
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def forbid_native():
    import v42_native
    import gurobipy as gp
    def deny(*args,**kwargs):raise PermissionError('AIDC_COMPRESSION_AUDIT_NATIVE_OPTIMIZE_FORBIDDEN')
    for name in ('optimize','presolve','computeIIS','feasRelax','feasRelaxS'):
        setattr(gp.Model,name,deny)


def capture_release_native0(context,case,built,folder):
    """Keep actual FULL bytes, release the audit-only native model before LP work.

    The production capture code executes unchanged up to its projection call.
    That boundary preserves only immutable indices/arrays, then the existing
    exact projection runs with its already supported model=None interface.
    This routing is confined to this Native0 process, never a Heavy executor.
    """
    from v42_integration.table_v_dw import capture_current_full,project_runtime_auxiliaries,objective_identity
    from v42_integration.table_v_compression_adapter import stage_binding
    from v42_a_stage_domain_v2.fast_backend import Backend
    from v42_may_campaign_native90.a_routing import rebound
    from v42_integration.m_engine import _write,file_record
    from v42_integration.table_v_memory import memory_sample
    model=built[0];metadata=deepcopy(built[6]);domains=model.__dict__['_table_v_authorized_domains']
    backend=Backend();backend.data=built[5];axes=backend._coupling_rows(model,built[4])
    objective=objective_identity(model);memo={};folder=Path(folder)
    class CaptureBoundary(Exception):pass
    def save_boundary(current,original,bindings,descriptor,data):
        memo.update(original=original,descriptor=descriptor,data=data,
            runtime={k:int(v.index) for k,v in bindings.get('Runtime_finish_counts',{}).items()
                     if hasattr(v,'index') and isinstance(v.index,int)},
            equalities=[i for i,name in enumerate(current.getAttr('ConstrName')) if name=='exact_Runtime_finish_count'],
            original_sha=original.fingerprint())
        raise CaptureBoundary()
    routed=rebound(capture_current_full,dict(capture_current_full.__globals__,project_runtime_auxiliaries=save_boundary))
    try:
        routed(context,case,built,folder)
        raise AssertionError('NATIVE0_FULL_CAPTURE_BOUNDARY_NOT_REACHED')
    except CaptureBoundary:
        pass
    finally:
        model.dispose()
    # Disposed Var proxies are unnecessary for any remaining Native0 checks.
    case.grid.planning_arrays=None
    _write(folder/'NATIVE0_NATIVE_MODEL_RELEASE.json',dict(Native_calls=0,native_model_disposed=True,
        original_FULL_snapshot_sha=memo['original_sha'],before_LP_projection=True,memory=memory_sample()))
    return memo,domains,axes,metadata,objective


def audit(day,output,*,matrix=False,reuse_capture=None):
    from v42_integration.release_date_case import compile_date_case
    from v42_integration.table_v_flex_planning import compile_table_v_flex_context,build_flex_native_model
    from v42_integration.table_v_geometry_cache import authorized_data
    from v42_integration.table_v_compression import semantic_classes,size
    from v42_integration.table_v_compression_adapter import VERSION
    from v42_integration.table_v_dw import audit_source_domain,prepare_current_dw,objective_identity,_freeze_sources
    from v42_integration.table_v_dates import require_day
    from v42_integration.table_v_memory import memory_sample
    from v42_integration.table_v_resources import admit_resources
    from v42_integration.m_engine import _write,file_record
    from v42_integration.a_engine import digest
    from v42_integration.d0_resource import native_binding
    from v42_a_stage_compact_rowgen.assembly import partition
    from v42_a_stage_phase1.core import elastic_master
    from v42_a_stage_phase1.backend import artificial_point
    import gurobipy as gp
    import psutil
    require_day(day);output=Path(output).resolve()
    if output.exists():raise FileExistsError('INDEPENDENT_DATE_AUDIT_MUST_NOT_OVERWRITE')
    output.mkdir(parents=True);forbid_native();started=perf_counter()
    _write(output/'START.json',dict(day=day,matrix=matrix,Native_calls=0,memory=memory_sample()))
    basic=compile_date_case(day,output=output/'INPUTS/BASIC',call_cap=5400.)
    context=compile_table_v_flex_context(basic,output=output/'INPUTS/FULL_FLEX',call_cap=5400.)
    _write(output/'SOURCE_DOMAIN_NATIVE0_AUDIT.json',audit_source_domain(context))
    rows=[];censuses=[]
    data,domains=authorized_data(SimpleNamespace(data=context['data'],window_slots=context['windows'],
        qos_receipts=context['receipts'],progress=None))
    for arm,stage in [('B1','A1'),('B3','A1'),('B3','A2')]:
        tick=perf_counter()
        # The complete current-day geometry is immutable. Each stage's class
        # key is recomputed, and actual grid/Fixed-MESS equality is a later
        # mandatory full-matrix gate, never inferred from this shared geometry.
        census=semantic_classes(data,domains,context['tablev_flex']['known_issued_receipts'])
        censuses.append(census)
        row=dict(day=day,arm=arm,stage=stage,Job_count=len(data[1]),class_before=len(data[7]['classes']),
            class_candidates=census['class_count'],class_after=None,class_sizes=census['class_sizes'],
            original_input_sha=context['input_audit']['a_input_sha'],source_sha=context['manifest']['source_sha'],
            source_identity=context['manifest']['identity'],Domain_sha=data[7]['physical_domain_hash'],
            initial_state_sha=context['state']['common_initial_state_sha'],semantic_sha=digest(census['identities']),
            domain_census_wall_seconds=perf_counter()-tick,domain_equivalence='PASS',
            mathematical_matrix_equivalence='NOT_YET_BUILT',pricing_coverage='NOT_YET_BUILT',
            DW_rows=None,DW_columns=None,DW_NNZ=None,FULL_rows=None,FULL_columns=None,FULL_NNZ=None,
            integer_compression_applied=False,model_build_wall_seconds=None,pricing_preparation_wall_seconds=None,
            Peak_RSS_bytes=None,Peak_private_commit_bytes=None,Native_calls=0,
            status='PENDING_ACTUAL_MATRIX_VALIDATION',blockers=[],
            classes_recomputed_from_current_date_and_stage=True,previous_day_classes_or_LB_imported=False)
        if stage=='A2':
            row.update(status='BLOCKED_CURRENT_M1_REQUIRED',blockers=['NO_CURRENT_FULL_M1_FIXED_MESS_PARENT_WITHIN_NATIVE0_SCOPE'],
                fixed_MESS_sha=None,compression_launchable=False,
                matrix_validation_rule='RECOMPUTE_AND_VERIFY_ACTUAL_A2_FULL_MATRIX_AFTER_CURRENT_M1',
                A1_coefficients_or_classes_authorized_for_A2=False)
        _write(output/(arm+'_'+stage+'_CENSUS.json'),dict(row,groups=census['groups'],identities=census['identities']))
        rows.append(row)
        print('CURRENT_DATE_CLASS_CENSUS',day,arm,stage,len(data[1]),census['class_count'],flush=True)
    if censuses[0]['groups']!=censuses[1]['groups']:
        raise ValueError('CURRENT_DAY_B1_B3_A1_SEMANTIC_IDENTITY_DRIFT')
    _write(output/'UID_AUTHORITY_LEDGER.json',dict(day=day,original_UID_receipts=censuses[0]['uid_ledger'],
        source_identity=context['manifest']['identity'],separate_stage_census=True))
    built=None;state=None
    try:
        if matrix:
            case=context['make_a_case']('A1',arm='B1',folder=output/'B1/A1')
            stub=SimpleNamespace(worker_lock=Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),path=output/'NATIVE0_RESOURCE_RECORD.json')
            resources=admit_resources(stub,phase='COMPRESSION_NATIVE0_PRE_ORIGINAL_MODEL')
            admission=dict(status='PASS',operation='TABLE_V_FULL_FLEX_A_NATIVE0_BUILD',case_sha=case.case_sha,
                concurrent_heavy_solver=False,resource_snapshot=resources)
            dw=output/'B1/A1/DW';dw.mkdir(parents=True);_freeze_sources(dw)
            if reuse_capture is not None:
                prior=Path(reuse_capture).resolve()
                from v42_integration.table_v_flex_planning import require_flex_case
                old_manifest=json.loads((prior/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text(encoding='utf8'))
                require_flex_case(old_manifest)
                if old_manifest!=context['manifest']:raise ValueError('NATIVE0_REUSE_CURRENT_EXACT_SOURCE_CASE_REQUIRED')
                rec=json.loads((prior/'B1/A1/DW/FULL_CAPTURE/ORIGINAL_FULL_CAPTURE_RECEIPT.json').read_text(encoding='utf8'))['capture']
                if file_record(rec['path'])!=rec:raise ValueError('NATIVE0_REUSE_ORIGINAL_CAPTURE_SHA_DRIFT')
                with gzip.open(rec['path'],'rb') as stream:raw=pickle.load(stream)
                if (raw['case_sha']!=case.case_sha or raw['source_identity']!=context['manifest']['identity']
                        or raw['input_sha']!=context['input_audit']['a_input_sha']):
                    raise ValueError('NATIVE0_REUSE_FULL_MATRIX_STAGE_INPUT_SHA_DRIFT')
                metadata=json.loads((prior/'ORIGINAL_FULL_INTEGER_NATIVE0.json').read_text(encoding='utf8'))
                if metadata['native_binding']!=raw['native_binding']:raise ValueError('NATIVE0_REUSE_NATIVE_MATRIX_BINDING_DRIFT')
                memo=dict(original=raw['original'],descriptor=raw['original_descriptor'],data=raw['data'],
                    runtime=raw['original_runtime_bindings'],equalities=raw['runtime_equality_rows'],original_sha=raw['original'].fingerprint())
                verified_domains=domains;axes=raw['coupling_rows'];objective=raw['objective_sha']
                model_seconds=metadata['model_build_seconds']
                (dw/'FULL_CAPTURE').mkdir()
                import shutil
                source_snapshot=prior/'B1/A1/DW/FULL_CAPTURE/ORIGINAL_FULL_SNAPSHOT.pkl.gz'
                shutil.copyfile(source_snapshot,dw/'FULL_CAPTURE/ORIGINAL_FULL_SNAPSHOT.pkl.gz')
                _write(output/'ORIGINAL_FULL_INTEGER_NATIVE0.json',metadata)
                _write(output/'EXACT_CAPTURE_REUSE.json',dict(PASS=True,capture=rec,
                    current_exact_Source_Case_Input_NativeMatrix_verified=True,Native_calls=0))
                raw=None;gc.collect()
            else:
                tick=perf_counter();built=build_flex_native_model(case,build_admission=admission)
                built[0].Params.Threads=1;built[0].Params.OutputFlag=0
                built[0].setObjective(dict(built[2])['rho'],gp.GRB.MINIMIZE);built[0].update()
                built[6]['native_binding']=native_binding(built[0]);model_seconds=perf_counter()-tick
                _write(output/'ORIGINAL_FULL_INTEGER_NATIVE0.json',dict(built[6],model_build_seconds=model_seconds,
                    objective_sha=objective_identity(built[0]),integer_compression_applied=False))
                memo,verified_domains,axes,metadata,objective=capture_release_native0(context,case,built,dw/'FULL_CAPTURE')
            built=None;gc.collect()
            from v42_integration.table_v_dw import project_runtime_auxiliaries
            if memo['original'].fingerprint()!=memo['original_sha']:
                raise ValueError('NATIVE0_ORIGINAL_ARRAYS_CHANGED_ON_NATIVE_MODEL_DISPOSE')
            projected,descriptor,projection=project_runtime_auxiliaries(None,memo['original'],
                dict(Runtime_finish_counts=memo['runtime'],_runtime_equality_rows=memo['equalities']),
                memo['descriptor'],memo['data'])
            captured=dict(data=memo['data'],original=memo['original'],projected=projected,descriptor=descriptor,
                runtime_projection=projection,coupling_rows=axes,case_sha=case.case_sha,objective_sha=objective,
                native_binding=metadata['native_binding'],source_identity=context['manifest']['identity'],
                input_sha=context['input_audit']['a_input_sha'])
            from v42_integration.table_v_compression_adapter import stage_binding
            captured['stage_binding']=stage_binding(context,case,captured)
            from v42_a_stage_domain_v2.active import cache_noop_check
            for domain in verified_domains.values():domain.cache.check=cache_noop_check
            domain_path=dw/'NATIVE0_VERIFIED_DOMAIN_CACHE.pkl.gz'
            with gzip.open(domain_path,'xb',compresslevel=1) as stream:
                pickle.dump(dict(source_identity=context['manifest']['identity'],domains=verified_domains),stream,protocol=5)
            packet_path=dw/'FULL_CAPTURE/FULL_DW_CAPTURE.pkl.gz'
            with gzip.open(packet_path,'xb',compresslevel=1) as stream:pickle.dump(captured,stream,protocol=5)
            _write(dw/'FULL_CAPTURE/FULL_DW_CAPTURE_RECEIPT.json',dict(PASS=True,capture=file_record(packet_path),
                original_FULL_snapshot=file_record(dw/'FULL_CAPTURE/ORIGINAL_FULL_SNAPSHOT.pkl.gz'),
                case_sha=case.case_sha,native_binding=metadata['native_binding'],objective_sha=objective,Native_calls=0))
            built=[None]*5+[captured['data'],metadata]
            memo=None;projected=None;descriptor=None;verified_domains=None;gc.collect()
            state=prepare_current_dw(context,case,built,dw,captured=captured,
                independent_domain_receipt=file_record(domain_path))
            captured=None
            local,owned=partition(state['compact'],state['metas'],state['grows'])
            _,witness=artificial_point(elastic_master(state['compact'],state['grows']),state['prior_compact'])
            if not witness['PASS']:raise ValueError('ORIGINAL_PHASE_I_INITIAL_WITNESS_FAILED')
            roster=json.loads((dw/'BLOCK_PRICING_ORACLE_VERIFICATION.json').read_text(encoding='utf8'))['records']
            if (len(roster)!=len(local) or set(owned.values())!={k for k,m in state['metas'].items() if m['width']}):
                raise ValueError('CURRENT_DATE_FULL_PRICING_CLASS_COVERAGE')
            for record in roster:
                if file_record(record['external_full_block_cache']['path'])!=record['external_full_block_cache']:
                    raise ValueError('CURRENT_DATE_PRICING_CACHE_BYTES_DRIFT')
                with gzip.open(record['external_full_block_cache']['path'],'rb') as stream:cache=pickle.load(stream)
                if not cache['snapshot'].require():raise ValueError('INVALID_COMPLETE_LOCAL_PRICING_SNAPSHOT')
            from v42_a_stage_canary import pricing
            from v42_may_campaign_native90.a_routing import rebound
            import numpy as np
            oracle=rebound(pricing.full_pricing,dict(pricing.full_pricing.__globals__,HISTORY=dw))
            coverage,_=oracle(SimpleNamespace(remaining=lambda:1.),state['compact'],None,
                dict(X=state['prior_compact'],Pi=np.zeros(state['compact'].matrix.shape[0])),None,
                state['data'],state['domains'],state['ledger'],state['axes'],state['n'],state['grows'],
                local,owned,dw/'ANALYTICAL_ZERO_DUAL_COVERAGE',zero=True)
            if not coverage['PASS'] or not coverage['complete_STAY_and_migration_coverage']:
                raise ValueError('CURRENT_DATE_UNCHANGED_FULL_PRICING_COVERAGE_FAILED')
            profile=json.loads((dw/'CLASS_COMPRESSION_BUILD_PROFILE.json').read_text(encoding='utf8'))
            proof=json.loads((dw/'AIDC_FULL_DW_COMPRESSION_CERTIFICATE.json').read_text(encoding='utf8'))
            other=context['make_a_case']('A1',arm='B3',folder=output/'B3/A1')
            if (other.case_sha!=case.case_sha or other.grid.fixed_mess!=case.grid.fixed_mess
                    or other.d0_input_audit!=case.d0_input_audit):
                raise ValueError('B3_A1_EXACT_CURRENT_CASE_FIXED_MESS_INPUT_DRIFT')
            for row in rows[:2]:
                row.update(class_after=len(state['metas']),DW_rows=state['compact'].matrix.shape[0],
                    DW_columns=state['compact'].matrix.shape[1],DW_NNZ=state['compact'].matrix.nnz,
                    FULL_rows=metadata['rows'],FULL_columns=metadata['columns'],FULL_NNZ=metadata['nonzeros'],
                    original_DW_size=size(state['_class_sum']['original_LP']),
                    mathematical_matrix_equivalence='PASS_INDEPENDENT_ALL_UID_ACTUAL_A_B_RHS_BOUNDS_OBJECTIVE',
                    pricing_coverage='PASS_UNCHANGED_FULL_ORACLE_ZERO_DUAL_ANALYTICAL_NOT_PRODUCTION_LB',
                    model_build_wall_seconds=model_seconds,compression_prepare_wall_seconds=profile['wall_seconds'],
                    pricing_preparation_wall_seconds=profile['pricing_preparation_seconds'],
                    Peak_RSS_bytes=profile['peak_RSS_bytes'],Peak_private_commit_bytes=profile['peak_private_commit_bytes'],
                    fixed_MESS_sha=case.grid.fixed_mess['plan_sha'],stage_case_sha=case.case_sha,status='PASS_NATIVE0_MATRIX',
                    compression_launchable=True,certificate=file_record(dw/'AIDC_FULL_DW_COMPRESSION_CERTIFICATE.json'),
                    FULL_integer_compression_rows_removed=0,FULL_integer_compression_columns_removed=0,
                    FULL_integer_compression_NNZ_removed=0,
                    scaling_fallback_classes=[r['class_id'] for r in state['_class_sum']['result']['records'] if r['scaling_fallback']],
                    class_reduction_fraction=1-len(state['metas'])/row['class_before'],
                    DW_row_reduction_fraction=1-state['compact'].matrix.shape[0]/state['_class_sum']['original_LP'].matrix.shape[0],
                    DW_column_reduction_fraction=1-state['compact'].matrix.shape[1]/state['_class_sum']['original_LP'].matrix.shape[1],
                    DW_NNZ_reduction_fraction=1-state['compact'].matrix.nnz/state['_class_sum']['original_LP'].matrix.nnz,
                    exact_same_day_B1_B3_A1_matrix_inputs_replayed=True)
            _write(output/'MATRIX_PROOF.json',dict(PASS=True,Native_calls=0,rows=rows[:2],
                actual_original_source_Phase_I_initial_witness=witness,original_FULL_integer_unchanged=True,
                model_build_and_matrix_checks_only=True,Global_LB=None,UB=None,Gap=None))
    finally:
        if built is not None and built[0] is not None:built[0].dispose()
        state=None;built=None;data=None;domains=None;censuses=None;census=None
        gc.collect()
        _write(output/'MEMORY_RELEASE.json',dict(memory=memory_sample(),models_disposed=True,
            process_exit_releases_all_native_and_python_allocations=True))
    result=dict(schema='TABLE_V_MAY_COMPRESSION_NATIVE0_DATE_AUDIT_V1',day=day,rows=rows,
        Native_calls=0,P2_calls=0,R2='HOLD',Worker=1,Threads=1,version=VERSION,
        total_wall_seconds=perf_counter()-started,month_Heavy_approval=False)
    _write(output/'RESULT.json',result)
    print('DATE_COMPRESSION_NATIVE0_COMPLETE',day,[(r['arm'],r['stage'],r['status']) for r in rows],flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--day',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--matrix',action='store_true');parser.add_argument('--reuse-capture',type=Path);args=parser.parse_args()
    audit(args.day,args.output,matrix=args.matrix,reuse_capture=args.reuse_capture)

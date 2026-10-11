"""Restore the failed Source18 Native0 artifacts under reviewed repair authority.

Only saved structural matrices/domains/certificates are imported. No incumbent,
solver bound, checkpoint or start is read. Original Gurobi/domain producers are
denied; Compact and exact Static algebra are reconstructed from saved FULL CSR.
The same verified live case may then enter the separately capped Root probe.
"""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import time
import traceback
import numpy as np
from scipy import sparse

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import atomic, read, record, digest, now, sha
from v42_common_campaign.authority import source_files
from validate_svr11_dense_response import census, native_gate

OLD=Path(r'D:\v42_svr11_may_20261011_16')
PREDECESSOR=Path(r'D:\v42_dense_response_development_20261011')
DEV=Path(r'D:\v42_dense_response_development_repair_20261011')
DAY='2025-05-01'
GENERATION_SHA='4f6142c38017199a85afb0c80d13059b5644b972af79c894c94309d1194dc261'
GENERATION_COMMIT='af8b279c9c8edbd287e85275ae90fea07f1bf2fe'
GENERATION_CASE_SHA='c56d4566c1a1e374ad8c61686a459d5e8f94805582566ce86ccc4d8a6b088a8b'
REVIEWED_ADAPTER_SHA='1f4d556081e0814b7af1378635e2174fd2340ba245d9c67f661c0f02245405c9'
PACKETS=('FULL_A.npz','FULL_DATA.npz','C3A_A.npz','C3A_DATA.npz',
 'DENSE_RESPONSE_A.npz','DENSE_RESPONSE_DATA.npz','CURRENT_C2_AXES.npz',
 'CURRENT_C2_ALIASES.json','CURRENT_C2_ROW_PROOFS.json','CURRENT_C3A_AXES.npz',
 'CURRENT_C3A_ROW_CERTIFICATES.json','CURRENT_C3A_BOUND_PROOFS.json',
 'CURRENT_EXACT_C3A_PROOF.json','CURRENT_SECURITY_PRE_C2_SUMMARY.json',
 'CURRENT_SECURITY_PRE_C2_ROW_CERTIFICATES.json','CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json',
 'DENSE_RESPONSE_AXES.npz','DENSE_RESPONSE_PLANS.json','DENSE_RESPONSE_EQUIVALENCE.json',
 'EXACT_PHYSICAL_PRESCREEN.json','EXACT_GRID_OUTER_PRESCREEN.json',
 'ORIGINAL_DOMAIN_EQUIVALENCE.json','FIXED_AIDC_ANCHOR.json',
 'INPUT_AND_SOURCE_IDENTITY.json','SCIENTIFIC_CASE_IDENTITY.json')
RUNNERS=('tools/validate_svr11_dense_restore.py','tools/validate_svr11_dense_response.py',
 'tools/validate_svr11_root180.py','tools/root180_completion.py','tools/prepare_svr11_epoch17.py')


def require(condition, message):
    if not condition:raise PermissionError(message)


def generation_transition(started,sources):
    require(started['source_SHA']==GENERATION_SHA and started['source_commit']==GENERATION_COMMIT,
        'RESTORE_UNREVIEWED_GENERATION_AUTHORITY')
    previous=started['execution_sources']
    require(digest(previous)==GENERATION_SHA,'RESTORE_GENERATION_SOURCE_SEAL_DRIFT')
    require(set(previous)==set(sources),'RESTORE_EXECUTION_SOURCE_SET_DRIFT')
    changed=[n for n in sources if sources[n]!=previous[n]]
    require(set(changed)<={'v42_may_campaign_native90/m_model.py'},
        'RESTORE_PROTECTED_MATHEMATICAL_SOURCE_DRIFT')
    require(sources['v42_may_campaign_native90/m_model.py']==REVIEWED_ADAPTER_SHA,
        'RESTORE_ADAPTER_IS_NOT_THE_REVIEWED_METADATA_REPAIR')
    return dict(generation_source_SHA=GENERATION_SHA,generation_source_commit=GENERATION_COMMIT,
        validation_source_SHA=digest(sources),changed_execution_files=changed,
        reviewed_validation_adapter_SHA=REVIEWED_ADAPTER_SHA,
        unchanged_C3A_Dense_Physical_Grid_and_static_mathematical_sources=True)


def checked_generation_identity(saved):
    require(saved['case_sha']==GENERATION_CASE_SHA,'RESTORE_UNREVIEWED_GENERATION_CASE')
    identity={k:v for k,v in saved.items() if k!='case_sha'}
    require(digest(identity)==GENERATION_CASE_SHA,'RESTORE_GENERATION_CASE_SHA_DRIFT')
    return identity


def checked_packet_authority(identity,section,old_output,sources,allow_adapter=False):
    authority=identity[section]
    require(authority.get('proof',identity.get('transport',{})).get('PASS') is True,
        'RESTORE_PREDECESSOR_PROOF_NOT_PASS:'+section)
    certificate=authority['certificate'];path=Path(certificate['path']).resolve()
    require(path.parent==old_output.resolve() and path.name in PACKETS,
        'RESTORE_CERTIFICATE_NOT_OWNED_BY_NATIVE0_ATTEMPT')
    require(record(path)==certificate,'RESTORE_PREDECESSOR_CERTIFICATE_SHA_DRIFT')
    proof=read(path);expected=identity['transport'] if section=='transport_authority' else authority['proof']
    require(digest(proof)==digest(expected),'RESTORE_PREDECESSOR_CANONICAL_PACKET_DRIFT')
    for name,item in authority['sources'].items():
        if allow_adapter and name=='v42_may_campaign_native90/m_model.py':continue
        require(name in sources and sources[name]==item['sha256'],
            'RESTORE_PREDECESSOR_MATHEMATICAL_SOURCE_DRIFT:'+name)
    return proof


def saved_security(compact,graph,output):
    certificates=read(output/'CURRENT_SECURITY_PRE_C2_ROW_CERTIFICATES.json')
    bounds=read(output/'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json')
    lower=compact.d['lower'].copy();upper=compact.d['upper'].copy();seen=set()
    for item in bounds:
        j=int(item['column'])
        require(j not in seen and 0<=j<len(lower),'RESTORE_SECURITY_BOUND_AXIS')
        seen.add(j)
        require(item['name']==str(compact.d['names'][j])
            and float(item['old_lower'])==lower[j] and float(item['old_upper'])==upper[j],
            'RESTORE_SECURITY_OLD_BOUND_DRIFT')
        lower[j]=float(item['new_lower']);upper[j]=float(item['new_upper'])
    return dict(certificates=certificates,bounds=bounds,lower=lower,upper=upper,
        summary=read(output/'CURRENT_SECURITY_PRE_C2_SUMMARY.json'),battery=graph[3])


@contextmanager
def restore_only_guard():
    """Final native readback is outside this scope; all producers are denied."""
    import gurobipy as gp
    import v42_native.mess as native
    import v42_native.mess_domain as domain
    import v42_may_campaign_native90.m_model as constructor
    import v42_ultracompact.current as current
    import v42_ultracompact.security as security
    import v42_ultracompact.response as response
    attempts=[]
    def denied(*args,**kwargs):
        attempts.append(dict(UTC=now(),error='RESTORE_ORIGINAL_OR_DOMAIN_PRODUCER_DENIED'))
        raise PermissionError('RESTORE_ORIGINAL_OR_DOMAIN_PRODUCER_DENIED')
    with ExitStack() as stack:
        for obj,name in ((gp,'Model'),(gp,'read'),(native,'solve'),(native,'optimize'),
                (domain,'_cached'),(domain,'build_domain'),(constructor,'build_case'),
                (current,'reduce_current_c3a'),(security,'prepare_current_security'),
                (response,'reformulate_responses')):
            stack.enter_context(patch.object(obj,name,denied))
        yield attempts


def load_stage(output,prefix):
    A=sparse.load_npz(output/(prefix+'_A.npz')).tocsr(copy=False)
    with np.load(output/(prefix+'_DATA.npz'),allow_pickle=False) as z:d={k:z[k] for k in z.files}
    return A,d


def rebind_canonical(authority,proof,output,sources):
    path=output/Path(authority['certificate']['path']).name
    require(digest(read(path))==digest(proof),'RESTORE_COPIED_CANONICAL_PACKET_DRIFT')
    return dict(state_sha=authority['state_sha'],proof=read(path),certificate=record(path),
        sources={name:record(SOURCE/name) for name in authority['sources']})


def restore_case(bundle,planning,fixed,request,sources,generation,output,progress):
    import v42_may_campaign_native90.m_model as constructor
    from v42_bootstrap.m1 import native_inputs
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_ultracompact.current import CurrentC3A
    from v42_ultracompact.response import ReformulationResult,state_sha
    from v42_ultracompact.response_verify import verify_response_reformulation
    from v42_m1_hybrid.blocks import matrix_sha
    saved=read(output/'SCIENTIFIC_CASE_IDENTITY.json');identity=checked_generation_identity(saved)
    require(digest(bundle)==identity['bundle_sha'] and digest(fixed['identity'])==digest(identity['input_identity']),
        'RESTORE_FRESH_INPUT_IDENTITY_DRIFT')
    old_output=PREDECESSOR/'dates/B2'/DAY/'attempts/native0_once/output'
    old_proofs={name:checked_packet_authority(identity,name,old_output,sources,
        allow_adapter=name=='transport_authority') for name in (
        'transport_authority','c3_authority','response_authority',
        'physical_prescreen_authority','grid_prescreen_authority')}
    sites,initial,routes,battery,receipt=native_inputs(bundle)
    graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
        [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
    physical=constructor.restore_physical_domain(old_proofs['physical_prescreen_authority'],graph)
    from v42_temporal.native import load_power
    from v42_pr134_b1.native import original_coefficients_for_day
    import v42_may01.prepare as original
    cert,_,_,_=load_power(bundle);coeff=original_coefficients_for_day(original,cert,DAY)
    require(len(coeff)==96 and all(c.slot==t for t,c in enumerate(coeff)),'RESTORE_COEFFICIENT_TIME_AXIS')
    anchor=read(output/'FIXED_AIDC_ANCHOR.json')
    require(digest(anchor)==identity['anchor_sha'],'RESTORE_FIXED_AIDC_ANCHOR_DRIFT')
    columns=list(coeff[0].control_names);pcc=np.asarray(planning['PCC_P_kw'],dtype=float);aidc=list(map(str,planning['sites']))
    require(pcc.shape==(96,12) and len(set(aidc))==12 and set(aidc)==set(bundle['capacities']),
        'RESTORE_FRESH_PCC_AXIS_DRIFT')
    require(anchor['control_names']==columns and anchor['independent_AIDC_identity']==fixed['identity'],
        'RESTORE_AIDC_FORECAST_AUTHORITY_DRIFT')
    for t,c in enumerate(coeff):
        require(list(c.control_names)==columns,'RESTORE_CONTROL_AXIS_DRIFT')
        expected=[]
        for n in columns:
            site=n.split('[',1)[1][:-1]
            if n.startswith('aidc_load_kw'):expected.append(float(pcc[t,aidc.index(site)]))
            elif n.startswith(('mess_p_kw','mess_q_kvar')):expected.append(0.)
            else:raise ValueError('RESTORE_UNKNOWN_CONTROL_FAMILY')
        require(expected==anchor['controls'][t],'RESTORE_FRESH_FIXED_AIDC_CONTROL_DRIFT')
    progress(dict(phase='RESTORE_FULL_CSR_COMPACT_AND_STATIC'))
    A,d=load_stage(output,'FULL')
    require(matrix_sha(A)==identity['original_matrix_sha'] and constructor._domain_sha(d)==identity['original_domain_sha'],
        'RESTORE_SAVED_FULL_MATHEMATICAL_STATE_DRIFT')
    compact=Compact(A,d,graph[2],initial,96)
    pre=saved_security(compact,graph,output)
    presolve=Presolve(compact.A,dict(compact.d,lower=pre['lower'],upper=pre['upper']))
    presolve.current_security=pre;presolve.bound.extend(pre['bounds'])
    presolve.row_delete({int(p['row']) for p in pre['certificates']},pre['certificates'])
    security_size=census(presolve.A,presolve.d)
    presolve.run()
    for name,value in (('CURRENT_C2_ALIASES.json',presolve.steps),('CURRENT_C2_ROW_PROOFS.json',presolve.rows)):
        require(digest(value)==digest(read(output/name)),'RESTORE_STATIC_PACKET_DRIFT:'+name)
    with np.load(output/'CURRENT_C2_AXES.npz',allow_pickle=False) as z:
        require(np.array_equal(z['rows'],presolve.row_ids) and np.array_equal(z['columns'],presolve.col_ids),
            'RESTORE_STATIC_AXIS_DRIFT')
    require(constructor._transport_state_sha(compact,presolve,graph)==identity['transport_authority']['state_sha'],
        'RESTORE_STATIC_MATHEMATICAL_STATE_DRIFT')
    progress(dict(phase='RESTORE_FRESH_INDEPENDENT_TRANSPORT_REPLAY'))
    transport=constructor.verify_transport(compact,presolve)
    require(transport.get('PASS') is True and transport.get('integer_and_full_LP_domains_identical') is True
        and transport.get('daily_alias_replay_performed') is not False,'RESTORE_FULL_INDEPENDENT_TRANSPORT_REQUIRED')
    C,c=load_stage(output,'C3A')
    with np.load(output/'CURRENT_C3A_AXES.npz',allow_pickle=False) as z:
        row_ids=z['rows'];require(np.array_equal(z['columns'],np.arange(C.shape[1])),'RESTORE_C3A_COLUMN_AXIS_DRIFT')
    ultra=CurrentC3A(presolve.A,presolve.d,C,c,row_ids,
        read(output/'CURRENT_C3A_ROW_CERTIFICATES.json'),read(output/'CURRENT_C3A_BOUND_PROOFS.json'),
        old_proofs['c3_authority'],A,d)
    require(constructor._c3_state_sha(ultra)==identity['c3_authority']['state_sha'],
        'RESTORE_C3A_FULL_MATHEMATICAL_STATE_DRIFT')
    require(matrix_sha(C)==identity['C3A_matrix_sha'] and constructor._domain_sha(c)==identity['C3A_domain_sha'],
        'RESTORE_C3A_SELECTED_STATE_DRIFT')
    require(ultra.proof.get('independent_model_proof_replayed') is True
        and ultra.proof.get('integer_and_full_LP_domains_identical') is True,'RESTORE_C3A_INDEPENDENT_PROOF_REQUIRED')
    c3_authority=constructor._freeze_c3(ultra,output)
    transport.update(C3A_policy=identity['C3A_policy'],selected_C3A_independent_proof_PASS=True,
        selected_C3A_rows_removed=ultra.proof['removed_rows'],selected_C3A_bounds_tightened=ultra.proof['bounds_tightened'],
        selected_C3A_original_P1_bit_exact=ultra.proof['original_P1_bit_exact'],
        selected_C3A_integer_and_full_LP_domains_identical=ultra.proof['integer_and_full_LP_domains_identical'])
    transport_authority=constructor._freeze_transport(compact,presolve,graph,transport,output)
    B,e=load_stage(output,'DENSE_RESPONSE')
    with np.load(output/'DENSE_RESPONSE_AXES.npz',allow_pickle=False) as z:rows=z['rows'];cols=z['columns']
    response=ReformulationResult(C,c,B,e,rows,cols,read(output/'DENSE_RESPONSE_PLANS.json'),old_proofs['response_authority'])
    require(state_sha(response)==identity['response_authority']['state_sha'],'RESTORE_DENSE_FULL_MATHEMATICAL_STATE_DRIFT')
    fresh_response_proof=verify_response_reformulation(response)
    require(fresh_response_proof.get('PASS') is True,'RESTORE_DENSE_INDEPENDENT_PROOF_REQUIRED')
    response.proof=dict(response.proof,**fresh_response_proof)
    response_authority=constructor._freeze_response(response,output)
    physical_authority=rebind_canonical(identity['physical_prescreen_authority'],old_proofs['physical_prescreen_authority'],output,sources)
    grid_authority=rebind_canonical(identity['grid_prescreen_authority'],old_proofs['grid_prescreen_authority'],output,sources)
    identity.update(transport=transport,transport_authority=transport_authority,c3_authority=c3_authority,
        response_authority=response_authority,physical_prescreen_authority=physical_authority,
        grid_prescreen_authority=grid_authority,saved_native0_generation_source_SHA=GENERATION_SHA,
        source_transition=generation,saved_native0_predecessor_case_SHA=saved['case_sha'])
    case=constructor.CampaignMCase(B,e,A,d,None,graph,digest(identity),identity,compact,presolve,
        bundle,anchor,planning,coeff,output,ultra,response,physical_domain=physical)
    require(matrix_sha(B)==identity['selected_matrix_sha'] and constructor._domain_sha(e)==identity['selected_domain_sha'],
        'RESTORE_FINAL_MATHEMATICAL_STATE_DRIFT')
    atomic(output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**identity))
    atomic(output/'INPUT_AND_SOURCE_IDENTITY.json',dict(day=DAY,case_sha=case.case_sha,input_identity=fixed['identity'],
        route_table=record(bundle['route_table']['path']),electrical_certificate=record(bundle['electrical_certificate']['path']),
        generation_source_SHA=GENERATION_SHA,validation_source_SHA=digest(sources)))
    return case,security_size


def seal_run_guard(sources,runners,generation,copied,proof,denied,output):
    require(source_files()==sources and all(sha(SOURCE/n)==r['sha256'] for n,r in runners.items()),
        'RESTORE_SOURCE_OR_RUNNER_DRIFT')
    require(not denied and proof.get('PASS') is True,'RESTORE_DENIED_PRODUCER_OR_PROOF_FAILURE')
    for item in copied:require(record(item['original']['path'])==item['original'],'RESTORE_IMMUTABLE_PREDECESSOR_DRIFT')
    path=DEV/'RESTORE_RUN_GUARD.json'
    atomic(path,dict(PASS=True,source_SHA=digest(sources),runner_sources=runners,
        source_transition=generation,immutable_predecessor_files=copied,
        original_Gurobi_model_rebuilds=0,physical_domain_producer_calls=0,
        denied_original_or_domain_producer_attempts=denied,Native_optimize_calls=0,
        Gurobi_presolve_calls=0,prior_optimization_points_bounds_starts_read=0,UTC=now()))
    return record(path)


def run(*,run_root=False):
    require(not (DEV/'NATIVE0_STARTED.json').exists(),'RESTORE_RECEIPT_EXISTS_USE_REVIEWED_NEW_DIRECTORY')
    old_start=read(PREDECESSOR/'NATIVE0_STARTED.json');failure=read(PREDECESSOR/'VALIDATION_ERROR.json')
    require(old_start['Native_optimize_calls']==old_start['Gurobi_presolve_calls']==0
        and failure.get('Native_optimize_calls')==0 and failure.get('Native_Runtime')==0
        and failure.get('error')=="ValueError('CURRENT_M_PHYSICAL_PRESCREEN_PACKET_DRIFT')",
        'RESTORE_PREDECESSOR_NOT_THE_REVIEWED_PRE_NATIVE_FAILURE')
    sources=source_files();source_sha=digest(sources);generation=generation_transition(old_start,sources)
    generation.update(predecessor_failure=record(PREDECESSOR/'VALIDATION_ERROR.json'),
        predecessor_generation_seal=record(PREDECESSOR/'NATIVE0_STARTED.json'),
        predecessor_validation_PASS=False,predecessor_Native_calls=0,
        unchanged_saved_structural_matrices_and_domains=True)
    DEV.mkdir(exist_ok=True);output=DEV/'dates/B2'/DAY/'attempts/native0_restored/output';output.mkdir(parents=True,exist_ok=False)
    runners={n:record(SOURCE/n) for n in RUNNERS};commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
    started=time.perf_counter()
    atomic(DEV/'NATIVE0_STARTED.json',dict(source_SHA=source_sha,source_commit=commit,
        execution_sources=sources,runner_sources=runners,source_transition=generation,
        Native_optimize_calls=0,Gurobi_presolve_calls=0,UTC=now()))
    def progress(value):atomic(DEV/'PROGRESS.json',dict(value,source_SHA=source_sha,
        wall_seconds=time.perf_counter()-started,Native_optimize_calls=0,UTC=now()))
    old_output=PREDECESSOR/'dates/B2'/DAY/'attempts/native0_once/output';copied=[]
    for name in PACKETS:
        origin=old_output/name;before=record(origin);target=output/name;shutil.copyfile(origin,target)
        require(sha(target)==before['sha256'],'RESTORE_COPY_SHA_DRIFT')
        copied.append(dict(original=before,copied=record(target)))
    active=copy.deepcopy(read(OLD/'CAMPAIGN_MANIFEST.json'));active['independent_model_proof_replay']=True
    folder=OLD/'inputs/B2'/DAY;bundle=read(folder/'NATIVE_INPUT.json');fixed=read(folder/'B2_FIXED_AIDC.json')
    require(record(fixed['physical']['path'])==fixed['physical'],'RESTORE_FRESH_FIXED_INPUT_DRIFT')
    with np.load(fixed['physical']['path'],allow_pickle=False) as z:planning={k:z[k] for k in z.files}
    request=dict(root=str(DEV),campaign_root=str(DEV),arm='B2',day=DAY,attempt_id='native0_restored',
        output=str(output),source_SHA=source_sha,development_only=True,production_results_promoted=0)
    atomic(DEV/'REQUEST.json',request)
    from v42_svr11.authority import _active
    from v42_thermal.authority import current_authority
    from v42_may_campaign_native90.preflight import native_zero
    token=_active.set(active);current_authority.cache_clear()
    try:
        import v42_may_campaign_native90.m_model as constructor
        from v42_ultracompact.native_readback import ROOT_PARAMETERS,snapshot,verify_root_readback
        restore_started=time.perf_counter()
        with native_zero() as calls:
            with restore_only_guard() as denied:
                case,security_size=restore_case(bundle,planning,fixed,request,sources,generation,output,progress)
                proof=constructor.verify_case(case)
                require(not denied and not calls and proof.get('PASS') is True,'RESTORE_CURRENT_CASE_PROOF_REQUIRED')
                physical_size=census(case.original_A,case.original_d)
                sizes=dict(Original=physical_size,Physical=physical_size,
                    Compact=census(case.compact.A,case.compact.d),Security=security_size,
                    Static=census(case.presolve.A,case.presolve.d),
                    C3A=census(case.ultra.A,case.ultra.d),Dense=census(case.A,case.d))
            restore_wall=time.perf_counter()-restore_started
            atomic(DEV/'MATRIX_CENSUS.json',sizes)
            progress(dict(phase='RESTORED_NATIVE0_FINAL_MODEL_IDENTITY_AND_PARAMETER_READBACK'))
            from v42_common_mess.model import build,memory_observation
            readback_out=output/'FINAL_NATIVE0_READBACK';readback_out.mkdir()
            model,variables,identity=build(case,readback_out,numeric_parameters=ROOT_PARAMETERS)
            try:
                import gurobipy as gp
                nodes=DEV/'native_nodes';nodes.mkdir(exist_ok=True)
                model.Params.MIPGap=.03;model.Params.MIPGapAbs=0.;model.Params.SolutionLimit=gp.GRB.MAXINT
                model.Params.TimeLimit=600.;model.Params.NodefileDir=str(nodes)
                actual=snapshot(model);checked=verify_root_readback(actual)
                atomic(readback_out/'ACTUAL_PARAMETERS.json',dict(actual,verification=checked))
            finally:model.dispose()
        require(not calls,'RESTORE_NATIVE_ZERO_ATTEMPT_PREVENTS_QUALIFICATION')
        physical=case.identity['physical_prescreen_authority']['proof'];gate=native_gate(physical,sizes,proof)
        guard=seal_run_guard(sources,runners,generation,copied,proof,denied,output)
        copy_proof=dict(method='RESTORE_SAVED_NATIVE0_CSR_NO_ORIGINAL_MODEL_REBUILD',
            original_Gurobi_model_rebuilds=0,inherited_original_constructor_wall_seconds=None,
            inherited_constructor_last_progress_lower_bound_seconds=1305.356,
            case_restore_wall_seconds=restore_wall,saved_generation_source_SHA=GENERATION_SHA)
        report=dict(PASS=True,classification='EXACT_RESTORED_NATIVE0_VALIDATED_ROOT_NOT_MEASURED',
            source_SHA=source_sha,source_commit=commit,source_seal=record(DEV/'NATIVE0_STARTED.json'),
            generation_source_SHA=GENERATION_SHA,source_transition=generation,restore_run_guard=guard,
            case_SHA=case.case_sha,original_matrix_SHA=case.identity['original_matrix_sha'],
            original_domain_SHA=case.identity['original_domain_sha'],selected_matrix_SHA=case.identity['selected_matrix_sha'],
            selected_domain_SHA=case.identity['selected_domain_sha'],
            selected_Bound_SHA=hashlib.sha256(case.d['lower'].tobytes()+case.d['upper'].tobytes()).hexdigest(),
            original_integer_and_fractional_LP_projection_identical=True,
            Native_optimize_calls=0,Gurobi_presolve_calls=0,denied_native_attempts=calls,
            denied_original_or_domain_producer_attempts=denied,original_Gurobi_model_rebuilds=0,
            prior_optimization_points_bounds_starts_read=0,sizes=sizes,physical=physical,
            mathematical_proof=proof,Dense_Response_proof=case.identity['response_authority']['proof'],
            C3A_independent_proof_reused_after_exact_state_and_unchanged_source_SHA_checks=True,
            model_build_wall_seconds=0.,case_restore_wall_seconds=restore_wall,
            inherited_original_constructor_wall_seconds=None,
            fresh_input_sources=[record(folder/n) for n in ('NATIVE_INPUT.json','B2_FIXED_AIDC.json')],
            native_parameter_readback=record(readback_out/'ACTUAL_PARAMETERS.json'),
            actual_model_identity=record(readback_out/'MODEL_IDENTITY.json'),memory=memory_observation(),
            copy_elision=copy_proof,Root_measurement_gate=gate,final_Gurobi_presolved_NNZ=None,
            Root_completed_seconds=None,solver_LB=None,solver_gap=None,
            campaign_HOLD=True,production_results_promoted=0,UTC=now())
        atomic(DEV/'NATIVE0_VALIDATION.json',report)
        atomic(DEV/'ROOT_MEASUREMENT_HOLD.json',dict(gate,Native_optimize_calls=0,UTC=now()))
        print(json.dumps(dict(PASS=True,classification=report['classification'],sizes=sizes['Dense'],
            Root_measurement_gate=gate),ensure_ascii=False))
        if run_root:
            require(gate.get('allowed') is True,'RESTORE_ROOT_EXACT_OR_COMPRESSION_GATE_NOT_MET')
            from validate_svr11_root180 import measure_case_once,DEV as ROOT_DEV
            root=measure_case_once(case,request,sources=sources,source_sha=source_sha,source_commit=commit,
                build_wall=0.,copy_proof=copy_proof,progress=progress,sizes=sizes)
            atomic(DEV/'INTEGRATED_VALIDATION_INDEX.json',dict(report,
                Root_validation=record(ROOT_DEV/'ROOT180_VALIDATION.json'),Root_classification=root['classification']))
        return report
    except BaseException as error:
        from validate_svr11_root180 import DEV as ROOT_DEV
        ledger=ROOT_DEV/'NATIVE_RUNTIME_LEDGER.json';runtime=read(ledger) if ledger.exists() else None
        atomic(DEV/'VALIDATION_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),
            source_SHA=source_sha,generation_source_SHA=GENERATION_SHA,
            Native_optimize_calls=len(runtime['calls']) if runtime is not None and runtime.get('inflight') is None else
                None if runtime is not None else 0,
            Native_Runtime=runtime.get('measured_Native_Runtime') if runtime is not None else 0,
            runtime_ledger=record(ledger) if runtime is not None else None,UTC=now()))
        raise
    finally:_active.reset(token);current_authority.cache_clear()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root-once',action='store_true')
    run(run_root=parser.parse_args().root_once)

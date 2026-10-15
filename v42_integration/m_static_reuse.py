"""Reuse real, independently proved M artifacts; never a point or a bound.

The C2 producer is replayed from literal stored FULL bytes. Its complete
transport state, C3A state and Dense state must equal the actual prior proof
hashes. No missing proof can be manufactured from a matching matrix SHA.
"""
from copy import deepcopy,copy
import gc
import gzip
import json
from pathlib import Path
import pickle
import shutil
from time import perf_counter
import numpy as np
from scipy import sparse
from .a_engine import digest
from .m_engine import _write,file_record

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def require(value,reason):
    if not value:raise ValueError(reason)


def _proofs_current(identity,folder):
    for key in ('transport_authority','c3_authority','response_authority',
                'physical_prescreen_authority','grid_prescreen_authority'):
        authority=identity[key]
        for relative,record in authority['sources'].items():
            require(file_record(ROOT/relative)==record,'STATIC_M_PROOF_SOURCE_DRIFT:'+relative)
        record=authority['certificate']
        require(file_record(record['path'])==record,'STATIC_M_ACTUAL_PROOF_BYTES_DRIFT:'+key)
        proof=read(record['path'])
        require(proof.get('PASS') is True and proof.get('Native_optimize_calls',0)==0,
                'STATIC_M_ACTUAL_INDEPENDENT_PROOF_REQUIRED:'+key)
    require(identity['transport'].get('selected_C3A_independent_proof_PASS') is True,
        'STATIC_M_PRIOR_INDEPENDENT_C3A_PROOF_REQUIRED')
    require(read(folder/'DENSE_RESPONSE_EQUIVALENCE.json').get('independent_model_proof_replayed') is True,
        'STATIC_M_PRIOR_INDEPENDENT_DENSE_PROOF_REQUIRED')


def _retarget(case,output):
    """Only provenance paths change. Original mathematical source/case stays fixed."""
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    old=case.output;identity=deepcopy(case.identity)
    for key in ('transport_authority','c3_authority','response_authority',
                'physical_prescreen_authority','grid_prescreen_authority'):
        record=identity[key]['certificate'];p=output/Path(record['path']).name
        shutil.copyfile(record['path'],p)
        require(file_record(p)['sha256']==record['sha256'],'STATIC_M_PROOF_COPY_NOT_LITERAL')
        identity[key]['certificate']=file_record(p)
    case.output=output;case.identity=identity;case.case_sha=digest(identity)
    _write(output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**identity))
    _write(output/'FIXED_AIDC_ANCHOR.json',case.anchor)
    return old


def restore_proved_artifacts(folder,context,aidc,acceptance,output):
    """Native0 recovery from a completed static proof, not a solver checkpoint."""
    from .table_v_mess import payload_for_m
    from v42_may_campaign_native90.m_model import (CampaignMCase,_domain_sha,_transport_state_sha,
        _c3_state_sha)
    from v42_m1_hybrid.blocks import matrix_sha
    from v42_bootstrap.m1 import native_inputs
    from v42_native.mess_domain import build_domain
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from v42_ultracompact.current import CurrentC3A
    from v42_ultracompact.response import ReformulationResult,state_sha
    began=perf_counter();folder=Path(folder).resolve();saved=read(folder/'SCIENTIFIC_CASE_IDENTITY.json')
    case_sha=saved.pop('case_sha');require(digest(saved)==case_sha,'STATIC_M_SAVED_CASE_IDENTITY_DRIFT')
    require(saved['arm']=='B2' and saved['stage']=='M1','STATIC_M_NATIVE0_CURRENT_REFERENCE_SCOPE_REQUIRED')
    payload=payload_for_m(context,'B2','M1',aidc,acceptance)
    require(saved['D0_source_sha']==context['manifest']['source_sha']
        and saved['D0_parent_case_sha']==context['manifest']['identity']['case_sha']
        and saved['aidc_anchor']==aidc['aidc_anchor']
        and saved['bundle_sha']==digest(payload['bundle'])
        and saved['input_identity']==payload['identity'],'STATIC_M_EXACT_SOURCE_CASE_POLICY_ANCHOR_REQUIRED')
    _proofs_current(saved,folder)
    A=sparse.load_npz(folder/'FULL_A.npz').tocsr();d=dict(np.load(folder/'FULL_DATA.npz',allow_pickle=False))
    require(matrix_sha(A)==saved['original_matrix_sha'] and _domain_sha(d)==saved['original_domain_sha'],
        'STATIC_M_LITERAL_ORIGINAL_MATRIX_DOMAIN_REQUIRED')
    sites,initial,routes,battery,receipt=native_inputs(payload['bundle'])
    graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
        [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
    compact=Compact(A,d,graph[2],initial,96)
    bounds=read(folder/'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json')
    lower=compact.d['lower'].copy();upper=compact.d['upper'].copy()
    for record in bounds:
        j=record['column']
        require(lower[j]==float(record['old_lower']) and upper[j]==float(record['old_upper']),
            'STATIC_M_ORIGINAL_SECURITY_BOUND_AXIS_DRIFT')
        lower[j]=float(record['new_lower']);upper[j]=float(record['new_upper'])
    pre=dict(certificates=read(folder/'CURRENT_SECURITY_PRE_C2_ROW_CERTIFICATES.json'),bounds=bounds,
        lower=lower,upper=upper,summary=read(folder/'CURRENT_SECURITY_PRE_C2_SUMMARY.json'),battery=battery)
    presolve=Presolve(compact.A,dict(compact.d,lower=lower,upper=upper))
    presolve.current_security=pre;presolve.bound.extend(bounds)
    presolve.row_delete({int(p['row']) for p in pre['certificates']},pre['certificates'])
    presolve.run()
    require(_transport_state_sha(compact,presolve,graph)==saved['transport_authority']['state_sha'],
        'STATIC_M_COMPLETE_PRIOR_TRANSPORT_STATE_NOT_RECONSTRUCTED')
    C=sparse.load_npz(folder/'C3A_A.npz').tocsr();e=dict(np.load(folder/'C3A_DATA.npz',allow_pickle=False))
    axes=dict(np.load(folder/'CURRENT_C3A_AXES.npz',allow_pickle=False))
    ultra=CurrentC3A(presolve.A,presolve.d,C,e,axes['rows'],read(folder/'CURRENT_C3A_ROW_CERTIFICATES.json'),
        read(folder/'CURRENT_C3A_BOUND_PROOFS.json'),read(folder/'CURRENT_EXACT_C3A_PROOF.json'),A,d)
    require(_c3_state_sha(ultra)==saved['c3_authority']['state_sha'],
        'STATIC_M_COMPLETE_PRIOR_C3A_STATE_NOT_RECONSTRUCTED')
    B=sparse.load_npz(folder/'DENSE_RESPONSE_A.npz').tocsr();f=dict(np.load(folder/'DENSE_RESPONSE_DATA.npz',allow_pickle=False))
    axes=dict(np.load(folder/'DENSE_RESPONSE_AXES.npz',allow_pickle=False))
    response=ReformulationResult(C,e,B,f,axes['rows'],axes['columns'],read(folder/'DENSE_RESPONSE_PLANS.json'),
        read(folder/'DENSE_RESPONSE_EQUIVALENCE.json'))
    require(state_sha(response)==saved['response_authority']['state_sha'],
        'STATIC_M_COMPLETE_PRIOR_DENSE_STATE_NOT_RECONSTRUCTED')
    require(matrix_sha(B)==saved['selected_matrix_sha'] and _domain_sha(f)==saved['selected_domain_sha'],
        'STATIC_M_SELECTED_MATRIX_DOMAIN_DRIFT')
    physical=context['materialize_physical']()['physical'];physical.verify()
    anchor=read(folder/'FIXED_AIDC_ANCHOR.json')
    require(digest(anchor)==saved['anchor_sha'],'STATIC_M_EXACT_FIXED_ANCHOR_REQUIRED')
    case=CampaignMCase(B,f,A,d,None,graph,case_sha,saved,compact,presolve,payload['bundle'],anchor,
        payload['planning'],physical.coefficients,folder,ultra,response,
        physical_domain=build_domain(sites,initial,routes,battery,96))
    old=_retarget(case,output)
    from .m_candidates import generate
    from .m_engine import export_plan
    case.candidate_generator=generate;case.plan_exporter=export_plan
    _write(case.output/'STATIC_PROOF_REUSE.json',dict(PASS=True,
        prior_static_case_sha=case_sha,current_case_sha=case.case_sha,source_sha=saved['D0_source_sha'],
        scientific_case_sha=saved['D0_parent_case_sha'],AIDC_anchor=saved['aidc_anchor'],
        complete_transport_C3A_Dense_states_reconstructed=True,real_prior_independent_proofs_reused=True,
        original_matrix_domain_and_objective_unchanged=True,proof_bytes_copied_exactly=True,
        provenance_paths_rebound_only=True,old_output=str(old),wall_seconds=perf_counter()-began,
        prior_solution_or_bound_reused=False,Native_calls=0))
    gc.collect();return case


def save_verified_case(case,path):
    """Persist the actual reconstructed case only after dynamic Native0 PASS."""
    path=Path(path);static=copy(case);static.point=None
    for key in list(vars(static)):
        if (key.startswith('mess_') or key.startswith('global_gap_') or key in
                ('_direct_static_cache','candidate_pools','warm_route_seed')):
            vars(static).pop(key,None)
    with gzip.open(path,'xb',compresslevel=1) as stream:pickle.dump(static,stream,protocol=5)
    return file_record(path)


def load_verified_case(manifest_record,context,aidc,acceptance,output,*,dynamic_recheck=False):
    """Load a real Native0 cache; changed dynamic code requires fresh Native0.

    Production requires the entire current dynamic source receipt. A Native0
    recheck may reuse static models when their actual scientific producers,
    complete transport states, physical source/case and fixed plan still match.
    """
    from .table_v_mess import payload_for_m
    from v42_may_campaign_native90.m_model import (CampaignMCase,_domain_sha,_transport_state_sha,_c3_state_sha)
    from v42_ultracompact.response import state_sha
    from v42_m1_hybrid.blocks import matrix_sha
    began=perf_counter()
    require(file_record(manifest_record['path'])==manifest_record,'STATIC_M_NATIVE0_MANIFEST_BYTES_DRIFT')
    manifest=read(manifest_record['path'])
    require(manifest.get('status')=='PASS' and manifest.get('Native_calls')==0
        and manifest.get('FULL_UB_certified') is False and not manifest.get('blocked_Native_attempts'),
        'STATIC_M_ACTUAL_COMPLETED_NATIVE0_REQUIRED')
    iterations=manifest.get('seedless_iterations',[])
    require(len(iterations)==2 and len({r['pool_sha'] for r in iterations})==2
        and all(r['charge_modes']==384 and r['MIP_Start_present'] is False for r in iterations)
        and manifest.get('K16',{}).get('PASS') is True,'STATIC_M_COMPLETE_DYNAMIC_NATIVE0_REQUIRED')
    if not dynamic_recheck:
        require(manifest.get('current_source_records') and all(file_record(r['path'])==r for r in manifest['current_source_records']),
            'STATIC_M_CURRENT_DYNAMIC_NATIVE0_SOURCE_REQUIRED')
    cache=manifest['verified_static_case_cache']
    require(file_record(cache['path'])==cache,'STATIC_M_CACHE_BYTES_DRIFT')
    with gzip.open(cache['path'],'rb') as stream:case=pickle.load(stream)
    require(type(case) is CampaignMCase and case.point is None,'STATIC_M_LITERAL_UNSOLVED_CASE_REQUIRED')
    require(not any(k in vars(case) for k in ('mess_search_state','candidate_pools','warm_route_seed',
        '_direct_static_cache','mess_feedback_point')),'STATIC_M_NO_HEURISTIC_POOL_OR_INCUMBENT_TRANSFER')
    require(case.case_sha==manifest['case_sha'] and case.identity==manifest['source_case'],
        'STATIC_M_NATIVE0_CACHE_IDENTITY_MISMATCH')
    payload=payload_for_m(context,'B2','M1',aidc,acceptance);identity=case.identity
    require(identity['arm']=='B2' and identity['stage']=='M1'
        and identity['D0_source_sha']==context['manifest']['source_sha']
        and identity['D0_parent_case_sha']==context['manifest']['identity']['case_sha']
        and identity['input_identity']==payload['identity']
        and identity['aidc_anchor']==aidc['aidc_anchor']
        and identity['bundle_sha']==digest(payload['bundle'])==digest(case.bundle)
        and digest(case.planning)==digest(payload['planning'])
        and digest(identity)==case.case_sha,'STATIC_M_EXACT_CURRENT_SOURCE_CASE_POLICY_AND_PLAN_REQUIRED')
    _proofs_current(identity,case.output)
    require(matrix_sha(case.original_A)==identity['original_matrix_sha']
        and _domain_sha(case.original_d)==identity['original_domain_sha']
        and matrix_sha(case.A)==identity['selected_matrix_sha']
        and _domain_sha(case.d)==identity['selected_domain_sha']
        and digest(case.anchor)==identity['anchor_sha'],'STATIC_M_ACTUAL_MODEL_ARRAYS_DRIFT')
    require(_transport_state_sha(case.compact,case.presolve,case.graph)==identity['transport_authority']['state_sha']
        and _c3_state_sha(case.ultra)==identity['c3_authority']['state_sha']
        and state_sha(case.response)==identity['response_authority']['state_sha'],
        'STATIC_M_COMPLETE_PROVED_TRANSFORM_STATE_DRIFT')
    physical=context['materialize_physical']()['physical'];physical.verify()
    require(identity['physical_sha']==context['manifest']['physical_sha'],
        'STATIC_M_CURRENT_PHYSICAL_INPUT_REQUIRED')
    prior=case.case_sha;_retarget(case,output)
    from .m_candidates import generate
    from .m_engine import export_plan
    case.candidate_generator=generate;case.plan_exporter=export_plan
    _write(case.output/'STATIC_PROOF_REUSE.json',dict(PASS=True,prior_static_case_sha=prior,
        current_case_sha=case.case_sha,scientific_case_sha=identity['D0_parent_case_sha'],
        source_sha=identity['D0_source_sha'],AIDC_anchor=identity['aidc_anchor'],
        original_matrix_domain_and_objective_unchanged=True,complete_transport_C3A_Dense_states_reconstructed=True,
        real_prior_independent_proofs_reused=True,provenance_paths_rebound_only=True,
        cached_native0_manifest=manifest_record,cache=cache,dynamic_recheck=dynamic_recheck,
        prior_solution_or_bound_reused=False,Native_calls=0,wall_seconds=perf_counter()-began))
    return case

"""Binary M case/inverse restoration using the PR189/V43 primitives."""
from pathlib import Path
from types import SimpleNamespace,MethodType
import numpy as np
from scipy import sparse

from .common import read,record,verify,atomic,digest,NotReady
from .checkpoints import crash_admission


def arrays(path):
    with np.load(path,allow_pickle=False) as archive:return {k:archive[k].copy() for k in archive.files}


def restore(parent,output,request,payload,modules):
    from v42_bootstrap.m1 import native_inputs
    from v42_supercompact.formulation import Compact
    from v42_supercompact.presolve import Presolve
    from .frozen.v43_mess.library import current_identity
    parent=Path(parent);output=Path(output)
    admission=crash_admission(parent,request)
    if admission['status']!='RESTORABLE_M_BINARY':raise NotReady('M_BINARY_RESTORE_NOT_SUPPORTED')
    sites,initial,routes,battery,receipt=native_inputs(payload['bundle'])
    arcs=[(s,t,s,t+1,None) for s in sites for t in range(96)]+[
        (r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)]
    graph=(sites,initial,arcs,battery,receipt)
    A=sparse.load_npz(parent/'FULL_A.npz');B=sparse.load_npz(parent/'C3A_A.npz')
    data=arrays(parent/'FULL_DATA.npz');selected=arrays(parent/'C3A_DATA.npz')
    identity=read(parent/'SCIENTIFIC_CASE_IDENTITY.json');case_sha=identity.pop('case_sha')
    if digest(identity)!=case_sha or identity['aidc_anchor']!=payload['identity']['aidc_anchor']:
        raise ValueError('BINARY_RESTORE_PARENT_CASE_OR_AIDC_DRIFT')
    compact=Compact(A,data,arcs,initial,96);axes=arrays(parent/'CURRENT_C2_AXES.npz')
    inverse=SimpleNamespace(A=B,d=selected,col_ids=axes['columns'],row_ids=axes['rows'],
        initial_names=compact.d['names'],steps=read(parent/'CURRENT_C2_ALIASES.json'),
        rows=read(parent/'CURRENT_C2_ROW_PROOFS.json'),bound=read(parent/'CURRENT_C2_BOUND_PROOFS.json'))
    inverse.inverse=MethodType(Presolve.inverse,inverse)
    if not np.array_equal(compact.d['names'][inverse.col_ids],selected['names']):
        raise ValueError('BINARY_INVERSE_COLUMN_AXIS_DRIFT')
    def lift(point):
        if np.asarray(point).shape!=(B.shape[1],):raise ValueError('RESTORED_M_POINT_AXIS_DRIFT')
        return compact.inverse(inverse.inverse(point))
    from v42_svr11.model import load_coefficients
    coefficients=load_coefficients(read(payload['bundle']['electrical_certificate']['path']),request['day'])
    case=SimpleNamespace(original_A=A,original_d=data,A=B,d=selected,compact=compact,presolve=inverse,
        graph=graph,case_sha=case_sha,identity=identity,bundle=payload['bundle'],
        anchor=read(parent/'FIXED_AIDC_ANCHOR.json'),planning=payload['planning'],coefficients=coefficients,
        output=output,lift=lift,plan_exporter=modules['m_engine'].export_plan,mess_stage_budget_seconds=900.,
        checkpoint_source_output=parent)
    with np.load(read(payload['bundle']['electrical_certificate']['path'])['output']['path'],allow_pickle=False) as z:
        case._v43_coefficient_metadata={k:z[k].copy() for k in ('node_names','branch_names','transformer_ratings')}
    current_identity(case);verify_restored(case)
    atomic(output/'BINARY_RESTORE_RECEIPT.json',dict(admission,PASS=True,
        model_rebuilt=False,presolve_run=False,transport_and_FULL_matrix_SHA_replayed=True,
        case_sha=case.case_sha,original_AIDC_and_MESS_domain_preserved=True))
    return case


def verify_restored(case):
    """The immutable transport proof remains at its original owned location."""
    from v42_may_campaign_native90.m_model import verify_case
    current=case.output
    try:
        case.output=case.checkpoint_source_output
        return verify_case(case)
    finally:case.output=current


def registry(parent,case,module):
    found=[]
    for path in sorted(Path(parent).rglob('SAME_CASE_INCUMBENT_REGISTRY.json')):
        for entry in read(path):
            if entry['binding']!=module.binding(case):raise ValueError('RESTORED_FULL_INCUMBENT_CASE_BINDING_DRIFT')
            verify([entry['raw']]);found.append(entry)
    return list({r['raw']['sha256']:r for r in found}.values())


def packet(folder,case,module):
    folder=Path(folder);manifest=read(folder/'NATIVE0_MANIFEST.json');verify(manifest['files'])
    if manifest['source']!=module.identity(case):raise ValueError('RESTORED_K_PACKET_CASE_DRIFT')
    if (folder/'JOINT_START.npz').exists():raise NotReady('NON_SEEDLESS_K_PACKET_RESTORE_NOT_SUPPORTED')
    axes=arrays(folder/'JOINT_AXES.npz')
    value=dict(A=sparse.load_npz(folder/'JOINT_A.npz'),d=arrays(folder/'JOINT_DATA.npz'),
        rows=axes['rows'],columns=axes['columns'],cuts=read(folder/'EXACT_CUTS.json'),start=None,full_start=None,
        source=manifest['source'],original_replay=None,K=manifest['K'],selection=manifest['selection'],
        historical_point_or_bound_read=False,build_wall_seconds=manifest['build_wall_seconds'])
    proof=module.verify_packet(case,value)
    if proof!=read(folder/'CURRENT_SOURCE_PROJECTION_CERTIFICATE.json'):
        raise ValueError('RESTORED_K_PACKET_FULL_PROJECTION_PROOF_DRIFT')
    return value,proof


def continue_k48(parent,case,module,budget,output,control_module):
    """Same K16 -> K32 -> K48 sequence; no completed call or budget is reset."""
    parent=Path(parent);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    candidates=list((parent/'K48_EXECUTION').rglob('NATIVE0_MANIFEST.json'))
    candidates+=list((parent/'NATIVE0_K16').glob('NATIVE0_MANIFEST.json'))
    if not candidates:raise NotReady('SAVED_K16_K32_K48_BINARY_PACKET_REQUIRED')
    saved=max(candidates,key=lambda p:read(p)['K']);current,proof=packet(saved.parent,case,module)
    history=[];completed={}
    for path in sorted((parent/'K48_EXECUTION').rglob('K48_NATIVE_RESULT.json')):
        result=read(path)
        if result['source']!=module.identity(case) or result['Native_call'] not in budget.calls:
            raise ValueError('K48_COMPLETED_NATIVE_RESULT_NOT_RECONCILED_TO_LEDGER')
        if result['K'] in completed:raise ValueError('DUPLICATE_K48_NATIVE_RESULT')
        completed[result['K']]=(result,path)
        if result['K']<current['K']:
            history.append(result);control_module.mess_lower(case.global_gap_control,case,result,same_stage_restore=True)
    while True:
        k=current['K']
        if k in completed:
            result,path=completed[k];point_path=path.parent/'RELAXATION_INCUMBENT.npz'
            point=arrays(point_path)['point'] if point_path.exists() else None
        else:
            if budget.remaining()<=0:break
            result,point=module.solve_packet(current,proof,budget,output/f'K{k}/SOLVE')
        history.append(result);control_module.mess_lower(case.global_gap_control,case,result,same_stage_restore=True)
        if k==48 or point is None or budget.remaining()<=0 or case.global_gap_control.target_met():break
        cuts,separation=module.separate(case,current,point);atomic(output/f'SEPARATION_{k}.json',separation)
        if len(cuts)!=16:break
        current,proof=module.append_cuts(case,current,cuts,output/f'K{k+16}')
    summary=module.summarize_current_k48(current,proof,history)
    atomic(output/'CURRENT_K48_RESULT.json',summary);return summary

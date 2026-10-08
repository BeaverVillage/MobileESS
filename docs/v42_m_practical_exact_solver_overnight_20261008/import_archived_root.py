"""Reuse an existing OPTIMAL scientific LP certificate, with zero new solves."""
from practical_support import *
from fractions import Fraction as F

def receipt(oracle,node,run):
    assert node['id']==0 and node['parent'] is None and node['fixings']==[]
    source=hc.HISTORY;native=read(source/'PURE_LP_RESULT.json');transport=read(source/'C3A_IDENTITY_AUDIT.json')
    assert native['Status']==2 and transport['PASS'] and transport['pure_LP_transport']['PASS']
    assert transport['selected_hashes']['C3A_A.npz']==oracle.identity['A_SHA256'] and transport['selected_hashes']['C3A_DATA.npz']==oracle.identity['DATA_SHA256']
    identity=verifier.verify(ROOT,oracle.d);assert identity['PASS']
    with np.load(source/'PURE_LP_POINT.npz') as z:x=z['x'].copy();pi=z['dual'].copy();rc=z['reduced_cost'].copy();assert np.array_equal(z['original_types'],oracle.d['types'])
    certificate,clipped,residual,terms=hc.exact_bounded_lagrangian(oracle.CSC,oracle.d,pi)
    folder=run/'external_nodes/0000';folder.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(folder/'LP_POINT_PROOF.npz',x=x,Pi=pi,RC=rc,clipped_Pi=clipped,exact_residual_display=residual,exact_bound_terms_display=terms)
    bounds_hash=hashlib.sha256(oracle.d['lower'].tobytes()+oracle.d['upper'].tobytes()).hexdigest()
    certificate.update(PASS=True,LP_status='OPTIMAL',original_model_identity=oracle.identity,fixing_hash=node['fixing_hash'],bounds_SHA256=bounds_hash,proof_vector_SHA256=sha(folder/'LP_POINT_PROOF.npz'))
    atomic(folder/'LB_CERTIFICATE.json',certificate)
    binary=oracle.binary;values=x[binary];eligible=[int(j) for j in binary if x[j] not in (0,1)]
    assert eligible
    j=oracle.choose_branch(eligible,x)
    basis_hash=None;basis_origin=None;checkpoint=run/'OPEN_CHECKPOINT.json'
    if checkpoint.exists():
        for failed in reversed(read(checkpoint)['state'].get('failed_attempt_history',[])):
            prior=failed.get('result',{});partial=prior.get('partial_basis');archive=failed.get('archive')
            if prior.get('node_id')!=0 or not partial or not archive:continue
            assert prior['identity']==oracle.identity and prior['fixing_hash']==node['fixing_hash'] and prior['bounds_SHA256']==bounds_hash and partial['not_a_certificate']
            p=(run/archive['archive']/partial['file']).resolve();assert p.is_relative_to(run.resolve())
            assert sha(p)==partial['SHA256']==archive['files'][partial['file']]
            with np.load(p) as z:assert z['VBasis'].shape==(oracle.A.shape[1],) and z['CBasis'].shape==(oracle.A.shape[0],)
            (folder/'BASIS.npz').write_bytes(p.read_bytes());basis_hash=sha(folder/'BASIS.npz')
            basis_origin=dict(source=p.relative_to(run).as_posix(),SHA256=basis_hash,native_status=prior['native_status'],same_original_root_domain=True,not_node_proof=True)
            break
    origin=dict(PASS=True,archived_completed_OPTIMAL=True,new_root_optimize_calls=0,new_root_Runtime=None,archived_Runtime=native['Runtime'],archived_Work=native['Work'],source_result_SHA256=sha(source/'PURE_LP_RESULT.json'),source_identity_SHA256=sha(source/'C3A_IDENTITY_AUDIT.json'),source_point_SHA256=sha(source/'PURE_LP_POINT.npz'),source_files_scientific_unchanged=True,basis_available=basis_hash is not None,saved_same_domain_basis_origin=basis_origin,new_basis_computation_claimed=False,primal_objective_not_accepted_as_LB=True,primal_replay_PASS=native['independent_relaxed_matrix_replay']['PASS'],exact_dual_certificate_independently_recomputed=True)
    result=dict(identity=oracle.identity,fixing_hash=node['fixing_hash'],node_id=0,fixings=[],LP_status='OPTIMAL',native_status=2,LP_objective=native['objective'],certified_LB=certificate['exact_rational'],optimal_LP_certificate_PASS=True,exact_infeasibility_PASS=False,proof_checked=True,Runtime=0.,Work=0.,archived_runtime_excluded_from_night=True,archived_origin=origin,bounds_SHA256=bounds_hash,LP_primal_replay=hc.replay(oracle.A,dict(oracle.d,types=np.full(len(x),'C')),x,False),LB_certificate_SHA256=sha(folder/'LB_CERTIFICATE.json'),basis_output_SHA256=basis_hash,basis_supplied=False,basis_accepted=False,branch_variable=j,branch_name=str(oracle.d['names'][j]),branch_is_original_binary=True,raw_fractional_branch_value=float(x[j]),fractional_binary_count=int(np.count_nonzero(np.minimum(abs(values),abs(1-values))>1e-8)),witness=None,receipt='external_nodes/0000/RESULT.json',objective_identity=identity,callback_errors=[],exception=None)
    atomic(folder/'ARCHIVED_ORIGIN.json',origin);atomic(folder/'RESULT.json',result);return result

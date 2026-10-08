"""Solver-free reconstruction of node authority, proof and complete coverage."""
from support import *
from bb_controller import ExactBB,digest
from objective_identity import verify
import re

def audit():
    import gurobipy as gp
    def forbidden(*a,**k):raise AssertionError('AUDIT_OPTIMIZE_PRESOLVE_FORBIDDEN')
    gp.Model.optimize=forbidden;gp.Model.presolve=forbidden
    identity=read(OUT/'EXTERNAL_MODEL_AUTHORITY.json')['identity'];bb=ExactBB.load(OUT/'OPEN_CHECKPOINT.json',identity)
    A,d,_=hc.load();CSC=A.tocsc();binary=set(map(int,np.flatnonzero(d['types']=='B')));nodes=bb.state['nodes'];receipts=[]
    reconstruction=ExactBB(identity,bb.state['nodes']['0']['inherited_LB'],str(F.from_float(read(OUT/'NATIVE_RESULT.json')['global_UB'])),dict(point='BEST_VALID_POINT.npz',SHA256=sha(OUT/'BEST_VALID_POINT.npz'),replay='BEST_FULL_REPLAY.json'))
    for ledger in bb.state['ledger']:
        n=ledger['node_id'];node=nodes[str(n)];result=read(OUT/ledger['receipt']);folder=(OUT/ledger['receipt']).parent
        assert node['result_digest']==digest(result)
        assert result['identity']==identity and result['objective_identity']['PASS']
        assert all(j in binary and v in (0,1) for j,v in node['fixings'])
        e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
        for j,v in node['fixings']:e['lower'][j]=e['upper'][j]=v
        bounds_hash=hashlib.sha256(e['lower'].tobytes()+e['upper'].tobytes()).hexdigest();assert bounds_hash==result['bounds_SHA256']
        assert result['fixing_hash']==node['fixing_hash']
        proof_receipt=dict(node_id=n,PASS=True,fixing_hash=node['fixing_hash'],LP_status=result['LP_status'],bounds_SHA256=bounds_hash)
        if result['LP_status']=='OPTIMAL':
            assert read(folder/'OPTIMIZE_ONCE.json')['optimize_calls']==1
            cert=read(folder/'LB_CERTIFICATE.json');assert sha(folder/'LB_CERTIFICATE.json')==result['LB_certificate_SHA256'] and sha(folder/'LP_POINT_PROOF.npz')==cert['proof_vector_SHA256']
            with np.load(folder/'LP_POINT_PROOF.npz') as z:x=z['x'];pi=z['Pi'];clipped=z['clipped_Pi']
            computed,p,_,_=hc.exact_bounded_lagrangian(CSC,e,pi)
            assert computed['exact_rational']==cert['exact_rational']==result['certified_LB'] and np.array_equal(p,clipped)
            assert F.from_float(cert['lower_bound'])<=F(cert['exact_rational'])
            assert result['native_status']==2 and cert['LP_status']=='OPTIMAL'
            # The native objective is an observation. Only the exact conservative
            # dual certificate and inherited valid references authorize pruning.
            assert result['LP_objective']==float(d['objective']@x+float(d['constant']))
            if result.get('branch_variable') is not None:
                j=result['branch_variable'];assert j in binary and j not in dict(node['fixings']) and x[j] not in (0,1)
                assert float(x[j])==result['raw_fractional_branch_value']
                eligible=[j for j in sorted(binary) if j not in dict(node['fixings']) and x[j] not in (0,1)]
                assert j==min(eligible,key=lambda j:(-min(abs(float(x[j])),abs(1-float(x[j]))),j))
            with np.load(folder/'BASIS.npz') as z:
                assert z['VBasis'].shape==(A.shape[1],) and z['CBasis'].shape==(A.shape[0],)
                assert set(np.unique(z['VBasis']))<=set((0,-1,-2,-3)) and set(np.unique(z['CBasis']))<=set((0,-1))
            assert sha(folder/'BASIS.npz')==result['basis_output_SHA256']
            proof_receipt.update(exact_dual_bound_recomputed=True,certified_LB=cert['exact_rational'],primal_feasibility_observation=result['LP_primal_replay'])
        elif result['LP_status']=='INFEASIBLE':
            cert=read(folder/'INFEASIBILITY_CERTIFICATE.json');assert sha(folder/'INFEASIBILITY_CERTIFICATE.json')==result['infeasibility_certificate_SHA256']
            with np.load(folder/'FARKAS_PROOF.npz') as z:ray=z['FarkasDual']
            computed,_,_,_=hc.exact_bounded_lagrangian(CSC,dict(e,objective=np.zeros_like(d['objective']),constant=np.array(0.)),-ray)
            assert computed['exact_rational']==cert['exact_rational'];assert result['exact_infeasibility_PASS']==(F(computed['exact_rational'])>0)
            proof_receipt['exact_Farkas_recomputed']=True
        if result.get('witness'):
            witness=result['witness'];assert read(OUT/witness['replay'])['PASS'] and sha(OUT/witness['replay'])==witness['replay_SHA256']
        if result['basis_supplied']:
            parent=nodes[str(node['parent'])];assert result['basis_source']==f"external_nodes/{parent['id']:04d}/BASIS.npz"
            actual=[l for l in (folder/'LP.log').read_text(encoding='utf-8',errors='replace').splitlines() if re.search(r'warm.start|basis',l,re.I)]
            assert result['basis_evidence']==actual
            accepted=any('LP warm-start: use basis' in l for l in actual) and not any(re.search(r'ignored|invalid|discard',l,re.I) for l in actual)
            assert accepted==result['basis_accepted']
        # Each node log has exactly one native optimize header, never a sweep.
        log=(folder/'LP.log').read_text(encoding='utf-8',errors='replace');assert log.count('Optimize a model with')==1
        chosen=reconstruction.select();assert chosen['id']==n,'BEST_BOUND_ORDER_VIOLATION';reconstruction.begin(chosen);reconstruction.apply(n,result)
        receipts.append(proof_receipt);print('AUDIT_EXACT_NODE_PASS',n,flush=True)
    assert digest(reconstruction.state)==digest(bb.state),'QUEUE_OR_UB_RECONSTRUCTION_DIFFERENCE'
    assert protected()==read(OUT/'BASE_IDENTITY.json')['protected_before'] and verify(ROOT,d)['PASS']
    markers=list((OUT/'external_nodes').glob('*/OPTIMIZE_ONCE.json'));assert len(markers)==bb.state['processed']
    native_once=read(OUT/'NATIVE_ONCE.json');assert native_once['optimize_calls']==1
    for source in ('native_canary.py','support.py','objective_identity.py'):
        p=OUT/source;blob=subprocess.check_output(['git','show',native_once['source_commit']+':'+p.relative_to(ROOT).as_posix()],cwd=ROOT);assert hashlib.sha256(blob).hexdigest()==sha(p),'NATIVE_SOURCE_CHANGED_AFTER_RUN'
    for source in ('external_bb.py','bb_controller.py'):
        p=OUT/source;commits={read(marker)['source_commit'] for marker in markers}
        for commit in commits:
            blob=subprocess.check_output(['git','show',commit+':'+p.relative_to(ROOT).as_posix()],cwd=ROOT);assert hashlib.sha256(blob).hexdigest()==sha(p),'EXTERNAL_SOURCE_CHANGED_DURING_RUN'
    write('EXTERNAL_EXACT_AUDIT.json',dict(PASS=True,UTC=stamp(),nodes=receipts,coverage=bb.audit(),all_exact_certificates_recomputed=True,model_bounds_reconstructed_from_original_plus_binary_fixings=True,all_bases_and_proof_vector_hashes_verified=True,deterministic_queue_and_UB_reconstruction_identical=True,protected_history_unchanged=True,objective_identity_PASS=True,native_MIP_optimize_calls=1,external_LP_optimize_calls=len(markers),audit_optimize_calls=0,source_integrity_PASS=True))
    print('EXTERNAL_EXACT_AUDIT_PASS',len(receipts),flush=True)

if __name__=='__main__':audit()

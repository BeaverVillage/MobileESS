"""Recompute the exact LB from Git-packaged raw evidence, with optimize=0."""
from v42_physics_redesign.common import *
from .certificate import verify_certificate, tests

DEST=ROOT/'docs/v42_m1_b2_root_validation_20261008'

def main():
    prior.forbid_optimize()
    manifest=read(DEST/'SHA256_MANIFEST.json')
    assert all(sha(DEST/n)==v['sha256'] for n,v in manifest['files'].items())
    assert all(sha(ROOT/n)==v['sha256'] for n,v in manifest['source_modules'].items())
    assert all(sha(ROOT/n)==v['sha256'] for n,v in manifest['inherited_source_modules'].items())
    assert all(sha(hc.PARENT/n)==v for n,v in manifest['scientific_source_hashes'].items())
    A,d,_=hc.load()
    identity=read(DEST/'B2_ROOT_SOURCE_IDENTITY.json')
    for n,expected in identity['original_source_arrays_SHA256'].items():
        assert hashlib.sha256(np.asarray(d[n]).tobytes()).hexdigest()==expected
    T=sparse.load_npz(DEST/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr()
    with np.load(DEST/'artifacts/TEMPORAL_VALID_ROW_DATA.npz') as f:rhs=f['rhs'].copy()
    augmented=sparse.vstack([A,T],format='csr')
    full=dict(d,rhs=np.r_[d['rhs'],rhs],sense=np.r_[d['sense'],np.full(len(rhs),'<')])
    stored=read(DEST/'B2_ROOT_LB_CERTIFICATE.json')
    accepted=dict(stored['producer']['accepted'])
    for n in ('exact_path','npz_path'):
        accepted[n]=str(DEST/'artifacts'/Path(accepted[n]).name)
    independent=verify_certificate(augmented,full,accepted)
    assert independent['certified_LB']==stored['exact_certified_LB']
    with np.load(DEST/'B2_ROOT_RAW.npz') as f:x=f['x'].copy();pi=f['pi'].copy()
    with np.load(accepted['npz_path']) as f:projected=f['pi'].copy()
    wrong=((full['sense']=='<')&(pi>0))|((full['sense']=='>')&(pi<0))
    assert int(wrong.sum())==20566
    assert np.where(wrong,0.,pi).tobytes()==projected.tobytes()
    replay=hc.replay(A,d,x,False)
    assert not replay['PASS']
    decision=read(DEST/'B2_ROOT_FINAL_DECISION.json')
    assert decision['new_valid_global_LB']==max(LB,independent['certified_LB'])==LB
    assert decision['new_UB']==UB
    assert read(DEST/'checkpoints/B2_NATIVE_CALL_LEDGER.json')['native_calls']==1
    assert tests()['PASS']
    result=dict(PASS=True,
        exact_certified_LB=independent['certified_LB'],all_finite_bound_terms=independent['all_original_finite_bound_terms_checked'],
        raw_wrong_sign_count=int(wrong.sum()),raw_pi_preserved=True,separate_multiplier_matches_projection=True,
        original_strict_primal_PASS=replay['PASS'],native_calls=0,
        exact_payload_SHA256=independent['exact_payload_SHA256'],
        raw_payload_SHA256=sha(DEST/'B2_ROOT_RAW.npz'),
        scientific_source_hashes=manifest['scientific_source_hashes'],
        final_valid_global_LB=LB,UB=UB)
    write(REPORTS/'B2_GIT_PACKAGED_EXACT_REPLAY.json',result)
    print('B2_GIT_PACKAGED_EXACT_REPLAY_PASS',json.dumps(result),flush=True)

if __name__=='__main__':main()

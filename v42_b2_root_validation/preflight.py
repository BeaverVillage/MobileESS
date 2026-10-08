"""Reuse PR185 proofs and independently audit the new model transport."""
from v42_physics_redesign.common import *
from v42_physics_redesign.verify import main as original_verify

BASE185='6d1d64beaf012d32ddf39245890785e3d8f01d4b'
SOURCE=ROOT/'docs/v42_m1_physics_strengthened_20261008'

def main():
    started=time.perf_counter();prior.forbid_optimize()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE185
    remote=read(SOURCE/'artifacts/PR185_REMOTE_REFERENCE.json') if (SOURCE/'artifacts/PR185_REMOTE_REFERENCE.json').exists() else json.loads(subprocess.check_output(['gh','pr','view','185','--repo','BeaverVillage/MobileESS','--json','headRefOid,url'],cwd=ROOT,text=True))
    assert remote['headRefOid']==BASE185
    manifest=read(SOURCE/'SHA256_MANIFEST.json')
    assert all(sha(SOURCE/n)==v['sha256'] for n,v in manifest['files'].items())
    assert all(sha(ROOT/n)==v['sha256'] for n,v in manifest['source_modules'].items())
    A,d,_=hc.load();identity=prior.objective_identity(A,d)
    assert identity['PASS'] and identity['candidate_objective_SHA256']=='0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335'
    scientific={n:sha(hc.PARENT/n) for n in manifest['scientific_source_hashes']}
    assert scientific==manifest['scientific_source_hashes']
    assert A.shape==(582808,306040) and A.nnz==5351612
    assert (d['types']=='B').sum()==9322
    original_verify() # No Cut generation and no new fixture solves.
    T=sparse.load_npz(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr()
    with np.load(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz') as f:rhs=f['rhs'].copy()
    assert T.shape==(651,306040) and T.nnz==1302
    assert sha(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz')==manifest['files']['artifacts/TEMPORAL_VALID_ROWS.npz']['sha256']
    assert sha(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz')==manifest['files']['artifacts/TEMPORAL_VALID_ROW_DATA.npz']['sha256']
    witnesses=[]
    for p in sorted((P183/'artifacts/assignments').glob('*.npz')):
        with np.load(p) as f:x=f['x'].copy()
        replay=hc.replay(A,d,x,True);assert replay['PASS'],p.name
        violation=float(np.max(T@x-rhs,initial=0));assert violation<=1e-8
        witnesses.append(dict(id=p.stem,source_SHA256=sha(p),original_C3A_replay=replay,maximum_new_row_violation=violation,PASS=True))
    assert len(witnesses)==20
    arrays={n:hashlib.sha256(np.asarray(d[n]).tobytes()).hexdigest() for n in ['objective','constant','names','row_names','rhs','sense','lower','upper','types']}
    result=dict(PASS=True,base_HEAD=BASE185,scientific_authority='PR162 C3A',remote_PR185=remote,
        PR185_source_module_SHAs=manifest['source_modules'],PR185_manifest_file_count=len(manifest['files']),
        original_source_arrays_SHA256=arrays,scientific_source_files_SHA256=scientific,
        scientific_paths={n:str(hc.PARENT/n) for n in scientific},objective_identity=identity,
        original_rows=582808,columns=306040,binaries=9322,original_nnz=5351612,
        augmented_rows=583459,augmented_nnz=5352914,additional_rows=651,additional_nnz=1302,
        source_variable_types_permanently_unchanged=True,ROOT_only_binary_relaxation=True,
        inherited_integer_equivalence=read(SOURCE/'checkpoints/ROOT_EQUIVALENCE_GATE.json'),
        independent_new_transport=read(REPORTS/'INDEPENDENT_VALID_INEQUALITY_AUDIT.json'),
        original_20_witnesses=witnesses,best_UB_full_physical_replay=read(REPORTS/'ORIGINAL_PHYSICAL_REPLAY.json'),
        no_Cut_regeneration=True,no_new_fixture_solve=True,optimize_calls=0,
        controller_wall_seconds=time.perf_counter()-started)
    write(REPORTS/'B2_ROOT_SOURCE_IDENTITY.json',result)
    print('B2_SOURCE_IDENTITY_PASS',len(witnesses),'optimize=0',flush=True)

if __name__=='__main__':main()

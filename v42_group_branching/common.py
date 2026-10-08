from v42_physics_redesign.common import *
BASE187='e67ecfa827e4262c2f2df17c226d6442656af18b'
SOURCE187=ROOT/'docs/v42_m1_b2_root_validation_20261008'
SOURCE185=ROOT/'docs/v42_m1_physics_strengthened_20261008'
CHILD_SETTINGS=dict(SETTINGS,TimeLimit=480)
NAMESPACE='docs/v42_m1_group_branching_20261008'

def model_inputs():
    A,d,_=hc.load()
    T=sparse.load_npz(SOURCE187/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr()
    with np.load(SOURCE187/'artifacts/TEMPORAL_VALID_ROW_DATA.npz') as f:rhs=f['rhs'].copy()
    augmented=sparse.vstack([A,T],format='csr')
    full=dict(d,rhs=np.r_[d['rhs'],rhs],sense=np.r_[d['sense'],np.full(len(rhs),'<')],
        row_names=np.r_[d['row_names'],np.array([f'temporal_reachability[{i}]' for i in range(len(rhs))])])
    return A,d,T,augmented,full

def identity():
    prior.forbid_optimize()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE187
    remote=json.loads(subprocess.check_output(['gh','pr','view','187','--repo','BeaverVillage/MobileESS',
        '--json','headRefOid,headRefName,url'],cwd=ROOT,text=True))
    assert remote['headRefOid']==BASE187
    m=read(SOURCE187/'SHA256_MANIFEST.json');old=read(SOURCE185/'SHA256_MANIFEST.json')
    assert all(sha(SOURCE187/n)==v['sha256'] for n,v in m['files'].items())
    assert all(sha(ROOT/n)==v['sha256'] for n,v in m['source_modules'].items())
    assert all(sha(SOURCE185/n)==v['sha256'] for n,v in old['files'].items())
    assert all(sha(ROOT/n)==v['sha256'] for n,v in old['source_modules'].items())
    assert all(sha(hc.PARENT/n)==v for n,v in m['scientific_source_hashes'].items())
    A,d,T,augmented,full=model_inputs();objective=prior.objective_identity(A,d)
    assert objective['PASS'] and objective['candidate_objective_SHA256']=='0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335'
    assert A.shape==(582808,306040) and A.nnz==5351612 and T.shape==(651,306040) and T.nnz==1302
    assert augmented.shape==(583459,306040) and augmented.nnz==5352914
    assert int((d['types']=='B').sum())==9322
    witnesses=[]
    for p in sorted((P183/'artifacts/assignments').glob('*.npz')):
        with np.load(p) as f:x=f['x'].copy()
        r=hc.replay(A,d,x,True);assert r['PASS'] and float(np.max(T@x-full['rhs'][-651:],initial=0))<=1e-8
        witnesses.append(dict(id=p.stem,sha256=sha(p),PASS=True))
    assert len(witnesses)==20
    source=read(SOURCE187/'B2_ROOT_SOURCE_IDENTITY.json')
    with np.load(P183/'artifacts/BEST_VALID_POINT.npz') as f:x=f['x'].copy()
    replay=prior.prior.full_replay(A,d,x,hc.physical_reader())
    assert replay['PASS'] and float(d['objective']@x)==UB
    assert float(np.max(T@x-full['rhs'][-651:],initial=0))<=1e-8
    write(REPORTS/'ORIGINAL_PHYSICAL_REPLAY.json',replay)
    result=dict(PASS=True,base_HEAD=BASE187,remote_PR187=remote,objective_identity=objective,
        scientific_paths=source['scientific_paths'],scientific_source_files_SHA256=m['scientific_source_hashes'],
        preserved_PR187_files=len(m['files']),preserved_PR185_files=len(old['files']),
        original_types_preserved=True,continuous_route_flow_preserved=True,original_20_witnesses=witnesses,
        best_UB_full_physical_replay_reused=source['best_UB_full_physical_replay'],
        original_arrays_SHA256=source['original_source_arrays_SHA256'],additional_cut_generation=False,native_calls=0)
    write(REPORTS/'SOURCE_IDENTITY.json',result);return result

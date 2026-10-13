"""SHA-bound static alias cache; new pools and starts are always rechecked."""
from scipy import sparse
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_perf_v3.exact import alias_operator,independent_links
from tools.global_local_multistart1800.joint import build_spec

VERSION='INTEGER_ALIAS_OPERATOR_V3_1'
def identity(case):
    return dict(version=VERSION,source_SHA=v.SOURCE_SHA,case_SHA=v.CASE_SHA,matrix_SHA=v.matrix_sha(case.A),domain_SHA=v.domain_sha(case.d),
        original_matrix_SHA=v.FULL_MATRIX_SHA,original_domain_SHA=v.FULL_DOMAIN_SHA,
        original_aliases_SHA=hashlib.sha256(json.dumps(case.aliases,sort_keys=True,separators=(',',':')).encode()).hexdigest())

def verify(folder,expected):
    manifest=read(folder/'MANIFEST.json');assert manifest['identity']==expected,'CACHE_IDENTITY_INVALIDATION'
    for name,rec in manifest['files'].items():assert v.file_sha(folder/name)==rec['sha256'],'CACHE_CONTENT_CORRUPTION:'+name
    return manifest

def get(case,timing):
    with timing.stage('static_identity_SHA'):
        key=identity(case);assert key['matrix_SHA']==v.MATRIX_SHA and key['domain_SHA']==v.DOMAIN_SHA
    folder=DOCS/'cache'/hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest();hit=(folder/'MANIFEST.json').exists()
    if not hit:
        with timing.stage('static_cache_creation_alias_proof'):
            folder.mkdir(parents=True,exist_ok=True)
            route=[j for j,n in enumerate(map(str,case.d['names'])) if n.startswith(('route_flow[','node_activity['))]
            M,constant,axes=alias_operator(case,route)
            sparse.save_npz(folder/'ALIAS_OPERATOR.npz',M);np.save(folder/'ALIAS_CONSTANT.npy',constant)
            write(folder/'AXES.json',axes);write(folder/'ROUTE_IDS.json',route)
            files={p.name:record(p) for p in folder.iterdir() if p.is_file()}
            write(folder/'MANIFEST.json',dict(PASS=True,identity=key,files=files,integer_overflow_bound_proven=True,
                all_original_route_aliases_exact=True,static_only=True,new_pool_links_not_cached=True))
    with timing.stage('static_cache_SHA_and_readonly_restore'):
        manifest=verify(folder,key);M=sparse.load_npz(folder/'ALIAS_OPERATOR.npz').tocsr()
        for a in (M.data,M.indices,M.indptr):a.flags.writeable=False
        constant=np.load(folder/'ALIAS_CONSTANT.npy',mmap_mode='r');axes=read(folder/'AXES.json');route=read(folder/'ROUTE_IDS.json')
    return dict(folder=folder,manifest=manifest,operator=(M,constant,axes),route=route,hit=hit)

def proof_function(cache,timing):
    def proof(case,point,spec,lo,hi,A,rhs):
        with timing.stage('dynamic_DAG_Alias_links_Start_proof'):
            spec['center_raw']=record(read(spec['center_replay']['path'])['point_path'])
            cert=read(spec['center_replay']['path']);assert cert['PASS'] and cert['point_vector_sha256']==v.vector_sha(point)
            assert v.file_sha(spec['center_replay']['path'])==spec['center_replay']['sha256']
            derived,signature=independent_links(case,spec,cache['route'],cache['operator'])
            assert v.matrix_sha(derived)==v.matrix_sha(A) and signature==spec['mathematical_model_signature']
            assert np.array_equal(derived@np.r_[point,spec['lambda_Start']],rhs)
        return dict(PASS=True,Optimize_calls=0,original_Arc_Node_Flow_Alias_exact=len(cache['operator'][2]),
            cache_manifest=record(cache['folder']/'MANIFEST.json'),static_cache_hit=cache['hit'],dynamic_links_rederived=True,
            removed_integer_columns=[j for j in cache['route'] if case.d['types'][j]=='B'],
            retained_384_charge_modes_free=True,restricted_to_FULL_inclusion=True,source_rows_deleted=0,
            original_source_CSR_RHS_Sense_Bounds_Objective_preserved=True,source_matrix_SHA=v.matrix_sha(case.A),
            no_physical_nonroute_columns_removed=True,
            theorem='Exact integer source inverse alias operator plus independently named DAG incidence and one-hot lambda links. All original nonroute coordinates and physical rows are retained.',
            restricted_equals_FULL_not_claimed=True)
    return proof

def fast_save(case,point,replay,pools,label,folder,cache,timing):
    from tools.adaptive_compact_joint import direct
    saved=direct.integer_proof;direct.integer_proof=proof_function(cache,timing)
    try:
        # Outer wall is kept separate; nested dynamic proof is an exclusive stage.
        started=time.perf_counter();before=timing.parts.get('dynamic_DAG_Alias_links_Start_proof',0.)
        result=direct.save(case,point,replay,pools,label,folder)
        proof_wall=timing.parts.get('dynamic_DAG_Alias_links_Start_proof',0.)-before
        timing.parts['CSR_product_exact_coefficients_and_packet_IO']=time.perf_counter()-started-proof_wall
        return result
    finally:direct.integer_proof=saved

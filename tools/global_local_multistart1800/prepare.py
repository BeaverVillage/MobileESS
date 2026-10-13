"""Original FULL warm authority and preregistered global/local/dual Native0."""
import gc,shutil,subprocess,time
from collections import defaultdict
from tools.global_local_multistart1800.adapter import *
from tools.global_local_multistart1800.routes import generate
from tools.global_local_multistart1800.neighborhoods import priorities,make
from tools.global_local_multistart1800.dag import Graph
from tools.u4_primal_alns.analyze import original_plan

def main():
    DOCS.mkdir(exist_ok=True);assert not (DOCS/'RUN_STARTED.json').exists()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    for f in ('FINAL_STATE.json','BEST_PLAN_AUDIT.json','FINAL_INDEPENDENT_REVIEW.json'):
        assert (ROOT/'docs/v42_b2_route_centered_local_branching1800'/f).is_file()
    previous=read(ROOT/'docs/v42_b2_route_centered_local_branching1800/FINAL_STATE.json');assert previous['BEST_GLOBAL_UB']['UB']==INITIAL_UB
    assert read(ROOT/'docs/v42_b2_route_centered_local_branching1800/FINAL_INDEPENDENT_REVIEW.json')['PASS']
    assert previous['BEST_GLOBAL_UB']['point']['sha256']==RAW_SHA and v.file_sha(ROOT/RAW_REL)==RAW_SHA
    x=v.load_point(ROOT/RAW_REL);assert v.vector_sha(x)==VECTOR_SHA
    saved=read(ROOT/REPLAY_REL);assert saved['PASS'] and saved['Global_UB']==INITIAL_UB and v.file_sha(ROOT/REPLAY_REL)==previous['BEST_GLOBAL_UB']['replay']['sha256']
    cert=v.validate(ROOT/RAW_REL,solver_objective=INITIAL_UB,output=DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json');assert cert['PASS']
    case=v.load_native_case();assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(case.d)==v.DOMAIN_SHA
    plan,_=original_plan(case,ROOT/RAW_REL,cert);assert plan['move_count']==3
    assert [a['original_arc_index'] for a in plan['units']['MESS03']['move_routes']]==[4954,37751,44900]
    write(DOCS/'PR220_WARM_START_CERTIFICATE.json',dict(PASS=True,base_PR220=BASE,initial_UB=INITIAL_UB,point=record(ROOT/RAW_REL),
        vector_SHA=VECTOR_SHA,replay=record(DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json'),source_sha=v.SOURCE_SHA,case_sha=v.CASE_SHA,
        plan=plan,Native_optimize_calls=0,old_PR220_Native_separate=724.820999622345,Raw_clipping_rounding_repair=0))
    r.create_baseline();baseline=read(r.BASELINE);known={f['path'] for f in baseline['protected_files']}
    for prefix in ('docs/v42_b2_route_centered_local_branching1800','docs/v42_b2_minimax_beam1800','docs/v42_b2_time_decomposed_global_lb','docs/v42_b2_root_lp_tightening'):
        for f in (ROOT/prefix).rglob('*'):
            if f.is_file() and str(f) not in known:baseline['protected_files'].append(r.digest(f));known.add(str(f))
    external=Path('D:/v42_b2_route_centered_local_branching1800_20261012')
    for f in read(external/'docs/v42_b2_route_centered_local_branching1800/DELIVERY_ARTIFACT_INDEX.json')['files']:
        path=external/f['path'];assert v.file_sha(path)==f['sha256']
        if str(path) not in known:baseline['protected_files'].append(r.digest(path));known.add(str(path))
    write(r.BASELINE,baseline);r.baseline.cache_clear();resource=r.audit('GLOBAL_LOCAL_PREPARE',True);assert resource['PASS'];write(DOCS/'PRE_RUN_RESOURCE_SOURCE_AUDIT.json',resource)
    write(DOCS/'SOURCE_CASE_AUTHORITY.json',dict(PASS=True,base_PR220=BASE,Source_PR207=v.SOURCE_SHA,case_SHA=v.CASE_SHA,
        FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA,Dense_matrix_SHA=v.MATRIX_SHA,Dense_domain_SHA=v.DOMAIN_SHA,
        original_binary=9322,source_identity=case.identity,source_equivalence=case.source_evidence,all_predecessors_read_only=True))
    for name in ('SIGNED_SELECTION_CONTEXT.json','SIGNED_SELECTION_SOURCE_RAW.json','SIGNED_SELECTION_INDEPENDENT_NATIVE0.json','U4_K32_SIGNED_DIAGNOSTICS.json'):
        shutil.copyfile(ROOT/'docs/v42_b2_minimax_beam1800'/name,DOCS/name)
    context,receipt=g.refresh(case,x);sites,partners,ranks=priorities(case,x,context)
    write(DOCS/'INITIAL_CRITICAL_PRIORITY.json',dict(context=context,receipt=receipt,sites=sites,ranking=ranks))
    import tools.minimax_beam1800.grid as minimax_grid
    minimax_grid.DOCS=DOCS
    context_path=DOCS/'grid/epoch00/CRITICAL_MINIMAX_CONTEXT.json'
    if context_path.exists():
        minimax_context=read(context_path)
        assert minimax_context['center_vector_sha']==v.vector_sha(x) and minimax_context['source_sha']==v.SOURCE_SHA and minimax_context['case_sha']==v.CASE_SHA
        closure=minimax_context['raw_source_closure'];assert v.file_sha(closure['path'])==closure['sha256']
    else:minimax_context,context_path=minimax_grid.refresh(case,x,0)
    if (DOCS/'GLOBAL_CANDIDATE_POOL.json').exists():
        pool=read(DOCS/'GLOBAL_CANDIDATE_POOL.json')['candidates'];diversity=read(DOCS/'GLOBAL_ROUTE_DIVERSITY_AUDIT.json')
        assert diversity['PASS'] and diversity['scoring_center_vector']==v.vector_sha(x)
    else:pool,diversity=generate(case,x,minimax_context,0)
    grouped=defaultdict(list)
    for c in pool:grouped[c['family']].append(c)
    # Preserve a large balanced nonduplicate reservoir rather than a finite21 retry pool.
    selected=[]
    for fam,items in sorted(grouped.items()):
        buckets=defaultdict(list)
        for c in items:buckets[str(c['diversity_key'])].append(c)
        diverse=sorted((b[0] for b in buckets.values()),key=lambda c:(c['estimated_peak_loading'],c['signature']))
        selected.extend(diverse[:64])
    write(DOCS/'GLOBAL_CANDIDATE_POOL.json',dict(candidates=selected,generated_total=len(pool),retained_total=len(selected),heuristic_deferred=len(pool)-len(selected)))
    diversity['retained_by_family']={f:sum(c['family']==f for c in selected) for f in grouped};write(DOCS/'GLOBAL_ROUTE_DIVERSITY_AUDIT.json',diversity)
    from tools.global_local_multistart1800.joint import select_pools,build_spec,independent
    pools=select_pools(case,selected,x,6)
    spec,lo,hi,A,rhs=build_spec(case,x,DOCS/'PR220_FRESH_ORIGINAL_FULL_REPLAY.json',pools,'JOINT_POOL_000',120)
    spec['center_raw']=record(ROOT/RAW_REL)
    proof=independent(case,x,spec,lo,hi,A,rhs);assert proof['PASS']
    write(DOCS/'native0/JOINT_POOL_000/SPEC.json',spec);write(DOCS/'native0/JOINT_POOL_000/PROOF.json',proof)
    # Original Native model plus lambda/link rows is built/read back and disposed, Optimize0.
    from tools.global_local_multistart1800.joint_native0 import verify_build
    verify_build(case,x,spec,lo,hi,A,rhs,DOCS/'native0/JOINT_POOL_000/model')
    for fam in diversity['required_families']:
        c=next(c for c in selected if c['family']==fam);diagnostic=route_spec(case,c)
        dl,du,*_=restriction(case,None,diagnostic);assert audit(case,None,diagnostic,dl,du)['PASS']
    write(DOCS/'NATIVE0_GLOBAL_LOCAL_AUDIT.json',dict(PASS=True,Optimize_calls=0,main_algorithm='FOUR_MESS_JOINT_ROUTE_POOL_MILP',
        original_9322_binary_preserved=True,lambda_binary_added=spec['lambda_count'],proof=proof,solo_pairs_triples_are_ablation=True))
    lb=read(ROOT/'docs/v42_b2_minimax_beam1800/K32_K48_LB_CERTIFICATES.json');assert lb['PASS'] and lb['Global_LB']==GLOBAL_LB
    for folder in ('iteration01','iteration02'):
        authority=ROOT/'docs/v42_critical_grid_cg'/folder
        assert read(authority/'INDEPENDENT_CERTIFICATE.json')['PASS']
        for name,digest in read(authority/'INDEPENDENT_NATIVE0.json')['file_sha256'].items():assert v.file_sha(authority/name)==digest
    write(DOCS/'K32_K48_INHERITED_LB_CERTIFICATE.json',dict(lb,new_Optimize_calls=0,rehashed=True))
    del case,x,pool;gc.collect()
    from tools.global_local_multistart1800.lb import prepare
    prepare()
    policy=dict(PASS=True,Native_limit=1800,Threads=1,heavy_workers=1,RAM_reserve_GiB=4,Commit_reserve_GiB=6,
        main_algorithm='FOUR_MESS_JOINT_ROUTE_POOL_MILP',all_four_MESS_routes_selected_in_one_MILP=True,
        solo_pairs_triples_only_ablation=True,ablation_families=['G1','G2','G3','G4','PAIR_MESS01_MESS02','PAIR_MESS01_MESS04','PAIR_MESS02_MESS04'],
        initial_allocations=dict(JOINT=1300,ABLATION=250,DUAL=180,RETURN=8,adaptive=62),
        initial_pool_size=6,initial_Joint_cap=120,joint_cap=150,max_Joint_cap=175,
        max_pool_size=24,expand_each_vehicle_by=2,ablation_call_cap=30,ablation_stage_cap=250,
        dual_requested_seconds=175,dual_maximum180=True,dual_calls=1,dual_reserved_until_executed=180,return_reserve=8,
        switching='Joint then one ablation then expanded Joint, until seven comparison families considered; one Dual after Joint integrity gate; then all-four expanded pools until budget.',
        adaptive_generation='Expand all four units by2 after no strict gain, include current winning paths, preserve old paths, prefer unseen location/time diversity. On strict gain continue global pool expansion rather than stop. If reservoir cannot add paths generate new minimax epoch at current center, at most3 epochs. Never separately enumerate Cartesian path combinations.',
        adaptive_allocation='Small initial6/unit; if root incomplete use new diversified pool at same size before increasing, longer cap at most175 only after completed root; no identical pool/bounds/link matrix signatures.',
        pool_lambda='One binary lambda per original complete vehicle DAG path; sum lambda per unit =1; exact original Native Route Flow/Node links, affine original Arc/Alias proof; all9322 source binary types retained.',
        source_Start='Original FULL center and literal one-hot lambda readback; all384 Modes/P/Q/SOC free; no added MOVE forcing or Global objective cutoff.',
        strict_delta=DELTA,UB_tolerance=1e-8,Global_LB_never_restricted=True,conditional_LP_screen_calls=0,
        Actual='ACTUAL_NOT_RUN',old_Native_times_separate=True,source_policy_frozen_before_Native=True)
    write(DOCS/'SEARCH_SWITCHING_POLICY.json',policy)
    files=[]
    for directory in ('tools/global_local_multistart1800','tools/route_centered_lb1800','tools/minimax_beam1800','tools/k32_routefixed1800','tools/integrated_primal1800','tools/u4_primal_alns','v42_common_mess','tools/critical_grid_cg','tools/b2_root_lp_tightening','tools/time_decomposed_lb'):
        files.extend((ROOT/directory).glob('*.py'))
    files.extend(DOCS.rglob('SPEC.json'));files.extend(DOCS.rglob('PROOF.json'))
    files.extend(DOCS/name for name in ('GLOBAL_CANDIDATE_POOL.json','GLOBAL_ROUTE_DIVERSITY_AUDIT.json','SEARCH_SWITCHING_POLICY.json','LB_CANDIDATE_COMPARISON.json','FAST_LB_NATIVE0.json','PR220_WARM_START_CERTIFICATE.json','SOURCE_CASE_AUTHORITY.json','INITIAL_CRITICAL_PRIORITY.json','SIGNED_SELECTION_CONTEXT.json'))
    files.extend([ROOT/RAW_REL,ROOT/REPLAY_REL])
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{str(p.relative_to(ROOT)):v.file_sha(p) for p in files})
    print(json.dumps(dict(PASS=True,Optimize_calls=0,candidate_pool=len(selected),joint_lambda=spec['lambda_count'],warm_UB=INITIAL_UB)))

if __name__=='__main__':main()

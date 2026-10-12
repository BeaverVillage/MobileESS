"""Warm authority, Native0 neighborhood proofs, and source/policy freeze."""
import gc,shutil,sys,subprocess,time
from tools.route_centered_lb1800.adapter import *
from tools.route_centered_lb1800.dag import Graph
from tools.route_centered_lb1800.neighborhoods import priorities,descriptors,make
from tools.u4_primal_alns.analyze import original_plan

def main():
    DOCS.mkdir(parents=True,exist_ok=True);assert not (DOCS/'RUN_STARTED.json').exists()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    raw=ROOT/RAW_REL;replay=ROOT/REPLAY_REL;x=v.load_point(raw)
    assert v.file_sha(raw)==RAW_SHA and v.vector_sha(x)==VECTOR_SHA
    saved=read(replay);assert saved['PASS'] and saved['Global_UB']==INITIAL_UB and saved['case_sha']==v.CASE_SHA and saved['source_sha']==v.SOURCE_SHA
    cert=v.validate(raw,solver_objective=INITIAL_UB,output=DOCS/'PR219_FRESH_ORIGINAL_FULL_REPLAY.json');assert cert['PASS'] and cert['Global_UB']==INITIAL_UB
    case=v.load_native_case();assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(case.d)==v.DOMAIN_SHA
    assert case.identity['original_matrix_sha']==v.FULL_MATRIX_SHA and case.identity['original_domain_sha']==v.FULL_DOMAIN_SHA
    assert np.count_nonzero(case.d['types']!='C')==9322
    plan,rows=original_plan(case,raw,cert);assert plan['move_count']==3 and plan['travel_energy_kWh']==66.30848166605175
    assert [a['original_arc_index'] for a in plan['units']['MESS03']['move_routes']]==[4954,40511,47108]
    excess=np.maximum(case.d['lower']-x,x-case.d['upper']);positive=np.flatnonzero(excess>0)
    warm=dict(PASS=True,PR219_HEAD=BASE,initial_UB=INITIAL_UB,Global_LB=GLOBAL_LB,Global_gap=(INITIAL_UB-GLOBAL_LB)/INITIAL_UB,
        inherited_point=record(raw),inherited_full_replay=record(replay),fresh_original_FULL_replay=record(DOCS/'PR219_FRESH_ORIGINAL_FULL_REPLAY.json'),
        vector_SHA=VECTOR_SHA,case_SHA=v.CASE_SHA,FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA,
        original_plan=plan,new_Native_Runtime=0.,old_PR219_Native_Runtime=1795.0249993801117,Warm_Start_not_Cold_Start=True,
        raw_unmodified=True,rounding=0,clipping=0,repair=0,exact_Dense_bound_residuals=[dict(name=str(case.d['names'][j]),
        value=float(x[j]),lower=float(case.d['lower'][j]),upper=float(case.d['upper'][j]),excess=float(excess[j])) for j in positive],
        numerical_scope='Original unchanged FULL validator PASS; tiny binary64 continuous box residuals retained, no claim of dyadic exact primal feasibility')
    write(DOCS/'PR219_WARM_START_CERTIFICATE.json',warm)
    r.create_baseline();external=Path('D:/v42_b2_minimax_beam1800_20261012')
    previous=read(external/'docs/v42_b2_minimax_beam1800/FINAL_STATE.json');assert previous['stopped_reason']=='NATIVE_BUDGET_END'
    assert read(external/'docs/v42_b2_minimax_beam1800/FINAL_INDEPENDENT_REVIEW.json')['PASS']
    index=read(external/'docs/v42_b2_minimax_beam1800/DELIVERY_ARTIFACT_INDEX.json');baseline=read(r.BASELINE);known={i['path'] for i in baseline['protected_files']}
    for item in index['files']:
        path=external/item['path'];assert v.file_sha(path)==item['sha256']
        if str(path) not in known:baseline['protected_files'].append(r.digest(path));known.add(str(path))
    write(r.BASELINE,baseline);r.baseline.cache_clear();resource=r.audit('ROUTE_CENTERED_PREPARE',True)
    write(DOCS/'PRE_RUN_RESOURCE_SOURCE_AUDIT.json',resource);assert resource['PASS']
    write(DOCS/'SOURCE_CASE_AUTHORITY.json',dict(PASS=True,base_PR219=BASE,source_PR207=v.SOURCE_SHA,source_PR211='d12315a3757aec187c8da0685c28ef901466386a',
        case_SHA=v.CASE_SHA,FULL_matrix_SHA=v.FULL_MATRIX_SHA,FULL_domain_SHA=v.FULL_DOMAIN_SHA,Dense_matrix_SHA=v.MATRIX_SHA,Dense_domain_SHA=v.DOMAIN_SHA,
        original_binary_count=9322,identity=case.identity,source_equivalence=case.source_evidence,old_PR219_completed=True,
        old_PR219_published_files_rehashed=len(index['files']),resources=resource['checks']))
    for name in ('SIGNED_SELECTION_CONTEXT.json','SIGNED_SELECTION_SOURCE_RAW.json','SIGNED_SELECTION_INDEPENDENT_NATIVE0.json','U4_K32_SIGNED_DIAGNOSTICS.json'):
        dest=DOCS/name
        if not dest.exists():shutil.copyfile(ROOT/'docs/v42_b2_minimax_beam1800'/name,dest)
    context,receipt=g.refresh(case,x);sites,partners,ranking=priorities(case,x,context)
    write(DOCS/'INITIAL_CRITICAL_PRIORITY.json',dict(context=context,receipt=receipt,sites=sites,partners=partners,signed_ranking=ranking))
    graph=Graph(case);paths=paths_of(case,x);candidates,skips=graph.ablations(paths,sites)
    assert {c['candidate_id'].split('_',1)[0] for c in candidates}=={'A1','A2','A3','A4','A5','A6'}
    for candidate in candidates:
        spec=route_spec(case,candidate);lo,hi,*_=restriction(case,None,spec);assert audit(case,None,spec,lo,hi)['PASS']
    write(DOCS/'ABLATION_CANDIDATES.json',dict(A0_NOT_REOPTIMIZED=True,initial_route=paths,candidates=candidates,skipped_reconstructions=skips,
        effects_are_joint_four_vehicle_reoptimization_not_independent_causal_MOVE_effects=True))
    queue,reserve=descriptors(partners);proofs=[];signatures=set()
    for descriptor in queue:
        spec=make(case,x,DOCS/'PR219_FRESH_ORIGINAL_FULL_REPLAY.json',descriptor,sites)
        lo,hi,*_=restriction(case,x,spec);proof=audit(case,x,spec,lo,hi)
        assert proof['PASS'] and spec['mathematical_model_signature'] not in signatures;signatures.add(spec['mathematical_model_signature'])
        write(DOCS/f'native0/{descriptor["label"]}/SPEC.json',spec);write(DOCS/f'native0/{descriptor["label"]}/INDEPENDENT_PROOF.json',proof)
        proofs.append(dict(label=descriptor['label'],proof=proof,signature=spec['mathematical_model_signature']))
    # Corruption tests exercise distinct contracts, rather than mirroring the
    # construction implementation. No native model or Optimize is used.
    bad=dict(spec);bad['hamming_radius']=-1
    rejected=False
    try:audit(case,x,bad,lo,hi)
    except AssertionError:rejected=True
    assert rejected
    bad=dict(spec);bad['fixed_route_values']=list(spec['fixed_route_values']);bad['fixed_route_values'][0]=1-bad['fixed_route_values'][0]
    rejected_fix=False
    try:audit(case,x,bad,lo,hi)
    except AssertionError:rejected_fix=True
    assert rejected_fix
    write(DOCS/'ROUTE_DAG_CLOSURE_AUDIT.json',dict(PASS=True,Native_optimize_calls=0,proofs=proofs,
        Hamming_center_exclusion_rejected=rejected,corrupt_alias_fixing_rejected=rejected_fix,all_have_different_moving_witness=True))
    lb=read(ROOT/'docs/v42_b2_minimax_beam1800/K32_K48_LB_CERTIFICATES.json');assert lb['PASS'] and lb['Global_LB']==GLOBAL_LB
    for key,i in [('K32',1),('K48',2)]:
        folder=ROOT/f'docs/v42_critical_grid_cg/iteration{i:02d}'
        for name,digest in read(folder/'INDEPENDENT_NATIVE0.json')['file_sha256'].items():assert v.file_sha(folder/name)==digest
        assert read(folder/'INDEPENDENT_CERTIFICATE.json')['PASS']
    write(DOCS/'K32_K48_LB_CERTIFICATES.json',dict(lb,new_Optimize_calls=0,independently_rehashed=True))
    policy=dict(Native_limit=1800,Threads=1,heavy_workers=1,initial_budget=dict(ABLATION=250,R1_R2=500,R3=400,R4=400,R5_reserve=250),
        ablation_call_cap=40,first_Local_Branching_cap=120,max_Local_Branching_cap=300,return_reserve_seconds=8,
        UB_tolerance=1e-8,strict_delta=DELTA,material_vs_N1=MATERIAL,Global_gap_goal=.03,
        Hamming='Actual free route Node-Activity only, witness maximum distance plus preregistered slack; all384 modes excluded',
        no_improvement_goal_row_excluding_center=True,improving_raw_stop='First MIPSOL below current verified center by1e-5, then immediate original FULL replay',
        primary_descriptors=queue,reserve_descriptors=reserve,priority_partners=partners,
        R5_only_after_R1_R4_stagnation=True,beam_candidates_are_corridor_assistance_not56_route_fixed_restarts=True,
        warm_start_authority=record(DOCS/'PR219_WARM_START_CERTIFICATE.json'),ACTUAL='ACTUAL_NOT_RUN',new_LB_calls=0,unrestricted_FULL_calls=0,
        source_policy_frozen_before_Native=True,unchanged_original_tolerances=True,Raw_repair=False)
    write(DOCS/'PREREGISTERED_POLICY.json',policy)
    contract='''# Route-Centered Neighborhood 수학 계약

Source18r의 원본 Exact C3A+Dense CSR/RHS/Sense/types/objective는 변경하지 않는다. 원본 box의 일부 Route Node/Flow만 center literal로 고정하고 원본 bounds보다 좁은 영역에 Hamming 검색 제약을 추가한다. 이 영역은 원본 FULL 가능영역의 부분집합이며 제한 ObjBound는 Global LB가 아니다.

모든384 Mode와 4대 Pch/Pdis/Q/SOC97의 원래 bounds를 유지한다. Hamming은 자유 Route Node만 포함한다. Radius는 실제 원본 DAG witness의 최대 Node 변경거리에 사전등록 slack을 더하며 radius24/48을 강제하지 않는다. 중심과 다른 실제 MOVE 경로를 증명한 뒤 실행한다. Witness는 ETA/Arc/domain/alias/terminal topology의 증거이고 SOC/Grid 대체 가능성은 주장하지 않는다.

변경 구간은 중심의 실제 vertex에서 시작하고 끝난다. 선택 Site와 시간창은 heuristic corridor이며 원본 전체 경로 공간의 정확한 prescreen으로 부르지 않는다. 이 corridor 안에서 원본 Arc의 forward/backward reachability로 dangling Arc만 정확히 제외한다. 후속 Node/Flow와 원래 slot96 terminal 상태를 함께 열고 unselected 차량과 외부 구간은 원래 경로로 고정한다. 구간 경계의 기존 Site 고정은 이웃 정의이며 새 물리적 복귀 의무가 아니다.

원본 역 Alias를 독립 재귀 전개하여 닫힌 Original Arc/Node가 자유 Native 열을 통해 활성화되지 않음을 box에서 검증한다. Hamming native 계수/RHS/sense, full Source prefix, types, objective, bounds, Start vector와 center 포함성을 readback한다.

PR219 Raw는 원본 수치 validator PASS인 point이며 약5e-13 연속 상한 잔차를 보정하지 않는다. 원본 FeasibilityTol 정책을 유지하고 새 fixings/Hamming은 literal로 만족한다. 이 점을 dyadic exact primal feasible point라고 과장하지 않는다. 경로 고정 ablation은 center 경로와 모순되어 MIP Start를 사용하지 않는 별도 진단이다. A0를 재최적화하지 않는다.

R1/R2는 첫/후반 MOVE의 제한 연결, R3는 MESS03의96슬롯 경로와 고정된 나머지3대, R4는 MESS03+한 차량을 변경한다. R5는 앞 단계 정체 후 새 Beam path와 주변 Arc를 하나의 제한 MILP에 합쳐 보조한다. 동일 mathematical bounds/Hamming signature를 반복 실행하지 않는다. 개선 center는 FULL PASS이고 이전 UB보다 유의하게 낮을 때만 갱신한다.
'''
    (DOCS/'ROUTE_NEIGHBORHOOD_CONTRACT_KO.md').write_text(contract,encoding='utf-8')
    files=[]
    for directory in ('tools/route_centered_lb1800','tools/minimax_beam1800','tools/k32_routefixed1800','tools/integrated_primal1800',
        'tools/u4_primal_alns','v42_common_mess','tools/critical_grid_cg','tools/b2_root_lp_tightening','tools/time_decomposed_lb'):
        files.extend((ROOT/directory).glob('*.py'))
    files.extend([DOCS/'PREREGISTERED_POLICY.json',DOCS/'ROUTE_NEIGHBORHOOD_CONTRACT_KO.md'])
    write(DOCS/'EXECUTED_SOURCE_HASHES.json',{str(p.relative_to(ROOT)):v.file_sha(p) for p in files})
    print(json.dumps(dict(PASS=True,Native_calls=0,ablation_candidates=len(candidates),neighborhoods=len(proofs),warm_UB=INITIAL_UB)))

if __name__=='__main__':main()

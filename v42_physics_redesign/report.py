"""Candid Korean review; no invented native or performance evidence."""
from .common import *
import shutil
from datetime import datetime,timezone

def prepare():
    content=f'''# ROOT 사전등록\n\nSource: PR183 `{BASE}`, scientific PR162 C3A. B0는 archived C3A ROOT를 재사용한다. H1의 grid closure인 B1은 원래 LP와 동일하므로 중복 optimize=0이다. H2는 원본 380 SOC 열의 exact cumulative substitution이며 완화가 같고 예상 nnz 25,937,190으로 채택하지 않는다.\n\nB2는 full 96-slot physics + 모든 원래 grid 행을 보유한 compact monolithic branch-and-cut이다. 원래 변수 306,040개와 binary 9,322개를 그대로 유지하고 exact 정수 유효 이동/SOC 도달 제약 651행, 1,302 nnz를 추가한다. 총 583,459행, 5,352,914 nnz. 모든 scientific coefficients/ObjCon/원본 변수 bounds·types·행을 보존하며 ROOT 실행에서만 이산변수를 연속 완화한다.\n\nFull-scale B2 ROOT optimize는 자원 격리 통과 후에만 최대 1회, TimeLimit=900, Threads=1. 등록 설정: `{json.dumps(SETTINGS)}`. 원본 min rho_max objective hash `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`. ROOT 종료 후 primal/Pi/RC/slack를 먼저 저장하고 original augmented array의 exact finite-bound lower certificate만 채택한다. raw invalid multiplier는 거부하고 별도의 수학적 multiplier가 필요한 경우 명시적으로 별도 보존한다.\n\nMaterial gate: certified LB − {LB} ≥0.001, OPTIMAL 종료, Runtime≤900초, 원본 정수 domain/물리/objective 동치성 PASS. Native ObjVal/불완전 pricing/restricted bound를 global LB로 사용하지 않는다. 미완료 ROOT는 tractability failure다. 기존 UB={UB}, gap={100*(UB-LB)/UB:.9f}%, 0.5% 목표 LB={UB*.995}. 수치 보정만으로 그 차이를 메우겠다고 주장하지 않는다.\n\nCanary는 ROOT material gate 후에만 최대900초, validated incumbent Start, Threads1, original tolerance1e-8, full replay를 요구한다. Production은 canary의 valid bound gain과 search tractability가 확인될 때만 허용한다. 신규 full-scale native 전체 예산을 보수적으로3600초 이내로 기록하며 과거 Runtime을 초기화·삭제하지 않는다. 이번 자원 대기 상태에서는 canary/production을 실행하지 않는다. M1 accepted false와 downstream 금지를 유지한다. MemLimit/SoftMemLimit/RAM 자동 종료는 추가하지 않는다.\n\n다른 A/M native 프로세스가 관측되어 자원 격리를 확보하지 못하면 ROOT를 시작하지 않는다. 다른 작업의 PID/source/worktree/checkpoint/로그를 중지·수정하지 않는다.\n'''
    (REPORTS/'ROOT_PREREGISTRATION.md').write_text(content,encoding='utf-8')
    write(REPORTS/'REGISTERED_SOLVER_SETTINGS.json',dict(root=SETTINGS,scientific_objective='original min rho_max',all_original_bounds_types_retained=True,MemLimit='unchanged default infinity',SoftMemLimit='unchanged default infinity',RAM_based_termination=False,new_master_recourse_loop=False,maximum_distinct_ROOT_calls=1,B1_duplicate_calls=0,canary_gate='certified ROOT gain >= .001 and tractability',production_gate='valid canary gain plus search tractability',fullscale_new_native_budget_max=3600))

def main():
    prior.forbid_optimize()
    if not (REPORTS/'ROOT_PREREGISTRATION.md').exists():prepare()
    root=read(REPORTS/'ROOT_RESULT.json');proof=read(REPORTS/'INDEPENDENT_VALID_INEQUALITY_AUDIT.json');stop=read(REPORTS/'PREVIOUS_ZF_STOP_AUDIT.json');census=read(REPORTS/'SOURCE_CENSUS.json');temporal=read(REPORTS/'VALID_INEQUALITY_CERTIFICATES.json');physics=read(REPORTS/'ORIGINAL_PHYSICAL_REPLAY.json')
    gate=read(WORK/'checkpoints/ROOT_EQUIVALENCE_GATE.json')
    fixture=read(REPORTS/'BOUNDED_EXACT_FIXTURE_VERIFICATION.json')
    assert all(x['PASS'] for x in (gate,proof,fixture,physics,temporal))
    classification='M1_PHYSICS_REDESIGN_RESOURCE_PENDING' if root.get('reason')=='RESOURCE_ISOLATION_PENDING' else ('M1_PHYSICS_REDESIGN_MATERIAL_LB_GAIN' if root.get('material_gate_PASS') else ('M1_PHYSICS_REDESIGN_VALID_RUNTIME_FAIL' if root.get('executed') and root.get('Status')!=2 else 'M1_PHYSICS_REDESIGN_NONMATERIAL'))
    lb=root.get('new_certified_LB',LB);gap=100*(UB-lb)/UB
    decision=dict(classification=classification,source_BASE=BASE,scientific_authority_PR162='1d922c91eb27056a5ccc79c92ef18146707099ab',selected_candidate='B2 compact full-physics monolith plus exact route/SOC temporal disjunctions',selected_as_production_solver=False,M1_ACCEPTED=False,integer_equivalence_PASS=gate['full_original_integer_preservation_PASS'],objective_identity_PASS=gate['source_objective_bit_identity_PASS'],independent_cut_transport_PASS=proof['PASS'],bounded_fixture_PASS=fixture['PASS'],full_original_physical_replay_PASS=physics['PASS'],new_ROOT_native_calls=root.get('native_optimize_calls',0),new_canary_native_calls=0,new_production_native_calls=0,root_material_gain_measured=root.get('executed',False),root_material_gate_PASS=root.get('material_gate_PASS',False),old_LB=LB,new_LB=lb,old_UB=UB,new_UB=UB,global_gap_percent=gap,certified_LB_change=lb-LB,validated_UB_change=0,performance='NOT_MEASURED_RESOURCE_PENDING' if not root.get('executed') else 'MEASURED_ROOT_ONLY',target_LB_at_current_UB=UB*.995,production_gate_PASS=False,downstream_executed=False,unapproved_parameter_sweep=False,next_structural_experiment='동일한 compact 96-slot 물리 모델의 사전등록 B2 ROOT를 다른 native 작업과 분리된 시간에 한 번 실행해 651개 route–SOC 제약의 실제 certified LB 기여를 측정한다.',next_action_count=1,next_action_executed=False)
    decision.update(ROOT_Runtime=root.get('Runtime'),ROOT_Work=root.get('Work'),charged_new_native_Runtime=root.get('charged_native_Runtime',root.get('Runtime',0)))
    write(REPORTS/'FINAL_DECISION.json',decision)
    trajectory=[dict(event='inherited_verified_bounds',source='PR183',native_Runtime_new=0,LB=LB,UB=UB,gap_percent=100*(UB-LB)/UB),dict(event='new_root_'+('resource_pending' if not root.get('executed') else 'completed'),source='current separate task',native_Runtime_new=root.get('charged_native_Runtime',root.get('Runtime',0)),LB=lb,UB=UB,gap_percent=gap)]
    table(REPORTS/'FINAL_GLOBAL_BOUND_TRAJECTORY.csv',trajectory)
    baseline=read(ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/RESULT.json')
    comparisons=[dict(candidate='B0_ARCHIVED_ORIGINAL_C3A',source_HEAD='d541a9d15a03c4a6f8dbc1906a57c7486e9700e3',measurement='ARCHIVED',native_calls_new=0,native_status=baseline['native_status'],Runtime=baseline['Runtime'],Work=baseline['Work'],wall=baseline['total_wall_seconds'],rows=baseline['rows'],cols=baseline['columns'],nnz=baseline['nnz'],native_LP_primal=baseline['native_LP_objective'],current_valid_global_LB=LB,new_certified_gain='not a new experiment'),dict(candidate='B1_FULL_PHYSICS_GRID_CLOSURE',source_HEAD=BASE,measurement='REUSE_B0_IDENTICAL_LP_NO_DUPLICATE_SOLVE',native_calls_new=0,current_valid_global_LB=LB,new_certified_gain=0),dict(candidate='B2_TEMPORAL_DISJUNCTIVE_COMPACT_MODEL',source_HEAD=BASE,measurement='NOT_MEASURED' if not root.get('executed') else 'FRESH',native_calls_new=root.get('native_optimize_calls',0),native_status=root.get('Status'),Runtime=root.get('Runtime'),Work=root.get('Work'),charged_native_Runtime=root.get('charged_native_Runtime',root.get('Runtime',0)),wall=root.get('controller_optimize_wall_seconds'),rows=583459,cols=306040,nnz=5352914,current_valid_global_LB=lb,new_certified_gain='NOT_MEASURED' if not root.get('executed') else lb-LB)]
    table(REPORTS/'ROOT_LB_COMPARISON.csv',comparisons)
    write(REPORTS/'MIP_CANARY_RESULT.json',dict(executed=False,native_calls=0,Runtime=None,Work=None,charged_native_Runtime=0,reason='ROOT_MATERIAL_GATE_NOT_MET_OR_UNMEASURED',production_executed=False,M1_ACCEPTED=False))
    inherited_cert=read(WORK/'artifacts/PREVIOUS_ZF_COMPLETED_CERTIFICATE/INDEPENDENT_BATTERY_EXACT_CERTIFICATE.json')
    history=[('152','Incomplete exact pricing/convergence;1604columns, certified interval[0.5687115725336208,0.5741861223241257]','No pricing or trajectory-column enumeration; original compact axes retained'),('158/159','Grid-only generation and one-tree callbacks gave no certified bound gain; root remained stalled','All96-slot physics and original grid retained, actual new integer-valid temporal SOC inequalities'),('167','Tested local hulls:320rows, certified LB unchanged','All4 MESS / all96-slot movement arcs, global endpoint SOC consequences; no local-window EF'),('169','4-slot/two-block joint hulls gave certified gain0; UB improved independently','No 2.397M trajectory pattern enumeration or replicated window;651small sparse original-variable rows'),('179','Cold exact children:median197.566s, no certified node-floor gain, gap9.82%','ROOT-strengthening before B&B; no repeat child LP campaign without material gate'),('182','133254/225952addedcolumns and312931/1001388addedrows; ROOT TIME_LIMIT','Addedcolumns0; addedrows651; addednnz1302'),('183','Weak20cuts inactive atnewmaster, first recourse120s unresolved','Full96slot SOC/P/Q/PCS/energy incompactmaster, no giant recourse solve loop')]
    text='|Previous PR|Previous failure cause|New architecture difference|Measured improvement|\n|---|---|---|---|\n'
    for number,cause,diff in history:text+=f'|#{number}|{cause}|{diff}|NOT_MEASURED for certified LB/runtime; exact structure and fixture only|\n'
    (REPORTS/'EXISTING_METHOD_FAILURE_COMPARISON.md').write_text('# 과거 실패와의 비교\n\n'+text+'\n각 PR의 실제 head와 description을 PR_REFERENCE artifacts에 보존했다. PR169의 UB 개선을 LB 개선으로 해석하지 않는다. 새로운 full-domain exact pricing 구조의 실용성을 증명하지 못했으므로 pricing 대안은 개발하지 않았다.\n',encoding='utf-8')
    from .review import documents
    for name,content in documents(classification,root,decision,temporal,inherited_cert).items():
        (REPORTS/name).write_text(content,encoding='utf-8')
    print('REPORT_CLASSIFICATION',classification,flush=True)

def package():
    destination=ROOT/'docs/v42_m1_physics_strengthened_20261008';destination.mkdir(parents=True,exist_ok=True)
    for path in REPORTS.iterdir():
        if path.is_file() and path.name not in ('SHA256_MANIFEST.json','GIT_COMPLETION.json'):shutil.copyfile(path,destination/path.name)
    for sub in ('artifacts','logs','checkpoints'):
        for path in (WORK/sub).rglob('*'):
            if not path.is_file() or path.is_relative_to(WORK/'artifacts/source_authority'):continue
            out=destination/sub/path.relative_to(WORK/sub);out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,out)
    shutil.copyfile(WORK/'tmp/activate.ps1',destination/'ACTIVATE_D.ps1')
    files={str(p.relative_to(destination)).replace('\\','/'):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(destination.rglob('*')) if p.is_file() and p.name not in ('SHA256_MANIFEST.json','GIT_COMPLETION.json')}
    sources={str(p.relative_to(ROOT)).replace('\\','/'):dict(sha256=sha(p),bytes=p.stat().st_size) for p in (ROOT/'v42_physics_redesign').glob('*.py')}
    manifest=dict(created_UTC=datetime.now(timezone.utc).isoformat(),algorithm='SHA256',manifest_self_excluded=True,post_publication_git_completion_excluded=True,files=files,source_modules=sources,source_BASE=BASE,scientific_source_hashes=read(REPORTS/'SOURCE_CENSUS.json')['scientific_input_SHAs'],traffic_copy_sha256=sha(WORK/'artifacts/source_authority/ROUTE_TABLE.json.gz'))
    write(REPORTS/'SHA256_MANIFEST.json',manifest);write(destination/'SHA256_MANIFEST.json',manifest);print('PACKAGED',len(files),len(sources),flush=True)

if __name__=='__main__':
    if '--prepare' in sys.argv:prepare()
    else:main();package()

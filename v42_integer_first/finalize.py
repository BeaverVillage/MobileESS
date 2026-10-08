"""Solver-free final review, evidence mirror, and byte manifests."""
from .common import *
from .certificates import solver_transport,exact_value
from datetime import datetime,timezone
import shutil,re
DOC=ROOT/'docs/v42_m1_route_mode_benders_20261008'
def main():
    A,d,_=hc.load();reader=hc.physical_reader();best=np.load(WORK/'artifacts/BEST_VALID_POINT.npz')['x'];replay=prior.prior.full_replay(A,d,best,reader);assert replay['PASS']
    paths_audit('final_optimize_zero_validation');write(REPORTS/'BEST_FULL_REPLAY.json',replay)
    speed=json.loads((REPORTS/'RECOURSE_NUMERICAL_AUDIT.json').read_text(encoding='utf-8-sig'));can=json.loads((REPORTS/'CANARY_RESULT.json').read_text(encoding='utf-8-sig'));census=json.loads((REPORTS/'ASSIGNMENT_CENSUS.json').read_text(encoding='utf-8-sig'));registry=json.loads((REPORTS/'BENDERS_CUT_CERTIFICATES.json').read_text(encoding='utf-8-sig'));fixture=json.loads((REPORTS/'BOUNDED_FIXTURE_VERIFICATION.json').read_text(encoding='utf-8-sig'));account=json.loads((REPORTS/'FIXTURE_NATIVE_ACCOUNTING.json').read_text(encoding='utf-8-sig'));identity=json.loads((REPORTS/'SCIENTIFIC_IDENTITY.json').read_text(encoding='utf-8-sig'))
    assert can['canary_campaigns']==1 and can['master_calls']==1 and can['recourse_calls']==1 and can['native_Runtime']<900
    assert can['new_LB']==LB and best[239826]==can['new_UB']
    assert all(sha(path)==expected for path,expected in identity['sources'].items())
    identities=prior.objective_identity(A,d);assert identities['PASS']
    route_cols=np.flatnonzero([str(n).startswith('route_flow[') for n in d['names']]);B=np.flatnonzero(d['types']=='B');mode=np.flatnonzero([str(n).startswith('charge_mode[') for n in d['names']]);nodes=np.setdiff1d(B,mode)
    center=prior.center();diverse=set();patterns=[]
    for i,path in enumerate(sorted((WORK/'artifacts/assignments').glob('*.npz'))):
        x=np.load(path)['x'];rh=hashlib.sha256(np.rint(x[route_cols]).astype(np.uint8).tobytes()).hexdigest();diverse.add(rh)
        patterns.append(dict(assignment=path.stem,integer_route_SHA256=rh,source=census['valid'][i]['label'],charge_mode_ones=int(np.rint(x[mode]).sum())))
    write(REPORTS/'ASSIGNMENT_DIVERSITY.json',dict(count=len(patterns),distinct_integer_route_patterns=len(diverse),distinct_binary_patterns=len(set(x['id'] for x in census['valid'])),patterns=patterns,peak_period_historical_routes_included=True,sample_is_not_master_domain=True))
    change=dict(changed_node_activity_bits=int(np.count_nonzero(np.rint(best[nodes])-np.rint(center[nodes]))),changed_charge_mode_bits=int(np.count_nonzero(np.rint(best[mode])-np.rint(center[mode]))),changed_integer_route_flow_bits=int(np.count_nonzero(np.rint(best[route_cols])-np.rint(center[route_cols]))),changed_binary_names=[str(d['names'][j]) for j in B if round(best[j])!=round(center[j])],maximum_dispatch_change_by_family={family:float(abs(best-center)[[str(n).startswith(family+'[') for n in d['names']]].max(initial=0)) for family in ('Pch','Pdis','Q','SOC')})
    write(REPORTS/'VALID_UB_CHANGE.json',dict(old_UB=UB,new_UB=can['new_UB'],absolute_improvement=UB-can['new_UB'],relative_improvement=(UB-can['new_UB'])/UB,old_LB=LB,new_LB=can['new_LB'],old_gap_percent=100*(UB-LB)/UB,new_gap_percent=can['gap_percent'],source_best_assignment=speed['best_assignment'],full_replay_PASS=True,**change))
    cutvals=[];witnesses=sorted((WORK/'artifacts/assignments').glob('*.npz'))
    for raw in registry['certificates']:
        cc=raw if raw['PASS'] else raw['optimize_zero_recovery'];assert cc['PASS'];beta,alpha,tr=solver_transport(cc,d);assert tr['PASS']
        # Independently compare actual delivered floating affine rows in exact
        # Fraction arithmetic against their exact-source functions.
        from fractions import Fraction as F
        for path in witnesses:
            z=np.load(path)['z'];delivered=F.from_float(alpha)+sum((F.from_float(float(b))*int(v) for b,v in zip(beta,z)),F(0));assert delivered<=exact_value(cc,z)
        cutvals.append(dict(assignment=raw['assignment'],certificate_loss=cc['certificate_loss'],PASS=True))
    write(REPORTS/'FINAL_VALIDATION.json',dict(PASS=True,optimize_calls=0,original_objective_bit_identity=identities,all_sources_hash_unchanged=True,best_full_replay_PASS=True,actual_delivered_cuts_exactly_dominated_by_source_at_all_20_witnesses=True,cuts=cutvals,bounded_fixtures_PASS=fixture['PASS'],new_route_integrality=0,added_scientific_cuts=0,scientific_objective_changes=0,C_experiment_writes=0,A_stage_touches=0,downstream_solves=0))
    drive=json.loads((REPORTS/'D_DRIVE_EXECUTION_AUDIT.json').read_text(encoding='utf-8-sig'));reloc=json.loads((REPORTS/'RAW_INPUT_RELOCATION.json').read_text(encoding='utf-8-sig'));drive.update(all_writable_application_paths_D=True,strict_all_scientific_reads_D_from_start=False,read_path_deviation=reloc,all_subsequent_route_readers_D=True,all_new_outputs_D=True,initial_C_read_disclosed=True);write(REPORTS/'D_DRIVE_EXECUTION_AUDIT.json',drive)
    p179=json.loads((ROOT/'docs/v42_m_practical_exact_solver_overnight_20261008/RESULT.json').read_text(encoding='utf-8-sig'));p182=json.loads((ROOT/'docs/v42_m1_joint_formulation_20261008/RESULT.json').read_text(encoding='utf-8-sig'))
    phase_wall=speed['wall_seconds']+can['wall_seconds'];native=speed['native_Runtime']+can['native_Runtime'];work=speed['native_Work']+can['native_Work']
    comparisons=dict(PR179=p179['decision']['comparison'],PR182=p182['root_comparison'],pilot=dict(valid_LB_gain_per_fullscale_controller_wall_second=0.,valid_UB_gain_per_fullscale_controller_wall_second=(UB-can['new_UB'])/phase_wall,gap_reduction_percentage_points=100*(UB-LB)/UB-can['gap_percent'],feasible_recourse_per_native_second=20/speed['native_Runtime'],feasible_recourse_per_controller_wall_second=20/speed['wall_seconds'],canary_completed_iteration_throughput=0,fullscale_controller_wall_seconds=phase_wall,phase_wall_excludes_static_audits_git_and_bounded_fixtures=True,fullscale_native_Runtime=native,fullscale_native_Work=work,peak_RSS=max(speed['peak_RSS'],can['peak_RSS']),native_raw_certification_success_rate=19/20,exact_cut_acceptance_after_explicit_optimize_zero_recovery=20/20),comparison_limit='Fixed original integer recourse is a different workload from fractional monolithic ROOT / child LP. Method=1 unknown-candidate recourse and Method=2 feasible benchmark are also different algorithm policies. No causal monolithic solver speedup or production exact convergence claimed.')
    write(REPORTS/'PERFORMANCE_COMPARISON.json',comparisons)
    next_action='저장된 첫 master 배정 한 개에 대해, 원본 continuous route_flow를 상단 master의 좌표 f로 명시하고 z와 f를 함께 고정하는 original min-rho recourse 및 (z,f) affine cut의 exact support 인증을 120초 단일 파일럿으로 비교한다. 원본 정수 projection 증명과 finite-bound weak duality를 유지하며 새로운 과학적 물리식이나 route 제한은 추가하지 않는다.'
    result=dict(classification='INTEGER_FIRST_CUT_CERTIFICATION_FAIL',reason='Feasible recourse and original-domain master were fast; first new integer candidate failed to yield a terminal recourse or independently certified separating cut within its preregistered 120s limit. TIME_LIMIT is not infeasibility proof. The one 900s-cap canary stopped at the cut-validity gate.',equivalence_PASS=True,objective_identity_PASS=True,recourse_assignments_tested=20,recourse_median_Runtime=speed['median_Runtime'],recourse_p90_Runtime=speed['p90_Runtime'],recourse_max_Runtime=speed['max_Runtime'],feasible_replay_PASS=20,initial_native_certificate_rejections=1,explicit_optimize_zero_projection_recoveries=1,successful_fullscale_optimality_cuts=20,successful_fullscale_feasibility_cuts=0,canary_separation_unresolved=1,initial_LB=LB,final_LB=can['new_LB'],initial_UB=UB,final_UB=can['new_UB'],absolute_UB_improvement=UB-can['new_UB'],global_gap_percent=can['gap_percent'],fullscale_native_Runtime=native,fullscale_native_Work=work,fullscale_controller_wall_seconds=phase_wall,bounded_fixture_native_accounting=account,total_native_Runtime_with_rounded_fixture_logs=native+account['Runtime_log_rounded'],total_native_Work_with_rounded_fixture_logs=work+account['Work_log_rounded'],scientific_fullscale_optimize_calls=22,bounded_fixture_optimize_calls_including_failed_attempts=account['native_calls_from_pre_solve_audits'],total_native_optimize_calls=22+account['native_calls_from_pre_solve_audits'],peak_RSS=max(speed['peak_RSS'],can['peak_RSS']),point5_percent_achieved=False,production_promising=False,canary=can,next_action=next_action,next_action_count=1,next_action_executed=False,continuation_executed=False,paths={k:str(WORK/k) for k in ('repo','artifacts','logs','tmp','cache','checkpoints','reports')},git_common=str(ROOT/'.git'),C_installed_executable=os.path.realpath(sys.executable),initial_frozen_C_route_read_deviation_disclosed=True,all_new_files_D=True,git_completion='Post-publication GIT_COMPLETION.json is external only to avoid self-referential commit hashes.')
    write(REPORTS/'FINAL_RESULT.json',result)
    timestamp=datetime.now(timezone.utc).isoformat();write(REPORTS/'TASK_WALL_ACCOUNTING.json',dict(report_finalization_UTC=timestamp,fullscale_controlled_phase_wall_seconds=phase_wall,bounded_fixture_wall_seconds_not_persisted=True,does_not_equate_native_Runtime_to_total_task_wall=True,workspace_creation_to_git_completion_seconds_recorded_after_publication=True))
    review=f'''# M1 Integer-First Exact Decomposition 최종 검토

판정: **INTEGER_FIRST_CUT_CERTIFICATION_FAIL**. 원본 동치와 feasible recourse는 통과했으나, 첫 새 master 배정에서 인증된 separating cut을 얻지 못했다. production-promising=False이며 0.5% exact convergence는 달성하지 못했다.

| 항목 | 결과 |
|---|---:|
| 원본 objective / ObjCon / axis bit identity | PASS |
| 전체 integer projection / recourse / epigraph 증명 | PASS |
| 20개 원본 배정 feasible full replay | 20 PASS / 0 infeasible / 0 unknown |
| recourse Runtime median / p90 / max | {speed['median_Runtime']:.6f} / {speed['p90_Runtime']:.6f} / {speed['max_Runtime']:.6f} s |
| 초기 native cut 인증 | 19 accepted / 1 rejected |
| 명시적 optimize=0 multiplier 교정 후 valid optimality cuts | 20 |
| full-scale valid feasibility cuts | 0 |
| initial / final LB | {LB:.16f} / {can['new_LB']:.16f} |
| initial / final UB | {UB:.16f} / {can['new_UB']:.16f} |
| valid UB improvement | {UB-can['new_UB']:.16f} |
| global gap | {can['gap_percent']:.9f}% |
| full-scale native Runtime / Work | {native:.6f} s / {work:.6f} |
| full-scale controller wall 합계 | {phase_wall:.6f} s |
| bounded fixture native Runtime / Work, log-rounded | {account['Runtime_log_rounded']:.2f} s / {account['Work_log_rounded']:.2f} |
| 전체 optimize 횟수 | {22+account['native_calls_from_pre_solve_audits']} (과학적 full scale 22; 작은 fixture 및 실패 교정 {account['native_calls_from_pre_solve_audits']}) |
| peak RSS | {result['peak_RSS']} bytes ({result['peak_RSS']/2**30:.3f} GiB) |
| 0.5% 달성 / production 준비 / 자동 continuation | False / False / 없음 |

총 native 합계는 full-scale API 158.475초에 작은 fixture의 0.01초 정밀도 로그 합계 0.10초를 더한 값이다. controller wall 합계는 벤치마크와 canary만 포함하며 Git, 정적 감사, 문서 작성 및 작은 fixture wall과 구분한다. 전체 작업공간 생성부터 PR 게시까지의 경과시간은 외부 GIT_COMPLETION에 남긴다. 시간과 알고리즘 조건이 다른 PR179/182에 대해 인과적 speedup을 주장하지 않는다.

## 첫 canary의 실제 종료

등록 상한 900초에서 master 1회와 새 recourse 1회만 실행했다. master는 OPTIMAL, Runtime 2.218999863초, Work 2.831414536, 1 node, root barrier 1.17초 / crossover 0.02초였다. complete integer candidate의 binary와 implied route-flow 오차는 모두 0이다. BestBd는 inherited LB와 같다.

첫 새 recourse는 simplex Method=1, 원본 min rho로 120.000999928초 / Work 194.927626185 / 133287 iterations 뒤 TIME_LIMIT이다. 원본 전체 행렬에서 큰 primal infeasibility가 남았다. terminal infeasibility proof나 replay-PASS point를 얻지 못했고, 이 결과를 INFEASIBLE이라고 바꾸거나 restricted bound를 global LB로 사용하지 않았다. cut-validity gate에서 campaign을 중단했으므로 900초를 억지로 소비하지 않았다. 새 feasibility cut, 두 번째 candidate, 재실행, 1800초 continuation은 없다.

## Cut 강도와 수치 검증

20개 optimality cuts는 각 feasible source에서 거의 tight하지만 첫 master candidate에서 최대 delivered value가 0.5506661698094345로 floor 0.5687116104049206보다 작다. 따라서 모두 valid해도 이 배정의 theta를 올리지 못한다. 첫 새 배정을 제외할 인증된 feasibility cut이 나오지 않아 LB 진전이 없다. 시간을 늘리지 않고 이 원인을 `CUT_STRENGTH_DIAGNOSIS.json`에 보존했다.

raw multiplier wrong sign 3.671267600429335e-10인 한 certificate를 reject했다. native source 파일은 그대로 보존하고, admissible sign cone의 별도 multiplier에서 exact matrix products / finite-bound support / floating transport envelope 전체를 다시 계산하여 새 valid cut을 얻었다. 묵시적 coefficient clamp나 불완전한 ray 채택은 없다. PCS/grid/injection stationarity 잔차를 0이라고 가정하지 않는다. 원본 bounds는 모두 finite다. 큰 coefficient-range warning은 원본 matrix에서 발생하며 original coefficient나 rho objective는 변경하지 않았다.

작은 bounded **algebraic validation fixture** 두 개는 독립 direct monolithic MILP와 1e-8 이내 일치했다. 1 MESS/2 slots/2 sites는 objective 0.6, 2 MESS/3 slots/2 sites는 0.5565866383266509다. fixture에서 optimality 11개와 feasibility 7개를 통과시켰다. fixture는 과학적 synthetic physical input이나 원본 network 대체 데이터가 아니다. 처음 barrier INFEASIBLE에서 Farkas attribute가 없었던 실패와 이후 native sign rejection도 보존했다. 일반 full C3A 동치 증명은 별도 문서에 있다.

## 유효 UB의 출처

UB 개선은 첫 20개 recourse의 배정 018에서 나왔다. 원본 node activity와 route path는 기존 center와 같고 charge_mode 1개만 다르다. 바뀐 binary는 {change['changed_binary_names']}다. 원본 continuous dispatch를 optimize했고 route/movement/SOC/PQ/PCS/grid/A1의 full replay를 통과했다. best vector와 native dual/RC/slack는 검증 전에 저장했다. {len(diverse)}개의 서로 다른 integer route pattern과 20개 distinct binary pattern을 표본으로 검사했지만 이를 global search domain으로 제한하지 않았다.

## 경로와 보존 감사

새 checkout 및 Git common directory는 `D:\\v42_m1_route_mode_benders_20261008\\repo` / `.git`이다. artifacts, logs, tmp, cache, checkpoints, reports는 모두 같은 D: root 아래다. 모든 heavy solve 전에 TEMP/TMP/TMPDIR/PIP_CACHE_DIR/PYTHONPYCACHEPREFIX 및 solver LogFile/NodefileDir를 확인했다. 설치 Python/Gurobi executable만 C: 예외다. 원본 C3A / A1 / 과거 PR evidence / concurrent A-stage를 수정하거나 중단하지 않았다. zero scientific objective와 downstream 실행은 0회다.

**경로 규약 누락을 명시한다:** 초기 historical graph reader가 동결 traffic raw input을 C:에서 읽었다. 뒤에 D: 복사와 source-before / source-after / copy SHA256 일치를 검증하고, 이후 reader를 D:로 재지정했다. 초기부터 모든 scientific read가 D:였다고 주장하지 않는다. 새 실험파일과 C: scientific 쓰기는 없다. `RAW_INPUT_RELOCATION.json` 및 D audit에 이 편차를 보존했다.

## 다음 행동 정확히 하나

{next_action}

이번에는 실행하지 않았다. native solve를 모두 종료했고 이 단일 canary 뒤 멈췄다. final HEAD / Draft PR / remote HEAD match / clean tree는 게시 뒤 `D:\\v42_m1_route_mode_benders_20261008\\reports\\GIT_COMPLETION.json`에 기록하며 최종 답변에도 제공한다.
'''
    (REPORTS/'FINAL_REVIEW_KO.md').write_text(review,encoding='utf-8')
    # Mirror complete scientific evidence, never caches, nodefiles, .git or C.
    DOC.mkdir(parents=True,exist_ok=True)
    for path in REPORTS.iterdir():
        if path.is_file() and path.name not in ('SHA256_MANIFEST.json','GIT_COMPLETION.json'):shutil.copy2(path,DOC/path.name)
    for folder in ('artifacts','logs','checkpoints'):
        for path in (WORK/folder).rglob('*'):
            if path.is_file():target=DOC/folder/path.relative_to(WORK/folder);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    manifest=dict(created_UTC=timestamp,algorithm='SHA256',manifest_self_excluded=True,post_publication_git_completion_excluded=True,files={p.relative_to(DOC).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(DOC.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'},source_modules={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted((ROOT/'v42_integer_first').glob('*.py'))})
    write(DOC/'SHA256_MANIFEST.json',manifest);write(REPORTS/'SHA256_MANIFEST.json',manifest)
    print('FINAL_VALIDATION_PASS',result['classification'],'UB',can['new_UB'],'gap',can['gap_percent'],'mirrored_files',len(manifest['files']),flush=True)
if __name__=='__main__':main()

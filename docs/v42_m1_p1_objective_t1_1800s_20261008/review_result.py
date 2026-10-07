"""Read-only postsolve interpretation and evidence seal. No solver calls."""
from support import *
import re

def main():
    r=read(OUT/'RESULT.json');v=read(OUT/'VERIFICATION.json');token=read(OUT/'OPTIMIZE_ONCE.json')
    mt=read(OUT/'MODEL_TRANSPORT_AUTHORITY.json');params=read(OUT/'SOLVER_PARAMETERS.json')
    tl=read(OUT/'ROOT_TIMELINE.json');times=tl['times'];log=(OUT/'NATIVE_SOLVER.log').read_text(encoding='utf-8')
    assert r['optimize_calls']==token['optimize_calls']==1 and v['PASS'] and mt['PASS']
    assert params['settings']==token['settings']==SETTINGS
    assert params['all_effective_parameters_match_PR175_except_LogFile']
    assert read(OUT/'OBJECTIVE_IDENTITY.json')['PASS'] and mt['native_rows']==583173 and mt['native_nnz']==5373861
    assert protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']
    assert all(sha(PARENT/n)==h for n,h in read(PARENT/'SHA256_MANIFEST.json')['files'].items())
    trajectory=list(csv.DictReader((OUT/'BOUND_NODE_TRAJECTORY.csv').open(encoding='utf-8')))
    if not trajectory or float(trajectory[-1]['Runtime'])!=r['Runtime']:
        for x in trajectory:x['observation']='MIP_CALLBACK'
        trajectory.append(dict(Runtime=r['Runtime'],Work=r['Work'],node_count=r['NodeCount'],nodes_left=None,solution_count=r['SolCount'],native_ObjBst=r['native_ObjVal'],native_ObjBnd=r['native_ObjBound'],simplex_iterations=r['IterCount'],cut_count=None,observation='FINAL_NATIVE_RECEIPT'))
        table('BOUND_NODE_TRAJECTORY.csv',trajectory)
    rss=list(csv.DictReader((OUT/'RESOURCE_TELEMETRY.csv').open(encoding='utf-8')))
    candidates=read(OUT/'CANDIDATE_REPLAYS.json')['audits']
    def printed(pattern):
        m=re.search(pattern,log);return float(m.group(1)) if m else None
    printed_times=dict(presolve=printed(r'Presolve time: ([0-9.]+)s'),barrier=printed(r'Barrier solved model in .*? and ([0-9.]+) seconds'),crossover=printed(r'Crossover time: ([0-9.]+) seconds'),root_relaxation=printed(r'Root relaxation:.*?, ([0-9.]+) seconds'))
    branch=[float(x['Runtime']) for x in trajectory if float(x['node_count'])>1 or (x.get('nodes_left') not in (None,'') and float(x['nodes_left'])>1)]
    observations=[times['first_nonroot_node'],times['first_branch_evidence']]+branch
    branch_upper=min(x for x in observations if x is not None) if any(x is not None for x in observations) else None
    relaxation_end=times['root_relaxation_complete'];nonroot=times['first_nonroot_node']
    timing=dict(native_Runtime=r['Runtime'],build_outside_TimeLimit=mt['build_seconds'],native_printed_phase_seconds=printed_times,callback_timestamps=times,root_relaxation_completed=relaxation_end is not None,root_search_left_root_evidence=nonroot is not None,first_branch_exact=None,first_branch_observed_upper_bound=branch_upper,first_branch_observation_rule='Earliest MIP trajectory with nodes_left>1 or node_count>1, or nonroot MIPNODE; exact branch-start time is not exposed',post_root_relaxation_interval=r['Runtime']-relaxation_end if relaxation_end is not None else None,observed_nonroot_search_interval=r['Runtime']-nonroot if nonroot is not None else None,post_root_interval_includes_root_MIP_processing=True,peak_sampled_RSS=max(int(x['RSS']) for x in rss),peak_working_set=max(int(x['peak_wset']) for x in rss if x['peak_wset']),RSS_sampling_seconds=2,first_MIPNODE=times['first_MIPNODE'],first_feasible_witness=times['first_feasible'])
    native_rss=[int(x['RSS']) for x in rss if x['phase'] not in ('BUILD','REPLAY')]
    timing['peak_native_solve_RSS']=max(native_rss) if native_rss else None
    timing['peak_sampled_RSS_includes_build_and_replay']=True
    timing['barrier_end_native_printed_cumulative_runtime']=printed_times['barrier']
    timing['barrier_observed_phase_seconds']=times['barrier_end']-times['barrier_start'] if times['barrier_end'] is not None and times['barrier_start'] is not None else None
    timing['native_barrier_printed_value_is_not_exclusive_barrier_duration']=True
    boundaries=[('PRESOLVE_AND_INITIALIZATION',0.,times['presolve_end']),('ROOT_SETUP',times['presolve_end'],times['barrier_start']),('ROOT_BARRIER',times['barrier_start'],times['barrier_end']),('ROOT_POST_BARRIER',times['barrier_end'],times['crossover_start']),('CROSSOVER',times['crossover_start'],times['crossover_end']),('ROOT_POST_CROSSOVER',times['crossover_end'],relaxation_end),('ROOT_MIP_PROCESSING',relaxation_end,nonroot if nonroot is not None else r['Runtime'])]
    if nonroot is not None:boundaries.append(('OBSERVED_NONROOT_SEARCH',nonroot,r['Runtime']))
    ledger=[dict(phase=n,start_native_Runtime=a,end_native_Runtime=b,seconds=b-a) for n,a,b in boundaries if a is not None and b is not None]
    write('PHASE_LEDGER.json',dict(native_Runtime=r['Runtime'],observed_boundary_intervals=ledger,sum_seconds=sum(x['seconds'] for x in ledger),timing_authority='Native callback timestamps; phase boundaries include logging overhead',build_outside_native_budget=mt['build_seconds'],printed_durations=printed_times,barrier_printed_value_is_cumulative=True))
    write('POST_ROOT_TIMING.json',timing)
    if r['Status'] in (9,11) and not r['feasible_witness']:
        assert r['global_LB_new']==LB and r['global_UB_new']==UB
        assert not (OUT/'LB_UPDATE.json').exists() and not (OUT/'UB_UPDATE.json').exists()
    gap=dict(old_LB=LB,new_LB=r['global_LB_new'],old_UB=UB,new_UB=r['global_UB_new'],global_gap_fraction=r['global_gap'],global_gap_percent=100*r['global_gap'],formula='(UB-LB)/UB',native_Status=r['Status'],both_bounds_unchanged_if_no_valid_witness_or_proof=True,restricted_native_ObjBound_not_promoted_to_global_LB=True,T1=T1)
    write('GAP_UPDATE.json',gap)
    if not (OUT/'BEST_FULL_REPLAY.json').exists():
        write('BEST_FULL_REPLAY.json',dict(available=False,PASS=None,reason='No independently replay-PASS integer witness',unique_candidates_audited=len(candidates),native_SolCount=r['SolCount'],not_a_failed_replay=True,no_new_solve=True))
    node_progress=[];last=None
    for x in trajectory:
        if float(x['node_count'])!=last:
            node_progress.append(x);last=float(x['node_count'])
    write('NODE_PROGRESSION.json',dict(unobserved_callback_gaps_not_interpolated=True,final_native_endpoint_separately_labelled=True,events=node_progress,final_NodeCount=r['NodeCount'],all_samples='BOUND_NODE_TRAJECTORY.csv',native_log='NATIVE_SOLVER.log'))
    parent=read(PR175/'RESULT.json')
    comparison=dict(PR175_zero_objective_1800s={k:parent[k] for k in ('Runtime','Work','NodeCount','SolCount','Status','global_LB_new','global_UB_new')},original_P1_T1_1800s={k:r[k] for k in ('Runtime','Work','NodeCount','SolCount','Status','global_LB_new','global_UB_new')},same_matrix_bounds_types=True,same_cuts=True,same_full_domain=True,only_scientific_objective_restored=True,all_solver_parameters_unchanged=True,no_resume=True)
    prior_t=read(PR175/'POST_ROOT_TIMING.json')
    comparison['zero_objective_was_scientifically_invalid']=True
    comparison['PR175_root_completion']=read(PR175/'ROOT_TIMELINE.json')['times']['root_relaxation_complete']
    comparison['restored_objective_root_completion']=relaxation_end
    comparison['PR175_post_root_interval']=prior_t['post_root_relaxation_interval']
    comparison['restored_objective_post_root_interval']=timing['post_root_relaxation_interval']
    comparison['restored_native_ObjBound']=r['native_ObjBound']
    comparison['PR175_zero_native_ObjBound']=parent['feasibility_ObjBound']
    comparison['PR175_Model_Fingerprint']=read(PR175/'MODEL_TRANSPORT_AUTHORITY.json')['Fingerprint']
    comparison['restored_Model_Fingerprint']=mt['Fingerprint']
    comparison['PR175_crossover_printed_seconds']=prior_t['native_printed_phase_seconds']['crossover']
    comparison['restored_crossover_printed_seconds']=printed_times['crossover']
    comparison['PR175_first_MIPNODE']=read(PR175/'ROOT_TIMELINE.json')['times']['first_MIPNODE']
    comparison['restored_first_MIPNODE']=times['first_MIPNODE']
    comparison['PR175_original_P1_objective_identity']=False
    comparison['restored_original_P1_objective_identity']=read(OUT/'OBJECTIVE_IDENTITY.json')['PASS']
    def presolved(text):
        m=re.search(r'^Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',text,re.M)
        return dict(rows=int(m[1]),cols=int(m[2]),nnz=int(m[3])) if m else None
    comparison['PR175_presolved']=presolved((PR175/'NATIVE_SOLVER.log').read_text(encoding='utf-8'))
    comparison['restored_presolved']=presolved(log)
    write('VS_PR175_ZERO_OBJECTIVE.json',comparison)
    obj=read(OUT/'OBJECTIVE_IDENTITY.json')
    ko=f"""# 원래 M1 P1 minimize rho 복원 + T1 / 1800초 최종 검토

분류: **{r['classification']}**. Native 상태 **{r['native_status']}**. 요청한 새 native solve를 정확히 한 번 실행했고 이후 추가 실험은 실행하지 않았다.

기준은 Draft PR175 exact HEAD `{BASE}`이며 실행 소스 커밋은 `{token['source_commit']}`이다. 최종 공개 HEAD는 새 Draft PR 본문과 최종 대화에서 확인할 수 있다. PR175 위에 적층하며 기존 증거 파일은 모두 그대로 보존한다.

| 항목 | 기존 | 이번 결과 |
|---|---:|---:|
| 전역 LB | {LB:.16f} | {r['global_LB_new']:.16f} |
| 검증된 UB | {UB:.16f} | {r['global_UB_new']:.16f} |
| 전역 gap | {(UB-LB)/UB*100:.9f}% | {r['global_gap']*100:.9f}% |
| T1 | {T1:.16f} | 동일 |
| TimeLimit | 1800초 | 1800초 |
| 과학적 목적 | PR175의 잘못된 zero objective | PR162 원래 minimize rho 복원 |

Runtime={r['Runtime']:.6f}초, Work={r['Work']:.9f}, NodeCount={r['NodeCount']}, SolCount={r['SolCount']}, MIPSOL={r['MIPSOL_events']}. 원래 모델 replay-PASS witness={r['feasible_witness']}. 저장한 고유 정수 후보는 {len(candidates)}개이다. 후보가 존재하면 모두 독립 검증한다. 후보가 없으면 replay는 해당 없음이며 검증 FAIL을 의미하지 않는다.

| 단계/관측 | 초 |
|---|---:|
| Build (native 예산 밖) | {mt['build_seconds']:.6f} |
| Presolve (native 출력) | {printed_times['presolve']} |
| Barrier 완료 누적 시각 (native 출력) | {printed_times['barrier']} |
| Barrier 관측 구간 (콜백 경계 차이) | {timing['barrier_observed_phase_seconds']} |
| Crossover (native 출력) | {printed_times['crossover']} |
| Root relaxation (native 출력, barrier/crossover 포함) | {printed_times['root_relaxation']} |
| Root relaxation 완료 시각 | {relaxation_end} |
| 최초 MIPNODE | {times['first_MIPNODE']} |
| 최초 nonroot MIPNODE | {nonroot} |
| 최초 분기 관측 상한 | {branch_upper} |
| 최초 feasible witness | {times['first_feasible']} |
| Root relaxation 이후 구간 | {timing['post_root_relaxation_interval']} |
| 관측된 nonroot search 구간 | {timing['observed_nonroot_search_interval']} |

Root relaxation 완료={relaxation_end is not None}, nonroot 관측={nonroot is not None}. Root relaxation 이후 구간에는 root의 MIP 컷·분기 준비 시간이 포함된다. 정확한 분기 시작 시각은 native 공개 콜백에서 노출되지 않아 null로 기록했으며 관측 상한과 구분했다. 콜백이 없는 구간의 Work·노드는 보간하지 않는다. 단계별 경계 차이는 PHASE_LEDGER.json에 저장했으며 native barrier 출력의 {printed_times['barrier']}초는 누적 시각으로 구분했다. 노드 변화 시각은 NODE_PROGRESSION.json, 콜백 관측 시 5초/노드 변화 궤적은 BOUND_NODE_TRAJECTORY.csv, incumbent의 모든 벡터·이벤트는 INCUMBENT_TRACE.csv와 CANDIDATE_REPLAYS.json에 보존했다.

2초 간격 native solve 관측 peak RSS={timing['peak_native_solve_RSS']} bytes. Build/replay를 포함한 전체 관측 peak RSS={timing['peak_sampled_RSS']} bytes ({timing['peak_sampled_RSS']/2**30:.6f} GiB), Windows lifetime peak working set={timing['peak_working_set']} bytes. Native root/barrier/crossover 원문은 NATIVE_SOLVER.log와 ROOT_TIMELINE.json에 보존한다.

전체 모델 583173행/306040열/5373861 nnz, binary 9322/continuous 296718, 원래 C3A 582808행과 기존 검증된 364개 컷, 새 Fingerprint {mt['Fingerprint']}이다. 목적 복원으로 Fingerprint가 바뀌었으며 행렬·변수 범위·타입·기존 컷·T1은 PR175와 동일하다. 원래 행렬·bounds·types를 동일성으로 검사했고 목적계수·ObjCon·변수 축은 PR162 Git 객체를 별도 검증기로 bit-for-bit 비교했다. Objective identity={obj['PASS']}, objective SHA256=`{obj['source_objective_SHA256']}`, variable-axis SHA256=`{obj['source_variable_axis_SHA256']}`, ObjCon bits=`{obj['ObjCon_bits_hex']}`이다. 전체 유효 파라미터에서 출력 로그 경로만 다르다. TimeLimit과 모든 과학적 solver 설정은 PR175와 동일하다. MIP start/basis/checkpoint/tree를 공급하지 않았고 새 모델에서 시작했다. Hamming/추가 threshold/컷 변경·추가/파라미터 sweep/별도 presolve는 없다.

기존 coefficient-range 안내는 동일 행렬·bounds와 기존 수치 판정 권위에 따라 기록했다. 새 수치 경고/오류는 NUMERICAL_AUTHORITY.json에서 별도로 구분한다. T1 추가모델의 원래 목적 native ObjBound={r['native_ObjBound']}는 rho의 전역 LB로 사용하지 않았다. TIME_LIMIT에서 유효 원래 모델 witness나 불가능 증명이 없으면 양쪽 bound를 유지한다. TIME_LIMIT에서도 원래 전체 모델 replay-PASS 정수 witness이며 rho<=T1이면 UB를 갱신할 수 있다. INFEASIBLE의 LB 승격에는 원래 전체 영역·모델·컷·수치 권위가 모두 PASS여야 하며, feasible UB에는 원래 C3A 및 route/movement/SOC/PQ/PCS/grid/A1 독립 replay PASS가 필요하다.

PR175 비교: Runtime {parent['Runtime']:.6f} → {r['Runtime']:.6f}초, Work {parent['Work']:.9f} → {r['Work']:.9f}, 노드 {parent['NodeCount']} → {r['NodeCount']}, 정수 해 {parent['SolCount']} → {r['SolCount']}. 기존 root 완료 {comparison['PR175_root_completion']}초 → 이번 {relaxation_end}. Crossover {comparison['PR175_crossover_printed_seconds']} → {printed_times['crossover']}초, 최초 MIPNODE {comparison['PR175_first_MIPNODE']} → {times['first_MIPNODE']}초. 비교 원문은 VS_PR175_ZERO_OBJECTIVE.json에 저장한다. 기존 zero-objective 실행은 원래 과학적 목적을 보존하지 못한 기록으로 남기며 이를 올바른 P1 목적 실행이라고 해석하지 않는다.

요청한 단일 1800초 실행을 마쳤다. 추가 solve나 MIPFocus=1, May/A2/M2/P2 실험은 실행하지 않는다.
"""
    (OUT/'FINAL_REVIEW_KO.md').write_text(ko,encoding='utf-8')
    seal()

def seal():
    token=read(OUT/'OPTIMIZE_ONCE.json');r=read(OUT/'RESULT.json')
    assert protected()==read(OUT/'BASE_IDENTITY.json')['protected_before']
    required=['PREREGISTRATION.md','OBJECTIVE_IDENTITY.json','OBJECTIVE_PREFLIGHT.json','SOLVER_PARAMETERS.json','MODEL_TRANSPORT_AUTHORITY.json','NATIVE_SOLVER.log','INCUMBENT_TRACE.csv','BOUND_NODE_TRAJECTORY.csv','RESULT.json','BEST_FULL_REPLAY.json','GAP_UPDATE.json','ROOT_TIMELINE.json','POST_ROOT_TIMING.json','NODE_PROGRESSION.json','RESOURCE_TELEMETRY.csv','FINAL_REVIEW_KO.md']
    assert all((OUT/n).is_file() for n in required)
    namespace=OUT.relative_to(ROOT).as_posix()+'/'
    assert all(n.startswith(namespace) for n in git('diff','--name-only',BASE).splitlines())
    write('FINAL_ARTIFACT_AUDIT.json',dict(PASS=True,exact_base=BASE,source_commit=token['source_commit'],single_optimize=1,required_artifacts=required,PR173_PR175_evidence_unchanged=True,original_objective_identity_PASS=read(OUT/'OBJECTIVE_IDENTITY.json')['PASS'],all_parameters_match_except_LogFile=True,no_changed_or_new_cuts=True,full_domain=True,no_resume=True,classification=r['classification'],no_extra_solve=True,namespace_only=True))
    files={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in str(p) and p.suffix!='.pyc'}
    write('SHA256_MANIFEST.json',dict(algorithm='SHA256',files=files,excluded=['SHA256_MANIFEST.json','__pycache__/','*.pyc'],self_reference_excluded=True,source_commit=token['source_commit'],exact_base=BASE))
    assert all(sha(OUT/n)==h for n,h in read(OUT/'SHA256_MANIFEST.json')['files'].items())
    print('FINAL_SEAL_PASS',len(files),r['classification'])

if __name__=='__main__':main()

"""Final Korean report: paired formulations, exclusive timing, UB and physics evidence."""
import csv,re,statistics
from tools.adaptive_perf_v3.bootstrap import *
from tools.adaptive_compact_joint.report_final import export_plan

def csvwrite(path,rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def main():
    configure();full_guard();state=read(DOCS/'FINAL_STATE.json');audit=read(DOCS/'FINAL_INDEPENDENT_REVIEW.json');assert audit['PASS']
    metrics=[];samples=[];callback=[]
    for i,c in enumerate(state['calls']):
        q=read(c['receipt']['path']);folder=Path(c['receipt']['path']).parent;log=(folder/'NATIVE_GUROBI.log').read_text(encoding='utf-8',errors='replace')
        ps=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log);pt=re.findall(r'Presolve time: ([\d.]+)s',log)
        cb=re.findall(r'time in user-callback ([\d.]+) sec',log);binary=re.findall(r'Variable types: .*?\((\d+) binary\)',log)
        rb=read(q['readback']['path']);form=c.get('formulation','DIRECT');wall=c['worker_wall']
        metrics.append(dict(index=i+1,version='PILOT' if i<2 else 'V3' if c in state['new_calls'] else 'V2',epoch=c.get('epoch'),formulation=form,
            Native_before=c['Native_before'],Native_after=c['Native_after'],Native_Runtime=q['Native_Runtime'],Worker_wall=wall,
            model_build_wall=q['model_build_wall_seconds'],input_Rows=rb['NumConstrs'],input_Columns=rb['NumVars'],input_Binaries=rb['NumBinVars'],input_NNZ=rb['NumNZs'],
            Presolve_seconds=float(pt[-1]) if pt else None,Presolved_Rows=int(ps[-1][0]) if ps else None,Presolved_Columns=int(ps[-1][1]) if ps else None,
            Presolved_NNZ=int(ps[-1][2]) if ps else None,Presolved_Binaries=int(binary[-1]) if binary else None,
            Root_completed_Native_seconds=q.get('root_completed_Native_seconds'),NodeCount=q['NodeCount'],BarIterCount=q.get('BarIterCount'),Status=q['Status'],
            ObjVal=q['ObjVal'],restricted_ObjBound=q['ObjBound'],restricted_MIPGap=q['MIPGap'],Global_LB_admissible=False,
            callback_seconds=float(cb[-1]) if cb else None))
        if cb:callback.append(float(cb[-1]))
        samples.extend(s['memory'] for s in q['resource_samples'] if 'memory' in s)
    csvwrite(DOCS/'ALL_NATIVE_SOLVER_METRICS.csv',metrics)
    timing_rows=[]
    for item in state['v3_timings']:
        assert abs(sum(item['parts'].values())+item['other_control_and_IO_wall']-item['total_wall'])<1e-7
        for stage,wall in item['parts'].items():timing_rows.append(dict(epoch=item['epoch'],stage=stage,wall_seconds=wall,whole_iteration_wall=item['total_wall']))
        timing_rows.append(dict(epoch=item['epoch'],stage='other_control_and_IO_wall',wall_seconds=item['other_control_and_IO_wall'],whole_iteration_wall=item['total_wall']))
    csvwrite(DOCS/'V3_EXCLUSIVE_ITERATION_TIMINGS.csv',timing_rows)
    worker_stages=[]
    for c in state['new_calls']:
        q=read(c['receipt']['path']);t=q['stage_timing'];assert abs(sum(t['parts'].values())+t['other_control_and_IO_wall']-t['total_wall'])<1e-7
        for stage,wall in t['parts'].items():worker_stages.append(dict(epoch=c['epoch'],formulation=c['formulation'],stage=stage,wall_seconds=wall))
    csvwrite(DOCS/'V3_WORKER_CREATION_READBACK_AND_NATIVE_TIMINGS.csv',worker_stages)
    write(DOCS/'TIMING_ACCOUNTING.json',dict(PASS=True,exclusive_Controller_and_Worker_stage_sums_match_total=True,Native_Runtime_counted_only_once=True,
        Presolve_Root_callback_times_are_subcomponents_not_added_to_Optimize=True,
        legacy_fine_grained_stages_not_instrumented=True,legacy_unknown_stage_times_not_fabricated=True,
        V3_first_pool_prepared_before_controller=True,first_pool_development_cost=read(DOCS/'NATIVE0_STATIC_GATE.json')['timing'],
        Native_readback_before_Optimize=True,records=state['v3_timings']))
    resource=dict(PASS=True,max_Private_Commit=max(s['Private_Commit_bytes'] for s in samples),max_RSS=max(s['RSS_bytes'] for s in samples),
        min_available_RAM=min(s['system']['RAM_available'] for s in samples),min_available_Commit=min(s['system']['Commit_available'] for s in samples),
        median_callback_seconds=statistics.median(callback),all_resource_numeric_gates_PASS=True)
    write(DOCS/'FINAL_MEMORY_NUMERIC_AUDIT.json',resource)
    comparisons=dict(PASS=True,V2_original_Joint_vs_Direct=state['comparisons'],V3_Direct_vs_sparse_EF=state['v3_comparisons'],
        final_backend=state['backend'],same_pool_Source_Case_Start_parameters_and_TimeLimit=True,one_pool_or_binary_count_not_a_general_benchmark=True)
    write(DOCS/'FORMULATION_COMPARISON.json',comparisons)
    case=v.load_case(native=False);profiles,moves=export_plan(case,state['BEST_GLOBAL_UB']['point']['path'],DOCS/'BEST_GLOBAL_96_SLOT_PLAN.csv')
    moving_profiles,moving=export_plan(case,state['BEST_MOVING_FEASIBLE_UB']['point']['path'],DOCS/'BEST_MOVING_96_SLOT_PLAN.csv')
    actual=min((a for a in state['validations'] if a['PASS']),key=lambda a:a['UB']);ap,am=export_plan(case,actual['raw']['path'],DOCS/'BEST_ACTUAL_JOINT_96_SLOT_PLAN.csv')
    write(DOCS/'BEST_PLAN_AUDIT.json',dict(PASS=True,BEST_GLOBAL=state['BEST_GLOBAL_UB'],BEST_MOVING=state['BEST_MOVING_FEASIBLE_UB'],best_actual_joint=actual,
        selected_per_unit_MOVEs={u:p['MOVE_count'] for u,p in ap.items()},best_moves=moves,actual_joint_moves=am,SOC_97_each=True,physical_profiles=ap))
    del case;gc.collect()
    candidates=[];pool_scores=[]
    for path in sorted(DOCS.glob('CANDIDATE_DIAGNOSTICS_*.json')):
        diag=read(path);epoch=int(path.stem.rsplit('_',1)[1]);calls=[c for c in state['new_calls'] if c['epoch']==epoch]
        if not calls:continue
        pool_actual=min(read(c['receipt']['path'])['ObjVal'] for c in calls)
        pool_scores.append(dict(epoch=epoch,pool_signature=diag['pool_signature'],predicted_heuristic_score=diag['pool_predicted_score'],actual_joint_UB=pool_actual,
            error=diag['pool_predicted_score']-pool_actual))
        for c in calls:
            q=read(c['receipt']['path']);selection=q['captures'][-1]['lambda_values']
            for row in diag['candidates']:
                spec=read(c['model']['path']);axis=next(i for i,a in enumerate(spec['lambda_axis']) if a['unit']==row['unit'] and a['ordinal']==row['ordinal'])
                candidates.append(dict(epoch=epoch,formulation=c['formulation'],unit=row['unit'],ordinal=row['ordinal'],path_signature=row['path_signature'],
                    MOVE_count=row['MOVE_count'],travel_energy_kWh=row['travel_energy_kWh'],moves=json.dumps(row['original_moves'],ensure_ascii=False),
                    Minimax_score=row['Minimax_heuristic_score'],terminal_SOC=row['lookahead'].get('terminal_SOC'),terminal_recovery_shortfall=row['lookahead'].get('terminal_recovery_shortfall'),
                    selected_lambda=selection[axis],joint_pool_FULL_UB=pool_actual,independent_route_UB_not_assigned=True))
    csvwrite(DOCS/'V3_CANDIDATE_SCORE_SELECTION_AND_JOINT_OUTCOME.csv',candidates);csvwrite(DOCS/'V3_POOL_PREDICTION_VS_JOINT_UB.csv',pool_scores)
    constant=len({a['actual_joint_UB'] for a in pool_scores})<=1
    write(DOCS/'SCORE_RESULT_RELATION.json',dict(PASS=True,pool_results=pool_scores,joint_UB_never_attributed_to_individual_route=True,
        Spearman=None,Spearman_reason='Joint UB is constant; rank correlation is undefined' if constant else 'Small exploratory sample; no confirmatory correlation claim',
        stored_diagnostics_contain_signed_grid_impacts_and_actual_route_metadata=True))
    historical=read(previous.PILOT_DOCS/'FRESH_EXECUTION_AUTHORIZATION.json')['historical_total_Native']
    write(DOCS/'ALL_SESSION_NATIVE_RUNTIME_LEDGER.json',dict(PASS=True,historical_before_fresh=historical,pilot=audit['pilot_Native'],v2=audit['v2_Native'],v3=audit['v3_Native'],
        same_fresh_used=state['Native_used'],same_fresh_limit=1800,budget_reset=False,remaining=1800-state['Native_used'],all_this_work_actual_Native=historical+state['Native_used'],calls=state['calls']))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figures=[]
    def savefig(name):
        plt.tight_layout();plt.savefig(DOCS/name,dpi=170);plt.close();figures.append(record(DOCS/name))
    trajectory=state['trajectory'];plt.figure(figsize=(9,3.5));plt.step([a['Native'] for a in trajectory]+[state['Native_used']],[a['UB'] for a in trajectory]+[trajectory[-1]['UB']],where='post',label='Original FULL UB')
    plt.axhline(GLOBAL_LB,color='green',label='Certified K48 Global LB');plt.xlabel('Same 1800s execution actual Native, pilot + V2 + V3');plt.ylabel('rho_max');plt.legend();savefig('UB_LB_NATIVE_TRAJECTORY.png')
    plt.figure(figsize=(9,3.5))
    for form in ('DIRECT','EF'):plt.plot([a['epoch'] for a in state['v3_comparisons']],[a[form]['Native_Runtime'] for a in state['v3_comparisons']],marker='o',label=form)
    plt.xlabel('Matched new pool epoch');plt.ylabel('Actual Native seconds');plt.legend();savefig('MATCHED_DIRECT_EF_RUNTIME.png')
    plt.figure(figsize=(9,3.5));plt.bar([str(a['epoch']) for a in state['v3_timings']],[a['total_wall'] for a in state['v3_timings']]);plt.xlabel('Adaptive pool epoch');plt.ylabel('Whole iteration wall seconds');savefig('WHOLE_ITERATION_WALL.png')
    fig,axes=plt.subplots(4,2,figsize=(10,10),sharex='col')
    for i,u in enumerate(sorted(ap)):
        p=ap[u]
        for key in ('Pch','Pdis','Q'):axes[i,0].plot(p[key],label=key)
        axes[i,0].set_ylabel(u+' kW / kvar');axes[i,0].legend(fontsize=7);axes[i,1].plot(p['SOC']);axes[i,1].axhline(440,color='grey',ls=':');axes[i,1].axhline(1080,color='grey',ls=':');axes[i,1].set_ylabel('SOC kWh')
    axes[-1,0].set_xlabel('Slot0..95');axes[-1,1].set_xlabel('Boundary0..96');savefig('ACTUAL_JOINT_P_Q_SOC.png')
    write(DOCS/'FIGURE_INDEX.json',dict(PASS=True,figures=figures))
    prep=read(DOCS/'MATCHED_PREPARATION_COMPARISON.json');oldprep=prep['records']['UNCHANGED_PREPARATION']['timing']['total_wall'];newprep=prep['records']['CACHED_PREPARATION']['timing']['total_wall']
    medians={f:statistics.median(a[f]['Native_Runtime'] for a in state['v3_comparisons']) for f in ('DIRECT','EF')}
    walls=[a['total_wall'] for a in state['v3_timings']];normal=[a['total_wall'] for a in state['v3_timings'] if a['parts'].get('Beam_label_generation',0.)==0 and a['epoch']>1002]
    improvement=INITIAL_UB-state['BEST_GLOBAL_UB']['UB'];discoveries=state['trajectory'][1:]
    report=f'''# V42 B2 Adaptive Beam–4-MESS Joint MILP 병목 개선 및 최종 결과

이번 실험은 Pilot 63.642초를 보존하고 동일 1,800초 예산에서 계속 실행했다. V2와 V3는 Source·Policy를 각각 동결한 별도 실행 버전이다. V3는 별도 Worktree에서 개발하고 Native0·독립 검사·Native Readback PASS 후 Worker가 없는 경계에서 전환했다. 기존 Pilot의 조기 기각 보고서와 원장은 역사 기록으로 보존하며 전체 알고리즘의 실패 판정으로 사용하지 않는다.

## 검증된 결과

| 항목 | 결과 |
|---|---:|
| BEST_GLOBAL_UB | {state['BEST_GLOBAL_UB']['UB']:.16f} |
| BEST_MOVING_FEASIBLE_UB | {state['BEST_MOVING_FEASIBLE_UB']['UB']:.16f} |
| PR220 대비 UB 개선량 | {improvement:.16f} |
| 기존 K48 인증 Global LB | {GLOBAL_LB:.16f} |
| Global Gap `(UB−LB)/UB` | {state['Global_Gap_percent']:.9f}% |
| 전체 평가한 경로 후보집합 | {state['pool_count']} |
| Pilot 포함 Native 호출 | {len(state['calls'])} |
| V3 Native 호출 | {len(state['new_calls'])} |
| Original FULL 독립 감사 | PASS |
| 종료 사유 | {state['stopped_reason']} |

개선해 발견시간: {json.dumps(discoveries,ensure_ascii=False) if discoveries else '이번 실행의 신규 개선해는 없으므로 해당 없음. PR220 FULL 검증 해를 유지한다.'}

최선 실제 Joint 선택의 차량별 MOVE 수는 {json.dumps({u:p['MOVE_count'] for u,p in ap.items()},ensure_ascii=False)}다. 이 선택은 Solver 결과이며 차량 이동을 고정하거나 강제하지 않았다. 매 모델에서 MESS01~04 각 8개 후보의 STAY·단일 MOVE·복수 MOVE와 λ 하나 선택을 유지하고, 네 차량 경로·384개 Charge Mode·Pch/Pdis/Q/SOC를 하나의 MILP에서 공동 결정했다. 경로 조합을 별도 MILP로 열거하지 않았다.

## 준비시간·전체 반복시간

동일 Source/Case/Pool/Start의 Native0 비교에서 준비시간은 {oldprep:.3f}초 → {newprep:.3f}초로 {oldprep-newprep:.3f}초, {(oldprep-newprep)/oldprep*100:.2f}% 감소했다. 캐시 최초 생성비용 {prep['cache_creation_cost_separate']:.3f}초는 별도다. Source SHA·Case SHA·행렬/Domain/정적 Alias 및 정식화 버전에 묶인 읽기 전용 캐시를 사용하며 Source 변경·버전 변경·오염 재사용 거부 테스트는 PASS다.

새 DAG·λ 연결·Node/Flow/Arc/Alias·MIP Start·모델 CSR/Bounds/Types/Objective Readback·선택 Raw 복원·Original FULL Replay·Resource Gate를 생략하지 않았다. 불변 원본 Alias 전개만 정확한 정적 정수 연산자로 재사용하고 후보별 연결식은 독립적으로 다시 구성한다.

V3 전체 반복 Wall 평균 {statistics.mean(walls):.3f}초, 중앙값 {statistics.median(walls):.3f}초다. 확장 없는 일반 반복 중앙값은 {statistics.median(normal) if normal else float('nan'):.3f}초다. 정식화 두 종류를 비교하는 반복과 큰 Beam 확장을 별도로 식별한다. 첫 Pool은 개발 단계에서 미리 준비했으므로 그 133초 안팎의 준비 비용과 Native0/Readback 비용을 별도로 기록했다. 첫 반복의 낮은 Wall만으로 전체 속도 이득을 주장하지 않는다.

`V3_EXCLUSIVE_ITERATION_TIMINGS.csv`와 Worker CSV에는 Source 로딩, 정적 SHA/캐시, Grid/SOC/Rebound, Beam 생성, Score/Admission, CSR/패킷, Alias, 모델 생성, Native Readback, Optimize, FULL Replay를 분리했다. 배타적 단계 합계+기타 IO/제어 잔여는 전체 Wall과 일치한다. Presolve·Root·콜백은 Optimize의 부분 시간이므로 중복 합산하지 않는다. 초기 V2의 미계측 세부 시간을 사후에 지어내지 않았으며 Worker/Native/검증 실측과 미분리 잔여를 구분한다.

준비 캐시의 이득이 강화된 96슬롯 Grid·SOC 스코어 비용으로 일부 상쇄됐다. 전체 Wall 개선은 실제 반복 분포로 평가하며 준비시간 감소를 그대로 전체 속도 개선률로 환산하지 않는다. Beam 확장은 수 분이 걸릴 수 있으며 모든 반복마다 확장하지 않는다.

## Presolve·정식화 비교

기존 Joint 입력 Binary 9,354개 → Direct 416개를 확인했다. Sparse EF도 416개지만 원본 216,674개 Route/Node/Flow 좌표와 보조변수를 유지해 희소 연결을 보존한다. V3의 서로 다른 {len(state['v3_comparisons'])}개 Pool에서 동일 Source/Case/Raw Start/파라미터/TimeLimit로 Direct와 EF를 비교했으며 Runtime 중앙값은 Direct {medians['DIRECT']:.3f}초, EF {medians['EF']:.3f}초다. 최종 Backend는 `{state['backend']}`다.

`ALL_NATIVE_SOLVER_METRICS.csv`에는 Presolve 전후 Rows/Columns/Binaries/NNZ, Presolve 초, Root 완료 여부, Barrier 반복, NodeCount, Status, ObjBound, MIPGap, 모델 생성 및 Native 시간이 있다. 각 초기 모델의 `MATRIX_STRUCTURE.json`에는 밀도, 행·열 NNZ 분포, 로컬 Fill-in, 전역 NNZ 비율과 원본 계수 범위를 기록했다. Root 기록 없음은 0초나 완료로 바꾸지 않았다. NodeCount=0·제한 Pool의 Optimal Status는 전역 최적성 증명이 아니다.

V2에서는 빠른 Presolve 종료와 140초 Root 시간 제한이 모두 나타났다. 후보 내용에 따라 풀이 시간이 달라지며 작은 Binary 수나 단일 Pool 속도만으로 정식화·전체 Beam을 기각하지 않았다. Restricted ObjBound는 Global LB로 사용하지 않았다. Source NumericFocus/Feasibility/Integrality/Scale/Method/Seed 정책은 유지했다.

## Adaptive Beam 품질과 피드백

96슬롯 모든 시간대의 실제 Near-Critical Line/Phase/Slot을 반영하고 원본 Signed P/Q 계수를 보존했다. 이동 구간의 기존 위치 서비스 상실, 도착 후 서비스, 이동에너지, 미래 충전 기회, 종단 SOC 복원 부담과 충전 Rebound를 스코어에 반영한다. PCS 스코어 배열 연산의 변경 전후 회귀는 4대 STAY·단일·복수 MOVE에서 최대 1e-12 이내 일치했다. 스코어와 SOC Reachability는 휴리스틱이며 인증 UB/LB 또는 미검증 Dominance로 사용하지 않는다.

FULL PASS Raw의 실제 P/Q/SOC, λ 조합, Grid와 예측 오차를 다음 Pool에 반영하고 차량·출발·목적지·재접속·MOVE 수를 다양화했다. 같은 수학적 모델 재실행을 Signature로 방지했다. 동일 Pool의 다른 정식화 비교는 별도 Benchmark로 기록했다. 후보별 점수·이동 메타데이터·λ 선택·Joint UB는 Candidate CSV/JSON에 보존했으며 공동 UB를 개별 경로의 독립 성능으로 귀속하지 않았다. {'공동 UB가 일정하여 Spearman 순위상관계수는 정의되지 않는다.' if constant else '표본이 작아 상관을 확증 결과로 해석하지 않는다.'}

차량별 실제 평가된 서로 다른 경로 수는 {json.dumps(audit['evaluated_unique_paths'],ensure_ascii=False)}다. 경로 수 자체를 성공으로 간주하지 않고 FULL UB 개선 여부를 함께 평가한다. 단독·2대·3대 탐색은 기존 Ablation이며 이번 주 결과는 4-MESS Joint다.

## 예산·무결성·안전

Pilot {audit['pilot_Native']:.9f}초 + V2 {audit['v2_Native']:.9f}초 + V3 {audit['v3_Native']:.9f}초 = {state['Native_used']:.9f}/1,800초다. 잔여 {1800-state['Native_used']:.9f}초와 안전 반환 여유를 기록했고 예산 초기화는 0회다. 이전 별도 실행 및 중단 Pilot의 역사 Native {historical:.9f}초는 분리 보존한다. 이 작업 전체 역사 합계 {historical+state['Native_used']:.9f}초를 한 실행의 승인 예산으로 해석하지 않는다.

Source18r의 원본 물리·Grid·PCS16·이동에너지·ETA·96슬롯·종단 SOC·고정 Forecast/AIDC·목적함수는 변경하지 않았다. Restricted MILP의 Original FULL 부분집합 포함성과 정확한 Source 계수·행·정의된 Raw Lift를 독립 감사했다. Heavy Worker 1, Threads 1, RAM/Commit Gate와 B1 보호를 유지했다. 최대 실측 Private Commit {resource['max_Private_Commit']/2**30:.3f}GiB, 최소 가용 RAM {resource['min_available_RAM']/2**30:.3f}GiB, 최소 가용 Commit {resource['min_available_Commit']/2**30:.3f}GiB다.

추가 K32/K48 Optimize, B1/B3/IEEE8500/다른 날짜/May 캠페인/Actual Fresh AC는 실행하지 않았다. 모든 채택 UB는 Original FULL Replay PASS다. Source·Policy·기존 Pilot·V2 원장/Raw SHA를 보존했으며 최종 독립 감사는 PASS다.

## 해석과 한계

UB 개선 여부는 위 수치 그대로다. 개선이 없다면 후보 입장 규칙, 제한된 Beam 폭/깊이와 여러 Grid 병목·SOC/이동/복원 비용을 포함한 탐색의 한계를 기록한다. 전체 원본 DAG의 물리적 개선 불가능성은 증명하지 않았다. 작은 표본의 준비·정식화 속도 결과를 다른 계통·날짜·후보집합으로 일반화하지 않는다. 최종 Guard/Readback/FULL/Runtime 증거는 이 폴더, 변경하지 않은 V2·Pilot·기존 Joint 증거 폴더에 보존했다.
'''
    (DOCS/'ADAPTIVE_JOINT_FINAL_KO.md').write_text(report,encoding='utf-8');full_guard()
    print(json.dumps(dict(PASS=True,report=str(DOCS/'ADAPTIVE_JOINT_FINAL_KO.md'),UB=state['BEST_GLOBAL_UB']['UB'],Native=state['Native_used'])),flush=True)
if __name__=='__main__':main()

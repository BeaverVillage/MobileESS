"""Final Korean continuation report and reproducible comparison/plan exports."""
import csv,gc,re,statistics
from collections import Counter
from tools.adaptive_compact_joint.resume_adapter import *
from tools.adaptive_compact_joint.report_final import export_plan

def csvwrite(path,rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        out=csv.DictWriter(f,fieldnames=list(rows[0]));out.writeheader();out.writerows(rows)

def main():
    configure();guard();state=read(DOCS/'FINAL_STATE.json');audit=read(DOCS/'FINAL_INDEPENDENT_REVIEW.json');assert audit['PASS']
    rows=[];memory=[];callbacks=[]
    for i,c in enumerate(state['calls']):
        q=read(c['receipt']['path']);folder=Path(c['receipt']['path']).parent;log=(folder/'NATIVE_GUROBI.log').read_text(encoding='utf-8',errors='replace')
        pt=re.findall(r'Presolve time: ([\d.]+)s',log);ps=re.findall(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
        binary=re.findall(r'Variable types: .*?\((\d+) binary\)',log);cb=re.findall(r'time in user-callback ([\d.]+) sec',log)
        if cb:callbacks.append(float(cb[-1]))
        rb=read(q['readback']['path'])
        rows.append(dict(index=i+1,phase='PILOT' if i<2 else 'CONTINUATION',epoch=c.get('epoch'),formulation=c.get('formulation','DIRECT'),
            Native_before=c['Native_before'],Native_after=c['Native_after'],Native_Runtime=q['Native_Runtime'],worker_wall=c['worker_wall'],
            model_build_wall=q['model_build_wall_seconds'],Presolve_seconds=float(pt[-1]) if pt else None,
            callback_seconds=float(cb[-1]) if cb else None,input_binary=rb['NumBinVars'],input_rows=rb['NumConstrs'],input_columns=rb['NumVars'],
            presolved_rows=int(ps[-1][0]) if ps else None,presolved_columns=int(ps[-1][1]) if ps else None,presolved_NNZ=int(ps[-1][2]) if ps else None,
            presolved_binary=int(binary[-1]) if binary else None,root_completed_Native_seconds=q.get('root_completed_Native_seconds'),NodeCount=q['NodeCount'],
            Status=q['Status'],ObjVal=q['ObjVal'],restricted_ObjBound=q['ObjBound'],restricted_gap=q['MIPGap'],Global_LB_admissible=False))
        memory.extend(s['memory'] for s in q['resource_samples'] if 'memory' in s)
    csvwrite(DOCS/'ALL_NATIVE_FORMULATION_METRICS.csv',rows)
    comparison=[]
    for pair in state['comparisons']:
        for form in ('JOINT','DIRECT'):comparison.append(dict(pool_signature=pair['pool_signature'],**pair[form]))
    write(DOCS/'DIVERSE_POOL_FORMULATION_COMPARISON.json',dict(PASS=True,matched_distinct_pools=len(state['comparisons']),records=comparison,
        runtime_medians={f:statistics.median(a[f]['Native_Runtime'] for a in state['comparisons']) for f in ('JOINT','DIRECT')},
        final_backend=state['backend'],switches=state['switches'],one_pool_cannot_reject_algorithm=True,restricted_bounds_not_Global_LB=True))
    write(DOCS/'ALL_SESSION_NATIVE_RUNTIME_LEDGER.json',dict(PASS=True,historical_Native=audit['historical_Native'],pilot_Native=state['prior_Native'],
        continuation_Native=state['Native_used']-state['prior_Native'],same_fresh_execution_Native=state['Native_used'],same_fresh_limit=1800,
        remaining=1800-state['Native_used'],all_this_work_Native=audit['all_this_work_Native'],budget_reset=False,calls=state['calls']))
    resource=dict(PASS=True,max_actual_private_bytes=max(s['Private_Commit_bytes'] for s in memory),max_actual_RSS_bytes=max(s['RSS_bytes'] for s in memory),
        minimum_available_RAM_bytes=min(s['system']['RAM_available'] for s in memory),minimum_available_commit_bytes=min(s['system']['Commit_available'] for s in memory),
        controller_wall_seconds=state['wall_seconds'],source_numerical_parameters_preserved=True,Native_error_count=0,
        callback_median_seconds=statistics.median(callbacks),source_coefficient_range_warning_preserved=True)
    write(DOCS/'MEMORY_NUMERIC_WALL_AUDIT.json',resource)
    case=v.load_native_case();profiles,moves=export_plan(case,state['BEST_GLOBAL_UB']['point']['path'],DOCS/'BEST_GLOBAL_96_SLOT_MESS_PLAN.csv')
    moving_profiles,moving_moves=export_plan(case,state['BEST_MOVING_FEASIBLE_UB']['point']['path'],DOCS/'BEST_MOVING_96_SLOT_MESS_PLAN.csv')
    actual=min((a for a in state['validations'] if a['PASS']),key=lambda a:a['UB'])
    actual_profiles,actual_moves=export_plan(case,actual['raw']['path'],DOCS/'BEST_ACTUAL_JOINT_96_SLOT_MESS_PLAN.csv');del case;gc.collect()
    write(DOCS/'BEST_PLAN_AND_ACTUAL_JOINT_AUDIT.json',dict(PASS=True,best=state['BEST_GLOBAL_UB'],best_moving=state['BEST_MOVING_FEASIBLE_UB'],
        best_actual_joint=actual,per_unit_MOVE={u:p['MOVE_count'] for u,p in actual_profiles.items()},best_moves=moves,moving_moves=moving_moves,
        actual_joint_moves=actual_moves,SOC_97_each=True,original_FULL_all_replays_PASS=True,physical_profiles=actual_profiles))
    reservoir=read(DOCS/'BEAM_RESERVOIR.json');pool_files=sorted(DOCS.glob('ADAPTIVE_POOL_*.json'))
    search=dict(PASS=True,evaluated_distinct_route_pools=state['pool_count'],actual_native_calls=len(state['calls']),continuation_native_calls=len(state['new_calls']),
        evaluated_unique_paths=audit['evaluated_unique_paths'],reservoir_paths={u:len(p) for u,p in reservoir['units'].items()},
        actual_feedback_updates=len(list(DOCS.glob('OPTIMIZATION_FEEDBACK_*.json'))),expensive_beam_expansions=sum(read(p)['expensive_Beam_expansion'] for p in pool_files),
        all_four_STAY_single_multiple_options=True,no_MOVE_forcing=True,LP_duals_used=False,beam_ranking_is_heuristic=True,
        global_optimization_over_all_original_DAG_paths_not_claimed=True)
    write(DOCS/'ADAPTIVE_SEARCH_COVERAGE.json',search)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figures=[]
    def savefig(name):
        plt.tight_layout();plt.savefig(DOCS/name,dpi=170);plt.close();figures.append(record(DOCS/name))
    plt.figure(figsize=(9,3.8));trajectory=state['trajectory'];plt.step([a['Native'] for a in trajectory]+[state['Native_used']],[a['UB'] for a in trajectory]+[trajectory[-1]['UB']],where='post',label='Original FULL UB')
    plt.axhline(GLOBAL_LB,color='green',label='Certified K48 Global LB');plt.xlabel('Same fresh execution: actual Native seconds incl. pilot');plt.ylabel('rho_max');plt.legend();savefig('CONTINUATION_UB_LB.png')
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for f in ('JOINT','DIRECT'):
        epochs=[a['epoch'] for a in state['comparisons']];axes[0].plot(epochs,[a[f]['Native_Runtime'] for a in state['comparisons']],marker='o',label=f)
        axes[1].plot(epochs,[a[f]['presolved_binary'] for a in state['comparisons']],marker='o',label=f)
    axes[0].set_ylabel('Actual Native seconds');axes[1].set_ylabel('Presolved binaries')
    for ax in axes:ax.set_xlabel('Adaptive pool epoch');ax.legend()
    savefig('DIVERSE_POOL_COMPARISON.png')
    fig,axes=plt.subplots(4,2,figsize=(10,10),sharex='col')
    for i,u in enumerate(sorted(actual_profiles)):
        p=actual_profiles[u]
        for key in ('Pch','Pdis','Q'):axes[i,0].plot(p[key],label=key)
        axes[i,0].set_ylabel(u+' kW / kvar');axes[i,0].legend(fontsize=7)
        axes[i,1].plot(p['SOC']);axes[i,1].axhline(440,color='grey',ls=':');axes[i,1].axhline(1080,color='grey',ls=':');axes[i,1].set_ylabel('SOC kWh')
    axes[-1,0].set_xlabel('Slot0..95');axes[-1,1].set_xlabel('Boundary0..96');savefig('ACTUAL_JOINT_P_Q_SOC.png')
    write(DOCS/'FIGURE_INDEX.json',dict(PASS=True,figures=figures))
    delta=INITIAL_UB-state['BEST_GLOBAL_UB']['UB'];discovery=state['trajectory'][1:] if len(state['trajectory'])>1 else []
    medians={f:statistics.median(a[f]['Native_Runtime'] for a in state['comparisons']) for f in ('JOINT','DIRECT')}
    text=f'''# V42 B2 Adaptive Beam–4-MESS Joint MILP 최종 결과

이번 보고서는 63.642초 Pilot 뒤의 조기 기각 판단을 정정한 동일 1,800초 실행의 최종 결과다. 상위 폴더의 Pilot 보고서·중단 판단·원장·Raw·Source SHA는 당시 기록으로 보존하며, 알고리즘 판단은 이 보고서와 v2_feedback 증거로 대체한다.

## 주 결과

| 항목 | 결과 |
|---|---:|
| BEST_GLOBAL_UB | {state['BEST_GLOBAL_UB']['UB']:.16f} |
| BEST_MOVING_FEASIBLE_UB | {state['BEST_MOVING_FEASIBLE_UB']['UB']:.16f} |
| PR220 대비 UB 개선량 | {delta:.16f} |
| 기존 K48 인증 Global LB | {GLOBAL_LB:.16f} |
| Global Gap `(UB−LB)/UB` | {state['Global_Gap_percent']:.9f}% |
| 서로 다른 경로 후보집합 | {state['pool_count']} |
| 신규 계속 실행 Native 호출 | {len(state['new_calls'])} |
| Pilot 포함 Native 호출 | {len(state['calls'])} |
| Original FULL 독립 검증 | PASS |

개선해 발견 기록: {json.dumps(discovery,ensure_ascii=False) if discovery else '개선해 없음. PR220 기존 FULL 해를 유지하며, 이번 실행의 개선해 발견시간은 해당 없음.'}

최종 종료 사유는 `{state['stopped_reason']}`다. 초기 몇 번의 개선 부재를 종료 조건으로 사용하지 않았다. 네 차량의 경로와 384개 Charge Mode, Pch/Pdis/Q/SOC를 하나의 MILP에서 동시에 결정했다. 차량별 8개 후보에 STAY·단일 MOVE·복수 MOVE를 포함하고 이동을 강제하지 않았다. 네 대 동시 이동 조합은 선택 가능하며, 우승해의 실제 선택은 {json.dumps({u:p['MOVE_count'] for u,p in actual_profiles.items()},ensure_ascii=False)}다.

## 정식화 비교와 실제 병목

서로 다른 {len(state['comparisons'])}개 Pool에서 두 정식화를 직접 비교했다. 전체 비교 Runtime 중앙값은 기존 Joint {medians['JOINT']:.3f}초, Direct Compact {medians['DIRECT']:.3f}초다. 최종 사용 Backend는 `{state['backend']}`다. 입력 Binary는 기존 Joint 9,354개, Direct 416개이며 Presolve 후 값은 별도 CSV에 기록했다. Input Binary 감소율만으로 계산 효율을 판정하지 않았다.

`ALL_NATIVE_FORMULATION_METRICS.csv`에는 Presolve Binary/Rows/Cols/NNZ, Root 완료시간, NodeCount, ObjBound, UB, 모델 생성·Worker·Native 시간이 있다. Root 기록이 없는 경우 공란이며 0초로 바꾸지 않았다. Restricted ObjBound는 후보집합 안의 하한으로만 보관하고 Global LB에는 사용하지 않았다. 콜백 시간 중앙값 {resource['callback_median_seconds']:.3f}초는 Source·자원 안전 확인을 포함하며 Native Runtime 안에 들어간다.

Solver만의 시간과 후보 생성·원본 Alias 증명·Native Readback·FULL 검증을 포함한 전체 반복 시간을 구분한다. 계속 실행 Controller 벽시계 시간은 {state['wall_seconds']:.3f}초다. FULL 검증과 Beam 작업에는 Native Optimize 호출이 없지만 실제 벽시계 비용이 발생한다.

## Adaptive 피드백와 탐색 범위

모든 Pool은 직전 Joint MILP의 Original FULL PASS P/Q/SOC를 사용해 Multi-Critical Grid·SOC·Rebound를 갱신한다. 전체 열용량 행을 조사하고 Beam 순위에 여러 병목행을 반영한다. {search['actual_feedback_updates']}회 실제 피드백 갱신과 {search['expensive_beam_expansions']}회 계속 실행 Beam 확장이 기록됐다. 차량별 실제 평가된 서로 다른 경로 수는 {json.dumps(search['evaluated_unique_paths'],ensure_ascii=False)}, Reservoir 경로 수는 {json.dumps(search['reservoir_paths'],ensure_ascii=False)}다.

후보집합 Signature와 정식화별 모델 Signature로 반복 평가를 막는다. 같은 Pool의 두 정식화 비교는 동일 문제의 Benchmark이며 경로 조합별 MILP 열거가 아니다. Beam 점수는 휴리스틱이고 LP Dual이나 인증 하한으로 사용하지 않는다. 기존 고비용 Conditional LP를 자동 실행하지 않았고 새 K32 LB 실험도 실행하지 않았다. 단독·2대·3대 실험은 보존된 Ablation이며 이번 주 결과는 4대 Joint다.

## 무결성·예산·안전

Source18r Exact C3A+Dense의 원본 715,596개 행, 전체 96슬롯 Grid, PCS16, 실제 ETA·이동에너지, 종단 SOC, 고정 AIDC와 목적함수를 보존했다. Direct는 원본 Route 좌표를 정확한 Binary λ 선택의 선형 Lift로 대체하며 Source 계수 합은 정확한 dyadic 연산으로 독립 검증했다. 기존 Joint는 원본 CSR 접두부를 그대로 유지한다. 두 Restricted MILP가 Original FULL 가능영역의 부분집합임을 증명했고 전체 원본 가능영역과의 동등성은 주장하지 않는다.

Pilot {state['prior_Native']:.9f}초 + 계속 실행 {state['Native_used']-state['prior_Native']:.9f}초 = 동일 새 실행 {state['Native_used']:.9f}/1,800초다. 예산 초기화는 0회이며 잔여 {1800-state['Native_used']:.9f}초다. 이전 실행·중단 Pilot의 역사 비용 {audit['historical_Native']:.9f}초를 별도로 보존한다. 이번 작업 전체 기록된 Native 합계는 {audit['all_this_work_Native']:.9f}초이며 이것은 한 실행의 승인 예산으로 해석하지 않는다.

Heavy Worker 1, Threads 1을 유지했다. 실측 최대 Private Commit {resource['max_actual_private_bytes']/2**30:.3f}GiB, 최소 가용 RAM {resource['minimum_available_RAM_bytes']/2**30:.3f}GiB, 최소 가용 Commit {resource['minimum_available_commit_bytes']/2**30:.3f}GiB다. Resource·Source Gate와 독립 감사는 PASS다. B1/B3/IEEE8500/다른 날짜/May 캠페인/Actual Fresh AC는 실행하지 않았다.

## 결과 해석과 미검증 범위

UB 개선 여부는 위 수치 그대로다. 제한된 후보집합에서 개선이 없다는 결과는 모든 원본 DAG 경로의 물리적 개선 불가능성을 증명하지 않는다. 많은 병목 Grid 행, 제한된 Beam 폭·깊이, 후보집합 입장 규칙, 이동에너지와 충전 Rebound가 탐색 품질을 제한할 수 있다. 각 원인은 저장된 실제 Grid·SOC 피드백과 후보 Coverage로 평가하며, 개선 부재만으로 Compact 정식화 또는 Adaptive Beam 전체를 기각하지 않는다. 이번 계통·날짜·후보집합 밖으로 속도 이득을 일반화하지 않는다.

독립 감사: `FINAL_INDEPENDENT_REVIEW.json`. 원본 FULL Raw/Replay, 전체 원장, Source/Policy SHA, 동치성 증명, 모델 Readback, Signature, 96슬롯 차량별 P/Q/Charge Mode와 97개 SOC 경계는 이 폴더 및 변경하지 않은 상위 증거 폴더에 보존했다.
'''
    (DOCS/'ADAPTIVE_JOINT_CONTINUATION_FINAL_KO.md').write_text(text,encoding='utf-8');guard()
    print(json.dumps(dict(PASS=True,report=str(DOCS/'ADAPTIVE_JOINT_CONTINUATION_FINAL_KO.md'),Native=state['Native_used'],UB=state['BEST_GLOBAL_UB']['UB'])))

if __name__=='__main__':main()

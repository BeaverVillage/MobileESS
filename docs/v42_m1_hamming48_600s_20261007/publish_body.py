"""Generate the final Korean PR body from sealed results; no solve or remote mutation."""
from run_hamming48 import *
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    r=read(OUT/'RESULT.json');g=read(OUT/'GAP_UPDATE.json');d=read(OUT/'TRAJECTORY_DIFF.json');c=read(OUT/'UB_COMPARISON.json');n=read(OUT/'NEXT_ACTION_RECOMMENDATION.json');full=read(OUT/'BEST_FULL_REPLAY.json');grid=read(OUT/'GRID_EFFECT_AUDIT.json')
    critical='; '.join(f"{v['branch_name']} slot{v['slot']}: 요구 rho 감소 {v['required_rho_reduction']:.10f}" for v in grid['largest_critical_row_improvements_in_binary_block'][:3])
    body=f'''PR170 최선 검증 incumbent를 중심으로 같은 Hamming48 neighborhood에서 primal 품질을 더 개선할 수 있는지 확인했습니다. Native optimize를 정확히 한 번 실행했고, policy 변경은 TimeLimit300→600뿐입니다. Center/start/outside B 고정값은 사용자 지시대로 PR170 최선 해로 갱신했습니다.

분류: **{r['classification']}**.

- Valid UB: {g['UB_old']} → **{g['UB_new']}**, 추가 감소 **{g['absolute_improvement']}** ({100*g['relative_UB_improvement']:.9f}%).
- Global valid LB **{LB}** 유지. 새 global gap **{g['gap_new_percent']:.9f}%**. Restricted ObjBound {r['neighborhood_ObjBound']}는 global LB로 사용하지 않았습니다.
- Native status {r['Status']}, Runtime **{r['Runtime']}s**, Work **{r['Work']}**, nodes **{r['NodeCount']}**; TimeLimit600 / Threads1.
- MIPSOL event {r['MIPSOL_events']}개 전체 point 저장, 최초 center 이후 엄격한 개선 **{r['number_of_improving_incumbents']}회**, native pool SolCount {r['SolCount']}.
- Best valid-point H=**{r['H_best']}**, radius48 boundary active={r['HAMMING_BOUNDARY_ACTIVE']}. Node_activity {d['node_activity_bits_changed']} / charge_mode {d['charge_mode_bits_changed']} B 변경. Discrete units={d['affected_discrete_units']}, slots={d['affected_discrete_slots']}.

원래2100 free B(node2016+mode84), slots64..84, radius48을 그대로 사용하고 outside7222 B는 새 center로 고정했습니다. 모든 effective native parameters를 PR170과 비교해 TimeLimit와 LogFile 이외 차이가 없음을 확인했습니다. 원래 continuous bounds, C3A physics/objectives, A1 interface와 모든 tolerance를 유지했습니다. Sweep, 더 큰 radius, full global B&B, 수동 LB cut/hull, formulation 변경, 추가 solve는0입니다.

Center 독립 original replay와 H=0 start replay가 먼저 PASS했고 native start도 수락됐습니다. Best native candidate original full replay={r['best_solver_candidate_full_replay_PASS']}; 채택 valid point full replay={full['PASS']}. 원래 rows/bounds/integrality와 saved inverse route/movement/SOC/PQ/PCS, grid673920 rows 및 frozen A1 interface를 검증했습니다. FAIL 점은 UB로 채택하지 않는 규칙을 유지했습니다.

H24/112.52999997138977초: 0.6694159238756877→0.6339776033797229. H48/300.1989998817444초: 0.6339776033797229→0.6324498168172089. 이번 H48/600 policy: {UB}→{r['UB_new']}. 이번 gain/직전 gain={c['gain_600_over_gain_300']}; 진단={c['diagnostic']}. Center들이 다르고 runtime/resource overlap이 통제되지 않아 순수한 시간 효과나 전역 포화로 해석하지 않았습니다.

같은600초 실행 내 저장된300초 checkpoint valid UB={c['same_600s_run_verified_300s_checkpoint']}; 이후 추가 valid gain={c['additional_valid_gain_after_300_seconds']}. 별도 original replay만 수행했고 추가 optimize0회입니다. 이는 저장된 동일 실행의 시간 구간 비교이며, 별도300초 run의 반사실 결과와 같다고 주장하지 않습니다.

Critical grid 예: {critical}. 모든 retained thermal rows를 평가하고 원래 branch/time axes를 복구해 critical/top rows와 MESS affine 기여를 저장했습니다. Continuous 변수 전체가 자유로워 슬롯 밖 변화도 가능하며, 동반 관찰을 인과 기여로 주장하지 않았습니다.

다음 행동은 정확히1개 추천만 합니다: {n['recommendation']} 실행={n['executed']}.

검증: 전체 원래 모델/physical/grid replay, 모든 callback point hashes, SHA256 manifest, PR169/170 역사 자료 불변, optimize1, namespace-only diff PASS. 결과와 한국어 검토는 `docs/v42_m1_hamming48_600s_20261007/`에 있습니다.

Stacked base: PR170 `{BASE}`. Scientific authority: PR162 selected C3A `1d922c91eb27056a5ccc79c92ef18146707099ab`.

Final HEAD: {git('rev-parse','HEAD')}
'''
    Path(args.out).write_bytes(body.encode('utf-8'));print('PR_BODY_WRITTEN',args.out,flush=True)
if __name__=='__main__':main()

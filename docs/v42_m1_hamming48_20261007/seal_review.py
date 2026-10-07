"""Korean review and SHA256 sealing; no optimization."""
from run_hamming48 import *
def main():
    p=argparse.ArgumentParser();p.add_argument('--pr-url',default='생성 후 이 문서와 PR 본문에 기록');args=p.parse_args()
    r=read(OUT/'HAMMING48_RESULT.json');diff=read(OUT/'TRAJECTORY_DIFF.json');g=read(OUT/'GAP_UPDATE.json');c=read(OUT/'UB_COMPARISON.json');grid=read(OUT/'GRID_EFFECT_AUDIT.json');n=read(OUT/'NEXT_EXPERIMENT_RECOMMENDATION.json');params=read(OUT/'SOLVER_PARAMETERS.json');start=read(OUT/'MIP_START_VALIDATION.json')
    def fmt(x):return repr(float(x))
    critical=grid['largest_critical_row_improvements'][:5]
    crit_text='; '.join(f"{v['branch_name']} / slot{v['slot']} / C3A row{v['C3A_row']}: 요구 rho {v['center_required_rho']:.12f} → {v['new_required_rho']:.12f} (감소 {v['required_rho_reduction']:.12f})" for v in critical)
    block_crit='; '.join(f"{v['branch_name']} slot{v['slot']} row{v['C3A_row']}: 감소 {v['required_rho_reduction']:.12f}" for v in grid['largest_critical_row_improvements_in_binary_block'][:5])
    crit_text+='; 슬롯64..84 내 critical 예: '+block_crit+'. 슬롯 바깥 개선도 원래 continuous 변수를 자유롭게 유지한 재최적화의 관찰이다.'
    totals=diff['totals']
    questions=[
      ('Exact base HEAD?',BASE),
      ('정확한 center incumbent?',f"PR169 `docs/v42_m1_gap_rootcause_20261007/UB_LOCAL_NEIGHBORHOOD_POINT.npz`의 x. rho={UB}; SHA256={read(OUT/'BASE_IDENTITY.json')['center_SHA256']}"),
      ('Center replay PASS?', '예. 원래 C3A rows/bounds/B integrality 및 saved inverse·route·movement·SOC·P/Q·PCS·673920 grid rows·A1 frozen interface PASS. start 수리 0.'),
      ('Hamming24 정확한 정의?', '실제 PR169 solve_neighborhood.py의 원래 B 마지막 시간 인덱스64..84 선택을 복구했다. 저장된 2100 free_names와 순서까지 일치. 모든 MESS01..04의 node_activity 및 charge_mode만 포함. 나머지 B는 center로 고정, 원래 continuous bounds 유지. center=0이면 x, center=1이면 1−x를 합산.'),
      ('Hamming48은 반경만 달랐나?', '실험 설계의 변경은 반경24→48이다. 사용자 지시대로 center/start/outside 고정값은 새 PR169 incumbent로 갱신했다. 따라서 수치적으로 고정값과 local row 기준도 새 center를 따른다. 같은 옛 center 실험이라고 주장하지 않는다.'),
      ('Neighborhood B 수?', '2100 = node_activity2016 + charge_mode84.'),
      ('Outside fixed B 수?', '7222. 원래 B9322, C296718, 총306040 columns. 원래582808 rows에 Hamming row 한 개만 추가.'),
      ('Hamming48 start feasible?',f"예. 독립 제한-model replay PASS, H=0, native Start 배열 bit-identical. native 수락={start['start_accepted']}."),
      ('Solver 설정?', str(params['settings'])+'; solver 13.0.2. 모든 effective/default/nondefault parameters 별도 기록. LogFile 경로만 새 namespace. 별도 presolve call 없음.'),
      ('Optimize call 수?',str(r['optimize_calls'])+'회. exclusive OPTIMIZE_ONCE.json 및 single-call guard. 다음 실험 호출 0.'),
      ('Native status?',f"{r['Status']} ({'TIME_LIMIT' if r['Status']==9 else 'OPTIMAL within restricted MIPGap policy' if r['Status']==2 else 'native receipt 참조'}). 전역 정수 최적성 증명 없음."),
      ('Runtime?',fmt(r['Runtime'])+' native seconds. TimeLimit300이며 실제 runtime을 그대로 보고했다.'),
      ('Work?',fmt(r['Work'])),
      ('Nodes?',fmt(r['NodeCount'])),
      ('발견 incumbent 수?',f"MIPSOL {r['MIPSOL_events']} events(시작점과 종료시 중복 포함), new incumbent events {r['new_incumbent_events']}(최초 center 포함), 엄격한 추가 개선 event {r['strict_improvement_events_excluding_initial']}; native SolCount={r['SolCount']}. SolCount는 pool 수여서 callback event 수와 정의가 다를 수 있다. 모든 event point 저장."),
      ('최선 solver objective?',fmt(r['ObjVal']) if r['ObjVal'] is not None else '없음'),
      ('Best candidate original full replay?',str(r['best_solver_candidate_full_replay_PASS'])+'. 원래 C3A 및 frozen full physical/grid validator로 independently PASS 여부를 결정. 제한 neighborhood bound는 이 검증에 사용하지 않았다.'),
      ('Old valid UB?',fmt(g['UB_old'])),
      ('New valid UB?',fmt(g['UB_new'])),
      ('Absolute UB improvement?',fmt(g['absolute_improvement'])),
      ('Relative UB improvement?',fmt(g['relative_UB_improvement'])+f" ({g['relative_UB_improvement']*100:.9f}%)"),
      ('고정 valid LB로 새 global gap?',f"LB={LB}; (UB−LB)/UB={g['gap_new']}, {g['gap_new_percent']:.9f}%. 남은 차이={g['remaining_separation']}이며 증명된 integrality gap이라고 부르지 않는다."),
      ('Original separation 누적 제거 비율?',fmt(g['fraction_original_separation_removed'])+f" ({g['fraction_original_separation_removed']*100:.9f}%); originalUB={g['UB_original']}, 누적 감소={g['cumulative_poor_incumbent_attribution']}."),
      ('Hamming48 단독 current remaining separation 제거 비율?',fmt(g['fraction_current_remaining_separation_removed'])+f" ({g['fraction_current_remaining_separation_removed']*100:.9f}%)."),
      ('H_best?',str(r['H_best'])),
      ('Radius48 boundary active?',str(r['HAMMING_BOUNDARY_ACTIVE'])+'. 제한시간 결과이며 neighborhood 정수 optimum도 별도로 증명하지 않았다.'),
      ('PR169 대비 node_activity changed bits?',str(diff['node_activity_bits_changed'])),
      ('Charge_mode changed bits?',str(diff['charge_mode_bits_changed'])),
      ('Changed MESS units?', '이진변수 변경: '+(', '.join(diff['affected_discrete_units']) or '없음')+'; Pch/Pdis/Q/SOC 연속 궤적 변경: '+(', '.join(diff['affected_physical_continuous_units']) or '없음')),
      ('Changed slots?', '이진변수 변경: '+str(diff['affected_discrete_slots'])+'; 연속 물리 궤적 변경: '+str(diff['affected_physical_continuous_slots'])+'. MESS04 이동은 depart66/connect69 및 depart82/connect85이다. 이는 원래 route auxiliary가 도출한 결정이며, outside64..84의 원래 B는 모두 고정되어 있다.'),
      ('Movement 변화?',f"MOVE 선택 수 {totals['MOVE_count']['old']}→{totals['MOVE_count']['new']}; movement kWh {totals['movement_energy_kwh']['old']}→{totals['movement_energy_kwh']['new']}. MOVE 결정 변경 {diff['MOVE_decisions_changed']}, STAY 결정 변경 {diff['STAY_decisions_changed']}. 전체 arc 변경 목록과 depart/connect/energy 저장."),
      ('Charge/discharge 변화?',f"충전 활성 event {totals['charge_events']['old']}→{totals['charge_events']['new']}, 방전 {totals['discharge_events']['old']}→{totals['discharge_events']['new']}; 활성여부 변경 충전{diff['charging_events_changed']}/방전{diff['discharging_events_changed']}개(1e−8 kW 진단 기준). 충전 energy {totals['charge_energy_kwh']['old']}→{totals['charge_energy_kwh']['new']} kWh, 방전 {totals['discharge_energy_kwh']['old']}→{totals['discharge_energy_kwh']['new']} kWh. 모든 unit·96 slot Pch/Pdis/Q/SOC 및 초기/말기 SOC를 저장했다."),
      ('개선 critical grid rows?',crit_text or '이 선택된 center-active row 집합에서는 개선 없음. 전체 grid effect audit 참조.'),
      ('Global valid LB 변경?', 'NO. 0.5687116003498334로 유지.'),
      ('Neighborhood ObjBound를 global LB로 사용?',f"NO. native restricted ObjBound={r['neighborhood_ObjBound']}는 해당 고정/반경 제한에서만 유효."),
      ('Physics 변경?', 'NO. 4 MESS, time-DAG, travel energy/time, SOC dynamics/capacity/efficiency, PCS16, P/Q, grid/rating/transformer, A1 interface, P1/P2 정의 모두 유지. P2 solve 0.'),
      ('Tolerance 변경?', 'NO. native FeasibilityTol/OptimalityTol/IntFeasTol=1e−8, C3 replay=1e−8. 기존 frozen original inverse validator의 affine postsolve=1e−6, bound/route/grid=1e−8, 기존 physical subvalidator tolerance=1e−5도 그대로 유지했다. 이는 새 완화가 아니다. 후보 raw C3 vector는 변경하지 않았고 frozen route auxiliary inverse mapping만 기존 방식으로 적용했다.'),
      ('Solver sweep?', 'NO. 한 설정·한 optimize call.'),
      ('Primal search 전망?',f"진단: {c['diagnostic']}. H24 gain={c['Hamming24']['absolute_improvement']}, H48 추가 gain={c['incremental_gain_48']}, 비율={c['gain_48_over_gain_24']}. 최선 점은 현재 center에서 H={r['H_best']}, 옛 H24 center에서 H={c['Hamming_best_from_original_H24_center']}이므로 어느 center의 radius24 제한에서도 제외된다. 두 center와 실제 runtime이 다르고 resource overlap도 통제하지 않아 반경만의 인과 효과로 해석하지 않는다. 전역 포화 증명 없음."),
      ('단 하나의 다음 실험?',n['recommendation']),
      ('Final classification?',r['classification']),
      ('Final commit SHA?', '최종 40자리 HEAD는 이 Draft PR 본문의 `Final HEAD`와 사용자 최종 응답에 기록한다. 저장된 작업에서 `git rev-parse HEAD`로 동일 SHA를 확인한다. 사전등록 및 실행 source commit은 OPTIMIZE_ONCE.json에 별도로 기록한다. 자체 commit SHA를 같은 commit의 파일 내용에 넣는 순환을 만들지 않는다.'),
      ('Draft PR URL?',args.pr_url),
    ]
    text='# Hamming48 / 300초 최종 검토\n\n'+f"{r['classification']}. 유효 UB {UB} → {g['UB_new']}, 추가 감소 {g['absolute_improvement']}. 고정 global LB에 대한 새 gap {g['gap_new_percent']:.9f}%.\n\n"
    text+='| 탐색 | Center UB | 반경 | Native Runtime(s) | Best valid UB | 개선 |\n|---|---:|---:|---:|---:|---:|\n'
    for label in ('Hamming24','Hamming48'):
        x=c[label];text+=f"| {label} | {x['center_UB']} | {x['radius']} | {x['Runtime']} | {x['best_valid_UB']} | {x['absolute_improvement']} |\n"
    text+='\n'
    for i,(q,answer) in enumerate(questions,1):text+=f"{i}. **{q}** {answer}\n\n"
    text+='Grid 효과는 원래 C3A 행과 저장된 native row axes로 실제 branch/time을 복구하여 계산했다. Pch/Pdis/Q affine 기여 변화와 rho 감소의 동반 관찰은 인과 분해가 아니다. 모든 retained thermal rows를 평가하고 critical/top improvement rows를 CSV에 기록했으며, 원래 grid 전체는 별도 frozen replay로 확인했다.\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    verification=read(OUT/'VERIFICATION.json');verification.update(draft_PR_URL=args.pr_url,manifest_excludes_itself=True,final_HEAD_authority='Published Draft PR body Final HEAD; git rev-parse HEAD; user final response');write('VERIFICATION.json',verification)
    files={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json' and '__pycache__' not in str(p) and p.suffix!='.pyc'}
    write('SHA256_MANIFEST.json',dict(algorithm='SHA256',scope='All namespace files except manifest itself and Python caches',files=files))
    print('SEALED',len(files),flush=True)
if __name__=='__main__':main()

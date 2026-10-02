"""Korean evidence review; no scientific or optimizer operations."""
from .common import *

def write_review(comparison,a,b,blocker,flags):
    audit=read('RECONSTRUCTED_START_AUDIT.json')
    text=['# Exact Start 후속 실험 검토\n\n',f'기준은 Draft PR124 exact head `{BASE}`이다. 동일한 과학적 incumbent의 algebraic auxiliary만 재구성하고, Start probe 2회와 순차 600초 canary 1쌍만 실행했다.\n\n',
        '## 1. 두 equality residual의 원인\n\n행 220169/862496은 `response_line_correction_binding`이다. source는 `v42_m1_sparse.grid.add_compressed -> response`이며 line current correction affine helper를 정의한다. 직접 LHS는 모두 auxiliary이고 injection 부모를 통해 고정 Pch/Pdis/Q에 의존한다. 전체 LHS 변수·계수·RHS·원본 SHA는 START_RESIDUAL_ROOT_CAUSE.json에 있다.\n\n잔차는 원래 P_FIXED_ROUTE solver solution의 저장 전 matrix audit에도 있었다. NPZ·gzip JSON·Start import·PR124 vector가 비트 동일하므로 serialization이나 compact mapping이 잔차를 만들지 않았다. 두 행은 compact 변환으로 바뀌는 stay/arc 항을 포함하지 않는다. 과거 rejection의 solver-reported 원인까지 증명했다는 주장은 하지 않는다.\n\n',
        '## 2. 분류와 unique affine reconstruction\n\nOriginal 316,743개와 Compact 316,839개 변수 전체를 CSV에 분류했다. arc/mode/SOC/Pch/Pdis/Q/rho 및 compact movement_flow/node_activity는 primary다. injection P/Q와 line/transformer response helper만 재계산한다. 각 formulation의 81,216 auxiliary에는 source binding 식이 정확히 하나 있고 pivot은 +1이다. 모든 auxiliary 부모의 column index가 더 낮아 strictly triangular system이며, 고정 primary마다 유일한 affine 해를 준다.\n\nRHS−parent terms를 math.fsum으로 평가한다. optimizer·clipping·tolerance rounding·least squares·RHS/계수 변경은 없다. 각 표현의 Start를 별도로 재구성하며 두 실행의 NPZ SHA가 동일하다.\n\n',
        '## 3. 독립 matrix 및 physical gate\n\n']
    for kind in ['original','compact']:
        p=audit['formulations'][kind]
        text.append(f"{kind}: 최대 row violation {p['before']['maximum_row_violation']:.17g} → {p['after']['maximum_row_violation']:.17g}; rows>1e-8={p['after']['rows_exceeding_1e8']}, rows>1e-9={p['after']['rows_exceeding_1e9']}, bounds={p['after']['max_bound_violation']}, fractionality={p['after']['max_integer_fractionality']}.\n\n")
    text+=['primary 비트 차이와 Pch/Pdis/Q/SOC/rho/terminal SOC 차이는 0이다. 원래 route/path/movement timing/connected state/PCS/travel/depart/connect/all96 grid authority와 frozen AIDC를 보존했다. full independent physical validation과 Original→Compact→Original 전체 vector roundtrip이 PASS했다.\n\n',
        '## 4. 실제 Start acceptance\n\n']
    for kind in ['ORIGINAL','COMPACT']:
        p=read('START_ACCEPTANCE_'+kind+'.json')
        text.append(f"{kind}: accepted={p['Start_accepted']}, objective={p['raw_solver_UB']:.17g}, acceptance={p['Start_acceptance_time']:.6f}s, primary max difference={p['accepted_solution_primary_max_difference']}.\n\n")
    text+=['raw log의 `Loaded user MIP start with objective` 직후 callback으로 probe를 종료했다. status11은 의도적 termination이다. 초단기 probe에서 실제 사용 thread가 1로 표시되더라도 설정 Threads=4는 그대로다.\n\n',
        '## 5. 동일 solver 설정\n\n'+json.dumps(SETTINGS,ensure_ascii=False)+'\n\nC0→C1 순차, 각각 TimeLimit=600, BLAS/OpenMP=1이다. 각 optimize 전에 source/model/Start/preregistration SHA 및 effective parameter를 검사했다. tolerance 완화, manual cut tuning, Presolve/Method 변경, heuristic, node limit, route pruning, sweep은 없다.\n\n',
        '## 6. 600초 결과\n\n| arm | solver UB | raw BestBd | valid LB | valid gap | nodes | root completion | first branch | simplex iterations |\n|---|---:|---:|---:|---:|---:|---|---|---:|\n']
    for kind,p in [('original',a),('compact',b)]:
        v=comparison[kind]
        text.append(f"| {kind} | {p['raw_solver_UB']} | {p['raw_BestBd']} | {v['valid_retained_LB']} | {100*v['valid_global_gap']:.10f}% | {p['nodes']} | {p['root_relaxation_completion_time']} | {p['first_branch_time']} | {p['simplex_iterations']} |\n")
    text+=['\nroot completion과 first branch의 None은 미완료/미관측이며 0초를 뜻하지 않는다. callback이 제공하는 nonroot/processed-node proxy는 정확한 branch/processing 이벤트와 분리했다. Start load/acceptance, presolve rows/columns/types, memory/RSS, cuts, warnings는 개별 JSON과 raw log에 보존했다.\n\n',
        '## 7. trajectory 관측 범위\n\n30/60/120/300/600초의 requested timestamp와 actual observation timestamp를 분리했다. root simplex raw log의 iteration·infeasibility를 기록하며, 드문 MIP callback에서 관측된 UB/BestBd에는 관측 시각과 age를 붙였다. 이를 해당 log 시각에 새로 관측한 bound로 주장하지 않는다. infeasible simplex phase objective는 UB/LB로 사용하지 않는다. 원래 callback CSV도 별도 보존했다.\n\n',
        f"## 8. preregistered material gate\n\nInherited reference gap={comparison['inherited_gap']:.17g}. relative gap reduction={comparison['relative_global_gap_reduction']:.17g}, valid LB gain={comparison['valid_LB_gain']:.17g}. 20% OR 0.001 gate={'PASS' if comparison['material_gate_PASS'] else 'FAIL'}. C0 대 C1 비교는 별도 pair 필드에 있다. node speed와 binary 감소를 대체 gate로 쓰지 않았다.\n\n",
        '## 9. certificate와 inherited evidence 보존\n\nLB_valid=max(inherited LB, compatible same-physics BestBd), UB_valid=min(inherited UB, independently validated new UB)다. 낮은 raw bound로 inherited LB 0.5722125039436496을 덮어쓰지 않았다. PR124 tracked physical files 2469개의 SHA와 canonical Git blob을 보존했다. inherited CSV 2개는 물리적 CRLF를 편집하지 않고 local Git attributes로 기존 LF blob과 비교한다. 이전 실패 Start와 raw logs는 그대로다.\n\n',
        '## 10. resource와 비교의 한계\n\n각 실행 전 CPU/cores/RAM/pagefile/active Python·solver command lines를 RESOURCE_RECEIPTS.json에 기록했다. 다른 독립 작업은 병행 가능하며 Python 존재 자체로 대기하지 않았다. 이 snapshot은 실행 전체의 workload 부재를 증명하지 않는다. 동일 hardware/settings/thread의 순차 lane 비교이고, PR124 historical wall time에 대한 절대 speedup은 주장하지 않는다.\n\n',
        '## 11. binary reduction 해석\n\nPR124의 약95.477% binary 감소와 continuous/rows/nnz 증가, standalone root LP 시간 56.68→74.85초는 보존된 사실이다. 이번에는 standalone root LP를 재실행하지 않았다. accepted incumbent 이후 branching/proof의 실익을 평가했다.\n\n',
        f"## 12. 최종 상태와 다음 blocker\n\nCOMPACT_M1_PRODUCTION_AUTHORIZED={flags['COMPACT_M1_PRODUCTION_AUTHORIZED']}, production1800=NOT_RUN, M1_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false, P2/A2/M2/Actual/Fresh AC=NOT_RUN이다. 다른 formulation이나 decomposition을 자동 시작하지 않았다.\n\n다음 blocker: {blocker}\n\n",
        '## 13. 검증과 재현성\n\nfull inherited pytest와 추가 A–P regression의 실제 수는 VERIFICATION.json/TEST_OUTPUT.txt에 기록한다. SHA256_MANIFEST.json은 자신을 제외한 최종 evidence와 새 source/test를 포함한다. STAGED_BYTES_AUDIT.json과 마지막 재검사로 새 staged bytes 및 base preservation을 확인한다. inherited test의 bounded toy solver 호출은 full M1 benchmark와 구분하며 새 full Benders 호출은 0이다.\n']
    (OUT/'FINAL_REVIEW_KO.md').write_text(''.join(text),encoding='utf8')

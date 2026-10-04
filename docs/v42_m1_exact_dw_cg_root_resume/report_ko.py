import sys
sys.path.insert(0,sys.argv[1])
from v42_dw_resume.common import *
from v42_dw_resume.finalize import manifest
r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');v=read(OUT/'CORRECTION_VERIFICATION.json');s=read(OUT/'DW_RESUME_SPEED_AUDIT.json')
pub=read(OUT/'CORRECTION_PUBLICATION.json') if (OUT/'CORRECTION_PUBLICATION.json').exists() else {}
rea=read(OUT/'DW_ITER210_NUMERICAL_REAUDIT.json');g=r['material_gate'];p=s['phases']['cumulative']['pricing_solve_seconds'];m=s['phases']['cumulative']['RMP_solve_seconds']
optimal_rows=[row for row in ledger('DW_RESUME_ITERATION_LEDGER.csv',OUT) if row['full_original_row_max_violation']]
max_residual=max(float(row['full_original_row_max_violation']) for row in optimal_rows)
last_valid=optimal_rows[-1]
f=lambda x:'NULL' if x is None else str(x)
lines=[
f"PR: https://github.com/BeaverVillage/MobileESS/pull/140; 결과 commit {pub.get('correction_result_commit','게시 전')}. 최종 SHA/원격 일치/clean은 최종 응답에서 확인. semantic {v['tests']['SEMANTIC']['passed']} / full {v['tests']['FULL']['passed']} PASS.",
f"원본 INCONCLUSIVE 이력 보존: PASS; 기존 {v['original_history_files_preserved']}개 파일의 바이트 일치.",
"정정: 기존 V42 contract에 맞춰 affine postsolve audit 1e-8 → 1e-6.",
"Solver FeasibilityTol / IntFeasTol / OptimalityTol = 1e-8 유지.",
"Floating-point affine postsolve audit만 1e-6으로 변경. 원본 physical bounds, route equality, exact integer, reduced-cost 및 BestBd 기준 유지.",
"Checkpoint integrity PASS: SHA/축/원본 local rows/route/mode/PQ/SOC/초기·종료 SOC/travel-energy/PCS를 optimize 없이 검증.",
"복원 column: initial 4 + generated 836 = 840.",
f"Iteration 210: 기록된 residual {rea['logged_residual']}에 대한 old gate FAIL / new scalar gate PASS. 저장 primal이 없어 point 재평가를 주장하지 않으며 원본 STOP 이력 유지.",
"Failed iteration 210 dual reused=false. 원본 209 dual 이력은 보존하고 resume pricing에는 새 dual만 사용.",
f"Cold RMP 재구축 {r['RMP_rebuild_seconds']:.6f}초; old basis 미사용.",
f"첫 resumed RMP 목적값 {r['first_resumed_RMP_objective']}; 미인증 master 진단값.",
f"Resumed 전체 원본 행 postsolve 최대 residual {max_residual}; 첫 master {r['first_resumed_RMP_max_residual']}. Terminal RMP에는 validated residual 없음. 전체 원본 행 point 감사 결과 별도 보존.",
f"추가 RMP {r['new_RMP_solves']}회: complete CG 52회 + terminal TIME_LIMIT RMP 1회.",
f"추가 full-domain pricing {r['new_pricing_calls']}회.",
f"추가 validated columns {r['new_validated_columns']}개.",
f"누적 RMP {r['cumulative_RMP_calls']}회.",
f"누적 pricing {r['cumulative_pricing_calls']}회.",
f"누적 retained columns {r['cumulative_columns']}개.",
f"누적 heavy wall: {r['original_heavy_wall_seconds']:.6f} + {r['resumed_heavy_wall_seconds']:.6f} = {r['cumulative_heavy_wall_seconds']:.6f}/3600초. 예산 리셋 없음.",
f"누적 pricing median/p95/max {p['median']:.6f}/{p['p95']:.6f}/{p['maximum']:.6f}초. Original/resumed 분포와 columns/min은 speed audit에 보존.",
f"누적 RMP median/p95/max {m['median']:.6f}/{m['p95']:.6f}/{m['maximum']:.6f}초. 각 CG iteration timing 별도 보존.",
f"최종 MESS01–04 same-dual pricing certificates: {r['final_pricing_certificates']}.",
f"Exact CG convergence={r['DW_ROOT_OPTIMAL_CERTIFIED']}; status={r['status']}; stop={r['stop_reason']}.",
f"Certified D-W root LB={f(r['DW_root_LB'])}. 마지막 validated iteration {last_valid['iteration']}의 incomplete RMP {last_valid['objective_not_global_LB']}는 전역 LB가 아님. Terminal RMP는 미인증.",
f"Arc root {BASE_LB} 대비 certified delta={f(g['delta_LB'])}.",
f"Diagnostic gap: 이전 {100*g['baseline_gap']:.9f}%, 이후 {f(None if g['new_gap'] is None else 100*g['new_gap'])}. Uref={U_REF}는 진단 reference이며 UB 자동 승격 없음.",
f"Material gate={g['status']}.",
f"End-to-end speed improvement 주장={s['end_to_end_speed_improvement_claim']}. Arc reference 146.990초; per-pricing throughput과 root 인증 시간을 구분.",
"Branch-and-Price NOT_RUN. Production M1/P2/A2/M2/Actual/Fresh AC NOT_RUN.",
"May production optimizer/Actual/Fresh AC = 0/0/0. 기존 1,458-stage dry plan, B0→B1→B2→B3(L1) 이후 L2/L3/L4, 이전 Planning만 사용 및 Actual→Planning feedback 금지 보존."]
ending='''기존 pilot의 1e-8 raw-row postsolve gate 실패는 기록에서 삭제하거나 PASS로 소급 변경하지 않았다.

정정은 기존 V42 numerical contract에 맞춰 solver/reduced-cost certificate 1e-8은 유지하고, floating-point postsolve audit만 1e-6으로 통일한 것이다.

기존 840개 validated trajectory column을 checkpoint로 복원했으며 836회의 과거 pricing을 재실행하지 않았다.

failed iteration 210의 dual은 재사용하지 않고 840-column RMP를 다시 풀어 새 validated dual에서 CG를 재개했다.

Pricing timeout을 no-negative-column certificate로 해석하지 않았다.
'''
(OUT/'CORRECTION_FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+'\n\n'+ending,encoding='utf8')
manifest()
payload=read(OUT/'CORRECTION_SHA256_MANIFEST.json')
cache=[x for x in payload['files'] if '/__pycache__/' in x['path'] or x['path'].endswith('.pyc')]
payload['files']=[x for x in payload['files'] if x not in cache]
payload['excluded_generated_python_caches']=cache
payload['cache_exclusion_reason']='Ignored runtime bytecode cache is not a scientific artifact; every source, log, ledger, NPZ, receipt and report remains included.'
write('CORRECTION_SHA256_MANIFEST.json',payload)
print('KOREAN_REPORT_AND_MANIFEST_READY')

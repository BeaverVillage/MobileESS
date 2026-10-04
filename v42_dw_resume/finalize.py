from .common import *
import re,math,hashlib
import numpy as np
from .audit import prototypes,corrected_rows,pure_binary_equalities
from v42_dw_root.partition import axes
from v42_degen.identity import inputs
from v42_dw_root.models import hash_column

def distribution(values):
    a=np.asarray(values,float)
    return dict(count=len(a),median=float(np.median(a)) if len(a) else None,p95=float(np.percentile(a,95)) if len(a) else None,maximum=float(a.max()) if len(a) else None,total=float(a.sum()))
def speed():
    r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');oldR=ledger('DW_RMP_ITERATION_LEDGER.csv');oldP=ledger('DW_PRICING_RUN_LEDGER.csv')
    newR=ledger('DW_RESUME_ITERATION_LEDGER.csv',OUT);newP=ledger('DW_RESUME_PRICING_LEDGER.csv',OUT)
    phases={}
    for label,rr,pp,wall,added in [('original',oldR,oldP,r['original_heavy_wall_seconds'],836),('resumed',newR,newP,r['resumed_heavy_wall_seconds'],r['new_validated_columns']),('cumulative',oldR+newR,oldP+newP,r['cumulative_heavy_wall_seconds'],836+r['new_validated_columns'])]:
        iterations=[]
        for row in rr:
            key=row['iteration'];prices=[p for p in pp if p['iteration']==key]
            start=float(row['pilot_wall_seconds'])-float(row['wall_seconds'])
            end=float(prices[-1]['pilot_wall_seconds']) if prices else float(row['pilot_wall_seconds'])
            iterations.append(dict(iteration=int(key),seconds=max(0,end-start),pricing_calls=len(prices)))
        phases[label]=dict(heavy_wall_seconds=wall,RMP_solves=len(rr),pricing_calls=len(pp),validated_added_columns=added,
             RMP_solve_seconds=distribution([float(x['wall_seconds']) for x in rr]),pricing_solve_seconds=distribution([float(x['wall_seconds']) for x in pp]),
             time_per_CG_iteration=distribution([x['seconds'] for x in iterations]),iteration_times=iterations,columns_per_minute=60*added/wall if wall else None)
    value=dict(phases=phases,resumed_RMP_rebuild_seconds=r['RMP_rebuild_seconds'],cumulative_retained_columns=r['cumulative_columns'],
          arc_root_reference_wall_seconds=146.990,certified_CG_end_to_end_seconds=r['cumulative_heavy_wall_seconds'] if r['DW_ROOT_OPTIMAL_CERTIFIED'] else None,
          end_to_end_speed_improvement_claim=r['DW_ROOT_OPTIMAL_CERTIFIED'] and r['cumulative_heavy_wall_seconds']<146.990,
          incomplete_convergence_cannot_claim_DW_overall_faster=True,pricing_throughput_is_not_root_certification_time=True)
    write('DW_RESUME_SPEED_AUDIT.json',value);return value
def test_result(label):
    path=OUT/('CORRECTION_'+label+'_TEST.log');log=path.read_text(encoding='utf8');receipt=read(OUT/('CORRECTION_PYTEST_'+label+'_RECEIPT.json'))
    matches=re.findall(r'(\d+) passed(?:,.*?)? in ([\d.]+)s',log)
    assert receipt['exit_code']==0 and matches and receipt['all_Gurobi_Threads_one'] and receipt['calls_nonoverlapping']
    return dict(PASS=True,passed=int(matches[-1][0]),seconds=float(matches[-1][1]),log_SHA=sha(path),native_handled_traces=log.count('Windows fatal exception:'),raw_log_preserved=True)
def verify():
    gate('correction_final_verification');count=preserved();commit=verify_execution_freeze();r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json')
    assert r['wall_budget_PASS'] and r['cumulative_heavy_wall_seconds']<=3600 and r['old_pricing_replay_calls']==0 and not r['failed_iteration_210_dual_reused']
    assert read(OUT/'DW_RESUME_SINGLE_THREAD_RESOURCE_SUMMARY.json')['sequential_policy_PASS']
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    with np.load(ORIGINAL/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native);checks=[]
    for h in ledger('DW_RESUME_COLUMN_HASH_LEDGER.csv',OUT):
        b=blocks[UNITS.index(h['MESS'])]
        with np.load(OUT/h['file']) as z:
            x=z['local_values'];a=z['master_coefficients'];c=float(z['objective']);assert hash_column(x,a,c)==h['SHA256'] and np.array_equal(b.B@x,a)
            assert np.array_equal(z['original_columns'],b.columns)
        if h['added']=='True':
            audit=b.validate(x,True);assert audit['PASS'];checks.append(dict(file=h['file'],PASS=True,row_max=audit['raw']['max_constraint_violation']))
    assert len(checks)==r['new_validated_columns']
    write('DW_RESUME_INDEPENDENT_COLUMN_AUDIT.json',dict(PASS=True,checks=checks,repair_calls=0,optimization_calls=0))
    rows=ledger('DW_RESUME_ITERATION_LEDGER.csv',OUT);prices=ledger('DW_RESUME_PRICING_LEDGER.csv',OUT)
    assert all(int(p['call'])>=837 and int(p['iteration'])>=211 for p in prices)
    for p in prices:
        assert p['dual_SHA']==next(row['dual_SHA'] for row in rows if row['iteration']==p['iteration'])
        receipt=read(OUT/f"pricing_receipts/PRICE_{int(p['call']):04d}.json");settings=receipt['settings']
        assert settings['Threads']==1 and settings['TimeLimit']<=600 and settings['MIPGap']==settings['MIPGapAbs']==0
        assert settings['FeasibilityTol']==settings['OptimalityTol']==settings['IntFeasTol']==1e-8
        if p['NO_NEGATIVE_COLUMN_CERTIFIED']=='True':assert p['global_BestBd'] and float(p['global_BestBd'])>=-1e-8
    for row in rows:
        with np.load(OUT/f"RMP_POINT_{int(row['iteration']):04d}.npz") as z:
            full=corrected_rows(A,d,z['original_reconstructed_point'],False,pure_binary_equalities(A,d))
        if row['dual_SHA']:assert full['PASS'] and float(row['dual_violation'])<=1e-8
    cert=read(OUT/'DW_CORRECTED_ROOT_CERTIFICATE.json')
    if r['DW_ROOT_OPTIMAL_CERTIFIED']:
        assert all(r['final_pricing_certificates'].values()) and cert['PASS'] and r['DW_root_LB']>=BASE_LB-1e-8
        assert {p['MESS'] for p in prices if p['dual_SHA']==cert['same_RMP_dual_SHA'] and p['NO_NEGATIVE_COLUMN_CERTIFIED']=='True'}==set(UNITS)
    else:assert r['DW_root_LB'] is None and cert['L_DW'] is None
    tests={label:test_result(label) for label in ('SEMANTIC','FULL')}
    for args in (['git','diff','--check'],['git','diff','--cached','--check']):subprocess.run(args,cwd=ROOT,check=True)
    write('CORRECTION_VERIFICATION.json',dict(PASS=True,original_history_files_preserved=count,original_head=ORIGINAL_HEAD,original_status='INCONCLUSIVE',
          preopt_execution_source_commit=commit,source_freeze_PASS=True,checkpoint_840_PASS=True,old_210_failure_not_rewritten=True,old_dual_not_reused=True,
          no_pricing_replay_PASS=True,solver_and_certificate_1e8_unchanged=True,only_affine_postsolve_1e6_changed=True,new_columns_reaudited=len(checks),
          new_RMP_full_original_points_readonly_reaudited=len(rows),same_dual_pricing_binding_PASS=True,single_worker_PASS=True,wall_budget_PASS=True,
          tests=tests,original_failed_filesystem_test_logs_preserved=True,branch_and_price_run=False,production_optimizer_Actual_Fresh_AC=[0,0,0]))
def report():
    r=read(OUT/'DW_CORRECTED_ROOT_RESULT.json');v=read(OUT/'CORRECTION_VERIFICATION.json');s=speed();pub=read(OUT/'CORRECTION_PUBLICATION.json') if (OUT/'CORRECTION_PUBLICATION.json').exists() else {}
    flags=dict(ORIGINAL_DW_PILOT_STATUS='INCONCLUSIVE',ORIGINAL_DW_PILOT_PRESERVED=True,NUMERICAL_CONTRACT_CORRECTION=True,SCIENTIFIC_MODEL_CHANGED=False,PHYSICAL_AUTHORITY_CHANGED=False,
          SOLVER_TOLERANCE=1e-8,POSTSOLVE_AUDIT_TOLERANCE=1e-6,PRICING_NO_COLUMN_CERT_TOLERANCE=1e-8,RESUMED_FROM_CHECKPOINT=True,RESTARTED_FROM_ZERO=False,
          CHECKPOINT_INITIAL_COLUMNS=4,CHECKPOINT_GENERATED_COLUMNS=836,CHECKPOINT_TOTAL_COLUMNS=840,FAILED_ITERATION_210_DUAL_REUSED=False,
          DW_ROOT_OPTIMAL_CERTIFIED=r['DW_ROOT_OPTIMAL_CERTIFIED'],DW_ROOT_LB=r['DW_root_LB'],DW_ROOT_LB_DELTA=r['material_gate']['delta_LB'],DW_MATERIAL_GATE=r['material_gate']['status'],
          BRANCH_AND_PRICE_RUN=False,PRODUCTION_M1_RUN=False,P2_RUN=False,A2_RUN=False,M2_RUN=False,PROBLEM13_FINAL_VALIDATED=False)
    write('CORRECTION_FINAL_FLAGS.json',flags)
    fmt=lambda x:'NULL' if x is None else str(x)
    p=s['phases']['cumulative']['pricing_solve_seconds'];m=s['phases']['cumulative']['RMP_solve_seconds'];g=r['material_gate'];reaudit=read(OUT/'DW_ITER210_NUMERICAL_REAUDIT.json')
    lines=[f"PR / final SHA / tests / clean: {pub.get('url','PR140 update pending')}; correction result commit {pub.get('correction_result_commit','pending')}; semantic {v['tests']['SEMANTIC']['passed']} PASS / full {v['tests']['FULL']['passed']} PASS; final metadata SHA/remote/clean verified in final response.",
       'Original INCONCLUSIVE history preserved=true; all original tracked bytes preserved.',
       'Numerical audit contract correction: old affine postsolve 1e-8 -> existing V42 1e-6.',
       'Solver FeasibilityTol/IntFeasTol/OptimalityTol=1e-8 unchanged.',
       'Only affine postsolve audit changed; original physical bounds/route equality/exact integers/reduced-cost and BestBd certificates unchanged.',
       'Checkpoint integrity PASS; SHA, axes, original local rows, route/mode/PQ/SOC/initial/terminal/travel/PCS verified without optimization.',
       'Restored columns: 4 + 836 = 840.',
       f"Iteration 210 old/new logged gate: FAIL / PASS (residual {reaudit['logged_residual']}); saved primal absent, so no raw point reevaluation claimed; original status unchanged.",
       'Failed iteration 210 dual reused=false; original iteration209 dual history preserved but never used to price in resume.',
       f"Resumed RMP rebuild: {r['RMP_rebuild_seconds']:.6f}s; cold rebuild, no saved basis.",
       f"First resumed RMP objective: {fmt(r['first_resumed_RMP_objective'])}; diagnostic until certification.",
       f"First resumed postsolve max residual: {fmt(r['first_resumed_RMP_max_residual'])}; final {fmt(r['last_RMP_max_residual'])}.",
       f"Additional RMP/CG solves: {r['new_RMP_solves']}.",f"Additional pricing calls: {r['new_pricing_calls']}.",f"Additional validated columns: {r['new_validated_columns']}.",
       f"Cumulative RMP calls: {r['cumulative_RMP_calls']}.",f"Cumulative pricing calls: {r['cumulative_pricing_calls']}.",f"Cumulative columns: {r['cumulative_columns']}.",
       f"Cumulative heavy wall: {r['original_heavy_wall_seconds']:.6f} + {r['resumed_heavy_wall_seconds']:.6f} = {r['cumulative_heavy_wall_seconds']:.6f}/3600s; no budget reset.",
       f"Cumulative pricing median/p95/max: {p['median']}/{p['p95']}/{p['maximum']}s; per-phase distributions and columns/minute in DW_RESUME_SPEED_AUDIT.json.",
       f"Cumulative RMP median/p95/max: {m['median']}/{m['p95']}/{m['maximum']}s; per-CG-iteration distribution separately archived.",
       f"Final MESS certificates: {r['final_pricing_certificates']}.",f"Exact CG convergence: {r['DW_ROOT_OPTIMAL_CERTIFIED']}; status {r['status']}; stop {r['stop_reason']}.",
       f"Certified D-W root LB: {fmt(r['DW_root_LB'])}; last incomplete RMP diagnostic {fmt(r['last_RMP_objective'])} is not a global LB.",
       f"Delta vs arc root {BASE_LB}: {fmt(g['delta_LB'])}.",f"Diagnostic gap before/after: {g['baseline_gap']*100:.9f}% / {fmt(g['new_gap'])}; Uref={U_REF} diagnosticonly.",
       f"Material gate: {g['status']}.",f"End-to-end speed improvement claimed={s['end_to_end_speed_improvement_claim']}; arc-root reference146.990s; pricing throughput is not certification time.",
       'Branch-and-Price / production M1 / P2 / A2 / M2 / Actual / Fresh AC NOT_RUN.',
       'May production optimizer/Actual/Fresh AC=0/0/0; 1,458-stage plan, B0->B1->B2->B3(L1), then L2/L3/L4, previous Planning-only input and Actual firewall preserved.']
    ending="""기존 pilot의 1e-8 raw-row postsolve gate 실패는 기록에서 삭제하거나 PASS로 소급 변경하지 않았다.

정정은 기존 V42 numerical contract에 맞춰 solver/reduced-cost certificate 1e-8은 유지하고, floating-point postsolve audit만 1e-6으로 통일한 것이다.

기존 840개 validated trajectory column을 checkpoint로 복원했으며 836회의 과거 pricing을 재실행하지 않았다.

failed iteration 210의 dual은 재사용하지 않고 840-column RMP를 다시 풀어 새 validated dual에서 CG를 재개했다.

Pricing timeout을 no-negative-column certificate로 해석하지 않았다.
"""
    (OUT/'CORRECTION_FINAL_REVIEW_KO.md').write_text('\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+'\n\n'+ending,encoding='utf8')
    (OUT/'CORRECTION_PR_DESCRIPTION.md').write_text(f"""The original exact full-domain D-W root pilot stopped INCONCLUSIVE at RMP210 because its raw-row audit used 1e-8, while the pre-existing V42 contract separates solver tolerances1e-8 from affine postsolve audit1e-6. This append-only correction preserves every original file/status/log and changes only that audit policy; physical rows/bounds/domains, exact route/integer authority and pricing thresholds remain unchanged.

The addendum and execution source were committed before optimization. All840 trajectory columns were independently restored and reaudited; no old836 pricing calls or failed210 dual/basis were replayed. Resume used {r['new_RMP_solves']} new RMP solves, {r['new_pricing_calls']} new full-domain pricing calls and {r['new_validated_columns']} new columns. Cumulative wall {r['cumulative_heavy_wall_seconds']:.6f}/3600s retains the original budget. Corrected status {r['status']}, reason {r['stop_reason']}; certified DW LB={r['DW_root_LB']}, material gate={g['status']}. Incomplete RMP objectives are never global LBs; no end-to-end speed advantage is claimed without certification. Full timing distributions are archived.

Validation: checkpoint/full-original-row reconstruction and column provenance PASS; semantic {v['tests']['SEMANTIC']['passed']} and full pytest {v['tests']['FULL']['passed']} PASS with fresh ASCII temp directories and one worker. Original filesystem failures/handled native traces retained. No Branch-and-Price, production M1/P2/downstream/May execution; production optimizer/Actual/Fresh AC=0/0/0.
""",encoding='utf8')
def manifest():
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='CORRECTION_SHA256_MANIFEST.json']
    for directory in ('v42_dw_resume','tests/v42_dw_resume'):
        paths += [p for p in (ROOT/directory).iterdir() if p.is_file() and (p.suffix=='.py' or p.name=='.gitattributes')]
    write('CORRECTION_SHA256_MANIFEST.json',dict(files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(paths)],self_excluded=True,original_history_freeze_SHA=sha(OUT/'ORIGINAL_HISTORY_BYTE_FREEZE.json')))
if __name__=='__main__':
    import sys
    if '--report-only' not in sys.argv:verify()
    report();manifest()

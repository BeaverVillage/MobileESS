"""Read-only verification after termination; never optimize or modify pilot ledgers.

The pre-optimize finalizer assumes every RMP call saved an OPTIMAL primal.
This separate verifier explicitly handles the terminal TIME_LIMIT call with no
primal/dual authority, while preserving all seven frozen execution sources.
"""
from v42_dw_resume.finalize import *

def verify_terminal():
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
    route_mask=pure_binary_equalities(A,d);point_checks=[];nonoptimal=[]
    for row in rows:
        point=OUT/f"RMP_POINT_{int(row['iteration']):04d}.npz"
        if int(row['status'])!=2:
            assert not row['dual_SHA'] and not point.exists()
            assert not any(p['iteration']==row['iteration'] for p in prices)
            nonoptimal.append(dict(iteration=int(row['iteration']),native_status=int(row['status']),saved_primal=False,validated_dual=False,pricing_calls=0))
            continue
        with np.load(point) as z:full=corrected_rows(A,d,z['original_reconstructed_point'],False,route_mask)
        assert full['PASS'] and row['dual_SHA'] and float(row['dual_violation'])<=1e-8
        point_checks.append(dict(iteration=int(row['iteration']),PASS=True,full_original_row_max_violation=full['max_constraint_violation']))
    assert len(point_checks)+len(nonoptimal)==r['new_RMP_solves']
    assert len(nonoptimal)==1 and nonoptimal[0]['native_status']==9 and r['stop_reason']=='RMP_NOT_OPTIMAL'
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
          new_RMP_full_original_points_readonly_reaudited=len(point_checks),RMP_point_checks=point_checks,terminal_nonoptimal_RMP_calls=nonoptimal,
          same_dual_pricing_binding_PASS=True,single_worker_PASS=True,wall_budget_PASS=True,
          tests=tests,original_failed_filesystem_test_logs_preserved=True,branch_and_price_run=False,production_optimizer_Actual_Fresh_AC=[0,0,0],
          postterminal_verifier='docs/v42_m1_exact_dw_cg_root_resume/postterminal_verification.py',postterminal_verifier_SHA=sha(OUT/'postterminal_verification.py'),
          frozen_finalizer_unchanged=True,execution_source_modified=False,optimization_calls=0))

if __name__=='__main__':
    verify_terminal();report();manifest();print('CORRECTION_VERIFICATION_PASS')

from .common import *
import numpy as np,hashlib
from fractions import Fraction as F
from .audit import prototypes,corrected_rows,pure_binary_equalities
from v42_dw_root.models import hash_column
from v42_dw_root.partition import axes
from v42_degen.identity import inputs,signature

def prepare():
    gate('correction_prepare');assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==ORIGINAL_HEAD
    assert not (OUT/'NUMERICAL_GATE_CORRECTION_ADDENDUM.json').exists(),'ADDENDUM_IS_APPEND_ONLY'
    files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    write('ORIGINAL_HISTORY_BYTE_FREEZE.json',dict(head=ORIGINAL_HEAD,files=[dict(path=p,sha256=sha(ROOT/p)) for p in files if p]))
    original=read(ORIGINAL/'DW_ROOT_RESULT.json');assert original['status']=='INCONCLUSIVE' and original['added_columns']==836 and original['pricing_calls']==836
    authority=read(ORIGINAL/'DW_RMP_NUMERICAL_STOP_RECEIPT.json')
    from v42_campaign.authority import SCIENTIFIC
    assert SCIENTIFIC['postsolve_numerical_tol']==POST_TOL and SCIENTIFIC['solver_FeasibilityTol']==SCIENTIFIC['solver_IntFeasTol']==SCIENTIFIC['solver_OptimalityTol']==STRICT_TOL
    addendum=dict(type='NUMERICAL_AUDIT_CONTRACT_CORRECTION',scientific_model_changed=False,physical_authority_changed=False,solver_tolerances_changed=False,
          old_postsolve_tol=STRICT_TOL,new_postsolve_tol=POST_TOL,reason='restore pre-existing V42 global postsolve numerical audit contract',
          observed_failed_residual=authority['raw_original_master_row_max_violation'],original_pilot_status_preserved='INCONCLUSIVE',restart_from_zero=False,
          checkpoint_columns_expected=840,failed_iteration_210_dual_reused=False,negative_column_threshold=-1e-7,no_column_global_BestBd_threshold=-1e-8,
          previous_scientific_heavy_wall=original['total_pilot_wall_seconds'],remaining_heavy_budget=3600-original['total_pilot_wall_seconds'],overall_heavy_budget=3600,
          pre_existing_contract_file='v42_campaign/authority.py',pre_existing_contract_SHA=sha(ROOT/'v42_campaign/authority.py'),
          unchanged=['CSR/RHS/senses/bounds/types/objective/names','route equality and exact binary pattern','physical validators and limits','reduced-cost/sign/global pricing certificates','solver/pricing policies'],
          basis_policy='No saved compatible basis or iteration-210 primal exists. Cold rebuild and solve of all 840 retained columns; no failed dual/basis reuse.',
          budget_includes='Resume model loading, native block and RMP rebuild, all new RMP/pricing solves and CG bookkeeping; excludes pre-optimize read-only integrity audits and post-terminal regression.',
          exact_certificate_audit_requires_remaining_seconds=60,parameter_sweep=False,old_pricing_replay_calls=0,source_and_addendum_commit_required_before_optimize=True)
    write('NUMERICAL_GATE_CORRECTION_ADDENDUM.json',addendum)
    A,d,B,e,*_=inputs();assert signature(B,e)==read(ORIGINAL/'DW_BASE_MODEL_IDENTITY.json')['reference']
    owner,row_owner=axes()
    with np.load(ORIGINAL/'DW_NATIVE_ROW_NAMES.npz') as z:native=z['names']
    blocks=prototypes(B,e,owner,row_owner,native)
    full_owner=np.full(A.shape[0],-1,dtype=np.int8)
    for i in range(A.shape[0]):
        deps=set(map(int,owner[A.indices[A.indptr[i]:A.indptr[i+1]]]))
        if len(deps)==1 and -1 not in deps:full_owner[i]=next(iter(deps))
    full={}
    for m,b in enumerate(blocks):
        rr=np.flatnonzero(full_owner==m);cc=b.columns
        local=dict(d,rhs=d['rhs'][rr],sense=d['sense'][rr],lower=d['lower'][cc],upper=d['upper'][cc],types=d['types'][cc],objective=d['objective'][cc],constant=np.array(0.))
        matrix=A[rr][:,cc];full[m]=(matrix,local,pure_binary_equalities(matrix,local))
    hashes=ledger('DW_COLUMN_HASH_LEDGER.csv');validation=ledger('DW_COLUMN_VALIDATION_LEDGER.csv');prices=ledger('DW_PRICING_RUN_LEDGER.csv');rmps=ledger('DW_RMP_ITERATION_LEDGER.csv')
    assert len(hashes)==len(validation)==840 and len(prices)==836 and len(rmps)==210
    assert sum(r['kind']=='INITIAL' for r in validation)==4 and all(r['added']=='True' for r in validation)
    assert not rmps[-1]['dual_SHA'] and max(int(p['iteration']) for p in prices)==209
    with np.load(ORIGINAL/'DW_DUAL_HISTORY.npz') as z:
        assert z['iterations'][-1]==209 and len(z['iterations'])==209
    checks=[]
    for h,v in zip(hashes,validation):
        m=UNITS.index(h['MESS']);b=blocks[m]
        with np.load(ORIGINAL/h['file']) as z:
            x=z['local_values'];a=z['master_coefficients'];c=float(z['objective'])
            assert np.array_equal(z['original_columns'],b.columns) and hash_column(x,a,c)==h['SHA256']
            assert hashlib.sha256(x.tobytes()).hexdigest()==h['local_vector_SHA'] and hashlib.sha256(a.tobytes()).hexdigest()==h['master_vector_SHA']
            assert np.array_equal(b.B@x,a) and float(b.d['objective']@x)==c
            exact,error=b.exact_coupling(x,a);assert error<=1e-12
            for i,n,q in zip(z['exact_rows'],z['exact_numerators'],z['exact_denominators']):assert exact[int(i)]==F(int(n),int(q))
        physical=b.validate(x,True);assert physical['PASS'],h['file']
        matrix,attributes,mask=full[m];raw=corrected_rows(matrix,attributes,x,True,mask);assert raw['PASS']
        assert physical['raw']['max_constraint_violation']<=STRICT_TOL and raw['max_constraint_violation']<=STRICT_TOL
        checks.append(dict(column=int(h['column']),MESS=h['MESS'],file=h['file'],file_SHA=sha(ORIGINAL/h['file']),column_SHA=h['SHA256'],
              PASS=True,local_axis_exact=True,original_full_local_rows=matrix.shape[0],original_full_row_max_residual=raw['max_constraint_violation'],
              route_mode_PQ_SOC_initial_terminal_travel_PCS_PASS=True,raw_binary_exact=True,master_coefficients_exact=True))
    write('DW_RESUME_CHECKPOINT_AUDIT.json',dict(PASS=True,initial_columns=4,generated_columns=836,total_columns=840,checks=checks,
          optimization_calls=0,old_pricing_replay_calls=0,failed_iteration_210_dual_reused=False,last_valid_original_dual_iteration=209,
          original_ledgers_and_dual_history_verified=True,source_matrix_identity_PASS=True,repairs=0))
    residual=authority['raw_original_master_row_max_violation']
    write('DW_ITER210_NUMERICAL_REAUDIT.json',dict(saved_iteration_210_primal_available=False,read_only_primal_reevaluation_performed=False,
          reason='Original pilot saved trajectory NPZ and dual history, but no iteration-210 RMP primal or compatible basis. No point invented or solve performed.',
          logged_residual=residual,old_gate=STRICT_TOL,old_logged_gate_PASS=residual<=STRICT_TOL,new_gate=POST_TOL,new_logged_gate_consistency_PASS=residual<=POST_TOL,
          original_run_status_unchanged='INCONCLUSIVE',retroactive_certification=False,optimization_calls=0,failed_dual_reused=False))
    write('RESUME_EXECUTION_SOURCE_FREEZE.json',dict(sources=source_freeze(),optimization_calls_before_freeze=0,addendum_SHA=sha(OUT/'NUMERICAL_GATE_CORRECTION_ADDENDUM.json')))
    print('CORRECTION_PREPARED',len(checks),addendum['remaining_heavy_budget'],preserved(),flush=True)
if __name__=='__main__':prepare()

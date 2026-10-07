"""Recover saved primal/dual capture and log receipt; absolutely no solve."""
from common import *
import re

def main():
    stage='SINGLE_WINDOW_STRENGTHENED_LP';A,d,_=load();label='MESS04_69_72'
    B=sparse.load_npz(OUT/(label+'_EF_MATRIX.npz'))
    with np.load(OUT/(label+'_EF_DATA.npz')) as z:f={k:z[k] for k in ('lower','upper','rhs','sense')}
    M=sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],len(f['lower'])))],format='csr'),B],format='csr')
    e=dict(lower=np.r_[d['lower'],f['lower']],upper=np.r_[d['upper'],f['upper']],objective=np.r_[d['objective'],np.zeros(len(f['lower']))],constant=d['constant'],rhs=np.r_[d['rhs'],f['rhs']],sense=np.concatenate([d['sense'],f['sense']]))
    with np.load(OUT/(stage+'_PRIMAL.npz')) as z:x=z['x']
    with np.load(OUT/(stage+'_DUAL_RC_SLACK.npz')) as z:pi=z['dual'];rc=z['reduced_cost'];slack=z['slack']
    log=(OUT/(stage+'.log')).read_text();match=re.search(r'Barrier solved model in (\d+) iterations and ([0-9.]+) seconds \(([0-9.]+) work units\)',log);assert match
    objective=re.search(r'Optimal objective ([+-.eE0-9]+)',log);assert objective
    raw=replay(M,e,x);original=replay(A,d,x[:A.shape[1]])
    cert=exact_bounded_lagrangian(M,e,pi)[0];valid=max(LB,cert['lower_bound'])
    write('SINGLE_WINDOW_CAPTURE_FAILURE.json',dict(error="KeyError: 'types' in audit after primal/dual/RC/slack saved",source_SHA256=sha(OUT/'failed_capture_provenance/solve_window.py'),all_points_preserved=True,no_additional_optimize=True,native_ObjBound_API_value_lost=True,native_Runtime_Work_exact_API_values_lost=True,rounded_native_log_values_used_with_explicit_precision=True))
    result=dict(Status=2,status_authority='Native final log says Optimal objective; exact model status API not preserved',Runtime=float(match[2]),Work=float(match[3]),Runtime_Work_precision='Rounded native completion log, 2 decimals; exact API values unavailable',ObjVal=float(e['objective']@x),native_ObjVal_log_rounded=float(objective[1]),native_ObjBound=None,native_ObjBound_missing_reason='Capture postprocessing failed before receipt write; not inferred from barrier dual columns',barrier_iterations=int(match[1]),settings=read(OUT/(stage+'_ONCE.json'))['settings'],rows=M.shape[0],cols=M.shape[1],nnz=M.nnz,raw_augmented_replay=raw,original_C3A_replay=original,primal_saved_before_validation=True,all_duals_RC_slacks_saved=True,baseline_LB=LB,new_valid_LB=valid,delta_LB=valid-LB,material=valid-LB>=.001,optimize_calls=1,original_integer_set_preserved=True,original_rows_deleted=0,capture_recovered_without_optimize=True,raw_failures_not_hidden=True)
    write(stage+'.json',result)
    write('SINGLE_WINDOW_VALID_LB_CERTIFICATE.json',dict(exact_certificate=cert,baseline_LB=LB,new_valid_LB=valid,delta_LB=valid-LB,percent_required_LB_recovered=100*(valid-LB)/REQUIRED,native_ObjBound_observed=None,all_original_integer_projections_have_exact_EF_extensions=True,independent_hull_verification_SHA256=sha(OUT/(label+'_INDEPENDENT_VERIFICATION.json')),certificate_does_not_require_primal_feasibility=True))
    print('SAVED_CAPTURE_RECOVERED',result,flush=True)

if __name__=='__main__':main()

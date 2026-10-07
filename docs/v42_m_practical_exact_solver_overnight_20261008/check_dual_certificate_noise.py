"""One solver-free dual certificate noise-removal check on existing OPTIMAL LP."""
from practical_support import *
from fractions import Fraction as F

def run():
    A,d,_=hc.load();source=hc.HISTORY/'PURE_LP_POINT.npz';native=read(hc.HISTORY/'PURE_LP_RESULT.json');assert native['Status']==2
    with np.load(source) as z:pi=z['dual'].copy();slack=z['slack'].copy()
    original,_,_,_=hc.exact_bounded_lagrangian(A.tocsc(),d,pi)
    threshold=2.**-40;removed=(abs(pi)<=threshold)&(abs(slack)>=1e-6)&(pi!=0);filtered=pi.copy();filtered[removed]=0.
    refined,clipped,residual,terms=hc.exact_bounded_lagrangian(A.tocsc(),d,filtered)
    np.savez_compressed(OUT/'FILTERED_DUAL_CERTIFICATE.npz',original_Pi=pi,Pi=filtered,clipped_Pi=clipped,removed_mask=removed)
    refined.update(PASS=True,proof_vector_SHA256=sha(OUT/'FILTERED_DUAL_CERTIFICATE.npz'),scientific_A_SHA256=sha(hc.PARENT/'C3A_A.npz'),scientific_DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),source_native_status=2,source_point_SHA256=sha(source))
    atomic(OUT/'FILTERED_DUAL_CERTIFICATE.json',refined)
    gain=float(F(refined['exact_rational'])-F(original['exact_rational']))
    atomic(OUT/'DUAL_CERTIFICATE_NOISE_CHECK.json',dict(UTC=stamp(),optimize_calls=0,original_bound=original['lower_bound'],filtered_bound=refined['lower_bound'],exact_bound_gain=gain,removed_dual_rows=int(removed.sum()),dual_abs_threshold=threshold,slack_threshold=1e-6,thresholds_are_certificate_heuristics_not_model_tolerances=True,original_scientific_model_objective_unchanged=True,all_rows_retained_in_original_matrix=True,all_variables_and_bounds_in_exact_certificate=True,global_bound_ledger_unchanged=True,no_point_or_native_objective_accepted_as_LB=True,proof_always_independently_exact_for_original_domain=True,source_native_status=2))
    print(json.dumps(read(OUT/'DUAL_CERTIFICATE_NOISE_CHECK.json')))
if __name__=='__main__':run()

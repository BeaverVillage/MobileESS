"""One saved-OPTIMAL arithmetic experiment; no native optimize or bound update."""
from practical_support import *
from fractions import Fraction as F
from injection_dual_repair import repair_binding_duals

def run():
    source=OUT/'external_production/external_nodes/0020/RESULT.json';point=source.with_name('LP_POINT_PROOF.npz')
    before=sha(source);r=read(source);assert r['native_status']==2 and r['LP_status']=='OPTIMAL'
    assert read(source.with_name('LB_CERTIFICATE.json'))['proof_vector_SHA256']==sha(point)
    atomic(OUT/'INJECTION_DUAL_REPAIR_REGISTRATION.json',dict(UTC=stamp(),optimize_calls=0,source_node=20,source_result_SHA256=before,source_point_SHA256=sha(point),scope='One arithmetic correction of multipliers on original injection_P/Q_binding equalities; no inequality multiplier or model change',no_bound_update_in_this_check=True))
    A,d,_=hc.load();e=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
    for j,v in r['fixings']:e['lower'][j]=e['upper'][j]=v
    with np.load(point) as z:pi=z['clipped_Pi'].copy();residual=z['exact_residual_display'].copy()
    adjusted,changes=repair_binding_duals(A,e,pi,residual)
    certificate,clipped,new_residual,terms=hc.exact_bounded_lagrangian(A.tocsc(),e,adjusted)
    candidate=OUT/'INJECTION_DUAL_REPAIR_CANDIDATE.npz'
    with candidate.open('wb') as f:np.savez_compressed(f,Pi=adjusted,clipped_Pi=clipped,exact_residual_display=new_residual,exact_bound_terms_display=terms)
    old=F(r['certified_LB']);new=F(certificate['exact_rational'])
    assert before==sha(source);assert verifier.verify(ROOT,d,1)['PASS']
    result=dict(UTC=stamp(),optimize_calls=0,source_native_status=2,source_node=20,changes=len(changes),only_original_unrestricted_equality_multipliers_changed=True,scientific_objective_matrix_bounds_types_and_native_solution_unchanged=True,source_result_SHA256=before,source_point_SHA256=sha(point),candidate_SHA256=sha(candidate),original_exact_certificate=str(old),candidate_exact_certificate=certificate,exact_certificate_gain=float(new-old),better_than_source=new>old,above_registered_floor=new>F.from_float(.5687116104049206),max_changed_Pi=float(abs(adjusted-pi).max()),not_applied_to_OPEN_queue=True)
    atomic(OUT/'INJECTION_DUAL_REPAIR_CHECK.json',result)
    print(json.dumps({k:result[k] for k in ['optimize_calls','changes','exact_certificate_gain','better_than_source','above_registered_floor']}))
if __name__=='__main__':run()

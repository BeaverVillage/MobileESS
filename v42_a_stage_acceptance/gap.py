"""Gap acceptance deliberately does not alter integer optimality proofs."""
from fractions import Fraction
import math

def global_gap_acceptance(component,LB,UB,*,full_domain_verified=False,bound_verified=False,
                          primal_verified=False,locks_verified=False,native_status=None):
    usable=LB is not None and UB is not None and math.isfinite(float(LB)) and math.isfinite(float(UB))
    L=Fraction(LB) if usable else None;U=Fraction(UB) if usable else None
    consistent=usable and L<=U
    g=(U-L)/abs(U) if consistent and U else Fraction(0) if consistent and L==0 else None
    good=bool(full_domain_verified and bound_verified and primal_verified and locks_verified and
              g is not None and g<=Fraction(1,200))
    return dict(PASS=good,kind='GLOBAL_GAP_ACCEPTANCE',component=component,LB=LB,UB=UB,
        exact_gap=None if g is None else str(g),gap=None if g is None else float(g),target_gap=.005,
        full_domain_verified=full_domain_verified,bound_independently_audited=bound_verified,
        primal_original_model_replayed=primal_verified,sequential_locks_verified=locks_verified,
        native_status=native_status,native_status_overridden=False,
        exact_integer_optimum_claimed=False,exact_optimality_certificate_definition_changed=False)

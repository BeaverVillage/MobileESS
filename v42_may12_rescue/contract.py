"""P1-only scientific acceptance, distinct from four-objective A1 acceptance."""
from fractions import Fraction

def decide(zero,closure,bound,integer,physical):
    required=(zero.get('PASS'),closure.get('PASS'),bound.get('PASS'),integer.get('PASS'),physical.get('PASS'))
    if not all(x is True for x in required):
        return dict(PASS=False,A1_P1_ONLY_ACCEPTED=False,A1_ACCEPTED=False,reason='ALL_INDEPENDENT_ORIGINAL_CERTIFICATES_REQUIRED')
    if closure.get('classes')!=130 or not closure.get('complete_STAY_and_migration_coverage'):
        return dict(PASS=False,A1_P1_ONLY_ACCEPTED=False,A1_ACCEPTED=False,reason='FULL_130_CLASS_DOMAIN_REQUIRED')
    if not integer.get('original_integer_types_restored') or not physical.get('original_job_population_verified'):
        return dict(PASS=False,A1_P1_ONLY_ACCEPTED=False,A1_ACCEPTED=False,reason='ORIGINAL_INTEGER_PHYSICAL_SCHEDULE_REQUIRED')
    L=Fraction(bound['exact_LB']);U=Fraction(integer['exact_UB'])
    if U<L or U<0:raise ValueError('CERTIFIED_LB_UB_CONFLICT')
    gap=(U-L)/abs(U) if U else Fraction(0) if L==0 else None
    accepted=gap is not None and gap<=Fraction(1,200)
    return dict(PASS=accepted,A1_P1_ONLY_ACCEPTED=accepted,A1_ACCEPTED=False,
        exact_LB=str(L),exact_UB=str(U),exact_gap=None if gap is None else str(gap),gap=None if gap is None else float(gap),
        criterion='original rho global integer relative gap <= 0.005',P2_objectives_optimized=False,
        migration_and_shift_operating_decisions_retained=True)

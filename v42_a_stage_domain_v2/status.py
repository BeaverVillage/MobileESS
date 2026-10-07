"""Restricted-domain feasibility and LP pricing never certify integer closure."""
from copy import deepcopy
from collections.abc import Mapping


STATUS_FIELDS = ('HARD_PHYSICAL_DOMAIN_DEFINED', 'ACTIVE_DOMAIN_SUBSET',
    'FEASIBILITY_CLOSED', 'LP_PRICING_CLOSED', 'INTEGER_DOMAIN_CLOSURE_PROVEN',
    'PRODUCTION_DOMAIN_ACCEPTED')
INTEGER_CERTIFICATE_KINDS = frozenset(('COMPLETE_FINITE_DOMAIN_ACTIVATION',
    'EXACT_BRANCH_AND_PRICE_DOMAIN_CLOSURE', 'OTHER_VALID_INTEGER_DOMAIN_CERTIFICATE'))


def _sha256(value):
    return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def initial_domain_status(*, hard_physical_domain_defined=False, authority=None):
    return dict(HARD_PHYSICAL_DOMAIN_DEFINED=bool(hard_physical_domain_defined),
        ACTIVE_DOMAIN_SUBSET=True, FEASIBILITY_CLOSED=False,
        LP_PRICING_CLOSED=False, INTEGER_DOMAIN_CLOSURE_PROVEN=False,
        PRODUCTION_DOMAIN_ACCEPTED=False, authority=authority,
        integer_domain_certificate=None,
        scientific_full_domain_optimal=False,
        root_reduced_cost_is_integer_closure=False)


def validate_domain_status(status):
    if not isinstance(status, Mapping) or any(type(status.get(k)) is not bool for k in STATUS_FIELDS):
        raise PermissionError('EXPLICIT_A_STAGE_DOMAIN_STATUS_REQUIRED')
    if status['INTEGER_DOMAIN_CLOSURE_PROVEN']:
        proof = status.get('integer_domain_certificate')
        if (not status['HARD_PHYSICAL_DOMAIN_DEFINED'] or not isinstance(proof, Mapping)
                or proof.get('kind') not in INTEGER_CERTIFICATE_KINDS
                or proof.get('independent_verification_PASS') is not True
                or proof.get('full_scientific_domain_covered') is not True
                or not _sha256(proof.get('authority_sha256')) or not _sha256(proof.get('evidence_sha256'))
                or not isinstance(proof.get('independent_verification'),Mapping)
                or proof['independent_verification'].get('PASS') is not True):
            raise PermissionError('INTEGER_DOMAIN_CLOSURE_CERTIFICATE_REQUIRED')
    if status['PRODUCTION_DOMAIN_ACCEPTED'] and not (
            status['INTEGER_DOMAIN_CLOSURE_PROVEN'] and status['FEASIBILITY_CLOSED']
            and status.get('independent_physical_PASS') is True
            and status.get('all_scientific_objectives_certified') is True):
        raise PermissionError('PRODUCTION_DOMAIN_CLOSURE_REQUIRED')
    if status.get('scientific_full_domain_optimal') and not status['PRODUCTION_DOMAIN_ACCEPTED']:
        raise PermissionError('RESTRICTED_DOMAIN_IS_NOT_FULL_DOMAIN_OPTIMAL')
    return deepcopy(dict(status))


def close_feasibility(status, independent_verification):
    result = validate_domain_status(status)
    if independent_verification.get('PASS') is not True:
        raise PermissionError('INDEPENDENT_FEASIBILITY_CERTIFICATE_REQUIRED')
    result['FEASIBILITY_CLOSED'] = True
    result['feasibility_evidence'] = deepcopy(independent_verification)
    # This is only existence of a feasible scientific schedule, never closure
    # of omitted integer improving schedules.
    return validate_domain_status(result)


def close_lp_pricing(status, pricing_certificate):
    result = validate_domain_status(status)
    if (pricing_certificate.get('PASS') is not True
            or pricing_certificate.get('full_omitted_lp_pool_priced') is not True):
        raise PermissionError('EXACT_LP_PRICING_CERTIFICATE_REQUIRED')
    result['LP_PRICING_CLOSED'] = True
    result['lp_pricing_evidence'] = deepcopy(pricing_certificate)
    return validate_domain_status(result)


def close_integer_domain(status, certificate, independent_verifier):
    """Future interface: a real independent verifier must check the certificate.

    No integer-domain proof is issued by this formulation-review task. In
    particular ROOT_LP_REDUCED_COST is deliberately not an accepted kind.
    """
    result = validate_domain_status(status)
    if certificate.get('kind') not in INTEGER_CERTIFICATE_KINDS:
        raise PermissionError('ROOT_LP_PRICING_IS_NOT_INTEGER_DOMAIN_CLOSURE')
    verification = independent_verifier(deepcopy(certificate))
    if not isinstance(verification, Mapping) or verification.get('PASS') is not True:
        raise PermissionError('INDEPENDENT_INTEGER_DOMAIN_VERIFICATION_REQUIRED')
    proof = deepcopy(certificate)
    proof['independent_verification_PASS'] = True
    proof['independent_verification'] = deepcopy(dict(verification))
    result['integer_domain_certificate'] = proof
    result['INTEGER_DOMAIN_CLOSURE_PROVEN'] = True
    return validate_domain_status(result)


def accept_production_domain(status, *, physical_certificate, objective_certificate):
    result = validate_domain_status(status)
    result['independent_physical_PASS'] = physical_certificate.get('PASS') is True
    result['all_scientific_objectives_certified'] = objective_certificate.get('PASS') is True
    result['PRODUCTION_DOMAIN_ACCEPTED'] = True
    result['scientific_full_domain_optimal'] = True
    return validate_domain_status(result)


def require_production_domain_accepted(status):
    result = validate_domain_status(status)
    if result['PRODUCTION_DOMAIN_ACCEPTED'] is not True:
        raise PermissionError('PRODUCTION_DOMAIN_CLOSURE_REQUIRED')
    return result


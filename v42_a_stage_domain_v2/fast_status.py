"""Six distinct successor gates; fractional LP closure is never integer proof."""
from copy import deepcopy
from collections.abc import Mapping
from .fast_execution import canonical_hash, is_sha256
from .status import INTEGER_CERTIFICATE_KINDS

FIELDS = ('HARD_PHYSICAL_DOMAIN_DEFINED', 'ACTIVE_DOMAIN_FEASIBLE', 'LP_PRICING_CLOSED',
    'ACTIVE_INTEGER_SOLVED', 'INTEGER_DOMAIN_CLOSURE_PROVEN', 'FULL_DOMAIN_ACCEPTED')
PRICING_KINDS = frozenset(('EXACT_ORIGINAL_ROW_LP_PRICING',
    'EXACT_EQUIVALENT_BLOCK_PRICING', 'COMPLETE_FINITE_LP_DOMAIN_ACTIVATION'))


def initial_fast_status():
    return dict.fromkeys(FIELDS, False) | dict(ACTIVE_DOMAIN_SOLUTION_VALID=False,
        FULL_DOMAIN_OPTIMALITY_UNRESOLVED=True, root_LP_pricing_is_integer_closure=False,
        lp_pricing_certificate=None, integer_domain_certificate=None)


def validate_fast_status(status):
    if not isinstance(status, Mapping) or any(type(status.get(key)) is not bool for key in FIELDS):
        raise PermissionError('FAST_EXPLICIT_SIX_DOMAIN_FLAGS_REQUIRED')
    if status['LP_PRICING_CLOSED']:
        require_current_lp_pricing_closed(status.get('lp_pricing_certificate'))
    if status['ACTIVE_INTEGER_SOLVED'] and (not status['LP_PRICING_CLOSED']
            or status.get('all_four_active_lex_objectives_certified') is not True
            or status.get('ACTIVE_DOMAIN_SOLUTION_VALID') is not True):
        raise PermissionError('FAST_ALL_FOUR_ACTIVE_INTEGER_STAGES_REQUIRED')
    if status['INTEGER_DOMAIN_CLOSURE_PROVEN']:
        cert = status.get('integer_domain_certificate')
        if (not isinstance(cert, Mapping) or cert.get('kind') not in INTEGER_CERTIFICATE_KINDS
                or cert.get('full_scientific_domain_covered') is not True
                or cert.get('independent_verification', {}).get('PASS') is not True
                or not is_sha256(cert.get('authority_sha256'))
                or not is_sha256(cert.get('evidence_sha256'))):
            raise PermissionError('FAST_INTEGER_DOMAIN_CERTIFICATE_REQUIRED')
    if status['FULL_DOMAIN_ACCEPTED'] and not (status['HARD_PHYSICAL_DOMAIN_DEFINED']
            and status['ACTIVE_DOMAIN_FEASIBLE'] and status['ACTIVE_INTEGER_SOLVED']
            and status['INTEGER_DOMAIN_CLOSURE_PROVEN']
            and status.get('independent_physical_PASS') is True):
        raise PermissionError('FAST_FULL_DOMAIN_ACCEPTANCE_PROOF_REQUIRED')
    return deepcopy(dict(status))


def require_current_lp_pricing_closed(proof):
    """Check the receipt verified by the separately frozen pricing authority.

    Proof identity includes the exact LP snapshot/locks and original objective.
    No bare PASS, reduced-cost threshold alone or active-only scan is accepted.
    """
    if (not isinstance(proof, Mapping) or proof.get('PASS') is not True
            or proof.get('kind') not in PRICING_KINDS
            or proof.get('mode') != 'OPTIMALITY' or proof.get('lp_status') != 'OPTIMAL'
            or proof.get('full_omitted_lp_pool_priced') is not True
            or proof.get('inactive_stay_covered') is not True
            or proof.get('inactive_migration_covered') is not True
            or proof.get('original_rows_and_objective') is not True
            or proof.get('native_full_direction_coverage_verified') is not True
            or proof.get('independent_full_native_producer_verified') is not True
            or proof.get('independent_verification', {}).get('PASS') is not True
            or type(proof.get('negative_price_candidates')) is not int
            or proof.get('negative_price_candidates') != 0
            or not all(is_sha256(proof.get(key)) for key in (
                'physical_authority_sha256', 'lp_snapshot_sha256', 'objective_sha256',
                'current_locks_sha256', 'pricing_evidence_sha256'))):
        raise PermissionError('FAST_CURRENT_FULL_POOL_LP_PRICING_CERTIFICATE_REQUIRED')
    if proof.get('certificate_sha256') != canonical_hash({k: v for k, v in proof.items() if k != 'certificate_sha256'}):
        raise PermissionError('FAST_LP_PRICING_CERTIFICATE_IDENTITY_DRIFT')
    return True


def verified_pricing_certificate(build, pricing, verification, *, day, component, locks):
    """Bind independent actual pricing evidence to the current LP and lex locks."""
    cert = deepcopy(pricing.get('certificate', {}))
    cert.update(day=day, component=component, current_locks_sha256=canonical_hash(locks),
        independent_verification=deepcopy(verification))
    metadata = build.metadata
    if (cert.get('lp_snapshot_sha256') != metadata.get('lp_snapshot_sha256')
            or cert.get('physical_authority_sha256') != metadata.get('physical_authority_sha256')
            or cert.get('objective_sha256') != metadata.get('objective_sha256')):
        raise PermissionError('FAST_PRICING_CURRENT_MODEL_AUTHORITY_DRIFT')
    cert['certificate_sha256'] = canonical_hash(cert)
    require_current_lp_pricing_closed(cert)
    return cert

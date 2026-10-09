"""Operational permission only after all four independently accepted stages.

No environment flag or timer grants permission. This narrow scope authorizes
immutable freeze and physical replay, never an optimize/presolve call.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from fractions import Fraction
from v42_native.contracts import digest

_operational = ContextVar('v42_verified_operational_edge', default=None)


@contextmanager
def operational_scope(authority, receipts):
    if set(receipts) != {'A1','M1','A2','M2'}:
        raise PermissionError('ALL_FOUR_INDEPENDENT_STAGE_CERTIFICATES_REQUIRED')
    h = digest(authority)
    for stage, row in receipts.items():
        r = row['independent']; result = row['result']
        if (r.get('PASS') is not True or r.get('original_integer_physical_PASS') is not True or
            r.get('global_domain_certificate_PASS') is not True or r.get('input_identity') != h or
            r.get('decision_sha256') != digest(result['decisions'])):
            raise PermissionError('INDEPENDENT_STAGE_AUTHORITY_REQUIRED')
        L, U = Fraction(r['exact_LB']), Fraction(r['exact_UB'])
        if U < L or U < 0 or not (U == L == 0 or U > 0 and (U-L)/U <= Fraction(1,200)):
            raise PermissionError('GLOBAL_STAGE_GAP_REQUIRED')
        if stage != 'A1' and r.get('original_P2_certificate_PASS') is not True:
            raise PermissionError('DOWNSTREAM_P2_CERTIFICATE_REQUIRED')
    token = _operational.set(dict(day=authority['day'], authority_sha256=h, certificates_sha256=digest(receipts)))
    try:
        yield
    finally:
        _operational.reset(token)


def authorize_if_active(day, action):
    permit = _operational.get()
    if permit is None:
        return None
    if action not in ('PLANNING_FREEZE','ACTUAL','FRESH_AC'):
        raise PermissionError('V42_OPERATIONAL_SCOPE_CANNOT_OPTIMIZE')
    if day is not None and day != permit['day']:
        raise PermissionError('V42_OPERATIONAL_DAY_DRIFT')
    return permit['day']


def guard_operational_optimize():
    if _operational.get() is not None:
        raise PermissionError('V42_OPERATIONAL_SCOPE_CANNOT_OPTIMIZE')

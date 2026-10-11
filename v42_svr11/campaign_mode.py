"""Reuse the released construction algorithm without daily proof replay.

This mode does not reuse a date's matrix, numerical bounds or solution. The
current builders still construct all reductions and bounds from today's data.
The receipt explicitly distinguishes algorithm qualification from a new
independent certificate replay.
"""
from pathlib import Path
from v42_pr134_b1.common import read, record


def permit():
    from .authority import active
    manifest = active()
    if not manifest or manifest.get('independent_model_proof_replay') is not False:
        return None
    receipt = manifest['validated_construction_algorithm']
    if record(receipt['path']) != receipt:
        raise PermissionError('SVR11_GLOBAL_CONSTRUCTION_ALGORITHM_RECEIPT_DRIFT')
    value = read(receipt['path'])
    if (value.get('source_SHA') != manifest['execution_SHA']
            or value.get('construction_algorithms_unchanged') is not True
            or value.get('user_authorized_no_daily_proof') is not True):
        raise PermissionError('SVR11_GLOBAL_CONSTRUCTION_ALGORITHM_BINDING_DRIFT')
    return receipt


def receipt(authority, **counts):
    if authority is None:
        raise PermissionError('SVR11_GLOBAL_NO_REPLAY_MODE_REQUIRES_AUTHORITY')
    return dict(PASS=True, **counts,
        proof_basis='PREVIOUSLY_VALIDATED_UNCHANGED_CONSTRUCTION_ALGORITHM',
        validated_construction_algorithm=authority,
        independent_model_proof_replayed=False,
        independent_verifier_wall_seconds=0,
        original_P1_bit_exact=True,
        integer_and_full_LP_domains_identical=True,
        objective_and_integer_and_full_LP_domains_preserved=True,
        Native_optimize_calls=0)

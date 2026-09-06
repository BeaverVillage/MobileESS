"""Explicit, scoped restoration-bound revision for the paused May campaign.

The V17 source and its historical contract remain immutable. V40D overrides
only the termination bound during post-selection verification. Beam identities
remain those of the unchanged planning method; result identities include V40D.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import hashlib

POLICY_PATH = Path('dayahead/artifacts/v40d_ac_restoration/V40D_RESTORATION_POLICY.json')
PASS_ID = 'V40D'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_policy(repo):
    path = Path(repo) / POLICY_PATH
    policy = json.loads(path.read_text(encoding='utf-8'))
    identity = policy['identity']
    if policy.get('status') != 'APPROVED' or digest(identity) != policy.get('policy_sha256'):
        raise ValueError('V40D_POLICY_NOT_SEALED')
    if identity['base_max_rounds'] != 5 or identity['max_rounds'] != 10:
        raise ValueError('V40D_BOUND_NOT_AUTHORIZED')
    if identity['changed_controls'] != ['max_restoration_rounds'] or identity['voltage_limits'] != [0.95, 1.05]:
        raise ValueError('V40D_UNAUTHORIZED_SCIENCE_CHANGE')
    for relative, expected in identity['inherited_files'].items():
        if sha(Path(repo) / relative) != expected:
            raise ValueError('V40D_INHERITED_SOURCE_DRIFT:' + relative)
    return policy


def reference(repo, policy=None):
    policy = policy or load_policy(repo)
    path = Path(repo) / POLICY_PATH
    return {'path': str(path), 'sha256': sha(path), 'policy_sha256': policy['policy_sha256'],
            'max_rounds': policy['identity']['max_rounds'], 'exists': True}


def case_fingerprint(base, policy):
    value = deepcopy(base)
    value['planning_execution_fingerprint_sha256'] = value.pop('execution_fingerprint_sha256')
    value['AC_restoration_policy_sha256'] = policy['policy_sha256']
    value['max_restoration_rounds'] = policy['identity']['max_rounds']
    value['execution_fingerprint_sha256'] = digest(value)
    return value


def assert_campaign_not_paused(repo):
    pause = Path(repo) / 'dayahead/artifacts/v40b_v40a_may_launch/USER_PAUSE.json'
    if pause.exists():
        raise RuntimeError('CAMPAIGN_PAUSED_BY_USER: restore explicitly before launching day workers')


@contextmanager
def applied(repo, *, baseline_namespace=False):
    """Apply one audited bound to both inherited B2 and V40A B3 verification.

    The campaign has one solver thread per process. Heartbeats do not enter
    this context. Nested policy activation is rejected to prevent mixed caps.
    """
    from dayahead import v17_ac_restoration_contract as contract
    from dayahead.v37 import runner
    policy = load_policy(repo)
    if contract.K_MAX != 5:
        raise RuntimeError('V40D_RESTORATION_POLICY_ALREADY_ACTIVE')
    previous = (contract.K_MAX, runner.PASS_ID, runner._input_authority, runner.write_status)
    ref = reference(repo, policy)

    def input_authority(*args, **kwargs):
        value = previous[2](*args, **kwargs)
        value['immutable_references']['AC_restoration_policy'] = ref
        value['AC_restoration_policy_sha256'] = policy['policy_sha256']
        return value

    def write_status(*args, **kwargs):
        extra = dict(kwargs.get('extra') or {})
        if extra.get('restoration_round') is not None:
            extra['restoration_round_max'] = policy['identity']['max_rounds']
            extra['AC_restoration_policy_sha256'] = policy['policy_sha256']
        kwargs['extra'] = extra
        return previous[3](*args, **kwargs)

    try:
        contract.K_MAX = policy['identity']['max_rounds']
        if baseline_namespace:
            runner.PASS_ID = PASS_ID
        runner._input_authority = input_authority
        runner.write_status = write_status
        yield policy
    finally:
        contract.K_MAX, runner.PASS_ID, runner._input_authority, runner.write_status = previous

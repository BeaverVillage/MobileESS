"""Admit bounded complete native graphs for repeatedly negative P1 classes.

Every full pricing call, exact bound, prior-point inclusion and integer/FULL
acceptance check remains mandatory. Phase I is untouched.
"""
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from v44.common import read, atomic

POLICY = 'R031_B3_A2_P1_REPEAT_COMPLETE_NATIVE_SMALL_BLOCKS'
FIRST_DAY = '2025-05-03'
MAX_CLASSES = 3
MAX_COLUMNS_PER_CLASS = 8000
MAX_TOTAL_COLUMNS = 20000


def selected(request):
    return (request.get('arm') == 'B3' and request.get('stage') == 'A2'
            and FIRST_DAY <= request.get('day', '') <= '2025-05-07')


def contains(full, active):
    """Check all physical primitive indices and their exact payloads."""
    for name in ('events', 'states', 'compatible'):
        complete = getattr(full, name)
        for key, values in getattr(active, name).items():
            if not set(values).issubset(complete.get(key, ())):
                raise ValueError('R031_COMPLETE_GRAPH_MISSING_PRIOR_' + name.upper())
    for name in ('physical', 'transfers'):
        complete = getattr(full, name)
        for key, value in getattr(active, name).items():
            if key not in complete or complete[key] != value:
                raise ValueError('R031_COMPLETE_GRAPH_PRIOR_PAYLOAD_DRIFT_' + name.upper())
    if full.fixed != active.fixed:
        raise ValueError('R031_COMPLETE_GRAPH_FIXED_FLOW_DRIFT')


class Expansion:
    def __init__(self):
        self.seen = Counter()
        self.promoted = set()
        self.columns = 0

    def apply(self, negative, data, qualified, folder, loader):
        """Use only cache identities already admitted by this round's oracle."""
        from v42_a_stage_domain_v2.domain import graph_content_hash
        chosen, receipts = [], []
        required = {row['class_id']: row for row in qualified['records']}
        for candidate in negative:
            key = candidate['class_id']
            self.seen[key] += 1
            want = required[key]
            size = want['complete_native_primitive_columns']
            eligible = (self.seen[key] >= 2 and key not in self.promoted
                        and len(self.promoted) < MAX_CLASSES
                        and size <= MAX_COLUMNS_PER_CLASS
                        and self.columns + size <= MAX_TOTAL_COLUMNS)
            if not eligible:
                chosen.append(candidate)
                continue
            cache = loader(want)  # Checks the file SHA and complete snapshot SHA.
            full = cache['graph']
            if (graph_content_hash(full) != want['complete_graph_sha256']
                    or cache['snapshot'].matrix.shape[1] != size):
                raise ValueError('R031_COMPLETE_ORACLE_GRAPH_IDENTITY_DRIFT')
            members = data[7]['classes'][key]
            for member in members:
                contains(full, data[5][member])
            contains(full, candidate['graph'])
            if full.sha == candidate['support_sha256']:
                chosen.append(candidate)
                continue
            chosen.append(dict(candidate, graph=full, support_sha256=full.sha))
            self.promoted.add(key)
            self.columns += size
            receipts.append(dict(class_id=key, encounter=self.seen[key],
                old_direction_support_sha=candidate['support_sha256'],
                complete_graph_sha=full.sha, complete_snapshot_sha=cache['snapshot'].fingerprint(),
                oracle_cache=want['external_full_block_cache'], native_columns=size,
                all_prior_and_negative_direction_primitives_included=True,
                subsequent_original_prior_point_replay_required=True))
        atomic(Path(folder)/'R031_COMPLETE_NATIVE_EXPANSION.json', dict(
            PASS=True, policy=POLICY, promoted=receipts,
            total_promoted_classes=len(self.promoted), total_complete_native_columns=self.columns,
            all_classes_full_pricing_unchanged=True, phase_I_changed=False,
            original_integer_and_FULL_acceptance_unchanged=True))
        return chosen


@contextmanager
def install():
    from v44 import worker
    from v44_recovery_r029 import p1_acceleration
    original_stage, original_compile = worker.a_stage, p1_acceleration.compile_p1
    active = []

    def stage(request, *args, **kwargs):
        active.append(request)
        try:
            return original_stage(request, *args, **kwargs)
        finally:
            active.pop()

    def compile_p1(function, namespace):
        run = original_compile(function, namespace)
        if not active or not selected(active[-1]):
            return run
        original_pricing = namespace['full_pricing']
        expansion = Expansion()

        def full_pricing(*args, **kwargs):
            result, negative = original_pricing(*args, **kwargs)
            # Positional arguments are the original complete pricing contract.
            # Refuse Phase I and analytical zero-dual calls explicitly.
            if args[2] is not None or kwargs.get('zero', False):
                return result, negative
            data, folder = args[5], Path(args[13])
            from v42_a_stage_phase1.runner import load_cache
            oracle = Path(original_pricing.__globals__['HISTORY'])/'BLOCK_PRICING_ORACLE_VERIFICATION.json'
            negative = expansion.apply(negative, data, read(oracle), folder, load_cache)
            return result, negative

        namespace['full_pricing'] = full_pricing
        return run

    with patch.object(worker, 'a_stage', stage), patch.object(p1_acceleration, 'compile_p1', compile_p1):
        yield

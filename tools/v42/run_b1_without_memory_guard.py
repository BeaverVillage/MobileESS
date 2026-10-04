"""Explicit operational override for an already frozen B1 scientific run.

Import the original, hash-verified production implementation. Only memory
admission/cancellation changes; foreign-heavy admission and worker contracts stay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time


def policy_campaign(base):
    class WithoutMemoryGuard(base):
        def resource_state(self):
            with self.telemetry.lock:
                foreign = self.telemetry.samples[-1].get('foreign_heavy', [])
            return 'WAIT_RESOURCE' if foreign else 'SAFE'

        def enforce_guard(self, row):
            # Do not write CANCEL.json or terminate workers for memory telemetry.
            return False

    return WithoutMemoryGuard


def validate_policy(root, freeze):
    policy = json.loads((root / 'B1_OPERATIONAL_POLICY.json').read_text(encoding='utf-8-sig'))
    expected = dict(run_id=freeze['run_id'], scientific_SHA=freeze['scientific_SHA'],
                    frozen_Git_SHA=freeze['Git_SHA'], memory_guard_enabled=False,
                    foreign_heavy_admission_enabled=True)
    if any(policy.get(key) != value for key, value in expected.items()):
        raise PermissionError('B1_OPERATIONAL_POLICY_IDENTITY_OR_SCOPE')
    source = Path(__file__).resolve()
    if (policy.get('entrypoint') != str(source)
            or policy.get('entrypoint_SHA256') != hashlib.sha256(source.read_bytes()).hexdigest()):
        raise PermissionError('B1_OPERATIONAL_POLICY_SOURCE_DRIFT')
    return policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    freeze = json.loads((root / 'B1_PRODUCTION_FREEZE_MANIFEST.json').read_text(encoding='utf-8-sig'))
    policy = validate_policy(root, freeze)
    # Workers and receipt identities continue to use this original checkout.
    sys.path.insert(0, freeze['worktree'])
    from v42_b1_production.coordinator import Campaign, process_identity
    from v42_b1_production.common import atomic, now
    timeline = root / 'B1_RESOURCE_TIMELINE.csv'
    if timeline.exists():
        archive = root / 'resource_history'
        archive.mkdir(exist_ok=True)
        shutil.copy2(timeline, archive / f'B1_RESOURCE_TIMELINE_{time.time_ns()}.csv')
    campaign = policy_campaign(Campaign)(root)
    campaign.verify_sources()
    atomic(root / 'B1_OPERATIONAL_POLICY_APPLIED.json', dict(
        UTC=now(), policy=policy, process=process_identity(__import__('os').getpid()),
        memory_guard_enabled=False, scientific_sources_verified=True))
    return campaign.run()


if __name__ == '__main__':
    sys.exit(main())

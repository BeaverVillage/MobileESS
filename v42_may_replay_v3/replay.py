"""Reuse original replay criteria and retain the cause before failing closed."""
from pathlib import Path
import numpy as np
from v42_a_stage_phase1.core import primal_replay, verify_sign_convention
from v42_pr134_b1.common import atomic, now

VERSION = 'NUMERICAL_REPLAY_DIAGNOSTICS_V3'


def inspect(snapshot, raw):
    primal = primal_replay(snapshot, raw['X'])
    dual = verify_sign_convention(snapshot, raw['Pi'], raw['RC'])
    activity = snapshot.matrix @ raw['X']
    violations = np.maximum(0., np.where(snapshot.senses == '<', activity-snapshot.rhs,
        np.where(snapshot.senses == '>', snapshot.rhs-activity, abs(activity-snapshot.rhs))))
    bounds = np.maximum(0., np.maximum(snapshot.lower-raw['X'], raw['X']-snapshot.upper))
    rejected = np.flatnonzero(violations > primal['tolerance'])
    return dict(PASS=primal['PASS'] and dual['PASS'], version=VERSION,
        primal=primal, dual=dual,
        rejected_row_count=int(len(rejected)),
        rejected_rows=[dict(row=int(i), sense=str(snapshot.senses[i]),
            activity=float(activity[i]), rhs=float(snapshot.rhs[i]),
            violation=float(violations[i])) for i in rejected[:20]],
        rejected_bound_count=int(np.count_nonzero(bounds > primal['tolerance'])),
        original_tolerances_preserved=True, raw_point_modified=False,
        Native_calls=0, P2_calls=0, historical_point_bound_clock_loaded=False)


class ReplayNative:
    """Delegate each solve once; persist original replay without any retry."""
    def __init__(self, delegate):
        object.__setattr__(self, '_delegate', delegate)
        object.__setattr__(self, 'failure', None)

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def __setattr__(self, name, value):
        if name in ('_delegate', 'failure'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._delegate, name, value)

    def solve(self, snapshot, folder, component):
        result, raw = self._delegate.solve(snapshot, folder, component)
        if component in ('PHASE_I', 'ORIGINAL_P1') and result['status'] == 2 and all(
                k in raw for k in ('X', 'Pi', 'RC')):
            proof = inspect(snapshot, raw)
            proof.update(UTC=now(), component=component,
                original_snapshot_sha256=snapshot.fingerprint(),
                raw_attributes=result.get('raw_attributes'),
                measured_Native_Runtime=result.get('native_seconds'),
                classification='VERIFIED' if proof['PASS'] else 'NUMERICAL_FAILURE')
            path = Path(folder)/'ORIGINAL_NUMERICAL_REPLAY.json'
            atomic(path, proof)
            if not proof['PASS']:
                self.failure = dict(path=str(path), component=component,
                    max_row_violation=proof['primal']['max_row_violation'],
                    max_bound_violation=proof['primal']['max_bound_violation'],
                    maximum_dual_error=proof['dual']['maximum_absolute_error'])
                raise ValueError('ORIGINAL_NUMERICAL_REPLAY_REJECTED')
        return result, raw

"""The only ML values allowed across the V41 optimizer boundary.

Each job has one conditional Q90 scalar; each rolling H4 window has one
GPUh scalar. Quantile and reserve service levels are not probabilities.
Model features, calibration metadata and legacy predictions are not inputs.
"""
from dataclasses import dataclass
import hashlib
import json
import math

from .reserve import require


@dataclass(frozen=True, slots=True)
class OptimizerScalars:
    pending_runtime: tuple[tuple[str, float, int], ...]
    actionable_h4_gpuh: tuple[float, ...]

    def payload(self):
        return {
            'PENDING_JOB_Q90_SECONDS': {uid: seconds for uid, seconds, slots in self.pending_runtime},
            'PENDING_JOB_DURATION_SLOTS': {uid: slots for uid, seconds, slots in self.pending_runtime},
            'H4_ACTIONABLE_RESERVE_GPUh': list(self.actionable_h4_gpuh),
        }

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.payload(), sort_keys=True, separators=(',', ':'),
                                        allow_nan=False).encode()).hexdigest()


def finite_scalar(value, name):
    require(type(value) in (int, float) and math.isfinite(value), 'NONFINITE_OR_NONSCALAR:' + name)
    return float(value)


def project(snapshot):
    """Whitelist projection, never dictionary forwarding or probabilistic mixing."""
    seconds = snapshot['PENDING_JOB_Q90_SECONDS']
    durations = snapshot['PENDING_JOB_DURATION_SLOTS']
    require(type(seconds) is dict and type(durations) is dict and set(seconds) == set(durations),
            'RUNTIME_SCALAR_UID_AXIS')
    rows = []
    for uid in sorted(seconds):
        require(type(uid) is str and bool(uid), 'INVALID_RUNTIME_UID')
        value = finite_scalar(seconds[uid], 'Q90_seconds')
        slots = durations[uid]
        require(value > 0 and type(slots) is int and slots == math.ceil(value / 900),
                'RUNTIME_SCALAR_SINGLE_CEIL_CONTRACT')
        rows.append((uid, value, slots))
    reserve = snapshot['H4_ACTIONABLE_RESERVE_GPUh']
    require(type(reserve) is list and len(reserve) == 81, 'H4_SCALAR_WINDOW_AXIS')
    values = tuple(finite_scalar(v, 'H4_GPUh') for v in reserve)
    require(min(values) >= 0, 'NEGATIVE_H4_SCALAR')
    return OptimizerScalars(tuple(rows), values)


def policy_inputs(snapshot, policy, stage):
    require(policy in ('B0', 'B1', 'B2', 'B3'), 'UNKNOWN_V41_POLICY')
    require(stage in ('REFERENCE', 'A0', 'A1'), 'UNKNOWN_AIDC_STAGE')
    # Policy and stage select no model and perform no forecast arithmetic.
    return project(snapshot)


def validate_bound(context):
    from pathlib import Path
    data = Path(context.v41_ml_snapshot_path).read_bytes()
    require(hashlib.sha256(data).hexdigest() == context.v41_ml_snapshot_sha256,
            'ML_SNAPSHOT_MUTATED_BEFORE_AIDC')
    require(json.loads(data) == context.v41_ml_snapshot, 'ML_SNAPSHOT_MEMORY_DRIFT')
    value = project(context.v41_ml_snapshot)
    require(value == context.v41_optimizer_scalars, 'OPTIMIZER_SCALAR_INPUT_DRIFT')
    return value

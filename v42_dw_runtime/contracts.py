"""Immutable same-iteration authority and independent, default-off switches."""
from dataclasses import dataclass, fields
import hashlib
import json
import math
import struct

BASE_HEAD = 'ce5d30fb9bcb91ab8395d1313e868d24f5fde517'
QUOTA = 4
RC_THRESHOLD = -1e-7
STOP_REASON = 'DISCOVERY_QUOTA_FILLED'


def canonical(value):
    def scalar(v):
        if hasattr(v, 'item'):
            return v.item()
        raise TypeError(type(v).__name__)
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False, default=scalar)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def dual_sha(pi, convexity):
    # Matches PR143's float64(pi).tobytes() + float64(alpha).tobytes().
    return hashlib.sha256(struct.pack('<' + 'd' * (len(pi) + len(convexity)),
                                      *pi, *convexity)).hexdigest()


@dataclass(frozen=True)
class RuntimeFlags:
    DW_DISCOVERY_EARLY_STOP: bool = False
    DW_PARALLEL_VALIDATION: bool = False
    DW_INCREMENTAL_AUDIT: bool = False
    DW_PERSISTENT_RMP: bool = False

    @classmethod
    def from_environment(cls, environment):
        values = {}
        for field in fields(cls):
            raw = environment.get(field.name, 'false').lower()
            if raw not in ('true', 'false', '1', '0'):
                raise ValueError('Invalid boolean: ' + field.name)
            values[field.name] = raw in ('true', '1')
        return cls(**values)


@dataclass(frozen=True)
class DiscoverySnapshot:
    iteration: int
    true_dual: tuple
    smoothed_dual: tuple
    convexity_dual: tuple
    smoothed_convexity_dual: tuple
    alpha: float
    rmp_objective: float
    dual_SHA: str
    smoothed_dual_SHA: str

    def __post_init__(self):
        for key in ('true_dual', 'smoothed_dual', 'convexity_dual', 'smoothed_convexity_dual'):
            object.__setattr__(self, key, tuple(float(v) for v in getattr(self, key)))
        if (len(self.true_dual) != len(self.smoothed_dual) or
                len(self.convexity_dual) != len(self.smoothed_convexity_dual) or
                not 0 <= self.alpha <= 1 or self.iteration < 0):
            raise ValueError('Invalid snapshot axes/iteration/alpha')
        if not all(math.isfinite(v) for v in (*self.true_dual, *self.smoothed_dual,
                *self.convexity_dual, *self.smoothed_convexity_dual, self.alpha, self.rmp_objective)):
            raise ValueError('Nonfinite snapshot')
        if (self.dual_SHA != dual_sha(self.true_dual, self.convexity_dual) or
                self.smoothed_dual_SHA != dual_sha(self.smoothed_dual, self.smoothed_convexity_dual)):
            raise ValueError('Dual SHA mismatch')

    @classmethod
    def create(cls, iteration, true_dual, smoothed_dual, convexity, smoothed_convexity,
               alpha, objective):
        return cls(iteration, true_dual, smoothed_dual, convexity, smoothed_convexity,
                   alpha, objective, dual_sha(true_dual, convexity),
                   dual_sha(smoothed_dual, smoothed_convexity))


@dataclass(frozen=True)
class Candidate:
    unit: int
    values: tuple
    iteration: int
    true_dual_SHA: str

    def __post_init__(self):
        object.__setattr__(self, 'values', tuple(float(v) for v in self.values))


def certification_settings(kind, snapshot, flags):
    """Explicit firewall for future routing; existing Certification stays untouched."""
    if kind not in ('DISCOVERY', 'CERTIFICATION', 'FINAL_CERTIFICATION'):
        raise ValueError('Unknown pricing path')
    discovery = kind == 'DISCOVERY'
    return dict(search_dual=snapshot.smoothed_dual if discovery else snapshot.true_dual,
                convexity_dual=snapshot.smoothed_convexity_dual if discovery else snapshot.convexity_dual,
                dual_SHA=snapshot.smoothed_dual_SHA if discovery else snapshot.dual_SHA,
                early_quota_terminate=discovery and flags.DW_DISCOVERY_EARLY_STOP,
                incremental_pool_audit=discovery and flags.DW_INCREMENTAL_AUDIT,
                global_BestBd_required=not discovery, smoothed_certificate=False)

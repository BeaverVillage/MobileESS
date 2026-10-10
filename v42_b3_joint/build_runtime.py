"""Worker-local immutable source input reuse and comparable build profiles.

The cache contains inputs only. It never stores a solver, matrix, certificate,
bound or ledger, and its keys include every scientific input identity.
"""
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from time import perf_counter
import math

from .contracts import digest, require, require_sha

PHASES = ("input_preparation", "domain_or_route", "graph", "full_model",
          "compact_c3a", "equivalence", "total_preparation")


def immutable(value):
    if value is None or type(value) in (bool, int, float, str, bytes):
        require(type(value) is not float or math.isfinite(value), "CACHE_NONFINITE_INPUT")
        return value
    if isinstance(value, (tuple, list)):
        return tuple(immutable(item) for item in value)
    if is_dataclass(value):
        require(value.__dataclass_params__.frozen, "CACHE_MUTABLE_SOURCE_DATACLASS_FORBIDDEN")
        require(all(immutable(getattr(value, field.name)) == getattr(value, field.name)
                    for field in fields(value)), "CACHE_MUTABLE_SOURCE_FIELD_FORBIDDEN")
        return value
    # Array copying and locking uses the original array object's API. Source
    # imports remain in the guarded registry rather than this lightweight file.
    if type(value).__module__.startswith("numpy") and hasattr(value, "flags"):
        require(not value.dtype.hasobject, "CACHE_OBJECT_ARRAY_FORBIDDEN")
        copy = value.copy()
        copy.flags.writeable = False
        # A writable owning array can unlock its flags. Immutable bytes are
        # therefore the cache representation; each read reconstructs via source.
        return ("SOURCE_ARRAY_BYTES", copy.dtype.str, tuple(copy.shape), copy.tobytes())
    raise ValueError("CACHE_ONLY_IMMUTABLE_INPUTS:" + type(value).__name__)


@dataclass(frozen=True)
class BuildIdentity:
    worker: str
    day: str
    input_sha: str
    source_sha: str
    domain_sha: str
    grid_sha: str
    fixed_input_sha: str

    def __post_init__(self):
        require(isinstance(self.worker, str) and bool(self.worker), "CACHE_WORKER_ID_REQUIRED")
        require(isinstance(self.day, str) and len(self.day) == 10, "CACHE_DAY_REQUIRED")
        for value in (self.input_sha, self.source_sha, self.domain_sha,
                      self.grid_sha, self.fixed_input_sha):
            require_sha(value)


class ImmutableInputCache:
    def __init__(self, identity):
        require(isinstance(identity, BuildIdentity), "CACHE_TYPED_IDENTITY_REQUIRED")
        self.identity, self._entries = identity, {}
        self.hits, self.misses = 0, 0

    def get(self, identity, name, input_sha, producer, verifier):
        require(identity == self.identity, "CACHE_WORKER_DATE_OR_FIXED_INPUT_DRIFT")
        require_sha(input_sha)
        require(callable(producer) and callable(verifier), "CACHE_SOURCE_APIS_REQUIRED")
        # Verification precedes every hit as well as first construction; a
        # caller's historical PASS is never a substitute for source verification.
        proof = verifier()
        require(isinstance(proof, dict) and proof.get("PASS") is True
                and proof.get("input_sha") == input_sha, "CACHE_SOURCE_VERIFICATION_REQUIRED")
        key = (name, input_sha, digest(proof))
        if key not in self._entries:
            self._entries[key] = immutable(producer())
            self.misses += 1
        else:
            self.hits += 1
        return self._entries[key]

    def receipt(self):
        return {"worker": self.identity.worker, "day": self.identity.day,
                "fixed_input_sha": self.identity.fixed_input_sha,
                "hits": self.hits, "misses": self.misses,
                "cached_solver_models": 0, "cached_matrices": 0,
                "cached_bounds_or_ledgers": 0, "cross_worker_sharing": False}


class BuildProfile:
    def __init__(self, scope_sha, mode, *, clock=perf_counter):
        require_sha(scope_sha)
        require(mode in ("BASELINE", "OPTIMIZED", "FIXTURE_BASELINE", "FIXTURE_OPTIMIZED"),
                "BUILD_PROFILE_MODE_REQUIRED")
        self.scope_sha, self.mode, self.clock = scope_sha, mode, clock
        self.seconds, self.counts = {}, {}

    @contextmanager
    def phase(self, name):
        require(name in PHASES, "BUILD_PROFILE_UNKNOWN_PHASE")
        start = self.clock()
        try:
            yield
        finally:
            elapsed = self.clock() - start
            require(math.isfinite(elapsed) and elapsed >= 0, "BUILD_PROFILE_CLOCK_INVALID")
            self.seconds[name] = self.seconds.get(name, 0.0) + elapsed
            self.counts[name] = self.counts.get(name, 0) + 1

    def receipt(self):
        return {"scope_sha": self.scope_sha, "mode": self.mode,
                "seconds": dict(self.seconds), "phase_call_counts": dict(self.counts),
                "unmeasured_phases": [phase for phase in PHASES if phase not in self.seconds]}


def compare_profiles(baseline, optimized):
    require(baseline["scope_sha"] == optimized["scope_sha"], "BUILD_COMPARISON_SCOPE_DRIFT")
    require(set(baseline["seconds"]) == set(optimized["seconds"]), "BUILD_COMPARISON_PHASE_SCOPE_DRIFT")
    rows = {}
    for phase, old in baseline["seconds"].items():
        new = optimized["seconds"][phase]
        rows[phase] = {"baseline_seconds": old, "optimized_seconds": new,
                       "speedup": old / new if new > 0 else None}
    return {"scope_sha": baseline["scope_sha"], "phases": rows,
            "evidence_kind": "FIXTURE" if baseline["mode"].startswith("FIXTURE") else "MEASURED_SOURCE",
            "real_stage_speedup_inferred": False}

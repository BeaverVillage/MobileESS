"""Immutable physical-audit receipts; exact authority key and explicit audit tiers."""
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import math

from .contracts import canonical, digest


@dataclass(frozen=True)
class AuditAuthority:
    scientific_base_SHA: str
    scientific_matrix_SHA: str
    variable_axis_SHA: str
    row_axis_SHA: str
    validator_version_SHA: str
    physical_semantics_SHA: str
    numerical_tolerance_SHA: str

    def __post_init__(self):
        for name, value in asdict(self).items():
            lengths = (40, 64) if name == 'scientific_base_SHA' else (64,)
            if len(value) not in lengths or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Authority requires exact hexadecimal SHA')

    @property
    def key(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class AuditReceipt:
    trajectory_SHA: str
    authority: AuditAuthority
    max_residual: float
    true_RC: float
    true_dual_SHA: str
    iteration: int
    timestamp: str
    run_id: str
    physical_residuals_json: str

    def __post_init__(self):
        report = json.loads(self.physical_residuals_json)
        for sha in (self.trajectory_SHA, self.true_dual_SHA):
            if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError('Receipt SHA mismatch')
        if self.iteration < 0 or not self.timestamp or not self.run_id:
            raise ValueError('Receipt provenance required')
        if not (isinstance(self.authority, AuditAuthority) and report['local_PASS']
                and report['physical_PASS'] and report['integral'] and self.max_residual >= 0
                and math.isfinite(self.max_residual) and math.isfinite(self.true_RC)
                and self.max_residual == report['max_residual']):
            raise ValueError('Receipt requires complete legal physical audit')

    @property
    def key(self):
        return digest(dict(trajectory_SHA=self.trajectory_SHA, authority=asdict(self.authority)))

    @classmethod
    def issue(cls, result, authority, timestamp, run_id):
        if not result.accepted or not math.isfinite(result.max_residual) or not math.isfinite(result.true_RC):
            raise ValueError('Only fully accepted finite candidates receive receipts')
        return cls(result.trajectory_SHA, authority, result.max_residual, result.true_RC,
                   result.true_dual_SHA, result.iteration, timestamp, run_id, result.physical_residuals_json)


class AuditCache:
    """Stores historical physical feasibility only. Never answers current RC acceptance."""
    def __init__(self):
        self._receipts = {}

    def add(self, receipt):
        existing = self._receipts.get(receipt.key)
        if existing is not None and existing != receipt:
            raise ValueError('Immutable receipt cannot be overwritten')
        self._receipts[receipt.key] = receipt

    def lookup(self, trajectory_SHA, authority):
        return self._receipts.get(digest(dict(trajectory_SHA=trajectory_SHA, authority=asdict(authority))))

    def save(self, path):
        receipts = [asdict(self._receipts[k]) for k in sorted(self._receipts)]
        payload = dict(schema_version=1, receipts=receipts, payload_SHA=digest(receipts))
        target = Path(path)
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_text(canonical(payload) + '\n', encoding='utf8', newline='\n')
        temporary.replace(target)

    @classmethod
    def load(cls, path):
        payload = json.loads(Path(path).read_text(encoding='utf8'))
        if payload['schema_version'] != 1 or payload['payload_SHA'] != digest(payload['receipts']):
            raise ValueError('Receipt registry identity mismatch')
        cache = cls()
        for record in payload['receipts']:
            record['authority'] = AuditAuthority(**record['authority'])
            receipt = AuditReceipt(**record)
            report = json.loads(receipt.physical_residuals_json)
            if not (report['local_PASS'] and report['physical_PASS'] and report['integral']
                    and math.isfinite(receipt.max_residual) and math.isfinite(receipt.true_RC)):
                raise ValueError('Invalid physical receipt')
            cache.add(receipt)
        return cache


def audit_plan(kind, retained, newly_added, authority, cache, flags):
    """SHA bindings are recomputed from checkpoint values by the caller.

    Tier 1: validate_candidate on every new observation, with current true dual.
    Tier 2: audit current RMP point always + new columns + any stale retained receipt.
    Tier 3: full pool at Certification/final checkpoint, irrespective of flags/cache.
    """
    if kind not in ('DISCOVERY', 'CERTIFICATION', 'FINAL_CERTIFICATION', 'FINAL_CHECKPOINT'):
        raise ValueError('Unknown audit tier')
    retained, newly_added = set(retained), set(newly_added)
    full = kind != 'DISCOVERY' or not flags.DW_INCREMENTAL_AUDIT
    stale = {sha for sha in retained if cache.lookup(sha, authority) is None}
    required = retained | newly_added if full else stale | newly_added
    return dict(tier=3 if full else 2, current_RMP_point_required=True,
                columns_to_full_audit=sorted(required), reused_physical_receipts=sorted(retained - required),
                stale_receipts=sorted(stale), current_RC_recheck_required=True,
                historical_RC_is_current_authority=False)


def execute_audit_tiers(kind, retained, newly_added, authority, cache, flags,
                       current_RMP_auditor, full_column_auditor):
    """Execute the plan through original, caller-provided scientific audits.

    full_column_auditor returns a freshly audited AuditReceipt (its historical
    true_RC need not remain negative). Existing immutable receipts are preserved.
    Any failure raises before the current RMP/column addition can be accepted.
    """
    plan = audit_plan(kind, retained, newly_added, authority, cache, flags)
    point_report = current_RMP_auditor()
    if not point_report['PASS']:
        raise ValueError('Current RMP point failed authority audit')
    reaudited = []
    staged = []
    for sha in plan['columns_to_full_audit']:
        receipt = full_column_auditor(sha)
        if receipt.trajectory_SHA != sha or receipt.authority != authority:
            raise ValueError('Reaudit receipt authority mismatch')
        reaudited.append(sha)
        if cache.lookup(sha, authority) is None:
            staged.append(receipt)
    for receipt in staged:
        cache.add(receipt)
    return dict(plan=plan, current_RMP_point=point_report, reaudited_columns=reaudited,
                PASS=True)


def make_authority(scientific_base_SHA, matrices_and_attributes, variable_axis, row_axis,
                   validator_source_bytes, physical_semantics, tolerances):
    """Caller supplies ALL scientific/local/coupling matrices and physical inputs.

    No heavy inputs are loaded here. Axis/dtype/shape identity is included; file
    timestamps, array memory addresses and approximate comparisons are not keys.
    """
    import hashlib
    import numpy as np
    def array(value):
        x = np.asarray(value)
        if x.dtype.hasobject:
            return dict(dtype=x.dtype.str, shape=x.shape, values=x.tolist())
        return dict(dtype=x.dtype.str, shape=x.shape, bytes_SHA=hashlib.sha256(x.tobytes()).hexdigest())
    encoded = []
    for matrix, attributes in matrices_and_attributes:
        x = matrix.tocsr(copy=True)
        encoded.append(dict(shape=x.shape, indptr=array(x.indptr), indices=array(x.indices),
                            data=array(x.data), attributes={k: array(v) for k, v in sorted(attributes.items())}))
    return AuditAuthority(scientific_base_SHA, digest(encoded), digest(array(variable_axis)),
                          digest(array(row_axis)), hashlib.sha256(validator_source_bytes).hexdigest(),
                          digest(physical_semantics), digest(tolerances))

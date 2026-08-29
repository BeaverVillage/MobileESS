"""V16 science firewalls for source authority and locked evaluation periods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


WAITING_AIDC_AUTHORITY = "WAITING_AIDC_AUTHORITY"
UNRESOLVED_DEPENDENCIES = {
    "NLR_SOURCE_HIERARCHY": "WAITING_NLR_SOURCE_REPRODUCTION",
    "P_G_W_LINEAGE": "WAITING_AIDC_LABEL_LINEAGE",
    "REFERENCE_DELTA": "WAITING_REFERENCE_DELTA_CONTRACT",
    "SERVICE_CONTRACT": "WAITING_REFERENCE_MATCHED_SERVICE_CONTRACT",
}
FORBIDDEN_FALLBACK_TOKENS = (
    "numpy.random", "np.random", "synthetic", "nearest_fill", "clone_trace",
    "gpu_power_as_total_it", "fabricated_deadline", "ones_fallback", "zeros_fallback",
)


def reject_aidc_fallback(strategy: str | None) -> None:
    """Reject any missing-label strategy before production data construction."""
    if strategy is None:
        return
    normalized = strategy.strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized in FORBIDDEN_FALLBACK_TOKENS or any(token in normalized for token in FORBIDDEN_FALLBACK_TOKENS):
        raise RuntimeError(f"WAITING_AIDC_AUTHORITY: FORBIDDEN_AIDC_FALLBACK:{strategy}")
    raise RuntimeError(f"WAITING_AIDC_AUTHORITY: UNAUTHORIZED_AIDC_FALLBACK:{strategy}")


@dataclass(frozen=True)
class AuthorityGate:
    dependencies: Mapping[str, bool]
    scientific_eligible: bool

    def status(self) -> dict[str, object]:
        unresolved = [UNRESOLVED_DEPENDENCIES[key] for key, ready in self.dependencies.items() if not ready]
        if not self.scientific_eligible:
            unresolved.append("NON_SCIENTIFIC_AUTHORITY_REJECTED_IN_PRODUCTION")
        return {
            "status": "PASS" if not unresolved else WAITING_AIDC_AUTHORITY,
            "unresolved": unresolved,
            "synthetic_fallback_used": False,
        }

    def require(self) -> None:
        result = self.status()
        if result["status"] != "PASS":
            raise RuntimeError(f"{WAITING_AIDC_AUTHORITY}: {','.join(result['unresolved'])}")


CURRENT_AIDC_GATE = AuthorityGate({key: True for key in UNRESOLVED_DEPENDENCIES}, scientific_eligible=True)


@dataclass(frozen=True)
class ProductionFreezeToken:
    gates: Mapping[str, bool]
    configuration_frozen: bool
    token_id: str | None = None

    def require_locked_access(self, period: str) -> None:
        if period not in {"PRIMARY_2025MAY", "REPLICATION_2025JUN01_25"}:
            return
        missing = sorted(gate for gate in (f"G{i}" for i in range(16)) if not self.gates.get(gate, False))
        if missing or not self.configuration_frozen or not self.token_id:
            raise PermissionError(f"LOCKED_{period}_ACCESS_PROHIBITED:{','.join(missing)}")


PRE_FREEZE_TOKEN = ProductionFreezeToken({}, False, None)

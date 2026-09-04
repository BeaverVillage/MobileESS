"""Failure classification, bounded retry, and May whole-run quarantine rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Callable, Generic, TypeVar

from .contracts import APRIL_RETRY_LIMIT, FAILURE_CLASSES, MAY_RETRY_LIMIT


T = TypeVar("T")


def classify_failure(error: BaseException) -> str:
    message = f"{type(error).__name__}:{error}".upper()
    rules = (
        (("SCIENTIFIC_AUTHORITY", "AUTHORITY_CHANGE_REQUIRED"), "SCIENTIFIC_AUTHORITY_CHANGE_REQUIRED"),
        (("STORAGE", "SERIALIZ", "NPZ", "JSON", "SHA"), "STORAGE_INTEGRITY_DEFECT"),
        (("CACHE", "RESUME", "CHECKPOINT"), "ENGINEERING_CACHE_OR_RESUME_DEFECT"),
        (("SOLVER", "GUROBI", "MIPSTART", "INCUMBENT"), "ENGINEERING_SOLVER_INTEGRATION_DEFECT"),
        (("CASE_BIND", "OFFICIAL_CASE"), "CASE_BINDING_DEFECT"),
        (("AIDC_COUPLING", "AIDC_STAGE", "AIDC_MAPPING"), "AIDC_COUPLING_DEFECT"),
        (("MESS_COUPLING", "MESS_GRID", "ROUTE_TO_MILP"), "MESS_COUPLING_DEFECT"),
        (("FRESH", "OPENDSS"), "FRESH_INTERFACE_DEFECT"),
        (("FIREWALL", "CAUSALITY", "REROUTE", "ACTUAL_MESS_OPTIM"), "CAUSALITY_FIREWALL_DEFECT"),
    )
    for tokens, classification in rules:
        if any(token in message for token in tokens):
            return classification
    return "ENGINEERING_RUNTIME_DEFECT"


@dataclass(frozen=True)
class RepairAttempt:
    attempt: int
    failure_signature: str
    classification: str
    repaired: bool


class ScientificAuthorityBlocked(RuntimeError):
    pass


class RetryExhausted(RuntimeError):
    pass


def run_self_healing(
    execute: Callable[[int], T],
    repair: Callable[[BaseException, str, int], bool],
    *,
    campaign: str,
    on_failure: Callable[[BaseException, RepairAttempt], None] | None = None,
) -> tuple[T, tuple[RepairAttempt, ...]]:
    limit = MAY_RETRY_LIMIT if campaign.upper() == "MAY" else APRIL_RETRY_LIMIT
    attempts: list[RepairAttempt] = []
    signatures: dict[str, int] = {}
    for attempt in range(1, limit + 2):
        try:
            return execute(attempt), tuple(attempts)
        except BaseException as error:
            classification = classify_failure(error)
            signature = f"{classification}:{type(error).__name__}:{error}"
            signatures[signature] = signatures.get(signature, 0) + 1
            if classification == "SCIENTIFIC_AUTHORITY_CHANGE_REQUIRED":
                raise ScientificAuthorityBlocked(signature) from error
            if signatures[signature] > limit:
                raise RetryExhausted(f"V35_RETRY_LIMIT:{limit}:{signature}") from error
            repaired = bool(repair(error, classification, signatures[signature]))
            record = RepairAttempt(signatures[signature], signature, classification, repaired)
            attempts.append(record)
            if on_failure is not None:
                on_failure(error, record)
            if not repaired:
                raise
    raise AssertionError("unreachable")


def quarantine_may_run(run_root: Path, quarantine_root: Path, run_id: str) -> Path:
    source = run_root.resolve()
    destination_parent = quarantine_root.resolve()
    if not source.is_dir():
        raise FileNotFoundError("V35_MAY_RUN_ROOT_MISSING")
    if source == destination_parent or source in destination_parent.parents:
        raise ValueError("V35_MAY_QUARANTINE_SCOPE_INVALID")
    destination_parent.mkdir(parents=True, exist_ok=True)
    destination = destination_parent / run_id
    if destination.exists():
        raise FileExistsError("V35_MAY_QUARANTINE_RUN_ID_EXISTS")
    shutil.move(str(source), str(destination))
    if source.exists() or not destination.is_dir():
        raise RuntimeError("V35_MAY_QUARANTINE_MOVE_FAILED")
    return destination


assert set(FAILURE_CLASSES) >= {
    "ENGINEERING_RUNTIME_DEFECT", "STORAGE_INTEGRITY_DEFECT", "SCIENTIFIC_AUTHORITY_CHANGE_REQUIRED",
}

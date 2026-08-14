"""Reusable, provenance-checked generalized-Benders cut cache.

This module is the authority boundary between the route/work master and the
unchanged convex AC-aware QCP subproblem.  Solver adapters may populate the
cache, but only cuts carrying the same structural signature are reusable.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Dict, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class BendersCut:
    cut_type: str
    coefficients: Tuple[Tuple[str, float], ...]
    rhs: float
    structural_signature: str
    source_issue: int
    qcp_status: str

    def validate(self) -> None:
        if self.cut_type not in {"OPTIMALITY", "FEASIBILITY"}:
            raise ValueError("invalid Benders cut type")
        if not self.structural_signature:
            raise ValueError("Benders structural signature is required")
        if self.qcp_status not in {"OPTIMAL", "INFEASIBLE_CERTIFIED"}:
            raise ValueError("cut lacks an authoritative QCP status")
        names = [name for name, _ in self.coefficients]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("Benders coefficients must be sorted and unique")
        if not math.isfinite(self.rhs) or any(
            not math.isfinite(value) for _, value in self.coefficients
        ):
            raise ValueError("Benders cut coefficients and rhs must be finite")

    @property
    def checksum(self) -> str:
        payload = json.dumps(
            {
                "cut_type": self.cut_type,
                "coefficients": self.coefficients,
                "rhs": self.rhs,
                "structural_signature": self.structural_signature,
                "source_issue": self.source_issue,
                "qcp_status": self.qcp_status,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class BendersCutCache:
    def __init__(self) -> None:
        self._cuts: Dict[str, BendersCut] = {}

    def add(self, cut: BendersCut) -> bool:
        cut.validate()
        key = cut.checksum
        if key in self._cuts:
            return False
        self._cuts[key] = cut
        return True

    def applicable(self, structural_signature: str) -> Tuple[BendersCut, ...]:
        return tuple(
            cut
            for _, cut in sorted(self._cuts.items())
            if cut.structural_signature == structural_signature
        )

    def extend(self, cuts: Iterable[BendersCut]) -> int:
        return sum(1 for cut in cuts if self.add(cut))

    def stats(self) -> Mapping[str, int]:
        return {"total": len(self._cuts)}

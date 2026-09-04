"""Mass-conserving V30 recourse accounting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlotLedger:
    slot: int
    da_authorized_nodeh: float
    actual_available_nodeh: float
    executed_original_rack_nodeh: float
    executed_same_site_recourse_nodeh: float
    executed_cross_site_recourse_nodeh: float
    source_unavailable_nodeh: float
    true_rack_capacity_limit_nodeh: float
    grid_safety_blocked_nodeh: float
    other_explicit_nodeh: float
    terminal_backlog_nodeh: float

    @property
    def executed_nodeh(self) -> float:
        return self.executed_original_rack_nodeh + self.executed_same_site_recourse_nodeh + self.executed_cross_site_recourse_nodeh

    @property
    def authorization_identity_error_nodeh(self) -> float:
        return self.da_authorized_nodeh - (
            self.executed_nodeh + self.source_unavailable_nodeh + self.true_rack_capacity_limit_nodeh
            + self.grid_safety_blocked_nodeh + self.other_explicit_nodeh
        )


def aggregate_ledgers(rows: list[SlotLedger]) -> dict[str, float]:
    result = {
        "DA_AUTHORIZED": sum(row.da_authorized_nodeh for row in rows),
        "ACTUAL_AVAILABLE": sum(row.actual_available_nodeh for row in rows),
        "EXECUTED_ORIGINAL_RACK": sum(row.executed_original_rack_nodeh for row in rows),
        "EXECUTED_SAME_SITE_RECOURSE": sum(row.executed_same_site_recourse_nodeh for row in rows),
        "EXECUTED_CROSS_SITE_RECOURSE": sum(row.executed_cross_site_recourse_nodeh for row in rows),
        "SOURCE_UNAVAILABLE": sum(row.source_unavailable_nodeh for row in rows),
        "TRUE_RACK_CAPACITY_LIMIT": sum(row.true_rack_capacity_limit_nodeh for row in rows),
        "GRID_SAFETY_BLOCKED": sum(row.grid_safety_blocked_nodeh for row in rows),
        "OTHER_EXPLICIT": sum(row.other_explicit_nodeh for row in rows),
        "TERMINAL_BACKLOG": rows[-1].terminal_backlog_nodeh if rows else 0.0,
        "maximum_slot_authorization_identity_error_nodeh": max((abs(row.authorization_identity_error_nodeh) for row in rows), default=0.0),
    }
    result["EXECUTED_TOTAL"] = result["EXECUTED_ORIGINAL_RACK"] + result["EXECUTED_SAME_SITE_RECOURSE"] + result["EXECUTED_CROSS_SITE_RECOURSE"]
    result["authorization_mass_identity_error_nodeh"] = result["DA_AUTHORIZED"] - (
        result["EXECUTED_TOTAL"] + result["SOURCE_UNAVAILABLE"] + result["TRUE_RACK_CAPACITY_LIMIT"]
        + result["GRID_SAFETY_BLOCKED"] + result["OTHER_EXPLICIT"]
    )
    return result

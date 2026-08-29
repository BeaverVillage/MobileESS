"""Authority-bound Mobile ESS physics and time-expanded mobility audits."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


DT_HOURS = 0.25
MESS_IDS = tuple(f"MESS{index:02d}" for index in range(1, 5))
CAPACITY_KWH = 1200.0
E_MIN_KWH = 440.0
E_MAX_KWH = 1080.0
E_INITIAL_KWH = 760.0
E_TERMINAL_KWH = 760.0
P_LIMIT_KW = 550.0
PCS_KVA = 700.0
PCS_POLYGON_FACES = 16


class MobilityMode(str, Enum):
    CONNECTED = "CONNECTED"
    TRANSIT = "TRANSIT"
    CONNECTION_DELAY = "CONNECTION_DELAY"


@dataclass(frozen=True)
class MessSlot:
    location: str
    mode: MobilityMode
    p_dis_kw: float
    p_ch_kw: float
    q_kvar: float

    @property
    def p_kw(self) -> float:
        return self.p_dis_kw - self.p_ch_kw


def pcs_inner_polygon_satisfied(p_kw: float, q_kvar: float, *, tolerance: float = 1e-9) -> bool:
    apothem = PCS_KVA * math.cos(math.pi / PCS_POLYGON_FACES)
    return all(
        p_kw * math.cos(2 * math.pi * face / PCS_POLYGON_FACES)
        + q_kvar * math.sin(2 * math.pi * face / PCS_POLYGON_FACES)
        <= apothem + tolerance
        for face in range(PCS_POLYGON_FACES)
    )


def audit_pcs_exact_norm(p_kw: float, q_kvar: float, *, tolerance: float = 1e-9) -> None:
    if math.hypot(p_kw, q_kvar) > PCS_KVA + tolerance:
        raise ValueError("MESS_PCS_EXACT_NORM_EXCEEDED")


def validate_occupancy(occupancy: Mapping[tuple[str, int], Sequence[str]]) -> None:
    for (_mess_id, _slot), locations in occupancy.items():
        if len(tuple(locations)) != 1:
            raise ValueError("MESS_CANNOT_EXIST_AT_TWO_PLACES")


def validate_trajectory(slots: Sequence[MessSlot], *, initial_energy_kwh: float = E_INITIAL_KWH) -> tuple[float, ...]:
    if len(slots) != 96:
        raise ValueError("MESS trajectory must contain exactly 96 slots")
    energy = [float(initial_energy_kwh)]
    for index, slot in enumerate(slots):
        if slot.p_dis_kw < -1e-9 or slot.p_ch_kw < -1e-9:
            raise ValueError("P_dis/P_ch must be non-negative")
        if slot.p_dis_kw > 1e-9 and slot.p_ch_kw > 1e-9:
            raise ValueError("SIMULTANEOUS_CHARGE_DISCHARGE_PROHIBITED")
        if slot.mode in {MobilityMode.TRANSIT, MobilityMode.CONNECTION_DELAY} and (
            abs(slot.p_kw) > 1e-9 or abs(slot.q_kvar) > 1e-9
        ):
            raise ValueError(f"{slot.mode.value}_REQUIRES_P_Q_ZERO")
        if slot.mode == MobilityMode.CONNECTED and abs(slot.p_kw) > P_LIMIT_KW + 1e-9:
            raise ValueError("MESS_ACTIVE_POWER_LIMIT_EXCEEDED")
        if not pcs_inner_polygon_satisfied(slot.p_kw, slot.q_kvar):
            raise ValueError("MESS_16_FACE_PCS_INNER_POLYGON_EXCEEDED")
        audit_pcs_exact_norm(slot.p_kw, slot.q_kvar)
        next_energy = energy[-1] + DT_HOURS * (slot.p_ch_kw - slot.p_dis_kw)
        if not E_MIN_KWH - 1e-9 <= next_energy <= E_MAX_KWH + 1e-9:
            raise ValueError("MESS_SOC_BOUND_EXCEEDED")
        energy.append(next_energy)
    if slots[-1].mode == MobilityMode.TRANSIT:
        raise ValueError("DAY_END_TRANSIT_FORBIDDEN")
    if abs(energy[-1] - E_TERMINAL_KWH) > 1e-8:
        raise ValueError("MESS_TERMINAL_ENERGY_MUST_EQUAL_760_KWH")
    return tuple(energy)


def conservative_connection_delay_slots(minutes: float = 10.0) -> int:
    return max(1, math.ceil(minutes / 15.0))

"""Sequential, non-optimizing Actual replay of four frozen MESS commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from dayahead.mess_physics import (
    E_MAX_KWH, E_MIN_KWH, PCS_KVA, P_LIMIT_KW, pcs_inner_polygon_satisfied,
)
from dayahead.v29.mess_availability import normalize_mess_record


DT_HOURS = 0.25
ETA_CH = 1.0
ETA_DIS = 1.0


@dataclass(frozen=True)
class MessReplay:
    mess_ids: tuple[str, ...]
    p_exec_kw: np.ndarray
    q_exec_kvar: np.ndarray
    energy_kwh: np.ndarray
    locations_96x4: np.ndarray
    reasons_96x4: np.ndarray
    actual_travel_energy_kwh: np.ndarray
    command_time_shift_count: int
    substitute_vehicle_count: int

    def validate(self, p_da: np.ndarray, q_da: np.ndarray) -> None:
        shapes = (
            (self.p_exec_kw, (96, 4)), (self.q_exec_kvar, (96, 4)),
            (self.energy_kwh, (97, 4)), (self.locations_96x4, (96, 4)),
            (self.reasons_96x4, (96, 4)), (self.actual_travel_energy_kwh, (96, 4)),
        )
        if len(self.mess_ids) != 4 or any(np.asarray(array).shape != shape for array, shape in shapes):
            raise ValueError("V28R2_MESS_REPLAY_AXIS")
        if not all(np.isfinite(array).all() for array in (
            self.p_exec_kw, self.q_exec_kvar, self.energy_kwh, self.actual_travel_energy_kwh,
        )):
            raise ValueError("V28R2_MESS_REPLAY_NONFINITE")
        if np.any(self.energy_kwh < E_MIN_KWH - 1e-9) or np.any(self.energy_kwh > E_MAX_KWH + 1e-9):
            raise ValueError("V28R2_MESS_REPLAY_SOC")
        commanded = (np.abs(self.p_exec_kw) > 1e-10) | (np.abs(self.q_exec_kvar) > 1e-10)
        original_zero = (np.abs(p_da) <= 1e-10) & (np.abs(q_da) <= 1e-10)
        if np.any(commanded & original_zero):
            raise ValueError("V28R2_MESS_REPLAY_INVENTED_COMMAND")
        if self.command_time_shift_count or self.substitute_vehicle_count:
            raise ValueError("V28R2_MESS_REPLAY_SHIFT_OR_SUBSTITUTE")


def replay_mess(
    p_da_kw: np.ndarray, q_da_kvar: np.ndarray,
    actual_records: Sequence[Mapping[str, object]],
) -> MessReplay:
    p_da = np.asarray(p_da_kw, dtype=float); q_da = np.asarray(q_da_kvar, dtype=float)
    records = tuple(normalize_mess_record(row) for row in sorted(actual_records, key=lambda row: str(row["mess_id"])))
    if p_da.shape != (96, 4) or q_da.shape != (96, 4) or len(records) != 4:
        raise ValueError("V28R2_MESS_REPLAY_INPUT_AXIS")
    p_exec = np.zeros((96, 4)); q_exec = np.zeros((96, 4))
    energy = np.zeros((97, 4)); travel = np.zeros((96, 4))
    locations = np.empty((96, 4), dtype="U64"); reasons = np.empty((96, 4), dtype="U64")
    mess_ids = tuple(str(row["mess_id"]) for row in records)
    for mess, record in enumerate(records):
        mode = tuple(map(str, record["mode"]))
        available = tuple(map(bool, record["available"]))
        location = tuple(map(str, record["location"]))
        # The source authority is a deterministic engineering route.  Its
        # safe route energy is therefore the realized physical draw as well
        # as the planning reserve; no forecast value is substituted.
        actual_travel = tuple(map(float, record["safe_travel_energy_kwh"]))
        if not all(len(axis) == 96 for axis in (mode, available, location, actual_travel)):
            raise ValueError(f"V28R2_MESS_ACTUAL_AXIS:{mess_ids[mess]}")
        energy[0, mess] = float(record["initial_energy_kwh"])
        for slot in range(96):
            locations[slot, mess] = location[slot]
            travel[slot, mess] = actual_travel[slot]
            connection_delay = mode[slot] == "CONNECTION_DELAY"
            connected = available[slot] and mode[slot] == "CONNECTED"
            p = float(p_da[slot, mess]); q = float(q_da[slot, mess])
            reason = "EXECUTED"
            if not connected:
                p = q = 0.0
                reason = "CONNECTION_DELAY" if connection_delay else f"UNAVAILABLE_{mode[slot]}"
            elif abs(p) > P_LIMIT_KW + 1e-9 or not pcs_inner_polygon_satisfied(p, q):
                p = q = 0.0
                reason = "PCS_OR_ACTIVE_LIMIT_INFEASIBLE"
            p_ch = max(-p, 0.0); p_dis = max(p, 0.0)
            candidate = (
                energy[slot, mess] + ETA_CH * p_ch * DT_HOURS
                - p_dis * DT_HOURS / ETA_DIS - actual_travel[slot]
            )
            if candidate < E_MIN_KWH - 1e-9 or candidate > E_MAX_KWH + 1e-9:
                p = q = 0.0
                candidate = energy[slot, mess] - actual_travel[slot]
                reason = "SOC_COMMAND_INFEASIBLE"
            if candidate < E_MIN_KWH - 1e-9 or candidate > E_MAX_KWH + 1e-9:
                raise RuntimeError(f"V28R2_MESS_TRAVEL_SOC_PHYSICAL_FAIL:{mess_ids[mess]}:{slot}")
            p_exec[slot, mess] = p; q_exec[slot, mess] = q
            energy[slot + 1, mess] = candidate; reasons[slot, mess] = reason
    result = MessReplay(
        mess_ids, p_exec, q_exec, energy, locations, reasons, travel,
        command_time_shift_count=0, substitute_vehicle_count=0,
    )
    result.validate(p_da, q_da)
    return result

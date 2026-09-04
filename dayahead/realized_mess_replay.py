"""Frozen Mobile ESS command replay under realized connection availability."""

from __future__ import annotations

from typing import Mapping, Sequence


def replay_mess(planned_commands: Sequence[Mapping[str, object]], physically_connected: Sequence[bool]) -> dict[str, object]:
    if len(planned_commands)!=96 or len(physically_connected)!=96: raise ValueError("REALIZED_MESS_REPLAY_REQUIRES_96_SLOTS")
    executed=[]; missed=[]
    for slot,(command,connected) in enumerate(zip(planned_commands,physically_connected)):
        p=float(command.get("p_kw",0.0)); q=float(command.get("q_kvar",0.0))
        if connected: executed.append({**command,"p_kw":p,"q_kvar":q})
        else:
            executed.append({**command,"p_kw":0.0,"q_kvar":0.0})
            if abs(p)>1e-9 or abs(q)>1e-9: missed.append(slot)
    return {"executed":tuple(executed),"missed_command_slots":tuple(missed),"shifted_command_count":0,"solver_call_count":0}

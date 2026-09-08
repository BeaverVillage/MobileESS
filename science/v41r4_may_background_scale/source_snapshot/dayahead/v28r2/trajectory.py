"""Solver-free immutable physical trajectory DTO shared across namespaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .backend_contract import canonical_sha256


@dataclass(frozen=True)
class FrozenTrajectory:
    day: str
    namespace: str
    case: str
    pcc_p_kw: np.ndarray
    pcc_q_kvar: np.ndarray
    mess_p_kw: np.ndarray
    mess_q_kvar: np.ndarray
    mess_ids: tuple[str, ...]
    mess_locations_96x4: np.ndarray
    source_schedule_sha256: str

    def validate(self) -> None:
        if self.namespace not in {"DAYAHEAD", "ACTUAL", "PERFECT_INFORMATION"}:
            raise ValueError("V28R2_OPENDSS_NAMESPACE")
        expected = {
            "pcc_p": (self.pcc_p_kw, (96, 12)),
            "pcc_q": (self.pcc_q_kvar, (96, 12)),
            "mess_p": (self.mess_p_kw, (96, 4)),
            "mess_q": (self.mess_q_kvar, (96, 4)),
        }
        if any(np.asarray(array).shape != shape or not np.isfinite(array).all() for array, shape in expected.values()):
            raise ValueError("V28R2_OPENDSS_TRAJECTORY_SHAPE_OR_FINITE")
        if len(self.mess_ids) != 4 or np.asarray(self.mess_locations_96x4).shape != (96, 4):
            raise ValueError("V28R2_OPENDSS_MESS_AXIS")
        if len(self.source_schedule_sha256) != 64:
            raise ValueError("V28R2_OPENDSS_SCHEDULE_SHA")

    @property
    def immutable_sha256(self) -> str:
        self.validate()
        return canonical_sha256({
            "day": self.day, "namespace": self.namespace, "case": self.case,
            "pcc_p_kw": self.pcc_p_kw.tolist(), "pcc_q_kvar": self.pcc_q_kvar.tolist(),
            "mess_p_kw": self.mess_p_kw.tolist(), "mess_q_kvar": self.mess_q_kvar.tolist(),
            "mess_ids": self.mess_ids,
            "mess_locations_96x4": np.asarray(self.mess_locations_96x4).tolist(),
            "source_schedule_sha256": self.source_schedule_sha256,
        })

    @classmethod
    def from_schedule_payload(
        cls, payload: Mapping[str, object], *, day: str, namespace: str,
    ) -> "FrozenTrajectory":
        source = dict(payload)
        stored = source.pop("schedule_sha256", None)
        if stored is not None and stored != canonical_sha256(source):
            raise RuntimeError("V28R2_OPENDSS_SCHEDULE_PAYLOAD_SHA")
        route = source.get("mess_route_location")
        if not isinstance(route, Mapping):
            raise ValueError("V28R2_OPENDSS_MESS_ROUTE")
        mess_ids = tuple(sorted(map(str, route)))
        locations = np.asarray([
            list(route[mess].get("location_96", [route[mess]["service_site"]] * 96))
            for mess in mess_ids
        ], dtype=str).T
        result = cls(
            day=day, namespace=namespace, case=str(source["case"]),
            pcc_p_kw=np.asarray(source["planning_pcc_power_kw"], dtype=float),
            pcc_q_kvar=np.asarray(source["planning_pcc_reactive_kvar"], dtype=float),
            mess_p_kw=np.asarray(source["mess_p_kw"], dtype=float),
            mess_q_kvar=np.asarray(source["mess_q_kvar"], dtype=float),
            mess_ids=mess_ids, mess_locations_96x4=locations,
            source_schedule_sha256=str(stored or canonical_sha256(source)),
        )
        result.validate()
        return result

"""Immutable V28R2 trajectory-to-audited-IEEE123 mapping."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from .backend_contract import canonical_sha256, sha256_file
from .electrical_context import ElectricalContext, source_root


NATIVE_MASTER_SHA256 = "cc7c2f153ca1e57f9fb5cad8b3c3e1ecbcb20c5db59ca4d65539411a50525969"
REGULATORS = ("reg1a", "reg2a", "reg3a", "reg3c", "reg4a", "reg4b", "reg4c")
CAPACITORS = ("c83", "c88a", "c90b", "c92c")


@dataclass(frozen=True)
class FeederAssets:
    master: Path
    ratings: Path
    phase_pv: Path
    runtime_adapter: Path
    service_mapping: Path
    pcc: Path

    @classmethod
    def from_repo(cls, repo: Path) -> "FeederAssets":
        source = source_root(repo)
        return cls(
            source / "opendss_assets/IEEE123Master.dss",
            source / "opendss_assets/Generated_Planning_Line_Ratings_u080.dss",
            source / "power_v70_p4f_contract/Generated_PhasePV.dss",
            source / "power_v70_p4f_contract/opendss_runtime_adapter.json",
            source / "power_v70_p4f_contract/service_node_electrical_mapping_v1.csv",
            repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        )

    def validate(self) -> None:
        missing = [str(path) for path in self.__dict__.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"V28R2_OPENDSS_ASSET_MISSING:{missing}")
        if sha256_file(self.master) != NATIVE_MASTER_SHA256:
            raise RuntimeError("V28R2_NATIVE_IEEE123_SHA_MISMATCH")

    @property
    def sha256(self) -> dict[str, str]:
        self.validate()
        return {name: sha256_file(path) for name, path in self.__dict__.items()}


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
    mess_service_sites: tuple[str, ...]
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
        if len(self.mess_ids) != 4 or len(self.mess_service_sites) != 4:
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
            "mess_ids": self.mess_ids, "mess_service_sites": self.mess_service_sites,
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
        services = tuple(str(route[mess]["service_site"]) for mess in mess_ids)
        result = cls(
            day=day, namespace=namespace, case=str(source["case"]),
            pcc_p_kw=np.asarray(source["planning_pcc_power_kw"], dtype=float),
            pcc_q_kvar=np.asarray(source["planning_pcc_reactive_kvar"], dtype=float),
            mess_p_kw=np.asarray(source["mess_p_kw"], dtype=float),
            mess_q_kvar=np.asarray(source["mess_q_kvar"], dtype=float),
            mess_ids=mess_ids, mess_service_sites=services,
            source_schedule_sha256=str(stored or canonical_sha256(source)),
        )
        result.validate()
        return result


def aidc_injection_mapping(p_kw: float, q_kvar: float) -> dict[str, float]:
    """Positive AIDC P/Q is consumption in the dedicated PCC load."""

    return {"load_p_kw": float(p_kw), "load_q_kvar": float(q_kvar)}


def mess_injection_mapping(p_kw: float, q_kvar: float) -> dict[str, float]:
    """Positive MESS P is discharge/injection; negative P is charging load."""

    return {
        "generator_p_kw": max(float(p_kw), 0.0),
        "generator_q_kvar": float(q_kvar),
        "charging_load_p_kw": max(-float(p_kw), 0.0),
        "charging_load_q_kvar": 0.0,
    }


def _set_load(odd: object, name: str, p_kw: float, q_kvar: float) -> None:
    odd.Loads.Name(name)
    if str(odd.Loads.Name()).lower() != name.lower():
        raise RuntimeError(f"V28R2_OPENDSS_LOAD_NOT_FOUND:{name}")
    odd.Loads.kW(float(p_kw)); odd.Loads.kvar(float(q_kvar))


def _set_generator(odd: object, name: str, p_kw: float, q_kvar: float) -> None:
    odd.Generators.Name(name)
    if str(odd.Generators.Name()).lower() != name.lower():
        raise RuntimeError(f"V28R2_OPENDSS_GENERATOR_NOT_FOUND:{name}")
    odd.Generators.kW(float(p_kw)); odd.Generators.kvar(float(q_kvar))


def compile_clean_engine(assets: FeederAssets) -> tuple[object, Mapping[str, object]]:
    """Create an independent OpenDSS context and compile only frozen assets."""

    import opendssdirect as dss

    assets.validate()
    odd = dss.NewContext()
    odd.Basic.ClearAll()
    commands = (
        f'Compile "{assets.master}"', "MakeBusList", f'Redirect "{assets.pcc}"',
        "MakeBusList", "CalcVoltageBases", f'Redirect "{assets.ratings}"',
        f'Redirect "{assets.phase_pv}"',
        "Set mode=snapshot controlmode=static maxcontroliter=100",
    )
    for command in commands:
        odd.Text.Command(command)
        if int(odd.Error.Number()) != 0:
            raise RuntimeError(f"V28R2_OPENDSS_COMPILE:{command}:{odd.Error.Description()}")
    adapter = json.loads(assets.runtime_adapter.read_text(encoding="utf-8"))
    return odd, adapter


def apply_frozen_native_state(odd: object, voltage: object, slot: int) -> None:
    taps = np.asarray(voltage["regulator_taps"], dtype=float)
    caps = np.asarray(voltage["capacitor_states"], dtype=int)
    if taps.shape != (96, 7) or caps.shape != (96, 4):
        raise RuntimeError("V28R2_OPENDSS_NATIVE_STATE_AXIS")
    for name in odd.RegControls.AllNames():
        odd.Text.Command(f"Disable RegControl.{name}")
    for index, name in enumerate(REGULATORS):
        odd.Transformers.Name(name); odd.Transformers.Wdg(2); odd.Transformers.Tap(float(taps[slot, index]))
    for index, name in enumerate(CAPACITORS):
        odd.Capacitors.Name(name); odd.Capacitors.States([int(caps[slot, index])])
    odd.Text.Command("Set controlmode=off")


def apply_trajectory_slot(
    odd: object, adapter: Mapping[str, object], context: ElectricalContext,
    trajectory: FrozenTrajectory, slot: int,
) -> None:
    """Apply one frozen slot without changing its time or command arrays."""

    _reference, _vintage, background, _binding, _cache, _authority = context.legacy_context
    for row in adapter["loads"]:
        phases = tuple("ABC"[int(value) - 1] for value in row["phases"])
        bus = str(row["bus"]).lower()
        _set_load(
            odd, str(row["load_name"]),
            sum(float(background.gross_p_kw_96[slot].get((bus, phase), 0.0)) for phase in phases),
            sum(float(background.gross_q_kvar_96[slot].get((bus, phase), 0.0)) for phase in phases),
        )
    for row in adapter["pv_generators"]:
        bus = str(row["bus"]).lower(); phase = "ABC"[int(row["phase"]) - 1]
        _set_generator(
            odd, str(row["generator_name"]),
            float(background.pv_generation_kw_96[slot].get((bus, phase), 0.0)), 0.0,
        )
    for index in range(12):
        mapped = aidc_injection_mapping(trajectory.pcc_p_kw[slot, index], trajectory.pcc_q_kvar[slot, index])
        _set_load(odd, f"IDC_IDC{index + 1:02d}", mapped["load_p_kw"], mapped["load_q_kvar"])
    for name in odd.Generators.AllNames():
        if str(name).lower().startswith("mess_dis_"):
            _set_generator(odd, str(name), 0.0, 0.0)
    for name in odd.Loads.AllNames():
        if str(name).lower().startswith("mess_chg_"):
            _set_load(odd, str(name), 0.0, 0.0)
    by_service: dict[str, list[float]] = {}
    for index, service in enumerate(trajectory.mess_service_sites):
        totals = by_service.setdefault(service.upper(), [0.0, 0.0])
        totals[0] += float(trajectory.mess_p_kw[slot, index])
        totals[1] += float(trajectory.mess_q_kvar[slot, index])
    for service, (p_kw, q_kvar) in sorted(by_service.items()):
        mapped = mess_injection_mapping(p_kw, q_kvar)
        _set_generator(odd, f"MESS_DIS_{service}", mapped["generator_p_kw"], mapped["generator_q_kvar"])
        _set_load(odd, f"MESS_CHG_{service}", mapped["charging_load_p_kw"], mapped["charging_load_q_kvar"])

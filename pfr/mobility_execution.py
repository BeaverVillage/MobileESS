"""Execution-only MESS travel-time authority from frozen 2025 SUMO outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .mobility_physics import MobilityPhysics


class MobilityExecutionContractError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class MobilityExecutionRealization:
    issue: int
    date: str
    depart_slot5: int
    od_index: int
    rank: int
    eta_seconds: float
    energy_kwh: float
    source_authority: str
    source_day_sha256: str

    def validate(self) -> None:
        if (
            self.issue < 0
            or not 0 <= self.depart_slot5 < 288
            or self.od_index < 0
            or self.rank not in {1, 2, 3}
            or not math.isfinite(self.eta_seconds)
            or self.eta_seconds <= 0.0
            or not math.isfinite(self.energy_kwh)
            or self.energy_kwh <= 0.0
            or len(self.source_day_sha256) != 64
        ):
            raise MobilityExecutionContractError("SUMO mobility realization is invalid")


class Stage25fSumoExecutionAuthority:
    """Resolve post-decision route duration from full-year Stage25F SUMO output.

    This object is deliberately kept outside ``CausalExperimentFrame``.  It is
    called only after the optimizer has committed a route, so the 2025 realized
    travel time cannot enter route selection.
    """

    AUTHORITY_ID = "STAGE25F_2025_SUMO_FINAL_OPERATIONAL_TT_EXECUTION_ONLY_V1"

    def __init__(
        self,
        *,
        contract_path: Path,
        mobility_physics: MobilityPhysics,
        route_rows: Sequence[Mapping[str, Any]],
    ) -> None:
        contract_path = contract_path.resolve()
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version")
            != "mobileess.mess_mobility_execution_sumo.v1"
            or payload.get("status") != "FROZEN_EXECUTION_ONLY"
            or payload.get("authority_id") != self.AUTHORITY_ID
            or payload.get("optimizer_access") is not False
            or payload.get("post_decision_only") is not True
            or payload.get("travel_time_column") != "final_tt_sec"
            or payload.get("issue_zero_timestamp") != "2025-01-01T00:00:00"
            or payload.get("maximum_supported_route_eta_seconds") != 16200
        ):
            raise MobilityExecutionContractError("SUMO execution authority is invalid")

        sources = payload.get("sources", {})
        try:
            manifest_path = Path(sources["traffic_day_manifest"]["path"])
            sequences_path = Path(sources["route_sequences"]["path"])
            link_order_path = Path(sources["link_order"]["path"])
        except (KeyError, TypeError) as exc:
            raise MobilityExecutionContractError(
                "SUMO execution source paths are incomplete"
            ) from exc
        for name, path in (
            ("traffic_day_manifest", manifest_path),
            ("route_sequences", sequences_path),
            ("link_order", link_order_path),
        ):
            expected = str(sources[name].get("sha256", ""))
            if not path.is_file() or len(expected) != 64 or _sha256(path) != expected:
                raise MobilityExecutionContractError(
                    f"SUMO execution source fingerprint mismatch: {name}"
                )

        day_sources: dict[str, tuple[Path, str]] = {}
        with manifest_path.open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                date = str(row["date"])
                path = Path(row["path"])
                digest = str(row["sha256"])
                if date in day_sources or not path.is_file() or len(digest) != 64:
                    raise MobilityExecutionContractError(
                        f"invalid SUMO traffic-day manifest row: {date}"
                    )
                day_sources[date] = (path, digest)
        if len(day_sources) != 365 or min(day_sources) != "2025-01-01" or max(day_sources) != "2025-12-31":
            raise MobilityExecutionContractError(
                "SUMO execution manifest must cover all 365 days of 2025"
            )

        link_order = pd.read_csv(link_order_path)
        if len(link_order) != 509 or set(link_order["tensor_index"].astype(int)) != set(range(509)):
            raise MobilityExecutionContractError("SUMO reduced-link axis is invalid")
        self._link_index = {
            str(row.reduced_link_id): int(row.tensor_index)
            for row in link_order.itertuples(index=False)
        }

        with np.load(sequences_path, allow_pickle=False) as sequences:
            links = np.asarray(sequences["route_links"], dtype=np.int64)
            mask = np.asarray(sequences["route_mask"], dtype=bool)
            ranks = np.asarray(sequences["rank"], dtype=np.int64)
        if links.shape != (1656, 8) or mask.shape != links.shape or ranks.shape != (1656,):
            raise MobilityExecutionContractError("SUMO K=3 route sequence axis is invalid")
        self._route_links = tuple(
            tuple(int(value) for value in links[slot][mask[slot]])
            for slot in range(1656)
        )

        if len(route_rows) != 1656:
            raise MobilityExecutionContractError("physics route catalog must have 1656 slots")
        self._route_rows: dict[tuple[int, int], Mapping[str, Any]] = {}
        for expected_slot, route in enumerate(route_rows):
            slot = int(route["slot"])
            key = (int(route["od_index"]), int(route["rank"]))
            if slot != expected_slot or slot != key[0] * 3 + key[1] - 1:
                raise MobilityExecutionContractError("physics and SUMO route slots disagree")
            if int(ranks[slot]) != key[1] or key in self._route_rows:
                raise MobilityExecutionContractError("SUMO route rank identity is invalid")
            self._route_rows[key] = route

        mobility_physics.validate()
        self._physics = mobility_physics
        self._day_sources = day_sources
        self._day_cache: dict[str, np.ndarray] = {}
        self._verified_day_hashes: set[str] = set()
        self.contract_path = contract_path
        self.fingerprint = _sha256(contract_path)

    def _load_day(self, date: str) -> tuple[np.ndarray, str]:
        source = self._day_sources.get(date)
        if source is None:
            raise MobilityExecutionContractError(
                f"SUMO execution date is outside frozen 2025 authority: {date}"
            )
        path, expected_sha = source
        if date not in self._verified_day_hashes:
            if _sha256(path) != expected_sha:
                raise MobilityExecutionContractError(
                    f"SUMO traffic-day fingerprint mismatch: {date}"
                )
            self._verified_day_hashes.add(date)
        cached = self._day_cache.get(date)
        if cached is not None:
            return cached, expected_sha

        frame = pd.read_parquet(
            path, columns=["slot5", "reduced_link_id", "final_tt_sec"]
        )
        slots = pd.to_numeric(frame["slot5"], errors="coerce").to_numpy()
        link_indices = frame["reduced_link_id"].astype(str).map(self._link_index).to_numpy()
        travel = pd.to_numeric(frame["final_tt_sec"], errors="coerce").to_numpy(float)
        if (
            len(frame) != 288 * 509
            or np.isnan(slots).any()
            or pd.isna(link_indices).any()
            or not np.isfinite(travel).all()
            or (travel <= 0.0).any()
        ):
            raise MobilityExecutionContractError(
                f"SUMO final operational travel-time grid is invalid: {date}"
            )
        matrix = np.full((288, 509), np.nan, dtype=np.float64)
        integer_slots = slots.astype(np.int64)
        integer_links = link_indices.astype(np.int64)
        matrix[integer_slots, integer_links] = travel
        if not np.isfinite(matrix).all():
            raise MobilityExecutionContractError(
                f"SUMO final operational travel-time grid is incomplete: {date}"
            )
        self._day_cache.clear()
        self._day_cache[date] = matrix
        return matrix, expected_sha

    def realize(self, *, issue: int, route: Any) -> MobilityExecutionRealization:
        """Return actual ETA/energy after, never before, route commitment."""
        if issue < 0:
            raise MobilityExecutionContractError("execution issue must be non-negative")
        timestamp = datetime(2025, 1, 1) + timedelta(minutes=5 * issue)
        date = timestamp.date().isoformat()
        depart_slot = timestamp.hour * 12 + timestamp.minute // 5
        day, day_sha = self._load_day(date)

        key = (int(route.od_index), int(route.rank))
        geometry = self._route_rows.get(key)
        if geometry is None:
            raise MobilityExecutionContractError("selected route is outside frozen K=3")
        if (
            str(route.source_service_id) != str(geometry["source_service_id"])
            or str(route.destination_service_id)
            != str(geometry["destination_service_id"])
        ):
            raise MobilityExecutionContractError("selected route identity is inconsistent")
        slot = key[0] * 3 + key[1] - 1
        elapsed = 0.0
        for link_index in self._route_links[slot]:
            entry_slot = min(287, depart_slot + int(elapsed // 300.0))
            elapsed += float(day[entry_slot, link_index])
        energy = self._physics.energy_kwh(geometry, elapsed)
        realized = MobilityExecutionRealization(
            issue=issue,
            date=date,
            depart_slot5=depart_slot,
            od_index=key[0],
            rank=key[1],
            eta_seconds=elapsed,
            energy_kwh=energy,
            source_authority=self.AUTHORITY_ID,
            source_day_sha256=day_sha,
        )
        realized.validate()
        if realized.eta_seconds > 16200.0:
            raise MobilityExecutionContractError(
                "SUMO realization exceeds frozen H54 execution support: "
                f"issue={issue} od_index={key[0]} rank={key[1]} "
                f"eta_seconds={realized.eta_seconds:.12g}"
            )
        return realized

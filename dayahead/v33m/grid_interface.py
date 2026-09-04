"""Generic service/PCC mapping and MESS P/Q injection interface."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .contracts import MobilityContractError


FROZEN_SERVICE_PCC_MAPPING_SHA256 = (
    "c3763567f6785f182ab151ca0390918017d4e24c2733f6d72d2304bba416322e"
)


@dataclass(frozen=True)
class ServicePCCMapping:
    service_to_pcc: Mapping[str, str]
    authority_sha256: str

    def __post_init__(self) -> None:
        mapping = dict(self.service_to_pcc)
        if not mapping or any(not service or not pcc for service, pcc in mapping.items()):
            raise MobilityContractError("service/PCC mapping must be complete and non-empty")
        object.__setattr__(self, "service_to_pcc", MappingProxyType(mapping))


def load_frozen_service_pcc_mapping(
    path: Path,
    *,
    expected_sha256: str = FROZEN_SERVICE_PCC_MAPPING_SHA256,
) -> ServicePCCMapping:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise MobilityContractError(
            f"service/PCC mapping SHA mismatch: {digest} != {expected_sha256}"
        )
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"service_node_id", "electrical_host_bus"}
    if not rows or not required.issubset(rows[0]):
        raise MobilityContractError("service/PCC mapping schema is invalid")
    mapping = {
        str(row["service_node_id"]): str(row["electrical_host_bus"]).lower()
        for row in rows
    }
    if len(mapping) != len(rows):
        raise MobilityContractError("service/PCC mapping contains duplicate service IDs")
    return ServicePCCMapping(mapping, digest)

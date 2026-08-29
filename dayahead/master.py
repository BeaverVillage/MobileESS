"""Dimension-driven Day-Ahead master framework without fabricated AIDC data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .aidc_rack_model import RackTensorShape
from .authority import DimensionAuthority
from .science_firewall import AuthorityGate, CURRENT_AIDC_GATE


class CaseName(str, Enum):
    B0_NO_FLEXIBILITY = "B0_NO_FLEXIBILITY"
    B1_COMPUTE_FLEXIBILITY_ONLY = "B1_COMPUTE_FLEXIBILITY_ONLY"
    B2_MESS_FLEXIBILITY_ONLY = "B2_MESS_FLEXIBILITY_ONLY"
    B3_JOINT_PROPOSED = "B3_JOINT_PROPOSED"


@dataclass(frozen=True)
class MasterStructure:
    case: CaseName
    dimensions: RackTensorShape
    service_site_ids: tuple[str, ...]
    variable_index: Mapping[str, tuple[tuple[object, ...], ...]]


def build_master_structure(
    case: CaseName,
    authority: DimensionAuthority,
    service_site_ids: tuple[str, ...],
    *,
    production: bool = False,
    gate: AuthorityGate = CURRENT_AIDC_GATE,
) -> MasterStructure:
    dimensions = RackTensorShape.from_authority(authority, production=production)
    if production:
        gate.require()
    allocation = tuple((rack, slot) for rack in dimensions.rack_ids for slot in range(96))
    mess = tuple((mess, slot, site) for mess in range(4) for slot in range(96) for site in service_site_ids)
    return MasterStructure(case, dimensions, tuple(service_site_ids), {"rack_allocation": allocation, "mess_location": mess})

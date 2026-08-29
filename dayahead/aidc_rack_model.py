"""Dimension-parameterized Rack tensor shape and authority validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .authority import DimensionAuthority


@dataclass(frozen=True)
class RackTensorShape:
    aidc_ids: tuple[str, ...]
    rack_ids_by_aidc: Mapping[str, tuple[str, ...]]
    slots: int = 96

    @property
    def rack_ids(self) -> tuple[str, ...]:
        return tuple(rack for aidc in self.aidc_ids for rack in self.rack_ids_by_aidc[aidc])

    @classmethod
    def from_authority(cls, authority: DimensionAuthority, *, production: bool = False) -> "RackTensorShape":
        authority.validate(production=production)
        return cls(authority.aidc_ids, authority.rack_ids_by_aidc)

    def validate_tensor(self, tensor: Mapping[tuple[str, str, int], float]) -> None:
        expected = {
            (aidc, rack, slot)
            for aidc in self.aidc_ids
            for rack in self.rack_ids_by_aidc[aidc]
            for slot in range(self.slots)
        }
        if set(tensor) != expected:
            raise ValueError("workload allocation tensor does not match runtime authority axes")

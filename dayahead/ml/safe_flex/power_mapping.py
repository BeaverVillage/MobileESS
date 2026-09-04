"""Frozen tier-to-IT-power mapping with facility/PUE firewall."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


AUTHORITY = Path("dayahead/artifacts/v18r1_aidc_physical_coherence_repair/V18R1_HYBRID_NODE_POWER_AUTHORITY_REVALIDATION.json")
TIERS = ("FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL")


def coefficients_kWh_per_GPU_h(repo: Path) -> tuple[np.ndarray, dict[str, object]]:
    """Read frozen incremental IT-energy coefficients; PUE is excluded."""

    path = repo / AUTHORITY
    raw = path.read_bytes()
    contract = json.loads(raw)
    full = contract["fullnode"]["kappa_total_kW_per_active_node"]
    partial = float(contract["partialnode"]["kappa_kW_per_GPU"])
    values = [float(full[tier.split("_")[1]]) / 4.0 if tier.startswith("FULL_") else partial for tier in TIERS]
    return np.asarray(values), {
        "source_artifact": str(AUTHORITY).replace("\\", "/"), "source_SHA256": hashlib.sha256(raw).hexdigest(),
        "boundary": "IT_SIDE_INCREMENTAL_POWER", "partial_semantics": "GPU-board-only lower bound; CPU package not imputed",
        "PUE_calls": 0, "facility_MW_scale_calls": 0, "beta_AIDC_calls": 0,
    }


def service_to_IT_kW(service_GPU_h: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    """Map 15-minute tier service to IT kW, preserving latency aggregation."""

    service = np.asarray(service_GPU_h, dtype=float)
    if service.shape[-2:] != (6, 5):
        raise ValueError("V26M_POWER_SERVICE_SHAPE")
    return (service.sum(axis=-1) * coefficients).sum(axis=-1) / 0.25


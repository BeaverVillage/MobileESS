"""Frozen Dataset312 package-only incremental IT-power authority."""

from __future__ import annotations

from typing import Mapping

AUTHORITY_ID = "NLR_D312_INCREMENTAL_POWER_V1"
GPU_PER_NODE = 4
GPU_IDLE_W = 72.5
CPU_SOCKET_IDLE_W = 64.1
CPU_SOCKETS_PER_NODE = 2
KAPPA_KW_PER_ACTIVE_H100_NODE: Mapping[int, float] = {
    1: 2.289471346990805,
    2: 2.2220251879720374,
    4: 2.0938566188449466,
    8: 2.026464800777849,
    16: 1.9654597010662909,
}


def corrected_incremental_kw(
    *, nodes: int, gpu_measured_w: float, cpu_package_measured_w: float
) -> float:
    if nodes not in KAPPA_KW_PER_ACTIVE_H100_NODE:
        raise ValueError("UNMEASURED_DATASET312_NODE_CLASS")
    gpu_idle = nodes * GPU_PER_NODE * GPU_IDLE_W
    cpu_idle = nodes * CPU_SOCKETS_PER_NODE * CPU_SOCKET_IDLE_W
    return (float(gpu_measured_w) - gpu_idle + float(cpu_package_measured_w) - cpu_idle) / 1000.0


def audit_kappa(reproduced: Mapping[int, float], *, tolerance: float = 1e-6) -> dict[str, object]:
    failures = [
        nodes for nodes, expected in KAPPA_KW_PER_ACTIVE_H100_NODE.items()
        if nodes not in reproduced or abs(float(reproduced[nodes]) - expected) > tolerance
    ]
    return {
        "authority_id": AUTHORITY_ID,
        "status": "PASS" if not failures else "FAIL_CORRECTED_KAPPA_MISMATCH",
        "kappa_kw_per_active_h100_node": dict(KAPPA_KW_PER_ACTIVE_H100_NODE),
        "rapl_cpu_domain": "PACKAGE_ONLY",
        "cpu_core_subdomain_role": "DIAGNOSTIC_NOT_ADDED",
        "failed_node_classes": failures,
    }

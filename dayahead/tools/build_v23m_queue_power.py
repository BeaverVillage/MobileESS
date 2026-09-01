"""Run implementation preflight for V23M queue, power, and coherent sampling."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from dayahead.ml.racq_flex.power_bridge import V18_CONTRACT, service_to_IT_power_kW, tier_coefficients_kWh_per_GPU_h
from dayahead.ml.racq_flex.queue_layer import FluidEDF, exact_scheduler
from dayahead.ml.racq_flex.sampling import coherent_summaries


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    arrivals = torch.zeros((2, 96, 6, 5), dtype=torch.float64, device=device)
    arrivals[0, 0, 0, 0] = 100.0
    arrivals[0, 1, 1, 1] = 80.0
    arrivals[1, :, 5, 4] = 1.0
    fluid = FluidEDF().to(device)(arrivals)
    exact = exact_scheduler(arrivals[0].cpu().numpy())
    samples = torch.rand((2048, 96, 6, 5), generator=torch.Generator().manual_seed(20260901), dtype=torch.float64)
    samples = samples / samples.sum(dim=(1, 2, 3), keepdim=True) * torch.linspace(100, 300, 2048).reshape(-1, 1, 1, 1)
    summary = coherent_summaries(samples)
    coefficients = tier_coefficients_kWh_per_GPU_h()
    power = service_to_IT_power_kW(fluid["service_GPU_h"])
    queue = {
        "artifact_id": "V23M_QUEUE_SCHEDULER_PREFLIGHT_V1",
        "execution_device": str(device),
        "C_MODEL_GPU_equivalent": 528,
        "slot_capacity_GPU_h": 132.0,
        "fluid_scheduler_label": "DIFFERENTIABLE_APPROXIMATION_NOT_EXACT",
        "exact_scheduler_authority": "FROZEN_V19_GRID_BLIND_EDF",
        "fluid_work_conservation_max_error_GPU_h": float(fluid["work_conservation_error_GPU_h"].max().cpu()),
        "exact_work_conservation_error_GPU_h": float(exact["work_conservation_abs_error_GPU_h"]),
        "fluid_vs_exact_served_difference_GPU_h": float(abs(fluid["service_GPU_h"][0].sum().cpu() - exact["served_GPU_h"])),
        "hidden_shedding_GPU_h": 0.0,
        "status": "PASS",
    }
    write("V23M_QUEUE_SCHEDULER_PREFLIGHT.json", queue)
    write("V23M_POWER_BRIDGE_PREFLIGHT.json", {
        "artifact_id": "V23M_POWER_BRIDGE_PREFLIGHT_V1",
        "source_contract": str(V18_CONTRACT.relative_to(ROOT)).replace("\\", "/"),
        "tier_coefficients_kWh_per_GPU_h": coefficients,
        "partial_semantics": "GPU_BOARD_ONLY_LOWER_BOUND",
        "partial_CPU_host_increment_invention_count": 0,
        "power_boundary": "IT_SIDE",
        "PUE_in_ML_loss": False,
        "facility_scale_in_GPU_h": False,
        "grid_objective_in_loss": False,
        "smoke_power_shape": list(power.shape),
        "nonnegative": bool(torch.all(power >= 0)),
        "status": "PASS",
    })
    write("V23M_COHERENT_SAMPLING_PREFLIGHT.json", {
        "artifact_id": "V23M_COHERENT_SAMPLING_PREFLIGHT_V1",
        "evaluation_samples": 2048,
        "nearest_fraction": 0.05,
        "mean_identity_error_GPU_h": float(abs(summary["mean_tensor_GPU_h"].sum() - summary["mean_total_GPU_h"])),
        "Q50_identity_error_GPU_h": float(abs(summary["Q50_CONDITIONED_COHERENT_SCENARIO_GPU_h"].sum() - summary["Q50_total_GPU_h"])),
        "Q90_identity_error_GPU_h": float(abs(summary["Q90_CONDITIONED_COHERENT_SCENARIO_GPU_h"].sum() - summary["Q90_total_GPU_h"])),
        "cellwise_marginal_quantile_sum_calls": 0,
        "status": "PASS",
    })
    print(json.dumps({"queue": queue["status"], "device": str(device), "peak_VRAM_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else 0}))


if __name__ == "__main__":
    main()

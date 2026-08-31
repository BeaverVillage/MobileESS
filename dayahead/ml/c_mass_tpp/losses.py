from __future__ import annotations

import numpy as np
import torch
from torch.nn import functional as F

from .mass_head import pinball_loss, tweedie_deviance
from .sinkhorn import deterministic_sinkhorn, monotone_chunked_match


def negative_binomial_nll(target: torch.Tensor, mean: torch.Tensor, dispersion: torch.Tensor) -> torch.Tensor:
    mean = mean.clamp_min(1e-6)
    r = dispersion.clamp_min(1e-6)
    return -(
        torch.lgamma(target + r)
        - torch.lgamma(r)
        - torch.lgamma(target + 1.0)
        + r * (torch.log(r) - torch.log(r + mean))
        + target * (torch.log(mean) - torch.log(r + mean))
    ).mean()


def burst_labels(target: torch.Tensor, p50: float, p90: float) -> torch.Tensor:
    return torch.where(
        target < p50,
        torch.zeros_like(target, dtype=torch.long),
        torch.where(
            target < p90,
            torch.ones_like(target, dtype=torch.long),
            torch.full_like(target, 2, dtype=torch.long),
        ),
    )


def event_set_loss(
    output: dict[str, torch.Tensor],
    actual_time: torch.Tensor,
    actual_tier: torch.Tensor,
    actual_latency: torch.Tensor,
    actual_mass: torch.Tensor,
    sinkhorn_limit: int = 256,
) -> tuple[torch.Tensor, dict[str, float]]:
    n_actual = int(actual_time.numel())
    activity = output["activity_logit"][0]
    count_consistency = (torch.sigmoid(activity).sum() - output["count_mean"][0]).abs()
    if n_actual == 0:
        occurrence = F.binary_cross_entropy_with_logits(activity, torch.zeros_like(activity))
        return occurrence + 0.01 * count_consistency, {
            "matching": "ZERO_EVENT_DAY",
            "matched": 0,
            "ot_cost": 0.0,
        }
    selected = torch.topk(activity, k=min(n_actual, activity.numel()), sorted=False).indices
    ptime = output["arrival_h"][0, selected]
    pmass = output["event_mass_mean"][0, selected]
    ptier = output["tier_logits"][0, selected]
    platency = output["latency_logits"][0, selected]
    if n_actual <= sinkhorn_limit:
        time_cost = torch.abs(ptime[:, None] - actual_time[None, :]) / 24.0
        mass_cost = torch.abs(torch.log1p(pmass[:, None]) - torch.log1p(actual_mass[None, :]))
        tier_cost = -F.log_softmax(ptier, dim=-1)[:, actual_tier]
        latency_cost = -F.log_softmax(platency, dim=-1)[:, actual_latency]
        cost = time_cost + mass_cost + tier_cost + latency_cost
        plan = deterministic_sinkhorn(cost)
        matching_loss = (plan * cost).sum()
        matching_name = "DETERMINISTIC_ENTROPIC_SINKHORN"
    else:
        p_index, a_index = monotone_chunked_match(
            ptime.detach().cpu().numpy(), actual_time.detach().cpu().numpy()
        )
        pi = torch.from_numpy(p_index).long()
        ai = torch.from_numpy(a_index).long()
        matching_loss = (
            torch.abs(ptime[pi] - actual_time[ai]).mean() / 24.0
            + torch.abs(torch.log1p(pmass[pi]) - torch.log1p(actual_mass[ai])).mean()
            + F.cross_entropy(ptier[pi], actual_tier[ai])
            + F.cross_entropy(platency[pi], actual_latency[ai])
        )
        matching_name = "MEMORY_BOUNDED_MONOTONE_1D_OT_WITH_MARK_COST"
    occurrence_target = torch.zeros_like(activity)
    occurrence_target[selected] = 1.0
    occurrence = F.binary_cross_entropy_with_logits(activity, occurrence_target)
    total = matching_loss + 0.05 * occurrence + 0.001 * count_consistency
    return total, {
        "matching": matching_name,
        "matched": n_actual,
        "ot_cost": float(matching_loss.detach()),
    }


def total_loss(
    output: dict[str, torch.Tensor],
    target_mass: torch.Tensor,
    target_count: torch.Tensor,
    target_event_time: torch.Tensor,
    target_event_tier: torch.Tensor,
    target_event_latency: torch.Tensor,
    target_event_mass: torch.Tensor,
    variance_power: float,
    p50: float,
    p90: float,
    use_burst: bool,
    use_event_loss: bool,
) -> tuple[torch.Tensor, dict[str, float | str]]:
    mass = tweedie_deviance(target_mass, output["mean"], variance_power)
    quantile = pinball_loss(target_mass, output["q50"], 0.5) + pinball_loss(
        target_mass, output["q90"], 0.9
    )
    count = negative_binomial_nll(target_count, output["count_mean"], output["count_dispersion"])
    burst = torch.zeros((), dtype=mass.dtype)
    if use_burst:
        burst = F.cross_entropy(output["burst_logits"], burst_labels(target_mass, p50, p90))
    event = torch.zeros((), dtype=mass.dtype)
    event_meta: dict[str, float | str] = {"matching": "DISABLED", "ot_cost": 0.0}
    if use_event_loss:
        event, event_meta = event_set_loss(
            output,
            target_event_time,
            target_event_tier,
            target_event_latency,
            target_event_mass,
        )
    # Fixed preregistered weights, with magnitude normalization for GPU-h heads.
    total = mass + 0.0002 * quantile + 0.05 * burst + 0.05 * event + 0.01 * count
    components: dict[str, float | str] = {
        "mass": float(mass.detach()),
        "quantile": float(quantile.detach()),
        "burst": float(burst.detach()),
        "event": float(event.detach()),
        "count": float(count.detach()),
        **event_meta,
    }
    return total, components


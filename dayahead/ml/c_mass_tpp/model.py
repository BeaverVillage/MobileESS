from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F

from .burst_head import BurstRegimeHead
from .encoder import (
    CausalContinuousTimeEncoder,
    MacroContextEncoder,
    StandardTransformerWindowEncoder,
)
from .mass_head import DailyServiceMassHead
from .set_decoder import ChunkedServiceSetDecoder, hard_mass_reconciliation


@dataclass(frozen=True)
class CMASSTPPConfig:
    event_dim: int = 9
    macro_dim: int = 18
    hidden_dim: int = 24
    query_dim: int = 24
    k_max: int = 10012
    tier_count: int = 6
    latency_count: int = 5
    decoder_chunk_size: int = 512
    mass_scale_GPU_h: float = 528.0 * 24.0
    use_event_encoder: bool = True
    use_burst_head: bool = True
    use_hard_reconciliation: bool = True
    use_power_tier_mark: bool = True
    encoder_type: str = "continuous_time_decay_ssm"
    decoder_type: str = "event_set_kmax"


class CMASSTPP(nn.Module):
    def __init__(self, config: CMASSTPPConfig) -> None:
        super().__init__()
        self.config = config
        self.event_encoder = CausalContinuousTimeEncoder(config.event_dim, config.hidden_dim)
        self.transformer_encoder = StandardTransformerWindowEncoder(
            config.event_dim, config.hidden_dim
        )
        self.macro_encoder = MacroContextEncoder(config.macro_dim, config.hidden_dim)
        context_dim = config.hidden_dim * 2
        self.fusion = nn.Sequential(
            nn.Linear(context_dim, config.hidden_dim),
            nn.SiLU(),
            nn.LayerNorm(config.hidden_dim),
        )
        self.mass_head = DailyServiceMassHead(config.hidden_dim, config.hidden_dim)
        self.burst_head = BurstRegimeHead(config.hidden_dim, config.hidden_dim)
        self.count_mean = nn.Linear(config.hidden_dim, 1)
        self.count_dispersion = nn.Linear(config.hidden_dim, 1)
        decoder_queries = 96 if config.decoder_type == "hierarchical_96_slot" else config.k_max
        self.decoder = ChunkedServiceSetDecoder(
            config.hidden_dim,
            config.query_dim,
            decoder_queries,
            config.tier_count,
            config.latency_count,
            config.decoder_chunk_size,
        )

    def encode(
        self,
        event_features: torch.Tensor,
        event_ages_h: torch.Tensor,
        macro_features: torch.Tensor,
        event_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if macro_features.ndim == 1:
            macro_features = macro_features.unsqueeze(0)
        macro = self.macro_encoder(macro_features)
        if self.config.use_event_encoder:
            if self.config.encoder_type == "standard_transformer_15min_tokens":
                if event_features.ndim == 3 and event_features.shape[0] > 1:
                    event = torch.cat(
                        [
                            self.transformer_encoder(
                                event_features[i][event_mask[i]] if event_mask is not None else event_features[i],
                                event_ages_h[i][event_mask[i]] if event_mask is not None else event_ages_h[i],
                            )
                            for i in range(event_features.shape[0])
                        ],
                        dim=0,
                    )
                else:
                    event = self.transformer_encoder(event_features, event_ages_h)
            else:
                event = self.event_encoder(event_features, event_ages_h, event_mask)
        else:
            event = torch.zeros_like(macro)
        return self.fusion(torch.cat((event, macro), dim=-1))

    def forward_batch(
        self,
        event_features: torch.Tensor,
        event_ages_h: torch.Tensor,
        macro_features: torch.Tensor,
        event_mask: torch.Tensor | None = None,
        decode_events: bool = False,
    ) -> dict[str, torch.Tensor]:
        context = self.encode(event_features, event_ages_h, macro_features, event_mask)
        normalized_mass = self.mass_head(context)
        mass = {
            name: value * self.config.mass_scale_GPU_h
            for name, value in normalized_mass.items()
        }
        burst_logits = self.burst_head(context)
        count_mean = F.softplus(self.count_mean(context)).squeeze(-1)
        count_dispersion = F.softplus(self.count_dispersion(context)).squeeze(-1) + 1e-4
        result: dict[str, torch.Tensor] = {
            "context": context,
            "mean": mass["mean"],
            "q50": mass["q50"],
            "q90": mass["q90"],
            "burst_logits": burst_logits,
            "count_mean": count_mean,
            "count_dispersion": count_dispersion,
        }
        if not decode_events:
            return result
        return self._decode(result, context)

    def _decode(
        self, result: dict[str, torch.Tensor], context: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        decoded = self.decoder(context)
        if not self.config.use_power_tier_mark:
            decoded["tier_logits"] = torch.zeros_like(decoded["tier_logits"])
        result.update(decoded)
        if self.config.use_hard_reconciliation:
            for scenario in ("mean", "q50", "q90"):
                event_mass, alpha = hard_mass_reconciliation(
                    result[scenario], decoded["activity_logit"], decoded["mass_score_raw"]
                )
                result[f"event_mass_{scenario}"] = event_mass
                result[f"alpha_{scenario}"] = alpha
        else:
            independent = F.softplus(decoded["mass_score_raw"])
            result["event_mass_mean"] = independent
            result["event_mass_q50"] = independent
            result["event_mass_q90"] = independent
        return result

    def forward_one(
        self,
        event_features: torch.Tensor,
        event_ages_h: torch.Tensor,
        macro_features: torch.Tensor,
        decode_events: bool = True,
    ) -> dict[str, torch.Tensor]:
        return self.forward_batch(
            event_features,
            event_ages_h,
            macro_features,
            event_mask=None,
            decode_events=decode_events,
        )

    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

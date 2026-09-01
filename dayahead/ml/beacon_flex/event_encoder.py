"""Compact causal TCN event encoder for request-pressure histories."""

from __future__ import annotations

import torch
from torch import nn


class CausalResidualBlock(nn.Module):
    """A left-padded residual TCN block; it cannot access future path positions."""

    def __init__(self, width: int, dilation: int, dropout: float) -> None:
        super().__init__()
        self.pad = 2 * dilation
        self.conv1 = nn.Conv1d(width, width, 3, dilation=dilation)
        self.conv2 = nn.Conv1d(width, width, 3, dilation=dilation)
        self.dropout = nn.Dropout(dropout)
        self.norm1 = nn.GroupNorm(4, width)
        self.norm2 = nn.GroupNorm(4, width)

    def _causal(self, convolution: nn.Conv1d, x: torch.Tensor) -> torch.Tensor:
        return convolution(nn.functional.pad(x, (self.pad, 0)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        x = self.dropout(torch.relu(self.norm1(self._causal(self.conv1, x))))
        x = self.dropout(torch.relu(self.norm2(self._causal(self.conv2, x))))
        return x + residual


class CausalTCNEncoder(nn.Module):
    """Encode a normalized ``[batch,168,12]`` path into a finite latent vector."""

    def __init__(self, width: int = 32, latent: int = 64, explicit_features: int = 14) -> None:
        super().__init__()
        if width not in (32, 64):
            raise ValueError("V25M_ENCODER_WIDTH_NOT_PREREGISTERED")
        self.input_projection = nn.Conv1d(12, width, 1)
        self.blocks = nn.ModuleList([CausalResidualBlock(width, d, .10) for d in (1, 2, 4, 8, 16, 32)])
        self.attention = nn.Conv1d(width, 1, 1)
        pooled = 3 * width + explicit_features
        self.output = nn.Sequential(nn.Linear(pooled, 512), nn.ReLU(), nn.Dropout(.10), nn.Linear(512, latent))

    def forward(self, path: torch.Tensor, explicit: torch.Tensor) -> torch.Tensor:
        x = self.input_projection(path.transpose(1, 2))
        for block in self.blocks:
            x = block(x)
        last = x[:, :, -1]
        maximum = x.amax(dim=-1)
        weight = torch.softmax(self.attention(x).squeeze(1), dim=-1)
        attention = torch.sum(x * weight[:, None, :], dim=-1)
        return self.output(torch.cat((last, attention, maximum, explicit), dim=1))


def parameter_count(model: nn.Module) -> int:
    """Return the number of trainable parameters in an encoder."""

    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


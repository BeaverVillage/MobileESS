from __future__ import annotations

import torch
import subprocess


DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def execution_device_metadata() -> dict[str, object]:
    if DEVICE.type == "cuda":
        properties = torch.cuda.get_device_properties(DEVICE)
        return {
            "execution_device": str(DEVICE),
            "device_name": torch.cuda.get_device_name(DEVICE),
            "cuda_runtime": torch.version.cuda,
            "total_VRAM_bytes": int(properties.total_memory),
            "torch_version": torch.__version__,
        }
    return {
        "execution_device": "cpu",
        "device_name": "CPU",
        "cuda_runtime": torch.version.cuda,
        "total_VRAM_bytes": 0,
        "torch_version": torch.__version__,
    }


def sample_gpu_utilization_percent() -> float | None:
    if DEVICE.type != "cuda":
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits", "-i", "0"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return float(result.stdout.strip().splitlines()[0])
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None

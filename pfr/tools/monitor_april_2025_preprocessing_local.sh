#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
watch_seconds="${1:-10}"
cd "$repo_dir"
exec "$python_bin" -m pfr.tools.show_april_2025_preprocessing_progress \
    --watch-seconds "$watch_seconds"

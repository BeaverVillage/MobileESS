#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$ROOT"
python -m tools.final_campaign.prepare_v28r2_april_sources --gfs-workers 12

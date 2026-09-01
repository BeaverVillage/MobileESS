#!/usr/bin/env bash
set -euo pipefail

REPO='/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v28r2_heavy_backend'
cd "$REPO"
python -m tools.final_campaign.prepare_v28r2_april_sources --gfs-workers 12

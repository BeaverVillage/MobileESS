#!/usr/bin/env bash
set -Eeuo pipefail

# Authoritative name for the electrical-stress calibration campaign.  The old
# B6-named entry point is retained as a compatibility shim for existing notes
# and automation, but both execute the B07 raw-risk source.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec bash "$script_dir/run_january_b6_risk_calibration_local.sh" "$@"

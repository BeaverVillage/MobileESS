#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
python_bin="${PFR_PYTHON:-/home/jaewon/miniconda3/envs/power_v61_gpu/bin/python}"
run_root="${1:-}"
watch_seconds="${2:-10}"
if [[ -z "$run_root" || "$run_root" != /* || $# -gt 2 ]]; then
    echo "Usage: $0 ABSOLUTE_RUN_ROOT [WATCH_SECONDS]" >&2
    exit 64
fi
cd "$repo_dir"
"$python_bin" -m pfr.tools.jfm_isolation --run-root "$run_root" --check >/dev/null
exec "$python_bin" -m pfr.tools.show_january_to_april_progress \
    --run-root "$run_root" --watch-seconds "$watch_seconds"

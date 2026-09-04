#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
AUTHORITY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_WORK="${R12_BASE_WORK:-/home/jaewon/mobile_ess_work}"
REPO="${R12_REPO:-${BASE_WORK}/stage7_final_completion_20260815/repo}"
MOBILITY_CACHE="${R12_MOBILITY_CACHE:-${BASE_WORK}/stage7_r12_common_mobility_cache_2025}"
SOURCE_ROOT="${R12_SOURCE_ROOT:-${BASE_WORK}/stage7_r12_episode_sources_2025}"
RESULT_ROOT="${R12_RESULT_ROOT:-${BASE_WORK}/stage7_r12_results_2025}"
RUNNER="${AUTHORITY_ROOT}/stage7_r12_burnin_runner.py"
ORCHESTRATOR="${AUTHORITY_ROOT}/stage7_r12_orchestrator.py"
LEGACY_RUNNER="${R12_LEGACY_RUNNER:-/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/stage7_final_completion_20260815_work/actual_payload/stage7_r10_long576_actual.py}"
MOBILITY_PY="${R12_MOBILITY_PY:-/home/jaewon/venvs/kestrel_stagek5b3_py312/bin/python}"
CONTROLLER_PY="${R12_CONTROLLER_PY:-/home/jaewon/miniconda3/envs/power_v61/bin/python}"

if [[ -z "$MODE" ]]; then
  echo "usage: $0 {authority|source|canonical|restart|initializer|final-validate}" >&2
  exit 2
fi

cd "$AUTHORITY_ROOT"
sha256sum -c SHA256SUMS.txt
"$CONTROLLER_PY" validate_r12_authority.py
"$CONTROLLER_PY" preflight_r12_common_source.py --base-work "$BASE_WORK" --repo "$REPO"

if [[ "$MODE" == "authority" ]]; then
  exit 0
fi

if [[ "$MODE" == "source" ]]; then
  R12_MOBILITY_PHASE=all bash "$AUTHORITY_ROOT/run_r12_common_mobility_cache.sh"
  "$CONTROLLER_PY" materialize_r12_episode_power_price.py \
    --authority-root "$AUTHORITY_ROOT" \
    --output-root "$SOURCE_ROOT" \
    --base-work "$BASE_WORK"
  exit 0
fi

case "$MODE" in
  canonical|restart|initializer|final-validate) ;;
  *)
    echo "unknown mode: $MODE" >&2
    exit 2
    ;;
esac

"$CONTROLLER_PY" "$ORCHESTRATOR" \
  --mode "$MODE" \
  --runner "$RUNNER" \
  --legacy-runner "$LEGACY_RUNNER" \
  --repo "$REPO" \
  --base-work "$BASE_WORK" \
  --authority-root "$AUTHORITY_ROOT" \
  --source-root "$SOURCE_ROOT" \
  --common-mobility-cache "$MOBILITY_CACHE" \
  --result-root "$RESULT_ROOT" \
  --downloads /mnt/c/Users/kjw39/Downloads \
  --artifact-root "$BASE_WORK/frozen_artifacts" \
  --concurrency 4

if [[ "$MODE" == "final-validate" ]]; then
  echo "R12_STAGE7_FINAL_RESULT=$RESULT_ROOT/R12_STAGE7_FINAL_VALIDATION.json"
fi

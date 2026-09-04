#!/usr/bin/env bash
set -euo pipefail

AUTHORITY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_WORK="${R12_BASE_WORK:-/home/jaewon/mobile_ess_work}"
OUTPUT_ROOT="${R12_MOBILITY_CACHE:-${BASE_WORK}/stage7_r12_common_mobility_cache_2025}"
PYTHON="${R12_MOBILITY_PY:-/home/jaewon/venvs/kestrel_stagek5b3_py312/bin/python}"
LOCK="${BASE_WORK}/locks/stage7_r12_common_mobility_cache.lock"

mkdir -p "$(dirname "$LOCK")" "$OUTPUT_ROOT"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "FAIL_CLOSED: R12 common mobility cache lock is already held" >&2
  exit 2
fi

if pgrep -af 'driver_r25|stage7_r11_monthly_runner|stage7_r12_burnin_runner|gurobi_cl' >/dev/null; then
  echo "FAIL_CLOSED: competing heavy solver process detected" >&2
  pgrep -af 'driver_r25|stage7_r11_monthly_runner|stage7_r12_burnin_runner|gurobi_cl' >&2 || true
  exit 2
fi

available_kib=$(df -Pk "$BASE_WORK" | awk 'NR==2 {print $4}')
required_kib=$((50 * 1024 * 1024))
if (( available_kib < required_kib )); then
  echo "FAIL_CLOSED: at least 50 GiB free is required for the 6,912-issue burn-in cache" >&2
  exit 2
fi

"$PYTHON" "$AUTHORITY_ROOT/validate_r12_authority.py"
"$PYTHON" "$AUTHORITY_ROOT/preflight_r12_common_source.py" \
  --base-work "$BASE_WORK" \
  --repo "$BASE_WORK/stage7_final_completion_20260815/repo"

PHASE="${R12_MOBILITY_PHASE:-all}"
case "$PHASE" in
  all) PHASES=(traffic full) ;;
  traffic|full) PHASES=("$PHASE") ;;
  *) echo "FAIL_CLOSED: invalid R12_MOBILITY_PHASE=$PHASE" >&2; exit 2 ;;
esac

for CURRENT_PHASE in "${PHASES[@]}"; do
  "$PYTHON" "$AUTHORITY_ROOT/materialize_r12_common_mobility_cache.py" \
    --authority-root "$AUTHORITY_ROOT" \
    --output-root "$OUTPUT_ROOT" \
    --base-work "$BASE_WORK" \
    --batch-size 576 \
    --cpu-workers "${R12_SOURCE_CPU_WORKERS:-14}" \
    --phase "$CURRENT_PHASE"
done

echo "R12_COMMON_MOBILITY_OUTPUT=$OUTPUT_ROOT"

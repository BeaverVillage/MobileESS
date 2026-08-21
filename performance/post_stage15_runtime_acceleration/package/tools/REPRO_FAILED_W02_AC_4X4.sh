#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
REPO="/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration"
ROOT="/home/jaewon/mobile_ess_work/frozen_artifacts/B_FIRST6_REP_WEEKS_ACTUAL_CURRENT/W02_2025-01-13"
LOG="/home/jaewon/mobile_ess_work/logs/B_FIRST6_REP_WEEKS_ACTUAL_CURRENT/W02_2025-01-13/AC_RECOVERY_REGRESSION"
mkdir -p "$LOG"
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mapfile -t groups < <("$PY" "$HERE/tools/CPU_AFFINITY_4X4.py" --plain)
slots=(M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE M2_FIXED30_MOBILE M3_EVENT30_NO_LOCAL_REPAIR_MOBILE M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION)
configs=(P1_PROPOSED_EVENT30_LOCAL_REPAIR.json P2_FIXED30.json P3_EVENT30_NO_LOCAL_REPAIR.json M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json)
# Counts end exactly at the previously failed issue; all earlier committed issues are skipped.
counts=(63 80 69 56)
pids=()
for n in 0 1 2 3; do
  taskset -c "${groups[$n]}" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" \
    --repo "$REPO" --config "$HERE/configs/${configs[$n]}" --output "$ROOT/${slots[$n]}" \
    --candidate-id W02_2025-01-13 --benchmark-issues "${counts[$n]}" \
    >"$LOG/${slots[$n]}.log" 2>&1 &
  pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do if ! wait "$pid"; then failed=1; fi; done
(( failed == 0 )) || { echo "AC_FAILURE_REPRO_STATUS=FAIL"; exit 2; }
echo "AC_FAILURE_REPRO_STATUS=PASS_4_OF_4"

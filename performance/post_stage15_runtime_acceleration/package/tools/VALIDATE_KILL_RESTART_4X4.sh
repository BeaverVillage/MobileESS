#!/usr/bin/env bash
set -Eeuo pipefail

# Bounded pre-W02 infrastructure test only.  Four isolated policy processes
# recompute one already-known issue.  M4 is terminated after its transaction
# directory appears but before an atomic commit marker is present; the other
# three processes must finish independently.  M4 is then restarted from the
# preceding committed boundary and must quarantine the interrupted attempt.

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/home/jaewon/miniconda3/envs/power_v61/bin/python
REPO=/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration
SRC_ROOT=/home/jaewon/mobile_ess_work/frozen_artifacts/B_FIRST6_REP_WEEKS_ACTUAL_CURRENT/W02_2025-01-13
DST_ROOT=/home/jaewon/mobile_ess_work/frozen_artifacts/PRE_W02_KILL_RESTART_4X4_CURRENT

slots=(M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE M2_FIXED30_MOBILE M3_EVENT30_NO_LOCAL_REPAIR_MOBILE M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION)
configs=(P1_PROPOSED_EVENT30_LOCAL_REPAIR.json P2_FIXED30.json P3_EVENT30_NO_LOCAL_REPAIR.json M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION.json)
issues=(3520 3537 3526 3517)
counts=(65 82 71 62)

if [[ -e "$DST_ROOT" ]]; then
  mv "$DST_ROOT" "${DST_ROOT}_ARCHIVE_$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$DST_ROOT/logs"

# Hard-link cloning makes the bounded test cheap.  All production writes are
# atomic replacements; source hashes below additionally prove no source file
# was modified through a hard link.
for n in 0 1 2 3; do
  cp -al "$SRC_ROOT/${slots[$n]}" "$DST_ROOT/${slots[$n]}"
  mkdir -p "$DST_ROOT/${slots[$n]}/interrupted_attempts/test_removed"
  mv "$DST_ROOT/${slots[$n]}/engine/issue_$(printf '%06d' "${issues[$n]}")" \
     "$DST_ROOT/${slots[$n]}/interrupted_attempts/test_removed/"
done

"$PY" - "$SRC_ROOT" "$DST_ROOT/SOURCE_HASHES_BEFORE.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
root,out=map(Path,sys.argv[1:])
files=[]
for p in sorted(root.glob("*/engine/issue_*/A_B10_COMMIT_MARKER.json")):
    files.append(p)
for p in sorted(root.glob("*/control/POLICY_RUNTIME_CHECKPOINT.json")):
    files.append(p)
payload={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
PY

export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mapfile -t groups < <("$PY" "$HERE/tools/CPU_AFFINITY_4X4.py" --plain)
pids=()
for n in 0 1 2 3; do
  taskset -c "${groups[$n]}" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" --repo "$REPO" \
    --config "$HERE/configs/${configs[$n]}" --output "$DST_ROOT/${slots[$n]}" \
    --candidate-id W02_2025-01-13 --benchmark-issues "${counts[$n]}" \
    >"$DST_ROOT/logs/${slots[$n]}.log" 2>&1 &
  pids+=("$!")
done

m4_dir="$DST_ROOT/${slots[3]}/engine/issue_$(printf '%06d' "${issues[3]}")"
deadline=$((SECONDS+30))
while [[ $SECONDS -lt $deadline ]]; do
  if [[ -d "$m4_dir" && ! -f "$m4_dir/A_B10_COMMIT_MARKER.json" ]]; then break; fi
  sleep 0.05
done
[[ -d "$m4_dir" && ! -f "$m4_dir/A_B10_COMMIT_MARKER.json" ]] || {
  for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
  echo "KILL_RESTART_4X4_STATUS=FAIL_NO_UNCOMMITTED_WINDOW" >&2
  exit 2
}
kill -TERM "${pids[3]}"
if wait "${pids[3]}"; then
  echo "KILL_RESTART_4X4_STATUS=FAIL_KILLED_CHILD_EXITED_ZERO" >&2
  exit 2
fi

child_failed=0
for n in 0 1 2; do
  if ! wait "${pids[$n]}"; then child_failed=1; fi
done
if ((child_failed)); then
  echo "KILL_RESTART_4X4_STATUS=FAIL_SURVIVING_CHILD" >&2
  exit 2
fi
for n in 0 1 2; do
  test -f "$DST_ROOT/${slots[$n]}/engine/issue_$(printf '%06d' "${issues[$n]}")/A_B10_COMMIT_MARKER.json"
done

# Restart only the interrupted child.  Startup must move the partial issue to
# interrupted_attempts before rebuilding from the preceding committed POST.
taskset -c "${groups[3]}" "$PY" -u "$HERE/runtime/W02_POLICY_EPISODE_RUNNER.py" --repo "$REPO" \
  --config "$HERE/configs/${configs[3]}" --output "$DST_ROOT/${slots[3]}" \
  --candidate-id W02_2025-01-13 --benchmark-issues "${counts[3]}" \
  >"$DST_ROOT/logs/${slots[3]}_restart.log" 2>&1

"$PY" - "$SRC_ROOT" "$DST_ROOT" <<'PY'
import hashlib,json,sys
from pathlib import Path
src,dst=map(Path,sys.argv[1:])
slots=["M1_PROPOSED_EVENT30_LOCAL_REPAIR_MOBILE","M2_FIXED30_MOBILE","M3_EVENT30_NO_LOCAL_REPAIR_MOBILE","M4_FIXED_LOCATION_ESS_MOBILITY_ABLATION"]
issues=[3520,3537,3526,3517]
before=json.loads((dst/"SOURCE_HASHES_BEFORE.json").read_text())
after={k:hashlib.sha256((src/k).read_bytes()).hexdigest() for k in before}
source_unchanged=before==after
rows=[]
for slot,issue in zip(slots,issues):
    d=dst/slot/"engine"/f"issue_{issue:06d}"
    marker=json.loads((d/"A_B10_COMMIT_MARKER.json").read_text())
    audit=json.loads((d/"POLICY_ISSUE_AUDIT.json").read_text())
    rows.append({"slot":slot,"issue":issue,"committed":marker.get("status")=="COMMITTED",
                 "comparison_method_id":audit.get("comparison_method_id"),
                 "output_root":str(dst/slot)})
quarantined=list((dst/slots[3]/"interrupted_attempts").glob("*/issue_003517"))
isolated=len({r["output_root"] for r in rows})==4 and all(r["committed"] for r in rows)
ok=source_unchanged and isolated and bool(quarantined)
evidence={"schema_version":"mobileess.pre_w02.kill_restart_4x4.v1",
          "status":"PASS" if ok else "FAIL_CLOSED","bounded_test_only":True,
          "full_W02_executed":False,"processes":4,"gurobi_threads_per_process":4,
          "killed_slot":slots[3],"killed_issue":issues[3],
          "partial_attempt_quarantined":bool(quarantined),
          "quarantine_paths":[str(p) for p in quarantined],
          "other_children_committed_before_restart":True,
          "isolated_output_roots":isolated,"source_tree_sha_unchanged":source_unchanged,
          "rows":rows}
(dst/"PRE_W02_KILL_RESTART_4X4_EVIDENCE.json").write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n")
raise SystemExit(0 if ok else 2)
PY

echo KILL_RESTART_4X4_STATUS=PASS

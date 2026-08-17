#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="/home/jaewon/mobile_ess_work"
SHARED="$BASE/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT"
LOGROOT="$BASE/logs/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT"
mkdir -p "$SHARED" "$LOGROOT"

PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
AUTH="$SHARED/SHARED_EXOGENOUS_AUTHORITY.json"

# A completed shared source is immutable production authority.  Validate its
# cardinality and referenced source authorities, then reuse it without running
# the GPU/source pipeline or rewriting the authority file.
if [[ -f "$AUTH" ]] && "$PY" - "$SHARED" <<'PY'
import csv,json,sys
from pathlib import Path
r=Path(sys.argv[1]);a=json.loads((r/"SHARED_EXOGENOUS_AUTHORITY.json").read_text())
pa_path=r/"power_price/REP_WEEK_POWER_PRICE_SOURCE_AUTHORITY.json"
if not pa_path.is_file():pa_path=r/"power_price/A_B10_W02_POWER_PRICE_SOURCE_AUTHORITY.json"
pa=json.loads(pa_path.read_text());ma=json.loads((r/"mobility/R12_COMMON_MOBILITY_CACHE_AUTHORITY.json").read_text())
with (r/"mobility/R12_COMMON_MOBILITY_INDEX.csv").open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
same=a.get("same_source_for_all_methods",a.get("same_source_for_all_policies")) is True
ok=(a.get("status")=="PASS" and a.get("candidate_id")=="W02_2025-01-13" and a.get("scored_issue_count")==2016
    and a.get("mobility_source_cache_issues")==2304 and a.get("power_price_source_cache_issues")==2304 and same
    and pa.get("status")=="PASS" and pa.get("scored_issue_count")==2016 and ma.get("status")=="PASS"
    and len(rows)==2304 and [int(x["issue_step"]) for x in rows[:2016]]==list(range(3456,5472))
    and all((r/"mobility"/x["file"]).is_file() for x in rows))
raise SystemExit(0 if ok else 2)
PY
then
  echo "[W02 source] reuse frozen completed shared source"
  echo "W02_SHARED_SOURCE_STATUS=PASS_REUSED"
  echo "W02_SHARED_SOURCE_ROOT=$SHARED"
  exit 0
fi

WORKTREE="$($PY "$HERE/tools/ENSURE_PR4_WORKTREE.py" "$@" | python3 -c 'import sys,json; print(json.load(sys.stdin)["worktree"])')"

echo "[W02 source] PR4 worktree=$WORKTREE"
echo "[W02 source] power/price four 576-step blocks"
$PY -u "$HERE/scripts/PREPARE_W02_POWER_PRICE_SOURCE.py" \
  --repo "$WORKTREE" --output-root "$SHARED/power_price" 2>&1 | tee "$LOGROOT/power_price.log"

# Select a CUDA Python with required frozen traffic dependencies.
GPU_PY="$($PY - <<'PY'
import json,subprocess
from pathlib import Path
c=[Path("/home/jaewon/miniconda3/envs/scats_parser/bin/python3.12"),
   Path("/home/jaewon/miniconda3/envs/scats_parser/bin/python"),
   Path("/home/jaewon/miniconda3/envs/power_v61/bin/python")]
for p in c:
 if not p.is_file():continue
 cp=subprocess.run([str(p),"-c","import torch,numpy,pandas,scipy,sklearn,pyarrow; print(int(torch.cuda.is_available()))"],capture_output=True,text=True)
 if cp.returncode==0 and cp.stdout.strip().endswith("1"):
  print(p);break
else: raise SystemExit("no CUDA-capable Python with frozen mobility dependencies")
PY
)"
echo "[W02 source] mobility CUDA Python=$GPU_PY"

echo "[W02 source] mobility traffic phase: 4 x exact 576-origin contexts"
"$GPU_PY" -u "$HERE/scripts/PREPARE_W02_MOBILITY_SOURCE.py" \
  --repo "$WORKTREE" --output-root "$SHARED/mobility" --phase traffic --cpu-workers 4 \
  2>&1 | tee "$LOGROOT/mobility_traffic.log"

echo "[W02 source] mobility E3/E4 phase"
"$GPU_PY" -u "$HERE/scripts/PREPARE_W02_MOBILITY_SOURCE.py" \
  --repo "$WORKTREE" --output-root "$SHARED/mobility" --phase full --cpu-workers 4 \
  2>&1 | tee "$LOGROOT/mobility_full.log"

python3 - "$SHARED" <<'PY'
import csv,hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1])
pa=json.loads((r/"power_price/A_B10_W02_POWER_PRICE_SOURCE_AUTHORITY.json").read_text())
ma=json.loads((r/"mobility/R12_COMMON_MOBILITY_CACHE_AUTHORITY.json").read_text())
idx=r/"mobility/R12_COMMON_MOBILITY_INDEX.csv"
rows=list(csv.DictReader(idx.open()))
assert pa["status"]=="PASS" and pa["scored_issue_count"]==2016
assert ma["status"]=="PASS"
assert len(rows)==2304
assert [int(x["issue_step"]) for x in rows[:2016]]==list(range(3456,5472))
assert all(str(x["future_actual_target_read"]).lower() in {"false","0"} for x in rows)
h=hashlib.sha256()
for p in sorted(r.rglob("*")):
 if p.is_file():
  h.update(str(p.relative_to(r)).encode()+b"\0")
  h.update(hashlib.sha256(p.read_bytes()).digest())
out={"schema_version":"a_to_b.10.w02.shared_exogenous.v1","status":"PASS",
     "candidate_id":"W02_2025-01-13","scored_issue_first":3456,"scored_issue_last":5471,
     "scored_issue_count":2016,"mobility_source_cache_issues":2304,
     "power_price_source_cache_issues":2304,"same_source_for_all_policies":True,
     "future_actual_used_by_optimizer":False,"source_tree_digest":h.hexdigest()}
(r/"SHARED_EXOGENOUS_AUTHORITY.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print(json.dumps(out,indent=2))
PY
echo "W02_SHARED_SOURCE_STATUS=PASS"
echo "W02_SHARED_SOURCE_ROOT=$SHARED"

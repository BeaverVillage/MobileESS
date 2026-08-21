#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CANDIDATE="${1:?usage: PREPARE_REP_WEEK_SHARED_SOURCES.sh CANDIDATE_ID START_INDEX [WORKTREE]}"
START="${2:?missing START_INDEX}"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
BASE="/home/jaewon/mobile_ess_work"
if [[ "$CANDIDATE" == "W02_2025-01-13" ]]; then
  SHARED="$BASE/frozen_artifacts/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT"
  LOGROOT="$BASE/logs/B_W02_SHARED_EXOGENOUS_SOURCE_CURRENT"
else
  SHARED="$BASE/frozen_artifacts/B_${CANDIDATE}_SHARED_EXOGENOUS_SOURCE_CURRENT"
  LOGROOT="$BASE/logs/B_${CANDIDATE}_SHARED_EXOGENOUS_SOURCE_CURRENT"
fi
mkdir -p "$SHARED" "$LOGROOT"
WORKTREE="${3:-}"
if [[ -z "$WORKTREE" ]]; then
  WORKTREE="$($PY "$HERE/tools/ENSURE_PR4_WORKTREE.py" | python3 -c 'import sys,json; print(json.load(sys.stdin)["worktree"])')"
fi

$PY -u "$HERE/scripts/PREPARE_W02_POWER_PRICE_SOURCE.py" --repo "$WORKTREE" \
  --output-root "$SHARED/power_price" --candidate-id "$CANDIDATE" --start-index "$START" \
  2>&1 | tee "$LOGROOT/power_price.log"

GPU_PY="$($PY - <<'PY'
import subprocess
from pathlib import Path
for p in (Path('/home/jaewon/miniconda3/envs/scats_parser/bin/python3.12'),
          Path('/home/jaewon/miniconda3/envs/scats_parser/bin/python'),
          Path('/home/jaewon/miniconda3/envs/power_v61/bin/python')):
 if not p.is_file(): continue
 cp=subprocess.run([str(p),'-c','import torch,numpy,pandas,scipy,sklearn,pyarrow; print(int(torch.cuda.is_available()))'],capture_output=True,text=True)
 if cp.returncode==0 and cp.stdout.strip().endswith('1'):
  print(p);break
else: raise SystemExit('no CUDA-capable Python with frozen mobility dependencies')
PY
)"
for PHASE in traffic full; do
  "$GPU_PY" -u "$HERE/scripts/PREPARE_W02_MOBILITY_SOURCE.py" --repo "$WORKTREE" \
    --output-root "$SHARED/mobility" --candidate-id "$CANDIDATE" --start-index "$START" \
    --phase "$PHASE" --cpu-workers 4 2>&1 | tee "$LOGROOT/mobility_${PHASE}.log"
done

$PY - "$SHARED" "$CANDIDATE" "$START" <<'PY'
import csv,hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]);candidate=sys.argv[2];start=int(sys.argv[3]);end=start+2015
pa=json.loads((r/'power_price/REP_WEEK_POWER_PRICE_SOURCE_AUTHORITY.json').read_text())
ma=json.loads((r/'mobility/R12_COMMON_MOBILITY_CACHE_AUTHORITY.json').read_text())
rows=list(csv.DictReader((r/'mobility/R12_COMMON_MOBILITY_INDEX.csv').open()))
assert pa['status']=='PASS' and pa['candidate_id']==candidate and pa['scored_issue_first']==start
assert ma['status']=='PASS' and len(rows)==2304
assert [int(x['issue_step']) for x in rows[:2016]]==list(range(start,end+1))
assert all(str(x['future_actual_target_read']).lower() in {'false','0'} for x in rows)
h=hashlib.sha256()
for p in sorted(r.rglob('*')):
 if p.is_file() and p.name!='SHARED_EXOGENOUS_AUTHORITY.json':
  h.update(str(p.relative_to(r)).encode()+b'\0');h.update(hashlib.sha256(p.read_bytes()).digest())
out={'schema_version':'mobileess.post_stage15.rep_week.shared_exogenous.v2','status':'PASS',
     'candidate_id':candidate,'scored_issue_first':start,'scored_issue_last':end,
     'scored_issue_count':2016,'mobility_source_cache_issues':2304,
     'power_price_source_cache_issues':2304,'same_source_for_all_methods':True,
     'future_actual_used_by_optimizer':False,'source_tree_digest':h.hexdigest()}
(r/'SHARED_EXOGENOUS_AUTHORITY.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps(out,indent=2))
PY
echo "REP_WEEK_SHARED_SOURCE_STATUS=PASS candidate=$CANDIDATE"

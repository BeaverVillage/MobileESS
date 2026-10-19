"""Count repeated physical trajectory identities in already durable probes."""
from pathlib import Path
import collections
import json
import re
import sys

root=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/AC_AUDIT/svr11_revision01/AC_PROBES/2025-05-01/B3')
paths=sorted((p for p in root.iterdir() if p.is_dir() and not p.name.endswith('_REFERENCE')),key=lambda p:p.stat().st_mtime)
paths=[p for p in paths if p.stat().st_mtime>=1792213334]
counts=collections.Counter();sequence=[];missing=0
for path in paths:
    files=list(path.glob('*SLOTS.json'))
    if not files:
        missing+=1;continue
    with files[0].open('rb') as stream:
        data=stream.read(8192)
    match=re.search(rb'"frozen_trajectory_SHA":"([a-f0-9]+)"',data)
    if match:
        key=match.group(1).decode();counts[key]+=1;sequence.append(key)
result=dict(read=len(sequence),missing=missing,unique_trajectories=len(counts),duplicate_probes=len(sequence)-len(counts),most_common=counts.most_common(8))
result['scope']='Physical trajectories only; does not establish full input cache equivalence across changing observations.'
Path(sys.argv[1]).write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))

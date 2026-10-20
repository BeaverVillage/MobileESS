import v44_recovery_r044
from pathlib import Path
from collections import Counter
from v44.common import read,record,atomic,now
from v44_week2 import operations as week
from v44 import inputs
import json

with week.bindings():
    state=read(week.STATE);rows=[]
    for day in week.DAYS:
        checked=inputs.inspect_day(day)
        native=read(checked['files']['native']['path']);reference=read(native['reference']['path'])
        known={r['job_uid']:r for r in native['known_population']};old={r['job_uid']:r for r in reference}
        bundle=read(checked['files']['planning_input']['path'])
        extras=sorted(set(old)-set(known));missing=sorted(set(known)-set(old))
        row=dict(day=day,status=checked['status'],blockers=checked['blockers'],known=len(known),reference=len(old),
            extra_reference=[dict(reference=old[u],uid=u) for u in extras],missing_reference=missing,
            input_files={k:checked['files'][k] for k in ('native','windows','planning_input','actual_input','provenance','R0_reference','traffic_forecast','electrical','initial_running_authority','initial_MESS_authority','request_descriptors')})
        row['extra_plan_rows']=[r for r in bundle.get('known_population',[]) if r['job_uid'] in extras]
        rows.append(row)
        print(json.dumps({k:v for k,v in row.items() if k!='input_files'},ensure_ascii=False))
    jobs=[]
    for j in state['jobs']:
        root=Path(j['case_root']);handoff=root/'PRE_ACTUAL_READY.json'
        stages=[]
        for s in ('A1','M1','A2','M2'):
            p=root/s/'RESULT.json'
            if p.exists():
                r=read(p);stages.append(dict(stage=s,PASS=r.get('PASS'),status=r.get('status'),error=r.get('error')))
        jobs.append(dict(day=j['day'],arm=j['arm'],status=j['status'],case_root=str(root),
            started=(root/'START.json').exists(),actual_started=(root/'ACTUAL_START.json').exists(),
            actual_folder=(root/'ACTUAL').exists(),handoff=record(handoff) if handoff.exists() else None,stages=stages))
    audit=dict(UTC=now(),days=rows,jobs=jobs,counts=dict(Counter(j['status'] for j in jobs)))
    atomic(week.OPS/'R045_DATE_AND_FAILURE_AUDIT.json',audit)
    print(json.dumps(dict(counts=audit['counts'],jobs=jobs),ensure_ascii=False,indent=2))

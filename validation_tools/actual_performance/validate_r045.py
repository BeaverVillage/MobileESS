import v44_recovery_r045
from pathlib import Path
import json
import numpy as np
import pytest
from v44_recovery_r045 import operations as op
from v44_recovery_r045.reference import project,roster
from v44.common import read,record,verify,atomic,now
from v44.config import axis

with op.week.bindings():
    audit=read(op.OPS/'R045_DATE_AND_FAILURE_AUDIT.json');state=read(op.STATE);rows=[];plans=[]
    for day in op.week.DAYS:
        proof=next(j for j in audit['days'] if j['day']==day)
        assert not proof['blockers'];verify(list(proof['input_files'].values()))
        native=read(proof['input_files']['native']['path']);windows=read(proof['input_files']['windows']['path'])
        known={r['job_uid'] for r in native['known_population']};windowids={r['job_id'] for r in windows}
        eligible={r['job_uid'] for r in native['known_population'] if r['planning_eligible']}
        assert eligible==windowids,(day,'WINDOWS_ELIGIBLE_ROSTER',len(eligible),len(windowids))
        sites,caps,known_gpu,anon,selected,service,carry,conservation=project(native)
        assert conservation['PASS'],(day,conservation)
        assert np.isfinite(known_gpu).all() and np.isfinite(anon).all()
        requests=[]
        for job in [j for j in state['jobs'] if j['day']==day]:
            request=read(job['prepare_request']);assert (request['day'],request['arm'])==op.seq.key(job)
            assert request['axis']==axis(day)
            assert any(r['sha256']==proof['input_files']['native']['sha256'] for r in request['sources'])
            root=Path(job['case_root']);handoff=root/'PRE_ACTUAL_READY.json';reuse=handoff.exists()
            if reuse:
                from v44_recovery_r038.phases import load_handoff
                checked=dict(request,R038_pre_actual_handoff=record(handoff));load_handoff(checked)
                target=root
            else:
                attempts=list(root.parent.glob('attempt[0-9][0-9][0-9]'))
                target=root.parent/f"attempt{max(int(p.name[-3:]) for p in attempts)+1:03d}"
                assert not target.exists()
            plans.append(dict(day=day,arm=job['arm'],case_root=str(target),reuse_prepared=reuse,
                original_request=job['prepare_request'],original_case_root=str(root)))
            requests.append(dict(arm=job['arm'],request=record(job['prepare_request']),axis_matches=True,native_SHA_matches=True))
        rows.append(dict(day=day,PASS=True,known_UIDs=len(known),planning_eligible_UIDs=len(eligible),windows_UIDs=len(windowids),
            baseline_conservation=conservation,requests=requests,input_files=proof['input_files']))
        print(json.dumps(dict(day=day,PASS=True,known=len(known),baseline_PASS=True,requests=4)))
    code=pytest.main(['-q','-p','no:cacheprovider','tests/test_v44_recovery_r045.py','tests/test_v44_recovery_r044.py',
        'tests/test_v44_week2_dispatch.py','tests/test_v44_week2_sequence.py','--junitxml='+str(op.OPS/'R045_REGRESSION.xml')])
    if code:raise SystemExit(code)
    atomic(op.VALIDATION,dict(PASS=True,UTC=now(),Native_calls=0,days=rows,all_28_request_date_and_input_joins_PASS=True,
        baseline_reference_projection_all_seven_days_PASS=True,prepared_handoffs_preserved=sum(p['reuse_prepared'] for p in plans),
        regression=record(op.OPS/'R045_REGRESSION.xml'),sources=op.sources()))
    atomic(op.OPS/'R045_RESTART_PLAN.json',dict(UTC=now(),plan=plans))
    print(json.dumps(dict(PASS=True,requests=len(plans),reuse_prepared=sum(p['reuse_prepared'] for p in plans))))

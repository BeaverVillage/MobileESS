"""Preserve live Source32 identities and Native prefixes before future repair enqueue."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,psutil
R=Path('D:/v42_may_restart_20261010_02');A=R/'autonomous'
def read(p):return json.loads(p.read_bytes())
def record(p):
    raw=p.read_bytes();return dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
cp=read(R/'SUPERVISOR_STATE.json');rows={}
for key,w in cp['workers'].items():
    p=psutil.Process(w['PID']);actual=dict(PID=p.pid,created=p.create_time(),command=p.cmdline(),cwd=p.cwd())
    assert actual['created']==w['created'] and actual['command']==w['command']
    assert Path(actual['cwd']).resolve()==Path('D:/v42run32')
    rp=Path(w['request']);req=read(rp)
    assert req['implementation_SHA']=='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'
    lp=rp.parent/'NATIVE_RUNTIME_LEDGER.json';raw=lp.read_bytes();ledger=json.loads(raw)
    target=A/('SOURCE35_PRE_ENQUEUE_'+key.replace('/','_')+'_NATIVE.json')
    assert not target.exists();target.write_bytes(raw)
    assert ledger['P2_calls']==0 and ledger['Native_ceiling_seconds']==5400
    rows[key]=dict(worker=w,actual_process=actual,request=record(rp),ledger_snapshot=record(target),
        original_ledger=str(lp),measured_Native_Runtime=ledger['measured_Native_Runtime'],completed_calls=len(ledger['calls']))
assert set(rows)=={'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}
sp=read(R/'SUPERVISOR_PROCESS.json');p=psutil.Process(sp['PID'])
assert p.create_time()==sp['created'] and p.cmdline()==sp['command']
doc=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),source32_workers=rows,
    supervisor=sp,Native_optimize_calls=0,model_constructions=0,scientific_worker_changes=0,
    source35_deployment_pending=True,final_science_PASS_not_claimed=True)
target=A/'SOURCE35_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json';assert not target.exists()
target.write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,receipt=record(target))))

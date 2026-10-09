"""Read-only snapshots of future immutable workers and actual Native entry."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,time,psutil
parser=argparse.ArgumentParser();parser.add_argument('--source',required=True)
parser.add_argument('--code-root',required=True);args=parser.parse_args()
ROOT=Path('D:/v42_may_restart_20261010_02');CODE=Path(args.code_root).resolve()
OUT=ROOT/'autonomous/source35_actual_watch';OUT.mkdir(exist_ok=True)
DAYS=('2025-05-01','2025-05-02','2025-05-03');seen=set()
def read(path):return json.loads(Path(path).read_bytes())
def seal(event,day,files,details):
    key=(event,day)
    if key in seen:return
    folder=OUT/(day+'_'+event+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    folder.mkdir();records=[]
    for path,raw in files:
        path=Path(path);target=folder/path.name
        assert not target.exists();target.write_bytes(raw)
        records.append(dict(original_path=str(path),path=str(target),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    doc=dict(schema='V42_SOURCE35_ACTUAL_READONLY_EVENT',event=event,day=day,
        UTC=datetime.now(timezone.utc).isoformat(),source_SHA=args.source,details=details,files=records,
        Native_optimize_calls=0,model_constructions=0,scientific_worker_changes=0,queue_changes=0,
        final_scientific_PASS_not_inferred=True)
    target=folder/'OBSERVATION.json';target.write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
    seen.add(key);print(json.dumps(dict(event=event,day=day,receipt=str(target))),flush=True)
print(json.dumps(dict(status='WATCHING_FUTURE_SOURCE35_FIRST3',source_SHA=args.source)),flush=True)
while True:
    try:cp=read(ROOT/'SUPERVISOR_STATE.json')
    except (FileNotFoundError,PermissionError):
        # Windows atomic replacement can briefly deny this read-only open.
        # Defer observations; never substitute an empty checkpoint/Native0.
        time.sleep(.25);continue
    for day in DAYS:
        worker=cp.get('workers',{}).get('B2/'+day)
        if not worker or worker.get('source_SHA')!=args.source:continue
        try:
            process=psutil.Process(worker['PID'])
            assert abs(process.create_time()-worker['created'])<.001
            actual_command=process.cmdline();actual_cwd=process.cwd()
            if actual_command!=worker['command'] or Path(actual_cwd).resolve()!=CODE:
                # A process-start observation can be incomplete on Windows.
                # Preserve the mismatch and defer; do not admit this identity.
                seal('DEFERRED_PROCESS_IDENTITY_MISMATCH',day,[],dict(worker=worker,
                    actual_command=actual_command,actual_cwd=actual_cwd,
                    identity_admitted=False,requires_later_exact_reobservation=True))
                continue
            request_path=Path(worker['request']);request_raw=request_path.read_bytes();request=json.loads(request_raw)
            assert request['implementation_SHA']==args.source and request['restart_from_zero'] is True and request['previous_attempts']==[]
            fixed=[(request_path,request_raw)]
            seal('PROCESS_ENTERED',day,fixed,dict(worker=worker,fresh_request=True))
            ledger_path=request_path.parent/'NATIVE_RUNTIME_LEDGER.json'
            ledger_raw=ledger_path.read_bytes() if ledger_path.exists() else None
            if ledger_raw is not None:
                ledger=json.loads(ledger_raw)
                assert ledger['P2_calls']==0 and ledger['Native_ceiling_seconds']==5400
                if ledger['measured_Native_Runtime']==0 and ledger['calls']==[] and ledger.get('inflight') is None:
                    assert ledger['historical_costs_reused'] is False and not ledger.get('prior_attempt')
                    seal('ACTUAL_NATIVE_ZERO_BIRTH_LEDGER',day,fixed+[(ledger_path,ledger_raw)],
                        dict(worker=worker,measured_Native_Runtime=0,Native_ceiling_seconds=5400))
                if ledger.get('calls'):
                    seal('ACTUAL_FIRST_COMPLETED_NATIVE_CALL',day,fixed+[(ledger_path,ledger_raw)],
                        dict(worker=worker,first_call=ledger['calls'][0],measured_Native_Runtime=ledger['measured_Native_Runtime']))
            output=Path(request['output'])
            entries=[('FULL_LP',output/'F1_FULL_LP_COMPUTATIONAL_ENTRY.json')]
            entries += [('RMP',path) for path in output.glob('*/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json')]
            for kind,path in entries:
                if not path.exists():continue
                raw=path.read_bytes();entry=json.loads(raw)
                files=fixed+[(path,raw)]+([] if ledger_raw is None else [(ledger_path,ledger_raw)])
                seal(kind+'_COMPUTATIONAL_ENTRY_OBSERVED',day,files,dict(worker=worker,entry=entry))
                if entry.get('status')=='COMPLETED':
                    seal(kind+'_COMPUTATIONAL_ENTRY_COMPLETED',day,files,dict(worker=worker,entry=entry))
            for price_path in sorted(output.glob('*/CURRENT_F1_COMPUTATIONAL_PRICE_SEED.json')):
                price_raw=price_path.read_bytes();price_entry=json.loads(price_raw)
                assert price_entry['method'] in ('L1','L4') and price_entry['PASS'] is True
                seal('ACTUAL_PRICE_SEED_'+price_entry['method'],day,
                    fixed+[(price_path,price_raw)]+([] if ledger_raw is None else [(ledger_path,ledger_raw)]),
                    dict(worker=worker,entry=price_entry,seed_entry_is_not_Global_LB_or_final_PASS=True))
            reuse=sorted(output.glob('*/CURRENT_ATTEMPT_PROJECTION_REUSE_RECEIPT.json'))
            if reuse:
                path=reuse[0];raw=path.read_bytes();entry=json.loads(raw)
                seal('ACTUAL_CURRENT_ATTEMPT_PROJECTION_REUSE',day,fixed+[(path,raw)],dict(worker=worker,entry=entry))
        except (FileNotFoundError,PermissionError,psutil.NoSuchProcess,psutil.AccessDenied):
            continue
    time.sleep(2)

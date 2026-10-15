"""Append-only post-stop receipt, immutable raw pins and executed source blobs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record
from v42_integration.table_v_status import classify_a_result


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write(path,value):
    with path.open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write('\n')


def audit(source,output):
    import psutil
    source,output=source.resolve(),output.resolve()
    if output.exists():raise FileExistsError('APPEND_ONLY_STOP_AUDIT')
    ledger=read(source/'PLANNING_NATIVE_LEDGER.json')
    if ledger.get('inflight') or ledger.get('active_stage_context'):
        raise RuntimeError('NATIVE_OR_STAGE_STILL_ACTIVE')
    if Path(ledger['worker_lock_path']).exists():raise RuntimeError('HEAVY_WORKER_LOCK_STILL_PRESENT')
    workers=[]
    for process in psutil.process_iter(['pid','cmdline']):
        try:
            command=process.info['cmdline'] or []
            if any(Path(x).name=='run_v42_table_v.py' for x in command):
                workers.append(process.info)
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    if workers:raise RuntimeError('TABLE_V_WORKER_STILL_RUNNING')
    output.mkdir(parents=True)
    snapshots=output/'SOURCES';snapshots.mkdir()
    frozen=read(source/'EXECUTION_SOURCE_FREEZE.json')
    preserved=[]
    for index,record in enumerate(frozen['files']):
        original=Path(record['path'])
        relative=original.relative_to(ROOT).as_posix()
        candidates=subprocess.check_output(['git','log','--all','--format=%H','--',relative],cwd=ROOT).decode().splitlines()
        found=None
        for revision in candidates:
            blob=subprocess.check_output(['git','show',revision+':'+relative],cwd=ROOT)
            if hashlib.sha256(blob).hexdigest()==record['sha256']:
                target=snapshots/(str(index).zfill(2)+'_'+original.name)
                target.write_bytes(blob)
                found=dict(original=record,snapshot=file_record(target),git_revision=revision)
                break
        if found is None:
            raise ValueError('EXECUTED_SOURCE_BLOB_NOT_RECOVERED:'+relative)
        preserved.append(found)
    result=read(source/'B1/A1/P1_ONLY_RESULT.json')
    native=[r for r in ledger['calls'] if r.get('solver')=='GUROBI'
            and r.get('stage_context',{}).get('arm')=='B1' and r.get('stage_context',{}).get('stage')=='A1']
    used=sum(r['Native_Runtime'] for r in native)
    raw=[file_record(p) for p in sorted(source.rglob('*')) if p.is_file()
         and not p.is_relative_to(source/'USER_STOP_20261015')]
    copied=[]
    for name in ['PLANNING_NATIVE_LEDGER.json','K48_NATIVE_LEDGER.json','EXECUTION_SOURCE_FREEZE.json',
                 'B1/ARM_OUTCOME.json','B1/A1/P1_ONLY_RESULT.json','B0/ARM_OUTCOME.json',
                 'B0/ACTUAL_RESULT.json','B0/FRESH_AC_RESULT.json','CAMPAIGN_STOP_REQUEST.json']:
        p=source/name
        if p.is_file():
            target=output/('AS_OF_'+name.replace('/','__'))
            target.write_bytes(p.read_bytes())
            copied.append(dict(original=file_record(p),snapshot=file_record(target)))
    call=result.get('Native_call') or {}
    record=dict(schema='PR230_USER_REQUESTED_NORMAL_SOLVER_INTERRUPTION_V1',
        observed_UTC=datetime.now(timezone.utc).isoformat(),source_root=str(source),
        method='WINDOWS_CONSOLE_CTRL_C_GUROBI_NORMAL_RETURN',heavy_workers=workers,
        final_status=classify_a_result(result),Gurobi_Status=call.get('status'),
        SolCount=0 if not result.get('FULL_feasible') and result.get('objective') is None else result.get('SolCount'),
        objective=result.get('objective'),native_matrix_bound=result.get('bound'),
        native_matrix_bound_is_DW_pricing_certificate=False,DW_Global_LB=None,FULL_feasible_UB=None,Global_Gap=None,
        final_call_Native_seconds=call.get('Native_Runtime'),B1_A1_cumulative_Native_seconds=used,
        B1_A1_remaining_approved_Native_seconds=max(0.,5400.-used),
        P2_calls=0,Native_usage_reset=False,raw_results_rewritten=False,
        original_source_case=call.get('stage_context'),native_binding=call.get('native_binding'),
        inflight=None,active_stage_context=None,worker_lock_released=True,
        preserved_source_blobs=preserved,snapshots=copied,immutable_raw_records=raw)
    write(output/'STOP_COMPLETION.json',record)
    print(json.dumps({k:record[k] for k in ('final_status','Gurobi_Status','final_call_Native_seconds',
        'B1_A1_cumulative_Native_seconds','B1_A1_remaining_approved_Native_seconds','worker_lock_released')},indent=2))
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.source,a.output)

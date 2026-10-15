"""Prepare an explicit Git path list without staging live simulation output."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'

def main():
    out=BASE/'RC04/TABLE_V/PR_CHECKPOINT01';out.mkdir(parents=True,exist_ok=True)
    if (out/'CHECKPOINT_NATIVE_SNAPSHOTS.json').exists():raise FileExistsError('CHECKPOINT_MUST_NOT_RESET')
    snapshots=[]
    for name in ('PLANNING_NATIVE_LEDGER.json','K48_NATIVE_LEDGER.json'):
        source=BASE/'RC04/TABLE_V/EXECUTION01'/name
        destination=out/('AS_OF_'+name)
        destination.write_bytes(source.read_bytes())
        snapshots.append(dict(live_path=str(source),snapshot=file_record(destination),
            mutable_live_ledger_not_staged=True))
    _write(out/'CHECKPOINT_NATIVE_SNAPSHOTS.json',dict(UTC=datetime.now(timezone.utc).isoformat(),
        snapshots=snapshots,Native_budget_reset=False,all_four_arms_complete=False,
        current_scope='B0_CURRENT_FULL96_PASS_B1_A1_NATIVE_IN_PROGRESS_B2_B3_WAITING'))
    packages=json.loads((BASE/'RC03/EVIDENCE_DELIVERY/COMPRESSED_EVIDENCE_MANIFEST.json').read_text(encoding='utf8'))
    excluded=set(packages['git_plain_large_raw_excluded'])
    files=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z','tools','tests','v42_integration',
        str(BASE.relative_to(ROOT)).replace('\\','/')],cwd=ROOT).decode('utf8').split('\0')
    selected=['.gitattributes'];live_excluded=[]
    prefix=BASE.relative_to(ROOT).as_posix()+'/'
    for path in files:
        if not path:continue
        if path in excluded:continue
        if path.startswith(prefix):
            relative=path[len(prefix):]
            if not relative.startswith(('RC02/','RC03/','RC04/')):continue
            if (relative.startswith(('RC04/TABLE_V/EXECUTION01/B1/','RC04/TABLE_V/EXECUTION01/B2/','RC04/TABLE_V/EXECUTION01/B3/'))
                    or relative in ('RC04/TABLE_V/EXECUTION01/PLANNING_NATIVE_LEDGER.json','RC04/TABLE_V/EXECUTION01/K48_NATIVE_LEDGER.json')):
                live_excluded.append(path);continue
        elif not path.startswith(('tools/','tests/','v42_integration/')):continue
        if (ROOT/path).stat().st_size>=100_000_000:raise ValueError('LARGE_FILE_REQUIRES_LOSSLESS_PACKAGE:'+path)
        selected.append(path)
    selected=sorted(set(selected))
    # Include this staging receipt itself after it is saved.
    receipt=out/'GIT_PATH_SELECTION.json'
    selected.extend([receipt.relative_to(ROOT).as_posix(),(out/'GIT_PATHS.nul').relative_to(ROOT).as_posix()])
    selected=sorted(set(selected))
    _write(receipt,dict(selected_paths=selected,live_outputs_excluded=live_excluded,
        packaged_large_raw_excluded=sorted(excluded),unrelated_historical_files_excluded=True,
        Native_workers_touched=0,Raw_originals_deleted=False))
    (out/'GIT_PATHS.nul').write_bytes(b''.join(p.encode('utf8')+b'\0' for p in selected))
    print(json.dumps(dict(selected_files=len(selected),live_outputs_excluded=len(live_excluded),
        packaged_raw_files=len(excluded),pathspec=str(out/'GIT_PATHS.nul'))),flush=True)

if __name__=='__main__':main()

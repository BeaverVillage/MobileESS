"""Recover archive-only failure with zero numerical replay or DA recompute."""
import time, shutil, tempfile
from pathlib import Path
from fast_prepare import ROOT, read, record
from dayahead.paper_analysis.storage import write_json
from v41r4_loop_runtime import MAY_RUN, MAY_OUT, LOGS, install_reports
from dayahead.v41 import scientific_archive as archive
from dayahead.v40h.identity import verify_manifest as verify_source
from mission_loop_archive import install, check_path

def main():
    day='2025-05-02';policy='B0';root=MAY_RUN/day/policy
    evidence=MAY_OUT/'mission/ARCHIVE_JUNCTION_REPAIR';evidence.mkdir(parents=True,exist_ok=True)
    state=read(MAY_RUN/'campaign_progress.json')
    assert state['status']=='FAIL_CLOSED' and not state['active']
    import psutil
    assert not psutil.pid_exists(state['supervisor_pid']), 'SUPERVISOR_STILL_ALIVE'
    phase=MAY_OUT/day/'PHASE_B0_AC.json';failure=read(phase)
    assert failure['status']=='FAIL_CLOSED' and 'not in the subpath' in failure['traceback']
    for p in (phase,LOGS/day/'B0_AC.log',MAY_RUN/'campaign_progress.json',MAY_RUN/'CAMPAIGN_FINISHED.json',root/'UNIT_SCIENTIFIC_MANIFEST.json'):
        shutil.copy2(p,evidence/p.name)
    try: archive.verify_manifest(root/'UNIT_SCIENTIFIC_MANIFEST.json')
    except ValueError: pass
    else: raise AssertionError('ORIGINAL_FAILURE_NOT_REPRODUCED')
    install()
    archive.verify_manifest(root/'UNIT_SCIENTIFIC_MANIFEST.json')
    for stage in ('dayahead','actual'):
        archive.verify_manifest(root/stage/'SCIENTIFIC_MANIFEST.json')
        r=read(root/stage/(stage.upper()+'_RECEIPT.json'))
        assert r['status']=='COMPLETE'
        verify_source(r['science'])
        assert all(record(x['path'])==x for x in r['files'].values())
    ac=read(root/'actual/ACTUAL_RECEIPT.json')
    assert ac['day_ahead']==record(root/'dayahead/DAYAHEAD_RECEIPT.json')
    assert read(root/'actual/authority/COMMON_INPUT_IDENTITY.json')==read(root/'dayahead/authority/COMMON_INPUT_IDENTITY.json')
    tests=[]
    for p in (root/'dayahead/../../B1/dayahead/DAYAHEAD_RECEIPT.json',root/'actual/../../../../outside.json'):
        try:check_path(p,root)
        except (ValueError,AssertionError):tests.append('TRAVERSAL_REJECTED')
        else:raise AssertionError('TRAVERSAL_ACCEPTED')
    # Exercise unchanged hash/schema readback using a disposable local fixture.
    with tempfile.TemporaryDirectory(prefix='v41_archive_test_') as directory:
        t=Path(directory);f=t/'data.json';f.write_text('{"value":1}')
        entry=archive.artifact_entry(f,t,'actual')
        m=t/'SCIENTIFIC_MANIFEST.json'
        write_json(m,dict(schema=archive.SCHEMA,status='PASS',artifacts=[entry]))
        archive.verify_manifest(m)
        f.write_text('{"value":2}')
        try:archive.verify_manifest(m)
        except (ValueError,AssertionError,RuntimeError):tests.append('HASH_DRIFT_REJECTED')
        else:raise AssertionError('HASH_DRIFT_ACCEPTED')
    install_reports()
    from v41r4_report import accept_actual
    result=accept_actual(day,policy)
    preserved=MAY_OUT/'mission'/f'PRESERVED_PHASE_{day}_{policy}_AC_FAILURE.json'
    assert not preserved.exists();shutil.copy2(phase,preserved)
    repair=dict(status='PASS',root_cause='Retained DA junction resolves outside new unit root; numerical Actual already COMPLETE',
        tests=tests,actual_receipt_unchanged=record(root/'actual/ACTUAL_RECEIPT.json'),
        numerical_replays=0,DA_recomputations=0,science_changed=False,
        adapter=record(ROOT/'mission_loop_archive.py'),launcher=record(ROOT/'mission_loop_resume.py'),recovered_at=time.time())
    write_json(evidence/'REPAIR.json',repair)
    write_json(phase,dict(status='PASS',day=day,phase='B0_AC',started_at=failure['started_at'],completed_at=time.time(),
        elapsed_seconds=time.time()-failure['started_at'],result=result,budget_version='FIXED_1800_LOOP_WALL_CLOCK',
        automatic_repeat=False,retry_count=1,recovery=record(evidence/'REPAIR.json')))
    print(repair,flush=True)

if __name__=='__main__':main()

"""Freeze final evidence without starting or replacing the Full May release."""
import shutil
from pathlib import Path
import psutil
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import ROOT,record
from dayahead.v41.execution import science,commit
from .first_replay import OUT
from .flex_diagnostic import OUT as DIAG,RUNTIME

def run(tag='first02'):
    root=RUNTIME/'fa'/tag;result=read(root/'ACCEPTANCE_RESULT.json')
    assert result['status']=='PASS' and result['source']==science()
    diagnostic=read(DIAG/'DIAGNOSTIC_FREEZE.json')
    for ref in diagnostic['files']:assert record(ref['path'])==ref,ref['path']
    for ref in result['artifacts'].values():assert record(ref['path'])==ref
    rows=[]
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid==psutil.Process().pid:continue
        command=' '.join(p.info.get('cmdline') or [])
        if (p.info.get('name') or '').lower().startswith('python') and any(key in command for key in
            ('dayahead.v41r1.fo_acceptance','dayahead.v41r1.campaign_run','dayahead.v41r1.watchdog','dayahead.v41r1.flex_','dayahead.v41r1.first_regression')):
            rows.append(dict(pid=p.pid,command=command))
    assert not rows,rows
    release=RUNTIME/'FULL_MAY_FROZEN_RELEASE.json'
    write_json(OUT/'FULL_MAY_HOLD_AND_STOP.json',dict(status='STOPPED_ON_USER_HOLD',active_task_workers=rows,
        Full_May_started=False,previous_campaign_release=record(release),
        previous_release_not_replaced=True,current_source=science(),git_HEAD=commit(),
        code_frozen_by_manifest=True,working_tree_validation=True,
        full_May_ready=False,reason='May-04 acceptance only; no 31-day/B3 release requalification or new campaign release in this task.'))
    paths=[Path(r['path']) for r in science()['files']]
    paths+=list((ROOT/'dayahead/v41r1').glob('first_*.py'))
    paths+=[ROOT/'dayahead/v41r1/fo_acceptance.py',ROOT/'tests/dayahead/test_v41r1_first_improvement.py']
    for p in paths:
        target=OUT/'source'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(p,target)
        assert record(p)['sha256']==record(target)['sha256']
    frozen=OUT/'V41R1_FIRST_IMPROVEMENT_FREEZE.json'
    if frozen.exists():raise RuntimeError('PRESERVE_FIRST_IMPROVEMENT_FREEZE')
    files=[]
    for directory in (OUT,root,RUNTIME/'fa/first01'):
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p!=frozen:files.append(record(p))
    write_json(frozen,dict(status='FROZEN',source=science(),git_HEAD=commit(),working_tree_validation=True,
        acceptance=record(root/'ACCEPTANCE_RESULT.json'),diagnostic=record(DIAG/'DIAGNOSTIC_FREEZE.json'),
        files=files,Full_May_started=False,production_scientific_feasible_set_unchanged=True))
    assert all(record(ref['path'])==ref for ref in files)
    print('FIRST_IMPROVEMENT_FREEZE_PASS',len(files),record(frozen)['sha256'],flush=True)

if __name__=='__main__':run()

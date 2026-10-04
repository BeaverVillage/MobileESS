"""Freeze a new current-input campaign; historical decisions are never imported."""
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from .common import *


def prepare(audited_inputs=None):
    from tools.v42.preflight_b1_may import barrier,B0_ROOT
    b0=barrier(read(ROOT/'docs/v42_may_b0_production_31d/B0_CAMPAIGN_FINAL.json'),read(B0_ROOT/'CAMPAIGN_STATE.json'),B0_ROOT)
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
    dirty=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()
    if dirty: raise PermissionError('COMMIT_ADAPTER_BEFORE_FREEZE')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    days=[f'2025-05-{i:02d}' for i in range(1,32)]
    tag=uuid.uuid4().hex[:8]; run_id='B1_202505_'+datetime.now().strftime('%Y%m%dT%H%M%S')+'_'+tag
    root=Path('C:/v42_b1_runs')/tag; root.mkdir(parents=True,exist_ok=False)
    if audited_inputs:
        audited_inputs=Path(audited_inputs)
        index=read(audited_inputs/'INPUT_INDEX.json')
        for row in index['sources']+list(index['bundles'].values()):
            if sha(row['path'])!=row['sha256']: raise PermissionError('AUDITED_CURRENT_INPUT_DRIFT')
        if list(index['bundles'])!=days: raise PermissionError('FULL_CURRENT_31_DAYS_REQUIRED')
        sources=index['sources']; bundles={}
        for day in days:
            value=read(index['bundles'][day]['path'])
            if value['day']!=day or value['role']!='B1_PRODUCTION' or value['old_A1_freeze_reused']:
                raise PermissionError('AUDITED_INPUT_SCOPE')
            atomic(root/'inputs'/day/'NATIVE_INPUT.json',value)
            shutil.copyfile(audited_inputs/'inputs'/day/'COMMON_REFERENCE.json',root/'inputs'/day/'COMMON_REFERENCE.json')
            bundles[day]=record(root/'inputs'/day/'NATIVE_INPUT.json')
    else:
        from .inputs import build_inputs
        bundles,sources=build_inputs(root,days)
    # Freeze full local scientific code and accepted imported historical code.
    sources.extend(record(p) for folder in ROOT.glob('v42*') if folder.is_dir() for p in folder.rglob('*.py'))
    sources.extend(record(p) for p in ROOT.glob('v42*.py'))
    sources.extend(record(p) for p in (ROOT/'tools/v42').glob('*') if p.is_file() and p.suffix in ('.py','.ps1'))
    sources.extend(record(p) for p in CODE.joinpath('dayahead').rglob('*.py'))
    from v42_holdout.common import source_freeze
    from v42_capacity.common import resolve
    for row in source_freeze()['frozen_sources']:
        sources.append(record(resolve(row)))
    for folder in ('v42_final_integration','v42_ts_cc4_temporal_refinement','v42_cc4_service_timing_envelope',
                   'v42_regcontrol_source_audit','v42_transformer_normalamps_authority'):
        sources.extend(record(p) for p in (ROOT/'docs'/folder).rglob('*') if p.is_file())
    # Module-level PR97 references are independently frozen (actual folder names).
    from v42_boundary.common import PR97
    sources.extend(record(p) for p in PR97.rglob('*') if p.is_file())
    sources.extend(record(p) for day in days for p in (root/'inputs'/day).iterdir() if p.is_file())
    sources.append(record(Path(sys.executable)))
    import importlib.metadata as metadata
    environment=python_environment()
    for name in environment['packages']:
        dist=metadata.distribution(name)
        sources.extend(record(dist.locate_file(p)) for p in dist.files if p.name=='METADATA')
    sources=list({r['path']:r for r in sources}.values())
    config=asdict(Config()); task='MobileESS_V42_B1_May_Production_'+run_id
    freeze=dict(run_id=run_id,mode='B1_PRODUCTION',Git_SHA=head,base_Git_SHA=BASE,
                days=days,day_input_SHA={d:r['sha256'] for d,r in bundles.items()},sources=sources,
                checker_SHA=CHECKER,Python=str(Path(sys.executable).resolve()),worktree=str(ROOT),
                task_name=task,created_UTC=now(),B0_barrier=b0,
                Python_environment=environment,
                historical_implementation_PRs=[24,25,26],historical_decisions_reused=0,
                stage_order=list(STAGES),statements=STATEMENTS,configuration=config)
    freeze['scientific_SHA']=digest(dict(configuration=config,checker=CHECKER,version=VERSION,
                        sources=sources,stage_order=list(STAGES),days=days))
    atomic(root/'B1_PRODUCTION_FREEZE_MANIFEST.json',freeze)
    atomic(root/'B1_CAMPAIGN_CONFIG.json',config)
    atomic(root/'CHECKPOINT.json',dict(run_id=run_id,scientific_SHA=freeze['scientific_SHA'],failures=[],
            stages={d+'/'+s:dict(status='NOT_RUN',attempts=0) for d in days for s in STAGES}))
    for name in ('B1_LIVE_STATUS','B1_HEARTBEAT','B1_RESOURCE_LIVE','B1_DAY_STATUS'):
        atomic(root/(name+'.json'),dict(run_id=run_id,state='PREPARED',timestamp_UTC=now()))
    atomic(root/'B1_TASK_RECEIPT.json',dict(run_id=run_id,task_name=task,state='NOT_LAUNCHED',statements=STATEMENTS))
    atomic(root/'B1_MONITOR_RECEIPT.json',dict(run_id=run_id,state='NOT_LAUNCHED',readonly=True,
                                           title='Mobile ESS V42 May B1 Production Monitor'))
    return dict(root=str(root),run_id=run_id,task_name=task,Git_SHA=head,scientific_SHA=freeze['scientific_SHA'])

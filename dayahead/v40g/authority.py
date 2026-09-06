"""New lineage, byte-preserved common service and V40F evidence."""
from pathlib import Path
from contextlib import contextmanager
import shutil
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, sha, digest, reference

REL=Path('dayahead/artifacts/v40g_joint_aidc')
PREVIOUS=Path('dayahead/artifacts/v40f_min_rho_aidc_correction')
METHOD='JOINT_TEMPORAL_SPATIAL_AIDC_GRID_OPTIMIZATION'
GATES={'TEMPORAL_FIRST_HARD_HIERARCHY':'NO','TEMPORAL_AND_SPATIAL_AIDC_PRIMARY_JOINT':'YES',
       'MIGRATION_PENALTY_LEVEL':'SECONDARY_ONLY','PRIMARY_GRID_OBJECTIVE_SACRIFICED_FOR_MIGRATION_AVOIDANCE':'NO',
       'FULL_MAY_AUTHORIZED':'NO','B2_B3_AUTHORIZED':'NO'}


def initialize(repo):
    repo=Path(repo).resolve(); root=repo/REL;root.mkdir(parents=True,exist_ok=True)
    manifest=root/'PRESERVED_V40F.json'
    if not manifest.exists():
        paths=[p for p in (repo/PREVIOUS).rglob('*') if p.is_file()]
        paths += list((repo/'dayahead/v40f').glob('*.py'))
        write_json(manifest,{'files':{str(p):sha(p) for p in sorted(paths)}})
    for folder in ('common_service','electrical','april_joint_authority'):
        source=repo/PREVIOUS/folder;destination=root/folder
        if not destination.exists():shutil.copytree(source,destination)
    for p in (repo/PREVIOUS/'common_service').iterdir():
        if p.is_file():assert sha(p)==sha(root/'common_service'/p.name)
    service=read(root/'common_service/COMMON_DA_SERVICE_AUTHORITY.json')
    assert service['COMMON_DA_DURATION_SHA']=='2f241ec63646ebec23bad86ac69b8b92d7c9daa9f2771b7c80b0eecfafab40f1'
    config={'method':METHOD,'FORMULATION_CORRECTION':'REMOVE_UNNECESSARY_TEMPORAL_SPATIAL_HIERARCHY',
            'May_result_based_tuning':False,
            'reason':'Restricting migration until temporal recourse fails can exclude a lower-rho feasible solution.',
            'objectives':['MIN rho_max on all modeled phase-line-time rows','MIN authorized RUNNING migration count',
                          'MIN canonical complete UID/site interval GPU-slot symmetric difference from B0','deterministic stable tie-break'],
            'primary_lock_degradation_allowance':0.,'solver_feasibility_tolerance':1e-9,'solver_work_limits':[60,180,300],
            'B0':'RW/reference AIDC, MESS OFF','B1':'Joint temporal + spatial/migration AIDC, MESS OFF',
            'B2':'Exact B0 AIDC, MESS optimization','B3':'A0 exact B1 -> M1 -> A1 -> MF',
            'before_M1_required':'B1_AIDC_DECISION_SHA == B3_A0_DECISION_SHA',
            'RUNNING_migration':'Single existing checkpoint/fixed-path/WAN/restart migration; immutable initial state; no return migration',
            'RUNNING_checkpoint':'Existing first 30-minute-phase checkpoint, conservative 15-minute slots, operating-day axis',
            'WAN':'Existing UID-serialized full path-capacity transfer; start cursor 2; maximum one active transfer',
            'service':'T_DA counts compute service. Migration pause is not compute; all service is retained. In-day obligation requires completion by H.',
            'terminal':'Exact common per-job post-H profile and site. A one-way move of a tail job is inadmissible.',
            'reference_metric':'Same canonical full interval UID/site GPU-slot symmetric difference; sum over source/destination segments for a migration',
            'common_service':reference(root/'common_service/COMMON_DA_SERVICE_AUTHORITY.json'),
            'COMMON_DA_DURATION_SHA':service['COMMON_DA_DURATION_SHA'],
            'user_request':reference(Path('C:/Users/kjw39/.codex/attachments/0f85e5c6-62fe-4e78-a661-6b4dc585e9d4/pasted-text.txt')),
            'authorized_dates':['2025-05-01'],'authorized_execution_cases':['B0','B1'],
            'temporal_only':'Diagnostic after final joint policy freeze; cannot select final policy',**GATES}
    path=root/'FORMULATION_CONTRACT.json'
    if path.exists():assert read(path)==config
    else:write_json(path,config)
    write_json(root/'V40F_SUPERSESSION.json',{'status':'SUPERSEDED_BY_JOINT_AIDC_FLEXIBILITY_FORMULATION',
        'reason':'Previous corrected formulation validated common T_DA and explicit min-rho, but the final normative formulation now removes any possible temporal/spatial hierarchy and exposes all authorized AIDC flexibility jointly.',
        'preserved_evidence':reference(manifest),'old_result_overwritten':False,'replacement':str(root),**GATES})
    return root


@contextmanager
def namespace():
    from dayahead.v40e import electrical
    old=electrical.REL;electrical.REL=REL;electrical.upstream.cache_clear()
    try:yield electrical
    finally:electrical.REL=old;electrical.upstream.cache_clear()


def current_context(repo):
    from dayahead.v38.authority import load_wan_authority
    with namespace() as electrical:ctx=electrical.planning_context(Path(repo).resolve(),'2025-05-01')
    ctx.wan=load_wan_authority(Path(repo))
    snapshot=Path(repo)/'dayahead/artifacts/v37_r4a_per_day_aidc/days/2025-05-01/V37_R4A_D1_SNAPSHOT.parquet'
    frame=pd.read_parquet(snapshot);ctx.elapsed={}
    issue=pd.Timestamp('2025-04-30T18:00:00+10:00')
    assert (pd.to_datetime(frame.submit_time,utc=True)<=issue).all()
    for row in frame[frame.state_at_issue=='RUNNING'].itertuples(index=False):
        start=pd.Timestamp(row.known_running_start)
        ctx.elapsed[str(row.id)]=(issue-start).total_seconds()
        assert ctx.elapsed[str(row.id)]>=0
    ctx.input_shas[str(snapshot)]=sha(snapshot)
    return ctx


def seal(repo):
    repo=Path(repo);root=repo/REL
    sources=list((repo/'dayahead/v40g').glob('*.py'))
    for name in ['v40a/grid.py','v40a/invariants.py','v40a/feedback.py','v40e/electrical.py','v40e/mapping.py','v40e/smoke.py','v38/authority.py','v38/wan.py','v38/contracts.py','v39c/evaluate.py','v40d_actual/job_replay.py','v40d_actual/rack_dispatch.py','v40d_actual/power_replay.py']:
        sources.append(repo/'dayahead'/name)
    shas={str(p):sha(p) for p in sorted(sources)}
    sources.append(repo/'tests/dayahead/test_v40g_joint.py')
    shas={str(p):sha(p) for p in sorted(sources)}
    config_files={str(root/name):sha(root/name) for name in ('FORMULATION_CONTRACT.json','B1_REUSE_AS_B3_A0_CONTRACT.json')}
    cfg=digest(config_files);src=digest(shas)
    payload={'source_SHA':src,'config_SHA':cfg,'source_files':shas,'config_files':config_files,'method':METHOD,
             'config_scope':'Joint formulation plus mandatory exact B1 reuse architecture'}
    payload['method_SHA']=digest(payload)
    path=root/'SOURCE_SEAL.json'
    if path.exists() and read(path)!=payload:
        archive=root/'repairs/final_lineage_completion/SOURCE_SEAL_before.json'
        assert archive.exists() and sha(archive)==sha(path),'FROZEN_SOURCE_DRIFT'
        write_json(path,payload)
    elif path.exists():assert read(path)==payload, 'FROZEN_SOURCE_DRIFT'
    else:write_json(path,payload)
    return payload


def verify_preservation(repo):
    root=Path(repo)/REL;files=read(root/'PRESERVED_V40F.json')['files']
    changes=[p for p,h in files.items() if not Path(p).is_file() or sha(p)!=h]
    value={'files':len(files),'changed_files':changes,'status':'PASS' if not changes else 'FAIL'}
    write_json(root/'PRESERVATION_CHECK.json',value);assert not changes
    return value

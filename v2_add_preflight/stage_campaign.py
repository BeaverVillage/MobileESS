"""May01 sequential coordinator. Default CLI is a plan; no auto campaign."""
from pathlib import Path
import argparse,traceback
from .stage_common import ROOT,OUT,RUN,SOURCE,read,record,day_inputs,put
from .prestart_execution import atomic
from .stage_authority import campaign_lease,stage_scope,require_approval
from .stage_resources import manifest
from .stage_checkpoint import seal,restore
from v44.stages import CHAINS,m_outcome,require_a2
from v44.common import now
from v42_native.contracts import digest


def source_files():
    packages=['v2_add_preflight','v42_may_campaign_native90','v42_job_capability','v42_boundary','v42_compact',
        'v42_integrated','v42_exact','v42_native','v42_temporal','v42_pr134_b1','v42_pr134_sc','v42_m1_research',
        'v42_supercompact','v42_capacity','v43_actual','v43_corrective','v43_baseline','v43_arms','v43_followup','v44']
    packages.extend(p.name for p in ROOT.glob('v42_a_stage_*') if p.is_dir())
    files=[p for package in packages for p in (ROOT/package).rglob('*.py')]
    files.extend(ROOT/p for p in ('docs/v44/V43_MESS_REUSE_SOURCE_MANIFEST.json',
        'docs/v2_add/static_complete/SOURCE_YY_HARDWARE_FREEZE.json',
        'docs/v2_add/static_complete/SOURCE_YY_COMPLETE_INPUT_CASE_IDENTITY.json'))
    # The pinned manifest is checked again by every source library load.
    pin=read(ROOT/'docs/v44/V43_MESS_REUSE_SOURCE_MANIFEST.json')
    files.extend(Path(r['source']['path']) for r in pin['sources'])
    return [record(p) for p in sorted(set(files))]


def request(root,arm,stage,sources):
    from v44.config import axis
    row=day_inputs();underlying=stage.split('_',1)[1] if stage.startswith('K48_') else stage
    out=Path(root)/'2025-05-01'/arm/stage
    return dict(day='2025-05-01',arm=arm,stage=underlying,logical_stage=stage,
        output=str(out),root=str(out),campaign_root=str(Path(root).resolve()),
        input_folder=str(Path(row['files']['native']['path']).parent),
        sources=sources,source_sha=digest(SOURCE),axis=axis('2025-05-01'),
        worker_slot=1,Threads=4 if underlying in ('M1','M2') else 1)


def validate(stage,result):
    if result.get('PASS') is not True:raise ValueError('STAGE_NOT_ACCEPTED:'+stage)
    if stage in ('A1','A1_REUSE','A2'):
        if (result.get('FULL_feasible') is not True or result.get('independent_Global_LB_validated') is not True
                or not 0<=result.get('certified_gap',1)<=.005 or not result.get('AIDC_reference')):
            raise ValueError('ORIGINAL_FULL_A_HALF_PERCENT_ACCEPTANCE_REQUIRED')
        if stage=='A2':require_a2(result,'2025-05-01')
    if stage in ('M1','M2') and not m_outcome(result)['allow_downstream']:raise ValueError('HEALTHY_FULL_M_REQUIRED')
    if stage.startswith('K48_') and not result.get('M_binary'):raise ValueError('REAL_CURRENT_K48_BINARY_REQUIRED')
    # A valid K48 numeric LB is not required to attempt the original UB core.
    if stage=='ACTUAL' and result.get('original_FULL_Job_PASS') is not True:raise ValueError('FULL_ACTUAL_JOB_REQUIRED')
    if stage=='FRESH' and not (result.get('full120_security_PASS') is True and result.get('independent_new_engine') is True
            and result.get('original_FULL_Job_PASS') is True):raise ValueError('NEW_ENGINE_FULL120_AND_JOB_REQUIRED')


def artifact_tree(folder):
    # Includes arrays and exact proof artifacts referenced by the result.
    return [record(p) for p in sorted(Path(folder).rglob('*')) if p.is_file() and p.name!='CHECKPOINT.json']


def run(root,approval,*,resume=False,retry_reconciled_m=False):
    require_approval(approval)
    from .stage_handlers import HANDLERS
    root=Path(root);sources=source_files();frozen=dict(source_files=sources,
        hardware=record(OUT/'SOURCE_YY_HARDWARE_FREEZE.json'),input_files=day_inputs()['files'])
    identity=digest(frozen);b1=None;results=[]
    with campaign_lease(root,approval) as lease:
        state=root/'CAMPAIGN_INPUT_IDENTITY.json'
        if state.exists():
            if not resume or read(state)!=frozen:raise ValueError('NEW_OR_SAME_IMMUTABLE_CAMPAIGN_REQUIRED')
        else:atomic(state,frozen)
        for arm in ('B0','B1','B2','B3'):
            parents={}
            for stage in CHAINS[arm]:
                req=request(root,arm,stage,sources);folder=Path(req['output']);checkpoint=folder/'CHECKPOINT.json'
                key=dict(campaign_identity=identity,day=req['day'],arm=arm,stage=stage)
                try:
                    if checkpoint.exists():
                        if not resume:raise ValueError('EXISTING_STAGE_REQUIRES_RESUME')
                        result=restore(checkpoint,key);validate(stage,result)
                    else:
                        # Never reset an inflight/failed Native clock or reuse
                        # a partially evolved Actual queue as a fresh attempt.
                        if folder.exists() and any(folder.iterdir()):
                            if not (resume and retry_reconciled_m and req['stage'] in ('M1','M2')):
                                raise ValueError('FAILED_OR_INFLIGHT_STAGE_REQUIRES_EXPLICIT_RECONCILED_REENTRY')
                            parent=Path(read(root/'CONTROL'/arm/(stage+'_ACTIVE_ATTEMPT.json'))['path'])
                            from v44.checkpoints import assert_dead
                            assert_dead(parent)
                            name='K48_NATIVE_LEDGER.json' if stage.startswith('K48_') else 'JOINT_NATIVE_LEDGER.json'
                            if (parent/name).exists():
                                from .stage_checkpoint import reconciled
                                reconciled(parent/name,300. if stage.startswith('K48_') else 900.)
                            attempt=1
                            while (folder/f'REENTRY_{attempt:03d}').exists():attempt+=1
                            req=dict(req,output=str(folder/f'REENTRY_{attempt:03d}'),root=str(folder/f'REENTRY_{attempt:03d}'),resume_parent=str(parent))
                        attempt_path=Path(req['output'])
                        # START lives next to this attempt's ledger; the stage
                        # builder requires a not-yet-created output directory.
                        atomic(root/'CONTROL'/arm/(stage+'_ACTIVE_ATTEMPT.json'),dict(path=str(attempt_path)))
                        with stage_scope(req,lease):
                            fn=HANDLERS[stage]
                            result=fn(req,parents,b1) if stage=='A1_REUSE' else fn(req,parents)
                        validate(stage,result)
                        folder.mkdir(parents=True,exist_ok=True)
                        atomic(folder/'RESULT.json',result)
                        seal(checkpoint,key,result,artifact_tree(folder))
                    parents[stage]=result
                    if arm=='B1' and stage=='A1':b1=result
                except BaseException as error:
                    folder.mkdir(parents=True,exist_ok=True)
                    atomic(folder/'FAILURE.json',dict(error=repr(error),traceback=traceback.format_exc(),UTC=now(),
                        Native_clock_reset=False,old_results_preserved=True))
                    results.append(dict(arm=arm,status='BLOCKED',stage=stage,error=repr(error)));break
            else:results.append(dict(arm=arm,status='COMPLETE'))
            atomic(root/'MONITOR.json',dict(cases=results,official_memory_policy=manifest(),sources=sources))
    return results


def plan():
    from .stage_handlers import HANDLERS
    return put('MAY01_STAGE_CAMPAIGN_HOLD.json',dict(status='HOLD_NO_CAMPAIGN_EXECUTION',experiment_id='V2_add',
        days=['2025-05-01'],chains={k:list(v) for k,v in CHAINS.items()},
        handlers={k:v.__module__+'.'+v.__name__ for k,v in HANDLERS.items()},
        official_campaign_executed=False,auto_run=False,worker_count=1,A_Threads=1,M_Threads=4,
        A_seconds=5400.,A_gap=.005,K48_seconds=300.,Joint_seconds=900.,Joint_call_cap=300.,M_gap=.03,
        resource_policy=manifest(),Python=str(RUN.parent/'.venv/Scripts/python.exe'),
        allowed_runtime_root=str(RUN/'official_stage_campaign'),
        future_command='python -m v2_add_preflight.stage_campaign campaign --root "'+str(RUN/'official_stage_campaign/May01_pending_user_approval')+'" --approval "<future-explicit-human-approval.json>"',
        resume_command='same command with --resume; only sealed complete stages resume automatically',
        incomplete_A_or_Actual_live_state_resume='BLOCKED_WITH_PRESERVED_EVIDENCE',
        reconciled_M_reentry='--resume --retry-reconciled-m; new attempt, original measured budget and FULL registry',
        command_runnable_now=False,required_certificate='FINAL_MAY01_PRESTART_GO_NO_GO.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['plan','campaign'],nargs='?',default='plan')
    parser.add_argument('--root');parser.add_argument('--approval');parser.add_argument('--resume',action='store_true')
    parser.add_argument('--retry-reconciled-m',action='store_true');args=parser.parse_args()
    if args.mode=='plan':plan()
    else:
        if not args.root or not args.approval:parser.error('--root and --approval required')
        run(args.root,args.approval,resume=args.resume,retry_reconciled_m=args.retry_reconciled_m)

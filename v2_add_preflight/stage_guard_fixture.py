"""Native0 checks of the real source Runtime and nested thread admission."""
import copy,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from .stage_common import *
from .prestart_native import native_zero
from .stage_budget import scope as budget_scope,JOINT_SECONDS,K48_SECONDS


def certify():
    from v42_may_campaign_native90 import budget as native
    from v44.budget import StageBudget,resume
    from .stage_threads import scope as threads
    from .stage_authority import stage_scope,require_approval
    from .stage_resources import campaign_scope,check_memory,apply_solver_memory_policy
    from .stage_campaign import request
    with measured('CAMPAIGN_PRESTART_EXECUTION_GUARDS.json') as (report,start),native_zero() as denied:
        root=WORK/('GUARD_FIXTURE_'+uuid.uuid4().hex[:8]);root.mkdir()
        context=dict(arm='B2',stage='M1',source_sha='a'*64)
        case=SimpleNamespace(identity=context,case_sha='b'*64)
        negative=[];ledgers=[]
        # Explicit synthetic Runtime receipts exercise ledger arithmetic only;
        # these are not measurements of an optimization or campaign result.
        with patch.object(native,'d_path',lambda p:Path(p)),budget_scope():
            for kind,ceiling in [('K48_SEPARATE',K48_SECONDS),('PLANNING_NATIVE',JOINT_SECONDS)]:
                folder=root/kind;folder.mkdir();old=StageBudget(folder/'old.json',case=case,kind=kind)
                old.calls=[dict(status='FINISHED',Native_Runtime=12.5,Native_Work=0.,fixture_synthetic_Runtime=True)]
                old.native_used=12.5;old.persist()
                new=resume(old.path,case=case,kind=kind,destination=folder/'new.json')
                assert new.used()==12.5 and new.remaining()==ceiling-12.5
                original=read(old.path)
                for name,change in [('inflight',lambda v:v.update(inflight=dict(status='IN_FLIGHT'))),
                    ('unknown_Runtime',lambda v:v['calls'][0].update(runtime_unavailable=True)),
                    ('wrong_total',lambda v:v.update(measured_Native_Runtime=0.)),
                    ('wrong_ceiling',lambda v:v.update(Native_ceiling_seconds=ceiling+1))]:
                    bad=copy.deepcopy(original);change(bad)
                    (folder/'bad.json').write_text(json.dumps(bad),encoding='utf-8')
                    try:resume(folder/'bad.json',case=case,kind=kind,destination=folder/(name+'.json'))
                    except (ValueError,PermissionError):negative.append(kind+':'+name)
                    else:raise AssertionError('UNRECONCILED_LEDGER_ACCEPTED')
                ledgers.append(dict(kind=kind,ceiling=ceiling,synthetic_old_Runtime=12.5,restored_Runtime=new.used(),remaining=new.remaining()))
        r=dict(day='2025-05-01',arm='B2',stage='M1',worker_slot=1,Threads=4)
        with threads(r) as one:
            with threads(r) as two:assert one is two
            try:
                with threads(dict(r,stage='M2')):raise AssertionError('CROSS_STAGE_OVERLAY_ACCEPTED')
            except PermissionError:negative.append('nested_thread_stage_drift')
        try:
            with stage_scope(dict(r,output=str(root)),dict()):raise AssertionError('FORGED_LEASE_ACCEPTED')
        except PermissionError:negative.append('no_held_OS_lease')
        try:require_approval(root/'never-created-approval.json')
        except (PermissionError,FileNotFoundError):negative.append('no_campaign_approval')
        with campaign_scope():
            assert check_memory(dict(RSS_bytes=128*1024**3,system_available_bytes=0))['memory_information_only']
            import gurobipy as gp
            model=gp.Model('V2_ADD_GUARDS_ONLY');model.Params.OutputFlag=0
            try:
                model.Params.MemLimit=1;model.Params.SoftMemLimit=.5
                assert apply_solver_memory_policy(model)==dict(MemLimit='Infinity',SoftMemLimit='Infinity')
            finally:model.dispose()
        # Exercise the real nested production scope down to the inherited
        # model guard, with explicit fixture authority and denied solvers.
        # No human approval or external OS lease is manufactured/admitted.
        from . import stage_authority as authority
        from v44.locks import process_identity
        fixture_lease=dict(**process_identity(),root=str(root),worker_slot=1,approval=dict(explicit_Native0_fixture=True))
        token=authority._lease.set(fixture_lease)
        try:
            for arm,stage,count in [('B1','A1',1),('B2','M1',4)]:
                req=dict(day='2025-05-01',arm=arm,stage=stage,Threads=count,worker_slot=1,
                    output=str(root/arm),sources=[],source_sha='a'*64)
                fixture_context=dict(request=req,worker=fixture_lease,lease=fixture_lease)
                with campaign_scope(),patch.object(authority,'current',lambda:fixture_context),authority.stage_scope(req,fixture_lease):
                    model=gp.Model('V2_ADD_SOURCE_GUARD_NATIVE0');model.Params.OutputFlag=0;model.Params.Threads=count
                    model.Params.MemLimit=1.;model.Params.SoftMemLimit=.5
                    try:
                        with native.native_scope(model,component='UB' if stage=='M1' else 'P1',track='M' if stage=='M1' else 'A'):
                            import math
                            assert math.isinf(model.Params.MemLimit) and model.Params.MemLimit>0
                            assert math.isinf(model.Params.SoftMemLimit) and model.Params.SoftMemLimit>0
                            native.guard(model)
                            model.Params.Threads=2
                            try:native.guard(model)
                            except PermissionError:negative.append(stage+':wrong_threads')
                            else:raise AssertionError('SOURCE_WRONG_THREAD_GUARD_NOT_REACHED')
                    finally:model.dispose()
        finally:authority._lease.reset(token)
        assert len(negative)==13 and not denied
        report.update(PASS=True,real_source_Runtime_resume_arithmetic=ledgers,negative_rejections=negative,
            nested_original_M4_overlay_PASS=True,official_memory_admission_and_termination=False,
            actual_original_model_scope_and_A1_M1_thread_guard_PASS=True,
            actual_original_Native_scope_restores_positive_Infinity_PASS=True,
            official_solver_memory_limits_unlimited=True,V2_add_expanded_budget_resume_verified=True,original_gaps_and_threads_preserved=True,
            external_worker_locks_not_acquired=True,fixture_Runtime_values_not_actual_measurements=True,
            complete_checkpoint_resume_test=record(OUT/'PRODUCTION_HANDLER_FINITE_IO_FIXTURE.json'),denied_attempts=denied)


if __name__=='__main__':certify()

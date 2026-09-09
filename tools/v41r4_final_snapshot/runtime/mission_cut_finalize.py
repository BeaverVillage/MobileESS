"""Resume scientific persistence after inherited fixed-discrete AC restoration."""
import inspect,textwrap,shutil,time
from pathlib import Path
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from dayahead.v41 import execution as original_execution
ORIGINAL_DA_SOURCE=textwrap.dedent(inspect.getsource(original_execution.dayahead))

def preserve(day,policy,output):
    from v41r4_loop_runtime import MAY_OUT
    destination=MAY_OUT/'mission/AC_CUT_FAILED_EVIDENCE'/day/policy
    if not (destination/'PRESERVED.json').exists():
        assert not (output/'DAYAHEAD_RECEIPT.json').exists()
        destination.mkdir(parents=True,exist_ok=True)
        shutil.copytree(output,destination/'dayahead',dirs_exist_ok=False)
        for name in (f'PHASE_{policy}_DA.json',f'PRODUCER_{policy}.json'):
            p=MAY_OUT/day/name
            if p.exists():shutil.copy2(p,destination/name)
        write_json(destination/'PRESERVED.json',dict(status='PASS',failed_decision=record(destination/'dayahead/FROZEN_JOINT_DECISION.json'),
            reason='Missing call to inherited postfreeze Fresh-AC restoration',at=time.time()))
    return destination

def finalize(day,policy,execution):
    import numpy as np,pandas as pd
    from dayahead.v41 import scientific_archive as archive
    from dayahead.v41.reserve import bind
    from dayahead.v41.electrical import load
    from dayahead.v41.persistence import optimizer_rows
    from dayahead.v40h.beam_driver import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from mission_ac_cut_restore import restore
    from dayahead.v40a.invariants import digest
    from v41r4_loop_runtime import MAY_RUN,MAY_OUT
    output=MAY_RUN/day/policy/'dayahead'
    saved=preserve(day,policy,output)
    assert not (output/'DAYAHEAD_RECEIPT.json').exists()
    # Persistence deliberately never overwrites tables. Preserve and move only
    # derived final outputs before regenerating them from the repaired commands.
    attempt=saved/('finalization_attempt_'+str(time.time_ns()))
    mutable=('optimization/stages/JOINT_FREEZE','optimization/stages/JOINT_FREEZE.json',
        'optimization/stages/AC_RESTORATION_OUTPUT','optimization/stages/AC_RESTORATION_OUTPUT.json',
        'fresh','fresh_readback','grid','mess','audit/mapper','audit/CRITICAL_PHYSICAL_EVENTS.parquet',
        'aidc/JOB_DECISIONS.parquet','aidc/JOB_SLOT_OCCUPANCY.parquet','aidc/SITE_TRAJECTORIES_96.parquet')
    for name in mutable:
        src=output/name;dst=attempt/name
        assert src.resolve().is_relative_to(output.resolve()) and dst.resolve().is_relative_to(saved.resolve())
        if src.exists():dst.parent.mkdir(parents=True,exist_ok=True);src.rename(dst)
    original=read(saved/'dayahead/FROZEN_JOINT_DECISION.json')['decision'];old=read(saved/'dayahead/PLANNING_RESULT.json')
    jobs=original['AIDC_decision'];snapshot_path=Path(original['ML_snapshot']['path'])
    context=load(day);bind(context,snapshot_path,original['ML_snapshot']['sha256'])
    try:
        with np.load(saved/'dayahead/FROZEN_AIDC_POWER.npz') as z:power={k:z[k].copy() for k in z.files}
        initial=MessTrajectory(tuple(_restore_slots(original['MESS_trajectory'])))
        repair_root=MAY_OUT/'mission/CUT_REPAIR'/day/policy;result=repair_root/'RESULT.json'
        if result.exists():
            report=read(result);assert report['status']=='PASS' and report['initial_trajectory_SHA']==digest(initial)
            assert report['coefficients']==context.v41_electrical_certificate
            assert record(report['margin_authority']['path'])['sha256']==record(ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4/audit/mission/AC_CUT_MARGIN_AUTHORITY.json')['sha256']
            trajectory=MessTrajectory(tuple(_restore_slots(report['final_slots'])))
        else:trajectory,report=restore(day,policy,jobs,power,initial,context,repair_root)
        archive.document(output/'AC_RESTORATION_RECEIPT.json',dict(status='PASS',report=record(result),
            original_optimizer_decision=record(saved/'dayahead/FROZEN_JOINT_DECISION.json'),
            original_generation=record(saved/'dayahead/GENERATION_INPUT_IDENTITY.json'),
            original_optimizer_source=read(saved/'dayahead/GENERATION_INPUT_IDENTITY.json')['source'],
            restored_with_source=execution.science(),AIDC_optimization_calls=0,route_search_calls=0,
            AIDC_unchanged=True,discrete_MESS_unchanged=True))
        compute=read(output/'POLICY_DAY_COMPUTE_REPORT.json')
        compute.update(AC_restoration_seconds=report['elapsed_seconds'],AC_restoration_rounds=report['restoration_rounds'],
            AC_restoration_outside_AIDC_FO_budget=True,AC_restoration_receipt=record(output/'AC_RESTORATION_RECEIPT.json'))
        write_json(output/'POLICY_DAY_COMPUTE_REPORT.json',compute)
        traces={p.stem:read(p) for p in (saved/'dayahead/optimization/stages').glob('*.json')}
        previous=traces.get('JOINT_FREEZE')
        def trace(name,current,mess=None,allowed=(),frozen=(),info=None):
            nonlocal previous
            from dataclasses import asdict
            commands=[asdict(r) for r in mess.slots]
            value=archive.stage(output,name,current,commands,context=context,allowed=allowed,frozen=frozen,previous=previous,info=info)
            traces[name]=value;previous=value
        trace('AC_RESTORATION_OUTPUT',jobs,trajectory,allowed=('MESS P/Q/SoC under inherited Fresh AC cuts',),
            frozen=('AIDC decisions','MESS mobility','ML'),info=dict(report=record(result)))
        classes=pd.read_parquet(output/'authority/JOB_CLASSES.parquet').set_index('job_id')
        requests=pd.read_parquet(output/'authority/JOB_REQUEST_INPUTS.parquet').set_index('job_id')
        local=dict(day=day,policy=policy,output=output,context=context,jobs=jobs,trajectory=trajectory,
            objective=old['objective'],stages=old['stages'],traces=traces,trace=trace,archive=archive,
            snapshot_path=snapshot_path,snapshot_seal=dict(snapshot=original['ML_snapshot']),
            common=dict(COMMON_DA_DURATION_SHA=original['common_service_SHA']),optimizer_rows=optimizer_rows,
            classes=classes,requests=requests,source=execution.science(),started=read(saved/'dayahead/DAYAHEAD_STARTED.json')['started_at'])
        begin=ORIGINAL_DA_SOURCE.index('        commands = off_commands()')
        end=ORIGINAL_DA_SOURCE.index('    finally:',begin)
        # The inner Fresh try/finally is indented eight spaces; find outer finally only.
        tail=ORIGINAL_DA_SOURCE[begin:]
        end=tail.index('\n    finally:')
        tail=textwrap.dedent(tail[:end])
        ns=dict(original_execution.__dict__,science=execution.science)
        body='def finish_saved(**state):\n    globals().update(state)\n'+textwrap.indent(tail,'    ')
        exec(compile(body,__file__+'::finish_saved','exec'),ns)
        receipt=ns['finish_saved'](**local)
        assert receipt['status']=='COMPLETE'
        return receipt
    finally:context.electrical.voltage.close();context.electrical.current.close()

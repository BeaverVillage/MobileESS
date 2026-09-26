from pathlib import Path
from dataclasses import asdict
import inspect,textwrap,shutil
import runtime_environment as env
PRODUCTION=env.ROOT
from dayahead.paper_analysis.storage import read,write_json as save
def final_persistence(day,ctx,source_da,jobs,mess,components):
    """Original DA persistence/Fresh tail, with no scheduling/search entry."""
    from dayahead.v41 import execution,scientific_archive as archive
    from dayahead.v41.persistence import optimizer_rows
    from dayahead.v41.preflight import record
    import pandas as pd
    output=PRODUCTION/'closed_runs'/day/'B3/dayahead'
    assert not env.exists(output),'PRESERVE_EXISTING_CLOSED_OUTPUT'
    output.mkdir(parents=True)
    for name in ['authority','ml']:
        if (source_da/name).is_dir():shutil.copytree(source_da/name,output/name)
    for name in ['GENERATION_INPUT_IDENTITY.json','DAYAHEAD_STARTED.json','POLICY_DAY_COMPUTE_REPORT.json','SEARCH_LOOP_WALL_CLOCK_AUDIT.json']:
        if (source_da/name).is_file():(output/name).write_bytes((source_da/name).read_bytes())
    # Preserve M1/A2/M2 raw stage evidence in the candidate namespace and copy
    # its stage ledger. Fresh and final joint data are produced anew here.
    stages_dir=source_da/'optimization/stages'
    for p in stages_dir.iterdir():
        if p.stem=='JOINT_FREEZE':continue
        dest=output/'optimization/stages'/p.name;dest.parent.mkdir(parents=True,exist_ok=True)
        if p.is_dir():shutil.copytree(p,dest)
        else:dest.write_bytes(p.read_bytes())
    old=read(source_da/'PLANNING_RESULT.json');original=read(source_da/'FROZEN_JOINT_DECISION.json')['decision']
    traces={p.stem:read(p) for p in (output/'optimization/stages').glob('*.json')}
    previous=traces.get('MF_OUTPUT')
    def trace(name,current,mess=None,allowed=(),frozen=(),info=None):
        nonlocal previous
        value=archive.stage(output,name,current,[asdict(r) for r in mess.slots],context=ctx,
            allowed=allowed,frozen=frozen,previous=previous,info=info)
        traces[name]=value;previous=value
    trace('ROUND2_FINAL_SELECTION',jobs,mess,frozen=('selected DA incumbent','no Actual input'))
    source=read(source_da/'DAYAHEAD_STARTED.json')['source']
    local=dict(day=day,policy='B3',output=output,context=ctx,jobs=jobs,trajectory=mess,
        objective=dict(OBJECTIVE_VECTOR=components),stages=old['stages'],traces=traces,trace=trace,archive=archive,
        snapshot_path=Path(original['ML_snapshot']['path']),snapshot_seal=dict(snapshot=original['ML_snapshot']),
        common=dict(COMMON_DA_DURATION_SHA=original['common_service_SHA']),optimizer_rows=optimizer_rows,
        classes=pd.read_parquet(output/'authority/JOB_CLASSES.parquet').set_index('job_id'),
        requests=pd.read_parquet(output/'authority/JOB_REQUEST_INPUTS.parquet').set_index('job_id'),
        source=source,started=read(source_da/'DAYAHEAD_STARTED.json')['started_at'])
    text=textwrap.dedent(inspect.getsource(execution.dayahead))
    tail=text[text.index('        commands = off_commands()'):];tail=textwrap.dedent(tail[:tail.index('\n    finally:')])
    ns=dict(execution.__dict__,science=lambda:source)
    body='def persist_selected(**state):\n    globals().update(state)\n'+textwrap.indent(tail,'    ')
    exec(compile(body,__file__+'::original_persistence_tail','exec'),ns)
    ns['persist_selected'](**local)
    return output

def close(day,case,runs):
    import time,importlib.util
    from authority_recovery import sha
    from dayahead.v41.preflight import record
    source=runs/day/'B3/dayahead';work=case/'closure'/day
    primary=read(source/'FRESH_RESULT.json')['summary']
    if not primary['physical_violation']:
        save(work/'ACCEPTANCE.json',dict(status='PASS',final_dayahead=str(source),final_joint=record(source/'FROZEN_JOINT_DECISION.json'),closure_wall_seconds=0.,baseline_incumbent_used=False));return
    from v41r4_electrical import configure
    from dayahead.v41.reserve import bind
    from dayahead.v40h.beam_driver import _restore_slots
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v40g_segments.canonical import planning_power
    from dayahead.v41r1.bounded_mess import validate
    d=read(source/'FROZEN_JOINT_DECISION.json')['decision'];ctx=configure(day).load(day);bind(ctx,d['ML_snapshot']['path'],d['ML_snapshot']['sha256']);started=time.time()
    try:
        power=planning_power(d['AIDC_decision'],ctx);current=MessTrajectory(tuple(_restore_slots(d['MESS_trajectory'])))
        from mission_ac_cut_restore import restore
        try:current,_=restore(day,'B3',d['AIDC_decision'],power,current,ctx,work/'local')
        except AssertionError as e:
            info=e.args[0] if e.args else None
            if not (isinstance(info,tuple) and info[0]=='CUT_RECOURSE_FAILURE' and info[1].get('status_code')==3):raise
            p=env.PR/'tools/v41r4_final_snapshot/runtime/restoration_revision_v1.py'
            rule=read(env.ORIGINAL/'frozen_artifacts/v41r4_restoration_revision_v1/RULE_FREEZE.json')
            assert sha(p)==next(r['sha256'] for r in rule['code'] if r['path'].endswith('restoration_revision_v1.py'))
            spec=importlib.util.spec_from_file_location('original_closure',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.OUT=module.NEWAC=work.resolve();ctx.revision_pcc=power['pcc'];current,_=module.fallback(day,'B3',d,power,current,ctx,work/'full_pq')
        _,grid=validate(d['AIDC_decision'],current,ctx);v=read(source/'optimization/OBJECTIVE_LEDGER.json')['OBJECTIVE_VECTOR'];v[0]=grid['rho_max'];v[1]=0.
        final=final_persistence(day,ctx,source,d['AIDC_decision'],current,v)
        assert not read(final/'FRESH_RESULT.json')['summary']['physical_violation']
        save(work/'ACCEPTANCE.json',dict(status='PASS',final_dayahead=str(final),final_joint=record(final/'FROZEN_JOINT_DECISION.json'),closure_wall_seconds=time.time()-started,baseline_incumbent_used=False))
    finally:ctx.electrical.voltage.close();ctx.electrical.current.close()

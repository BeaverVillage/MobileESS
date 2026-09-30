"""One 600-second externally supervised LP experiment; no A1 publication."""
from time import perf_counter
from collections import Counter
import os,shutil
from .common import *
from .column import ColumnFactory
from .pricing import initial_columns,structure_counts
from .master import Master
from .cg import generate
from v42_compact.native import prepare
from v42_native.supervision import supervise

GATES=('PRICING_EXHAUSTIVE_SYNTHETIC_AUDIT.json','PRICING_REAL_SUBSET_AUDIT.json',
       'REDUCED_COST_SIGN_AUDIT.json','FULL_COLUMN_MASTER_EQUIVALENCE.json','SMALL_INTEGER_EQUIVALENCE.json')

def worker(context,payload):
    for row in payload['sources']:require(sha(row['path'])==row['sha256'],'DW_SOURCE_DRIFT')
    require(sha(OUT/'PREREGISTRATION.json')==payload['prereg_sha256'],'PREREG_DRIFT')
    started=perf_counter();data=prepare(context)
    bundle,jobs,bounds,r,raw,graphs,prep=data
    factory=ColumnFactory(jobs,bounds,r,graphs,bundle,raw)
    counted={};structures={}
    for uid,g in sorted(graphs.items()):
        if g.fixed:continue
        if g.sha not in counted:counted[g.sha]=structure_counts(g,r.control_end)
        structures[uid]=counted[g.sha]
    atomic(context.folder/'PRICING_GRAPH_SIZES.json',dict(all_priced_jobs_complete=len(structures)==len(jobs)-sum(g.fixed is not None for g in graphs.values()),rows=structures,
        max_nodes=max(v['nodes'] for v in structures.values()),max_arcs=max(v['arcs'] for v in structures.values())))
    initial,fixed,audit=initial_columns(factory,context.check)
    atomic(context.folder/'INITIAL_COLUMN_AUDIT.json',dict(all_jobs=len(jobs),fixed_jobs=len(fixed),priced_jobs=len(initial),rows=audit,columns_per_movable_job=1,domain_enumeration=False))
    m=Master(factory,initial,fixed,context=context)
    restored=0
    if payload.get('resume_columns'):
        from v42_job_capability import Option
        source=payload['resume_columns'];require(sha(source['path'])==source['sha256'],'RESTORE_COLUMN_DRIFT')
        for record in read(source['path'])['columns']:
            wan=()
            if record['migrated']:
                wan=graphs[record['job_id']].transfers[record['initial_site'],record['destination'],record['transfer_start']].wan
                require(tuple(sorted(wan))==tuple(tuple(x) for x in record['WAN']),'RESTORE_WAN_PROFILE_MISMATCH')
            o=Option(record['start_slot'],record['initial_site'],tuple(tuple(s) for s in record['segments']),
                record['checkpoint'],record['physical_checkpoint_seconds'],record['destination'],record['transfer_start'],
                record['transfer_end'],record['restart_end'],wan)
            c=factory.make(record['job_id'],o);require(c.signature==record['canonical_signature'],'RESTORE_SIGNATURE_MISMATCH')
            restored+=int(m.add(c))
        m.m.update()
    initialization=dict(all_jobs=len(jobs),electrical_slots=96,fixed_jobs=len(fixed),priced_jobs=len(initial),initial_columns=len(initial),
        columns_per_job={u:1 for u in initial},artificial_count=len(m.artificial),physical_RMP=m.physical_size,
        initial_RMP=m.initial_size,global_build_seconds=m.global_build_seconds,model_build_seconds=m.build_seconds,
        initialization_wall_seconds=perf_counter()-started,workers=1,threads=1,full_PR99_event_model=False,
        restored_columns=restored,RMP_after_restoration=m.size())
    atomic(context.folder/'INITIALIZATION.json',initialization)
    latest={};last_snapshot=[0]
    def receipt(value):
        latest.update(value)
        atomic(context.folder/'CG_RECEIPT.json',clean(value))
        if value['iterations']:
            row=value['iterations'][-1]
            progress(context,dict(phase='DW_'+row['status'],**row))
    def snapshot():
        # LP values are diagnostic, never an integer physical plan.
        last_snapshot[0]+=1
        atomic(context.folder/'LP_SNAPSHOT.json',dict(iteration=last_snapshot[0],scientific_acceptance=False,
            artificial_objective=m.artificial_expr.getValue(),phase1_fixed_zero=m.phase1_zero,
            objective=m.m.ObjVal,maximum_linear_violation=m.m.MaxVio,
            lambda_values={s:v.X for s,v in m.variables.items() if v.X>1e-10},
            fractional_lambda_count=sum(1 for v in m.variables.values() if 1e-8<v.X<1.-1e-8)))
    outcome='INCOMPLETE'
    try:
        result=generate(m,check=lambda:context.check(3.),remaining=lambda:context.remaining,receipt=receipt,solve_audit=snapshot,progress=lambda value:progress(context,value))
        outcome='DANTZIG_WOLFE_LP_INFEASIBLE' if result['infeasible'] else ('DANTZIG_WOLFE_LP_CONVERGED' if result['converged'] else 'NONCONVERGED')
    except TimeoutError:
        outcome='EXTERNAL_BUDGET_NONCONVERGED'
    finally:
        # Persist the last partial sweep even when its 25-job flush boundary was
        # not reached. Pending columns are not counted as inserted.
        if latest:atomic(context.folder/'CG_RECEIPT.json',clean(latest))
        scientific_count=sum(x['level'] not in ('PHASE_I','deterministic_tie') for x in latest.get('levels',[]))
        atomic(context.folder/'FINAL_LP.json',clean(dict(outcome=outcome,phase1_zero=m.phase1_zero,
            final_size=m.size(),scientific_acceptance=False,integer_global_optimality=False,
            scientific_levels_converged=[x for x in latest.get('levels',[]) if x['level'] not in ('PHASE_I','deterministic_tie')],
            all_scientific_levels_converged=scientific_count==6,
            DW_LP_converged=scientific_count==6,deterministic_tie_converged=latest.get('converged',False),elapsed_worker_seconds=perf_counter()-started)))
        atomic(context.folder/'GENERATED_COLUMNS.json',dict(columns=[c.record() for c in m.columns.values()]))
        m.dispose()

def validator(candidate,payload):
    return dict(PASS=False,reason='LP_PROTOTYPE_NEVER_ACCEPTED_AS_INTEGER_A1')

def main():
    import sys
    os.environ['PYTHONUTF8']='1'
    for name in GATES:require(read(OUT/name)['PASS'],'FAILED_EXACTNESS_GATE:'+name)
    require(read(OUT/'REDUCED_COST_SIGN_AUDIT.json')['rows'],'EMPTY_RC_AUDIT')
    LOCAL.mkdir(exist_ok=True);folder=LOCAL/'LP';seconds=600.;restore=None;archive_name='executed_source'
    resuming='--resume-io' in sys.argv
    if resuming:
        prior=read(folder/'stage_receipt.json');log=(folder/'worker.log').read_text(encoding='utf8')
        require(prior['timeout_reason']=='WORKER_FAILURE' and 'PermissionError: [WinError 5]' in log,'ONLY_IO_FAILURE_RESUME')
        seconds=600.-prior['total_wall_seconds']-.25
        require(seconds>0,'TOTAL_EXPERIMENT_BUDGET_EXHAUSTED')
        restore=rec(folder/'GENERATED_COLUMNS.json');folder=LOCAL/'LP_io_resume';archive_name='executed_source_io_resume'
        dump('IO_REPAIR_RECEIPT.json',dict(reason='Windows atomic receipt replacement sharing violation',prior=prior,
            resumed_external_seconds=seconds,total_active_wall_cap=600.,cleanup_safety_seconds=.25,
            original_prereg=rec(OUT/'PREREGISTRATION.json'),scientific_algorithm_changed=False,RC_TOL_changed=False,
            legacy_source_changed=False,restore_columns=restore,restore_existing_columns_only=True))
    require(not folder.exists(),'NO_RETRY_MAY_EXPERIMENT')
    sources=[rec(p) for directory in ('v42_dw','v42_compact','v42_boundary','v42_temporal','v42_final','v42_native','v42_may01') for p in sorted((ROOT/directory).glob('*.py'))]+[rec(ROOT/'v42_job_capability.py')]
    archive=LOCAL/archive_name;archive.mkdir(exist_ok=False)
    for row in sources:
        source=Path(row['path']);target=archive/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    dump('SOURCE_MANIFEST_IO_RESUME.json' if resuming else 'SOURCE_MANIFEST.json',dict(base=BASE,prereg=rec(OUT/'PREREGISTRATION.json'),sources=sources,archive=str(archive),legacy_mutation=False))
    candidate,receipt=supervise('A1','v42_native.dw_worker:worker','v42_native.dw_worker:validator',dict(sources=sources,prereg_sha256=sha(OUT/'PREREGISTRATION.json'),resume_columns=restore),folder,seconds=seconds)
    require(candidate is None,'LP_MUST_NOT_ADVANCE_PIPELINE')
    dump('MAY_SUPERVISOR_RECEIPT_IO_RESUME.json' if resuming else 'MAY_SUPERVISOR_RECEIPT.json',receipt);print(receipt,flush=True)

if __name__=='__main__':main()

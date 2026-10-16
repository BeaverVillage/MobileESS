"""Prove the local zero/alias projection on every actual Class, Native=0."""
from pathlib import Path
import sys,argparse,json,time,gzip,pickle,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def audit(source,output):
    import numpy as np
    import gurobipy as gp
    from v42_integration.m_engine import file_record,_write
    from v42_integration.table_v_local_reduction import reduce_block
    from v42_integration.table_v_local_reduction_verify import verify
    from v42_a_stage_domain_v2.stress_backend import materialize
    from v42_integration.d0_resource import native_binding
    source=Path(source).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    roster_path=source/'B1/A1/DW/BLOCK_PRICING_ORACLE_VERIFICATION.json'
    roster=json.loads(roster_path.read_text())['records'];manifest=json.loads((source/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json').read_text())
    if len(roster)!=229 or sum(r['cardinality'] for r in roster)!=1555:
        raise ValueError('CURRENT_229_CLASS_1555_UID_ROSTER_REQUIRED')
    producers=[file_record(ROOT/p) for p in ['v42_integration/table_v_local_reduction.py','v42_integration/table_v_local_reduction_verify.py','tools/audit_v42_2_local_reduction.py']]
    started=time.perf_counter();blocked=[];records=[];raw=output/'BLOCKS';raw.mkdir()
    original_optimize=gp.Model.optimize;original_presolve=gp.Model.presolve
    def no_native(*args,**kwargs):
        blocked.append('NATIVE_ATTEMPT');raise PermissionError('LOCAL_REDUCTION_NATIVE0_OPTIMIZE_AND_PRESOLVE_BLOCKED')
    gp.Model.optimize=no_native;gp.Model.presolve=no_native
    _write(output/'START.json',dict(Native_calls=0,classes=229,source_roster=file_record(roster_path),producers=producers))
    try:
        for index,entry in enumerate(roster):
            rec=entry['external_full_block_cache']
            if file_record(rec['path'])!=rec:raise ValueError('COMPLETE_LOCAL_SOURCE_BLOCK_BYTES_DRIFT')
            with gzip.open(rec['path'],'rb') as stream:original=pickle.load(stream)
            start=time.perf_counter();result=reduce_block(original['snapshot'],original['B'],original['units'])
            independent=verify(original['snapshot'],original['B'],result,original['units'])
            model,objectives=materialize(result['snapshot'],'2025-05-01')
            try:
                model.Params.Threads=1;model.setObjective(objectives[0][1],gp.GRB.MINIMIZE);model.update()
                binding=native_binding(model)
                # materialize independently reads back every A, RHS, Sense,
                # LB, UB and VType; also explicitly read back the objective.
                expected=np.zeros(result['snapshot'].matrix.shape[1])
                for j,c in result['snapshot'].objectives[0].coefficients().items():expected[j]=float(c)
                if not np.array_equal(model.getAttr('Obj'),expected):raise ValueError('NATIVE0_REDUCED_OBJECTIVE_READBACK_DRIFT')
                if model.ObjCon!=float(result['snapshot'].objectives[0].constant):raise ValueError('NATIVE0_REDUCED_OBJECTIVE_CONSTANT_DRIFT')
            finally:model.dispose()
            result['proof']['mathematical_equivalence_independently_verified']=True
            result['independent_verification']=independent;result['native_binding']=binding
            path=raw/(entry['class_id'][:12]+'.pkl.gz')
            with gzip.open(path,'xb',compresslevel=1) as stream:pickle.dump(result,stream,protocol=5)
            p=result['proof'];records.append(dict(class_id=entry['class_id'],cardinality=entry['cardinality'],
                original_block=rec,transformation=file_record(path),source_snapshot_sha=p['source_snapshot_sha'],target_snapshot_sha=p['target_snapshot_sha'],
                before_rows=p['original_rows'],before_columns=p['original_columns'],before_NNZ=p['original_NNZ'],
                after_rows=p['reduced_rows'],after_columns=p['reduced_columns'],after_NNZ=p['reduced_NNZ'],
                independent_verification=independent,native_binding=binding,wall_seconds=time.perf_counter()-start))
            _write(output/'PROGRESS.json',dict(classes_complete=index+1,classes_required=229,Native_calls=0))
            if index%20==0:print('EXACT_LOCAL_NATIVE0_CLASS',index+1,229,flush=True)
    finally:gp.Model.optimize=original_optimize;gp.Model.presolve=original_presolve
    if any(file_record(p['path'])!=p for p in producers):raise ValueError('LOCAL_PROJECTION_PRODUCER_DRIFT_DURING_AUDIT')
    totals={key:sum(r[key] for r in records) for key in ['before_rows','before_columns','before_NNZ','after_rows','after_columns','after_NNZ']}
    proof=dict(schema='V42_2_COMPLETE_LOCAL_POLYTOPE_NATIVE0_V1',status='PASS_ALL_229_LOCAL_POLYTOPES_NOT_GLOBAL_INTEGRATION',
        PASS=True,Native_calls=0,blocked_native_attempts=blocked,classes=229,UIDs=1555,
        source_scientific_sha=manifest['source_sha'],source_case_identity=manifest['identity'],
        source_roster=file_record(roster_path),producers=producers,totals=totals,records=records,
        complete_local_domains_proved=True,all_original_coupling_rows_exact=True,all_original_UID_primitives_exact=True,
        original_integer_FULL_changed=False,finite_column_pool_used=False,Global_LB_issued=False,
        global_master_integration_verified=False,production_solver_used=False,performance_improvement_claimed=False,
        wall_seconds=time.perf_counter()-started)
    if blocked:raise ValueError('NATIVE0_HAD_BLOCKED_NATIVE_ATTEMPT')
    _write(output/'RESULT.json',proof);print('EXACT_LOCAL_NATIVE0_COMPLETE',totals,proof['wall_seconds'],flush=True)
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();audit(args.source,args.output)

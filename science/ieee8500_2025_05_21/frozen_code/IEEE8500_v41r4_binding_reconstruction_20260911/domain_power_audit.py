import sys,hashlib,json,gzip
from types import SimpleNamespace
from collections import Counter
import pandas as pd
import numpy as np
from frozen_binding import HOME,ROOT,DOMAIN,INPUT,context,read,record,save,sha,EXPECTED
from v41r4_ieee8500_adapter import bind_frozen_domain,compile_B1,compile_A1,compile_objectives,original_solver_binding
from dayahead.v41r1 import migration
from dayahead.v41 import objectives
ctx=context();count=Counter();base=read(DOMAIN/'base/V41R1_FULL_CANDIDATE_MANIFEST.json');h=hashlib.sha256();removed=0;perjob=[]
service=read(INPUT/'common_q90_v3/COMMON_DA_SERVICE_AUTHORITY.json');ledger=pd.read_parquet(service['source_ledger']['path'],columns=['job_id','PARTIAL_shared','requested_nodes','requested_gpus'])
ledger.index=ledger.job_id.astype(str);assert set(ledger.index)==set(ctx.references)
assert np.array_equal(ledger.PARTIAL_shared.astype(bool),ledger.requested_gpus<4*ledger.requested_nodes)
with gzip.open(base['candidate_artifact']['path'],'rb') as stream:
    for raw in stream:
        h.update(raw);v=json.loads(raw);uid=v['job_id'];opts=ctx.options[uid];r=ctx.references[uid]
        bset={tuple(o) for o in v['options']};fset={(o.site,o.start,o.end,o.checkpoint,o.transfer_start,o.transfer_end,o.initial_site) for o in opts};added=fset-bset
        assert bset<=fset and len(fset)==len(opts)
        row=dict(job_id=uid,base=len(bset),restored=len(added),total=len(opts),temporal=len({o.start for o in opts})>1,spatial=len({o.site for o in opts})>1,migration=any(o.migrated for o in opts),partial_shared=bool(ledger.loc[uid,'PARTIAL_shared']))
        count.update(reference_jobs=1,base_candidates=row['base'],restored_temporal_candidates=row['restored'],total_candidates=row['total'],temporal_option_jobs=int(row['temporal']),spatial_option_jobs=int(row['spatial']),migration_option_jobs=int(row['migration']),PARTIAL_shared_jobs=int(row['partial_shared']))
        # Hash decoded Option tuples serialized with the original manifest format;
        # no file is regenerated and no candidate is added or filtered.
        serialized=(json.dumps(dict(job_id=uid,options=[(o.site,o.start,o.end,o.checkpoint,o.transfer_start,o.transfer_end,o.initial_site) for o in opts]),separators=(',',':'))+'\n').encode()
        assert hashlib.sha256(serialized).hexdigest()==ctx.candidate_rows[uid]['sha256']
        perjob.append(row)
assert h.hexdigest()==base['candidate_set_SHA']
expected=dict(reference_jobs=708,temporal_option_jobs=39,spatial_option_jobs=364,migration_option_jobs=364,restored_temporal_candidates=16392,base_candidates=1325555,total_candidates=1341947,PARTIAL_shared_jobs=361)
assert dict(count)==expected
names=[row[0] for row in read(HOME/'IEEE8500_B1/DECISION_VARIABLES.json')]+['rho_max']
view=SimpleNamespace(update=lambda:None,getVars=lambda:[SimpleNamespace(VarName=n) for n in names])
with bind_frozen_domain(ctx,HOME/'DOMAIN_BINDING_AUDIT'):
    boundary=migration.model_boundary(view,ctx.reference,ctx.options,96)
    b1=compile_B1(ctx);a1=compile_A1(ctx);objective=compile_objectives(ctx)
    assert objective.__code__ is objectives.evaluate.__code__
    assert all(b1.__globals__['options'](r,ctx.capacity,ctx.wan,ctx.elapsed)==a1.__globals__['options'](r,ctx.capacity,ctx.wan,ctx.elapsed)==objective.__globals__['options'](r,ctx.capacity,ctx.wan,ctx.elapsed) for r in ctx.reference)
np.savez_compressed(HOME/'RECONSTRUCTED_AIDC_POWER_TABLES.npz',**ctx.tables)
original_power=HOME.parent/'IEEE8500_operating_point_20260911/V41R4_B0_AIDC_POWER_UNCHANGED.npz'
with np.load(original_power,allow_pickle=False) as z:diffs={k:float(np.max(np.abs(z[k]-ctx.power[k]))) for k in ['gpu','it','pcc','qcc']}
assert max(diffs.values())==0
budget_receipts=[]
for role in ['B1','B3_A1']:
    with original_solver_binding(ctx,role,HOME/role) as fn:
        from dayahead.v41r1 import bounded_solver,feasible_seed
        from v41r4_loop_budget import engine
        assert bounded_solver.BoundedLex is engine and ctx.v41_policy_budget.total==14400
        assert ctx.v41_policy_budget.loop_started is None
        budget_receipts.append(dict(role=role,seconds=14400,original_LoopBoundedLex_dispatch=True,solver_called=False))
save('DOMAIN_POWER_BINDING_PASS.json',dict(status='PASS',expected=expected,observed=dict(count),candidate_stream_sha256=EXPECTED,all_decoded_Option_rows_exact_original_bytes=True,candidate_order_preserved=True,base_options_removed=0,regenerated_candidate_files=0,B1_A1_objectives_share_same_frozen_option_reader=True,objectives_original_code_object_identity=True,installed_GPU=780,capacity_vector=list(ctx.capacity.site_capacity.values()),power_max_absolute_difference_from_frozen_operating_point_input=diffs,power_comparison_source=record(original_power),PARTIAL_shared_source=service['source_ledger'],PARTIAL_shared_semantics='Original aggregate GPU slots; no filtering or extra power injection',boundary=boundary,budget_binding=budget_receipts,optimization_calls=0,Fresh_calls=0))
save('DOMAIN_PER_JOB_AUDIT.json',perjob)
print(json.dumps(dict(status='DOMAIN_POWER_BINDING_PASS',counts=dict(count),power_difference=diffs)),flush=True)

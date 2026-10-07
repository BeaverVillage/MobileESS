"""Static complete producer/active native incidence audit; never optimize."""
from time import perf_counter
from dataclasses import replace
import numpy as np
import gzip,pickle
from v42_pr134_b1.common import atomic,record,read,digest
from .setup import OUT,HISTORY,STATIC,DAY,load_initial
from .producer import row_partition,native_block,complete_graph


def qualify():
    before=perf_counter()
    snapshot,descriptor,data,domains,ledger,axes,global_variables=load_initial()
    global_rows,local_rows,owned=row_partition(snapshot,descriptor,global_variables,axes.values())
    records=[];coupling_rows=list(axes.values())
    for i,(key,members) in enumerate(sorted(data[7]['classes'].items())):
        cols=sorted(j for j,c in owned.items() if c==key)
        rows=local_rows.get(key,())
        current,B,constant,_=native_block(data,key,data[5][members[0]],tuple(axes),averaged=False)
        actual=snapshot.matrix[list(rows)][:,cols].tocsr()
        if actual.shape!=current.matrix.shape:raise ValueError('ACTIVE_LOCAL_ROW_COLUMN_AXES:'+key+':'+str((actual.shape,current.matrix.shape)))
        difference=actual-current.matrix;difference.eliminate_zeros()
        if difference.nnz:raise ValueError('ACTIVE_HARD_LOCAL_COEFFICIENT_DRIFT:'+key)
        if any(not np.array_equal(getattr(snapshot,n)[list(rows)],getattr(current,n)) for n in ('senses','rhs')):
            raise ValueError('ACTIVE_LOCAL_ROW_AUTHORITY_DRIFT:'+key)
        if any(not np.array_equal(getattr(snapshot,n)[cols],getattr(current,n)) for n in ('lower','upper')):
            raise ValueError('ACTIVE_LOCAL_BOUND_AUTHORITY_DRIFT:'+key)
        difference=snapshot.matrix[coupling_rows][:,cols]-B;difference.eliminate_zeros()
        if difference.nnz:raise ValueError('ORIGINAL_GPU_RUNTIME_WAN_ACTIVE_COUPLING_DRIFT:'+key)
        domain=domains[members[0]]
        full=complete_graph(data[1][members[0]],domain,members[0] in data[7]['preserve_singleton_mixed_flow'])
        complete,CB,Cconstant,units=native_block(data,key,full,tuple(axes))
        # Every native primitive must retain a finite original/projected box.
        if np.any(~np.isfinite(complete.lower)) or np.any(~np.isfinite(complete.upper)):
            raise ValueError('COMPLETE_NATIVE_LOCAL_BOX_UNBOUNDED')
        cache=STATIC/'FULL_BLOCKS'/(key+'.pkl.gz');cache.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(cache,'wb',compresslevel=1) as stream:
            pickle.dump(dict(snapshot=complete,B=CB,constant=Cconstant,units=units,graph=full),stream,protocol=5)
        records.append(dict(class_id=key,cardinality=len(members),PASS=True,external_full_block_cache=record(cache),
            original_active_rows=len(rows),original_active_columns=len(cols),
            full_physical_STAY=len(domain.stays),full_physical_migration=domain.count-len(domain.stays),
            full_compact_blocks=len(domain.blocks),complete_graph_sha256=full.sha,
            complete_local_snapshot_sha256=complete.fingerprint(),
            complete_coupling_sha256=digest(dict(shape=CB.shape,indptr=CB.indptr,indices=CB.indices,data=CB.data)),
            complete_native_local_rows=complete.matrix.shape[0],complete_native_primitive_columns=complete.matrix.shape[1],
            complete_nnz=complete.matrix.nnz+CB.nnz,
            native_source_builder='v42_root.native.local_units / v42_root.factor / v42_compact.formulation',
            all_fractional_native_finish_directions=True,physical_path_variables=0,
            optional_lanes_sum_projection_LP_only=True))
        print('PHASE1_STATIC_CLASS',i+1,len(data[7]['classes']),key[:12],complete.matrix.shape,flush=True)
    result=dict(PASS=True,scope='COMPLETE_NATIVE_LOCAL_PRODUCER_AND_ORIGINAL_ACTIVE_COEFFICIENT_IDENTITY',
        dates=[DAY],classes=len(records),records=records,global_rows=len(global_rows),
        hard_local_rows=sum(len(r) for r in local_rows.values()),global_variables=global_variables,
        original_active_columns=snapshot.matrix.shape[1],original_active_rows=snapshot.matrix.shape[0],
        complete_STAY=sum(r['full_physical_STAY'] for r in records),
        complete_migration_paths=sum(r['full_physical_migration'] for r in records),
        no_scientific_domain_change=True,pricing_closure_claimed=False,native_optimize_calls=0,
        build_wall_seconds=perf_counter()-before,producer=record(__file__),
        native_builders=[record(OUT.parents[1]/p) for p in ('v42_a_stage_phase1/producer.py','v42_root/native.py',
            'v42_root/factor.py','v42_compact/formulation.py','v42_sparse/runtime.py')])
    from .backend import assemble_original
    rebuilt,_,_,_,_,_=assemble_original(snapshot,global_rows,global_variables,axes,data)
    column_order=list(range(global_variables))+[j for key in sorted(data[7]['classes'])
        for j in sorted(k for k,c in owned.items() if c==key)]
    row_order=list(global_rows)+[j for key in sorted(data[7]['classes']) for j in local_rows.get(key,())]
    expected=snapshot.matrix[row_order][:,column_order]
    delta=expected-rebuilt.matrix;delta.eliminate_zeros()
    if delta.nnz or any(not np.array_equal(getattr(snapshot,k)[column_order],getattr(rebuilt,k)) for k in ('lower','upper')):
        raise ValueError('REASSEMBLED_ORIGINAL_COEFFICIENT_OR_BOUND_DRIFT')
    if any(not np.array_equal(getattr(snapshot,k)[row_order],getattr(rebuilt,k)) for k in ('senses','rhs')):
        raise ValueError('REASSEMBLED_ORIGINAL_ROW_DRIFT')
    inverse={old:new for new,old in enumerate(column_order)}
    for objective in snapshot.objectives:
        actual=rebuilt.objective(objective.name)
        expected={inverse[j]:c for j,c in objective.coefficients().items()}
        if expected!=actual.coefficients() or objective.constant!=actual.constant:
            raise ValueError('REASSEMBLED_ORIGINAL_OBJECTIVE_DRIFT:'+objective.name)
    result['reassembled_initial_original_matrix_and_all_four_objectives_exactly_equal']=True
    result['build_wall_seconds']=perf_counter()-before
    result['backend_source']=record(OUT.parents[1]/'v42_a_stage_phase1/backend.py')
    atomic(OUT/'BLOCK_PRICING_ORACLE_VERIFICATION.json',result)
    return result

if __name__=='__main__':qualify()

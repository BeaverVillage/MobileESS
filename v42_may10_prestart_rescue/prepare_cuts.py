"""Create independently matched window cuts; no optimize calls."""
import gzip,pickle,time,shutil
import numpy as np
from v42_pr134_b1.common import atomic,read,record
from v42_a_stage_phase1.core import primal_replay
from .cuts import window_cuts,append_cuts,shift_cover_cuts
from .isolation import OUT,STATIC,assert_write_path,require_large_resource_isolation
from .inspect_saved import BASELINE


def externalize_cut_vectors(receipt):
    groups=('window_cuts','shift_integer_cover_cuts')
    cuts=[c for key in groups for c in receipt.get(key,[])]+[receipt['inherited_global_LB_cut']]
    path=assert_write_path(STATIC/'CUT_ORIGINAL_COLUMNS.npz')
    np.savez_compressed(path,**{f'cut_{i}':np.asarray(c['columns'],dtype=np.int64) for i,c in enumerate(cuts)})
    source=record(path)
    for i,c in enumerate(cuts):
        c['columns']=dict(array=f'cut_{i}',count=len(c['columns']),source=source)
    return receipt


def run():
    require_large_resource_isolation();start=time.perf_counter()
    with gzip.open(STATIC/'REBUILT_CONTEXT.pkl.gz','rb') as stream:ctx=pickle.load(stream)
    query=ctx['query'];reduction=ctx['reduction']
    cuts,stats=window_cuts(ctx['physical_state'],query)
    # Preserve the first, ineffective GPU-window-only candidate exactly.
    previous=OUT/'VALID_INEQUALITY_VERIFICATION.json'
    if previous.exists() and not (OUT/'VALID_INEQUALITY_GPU_ONLY_ATTEMPT0.json').exists():
        shutil.copyfile(previous,assert_write_path(OUT/'VALID_INEQUALITY_GPU_ONLY_ATTEMPT0.json'))
        shutil.copyfile(STATIC/'STRENGTHENED_SNAPSHOT.pkl.gz',assert_write_path(STATIC/'GPU_ONLY_ATTEMPT0.pkl.gz'))
    shift_row=read(BASELINE/'P2/PRESTART_RELOCATION/LOCK_REBUILD.json')['lock_rows']['shift_magnitude']
    covers=shift_cover_cuts(query,shift_row,reduction.kept_columns)
    cuts.extend(covers)
    # A valid existing *global* bound is an additional exact lower-bound row.
    # It does not count as a newly discovered mathematical bound improvement.
    certificate=read(BASELINE/'P2/PRESTART_RELOCATION/GLOBAL_GAP_ACCEPTANCE.json')
    native=read(BASELINE/'P2/PRESTART_RELOCATION/NATIVE/NATIVE_RESULT.json')
    compiled=read(BASELINE/'P2/PRESTART_RELOCATION/NATIVE/INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')
    if not (certificate['full_domain_verified'] and certificate['bound_independently_audited']
        and certificate['full_current_query_covers_all_native_open_branches'] and native['ObjBound']==2
        and native['native_error'] is None and compiled['PASS']
        and compiled['original_snapshot_sha256']==query.fingerprint()):
        raise ValueError('INHERITED_GLOBAL_LB2_AUTHORITY_NOT_VERIFIED')
    objective=query.objective('prestart_relocation')
    if objective.constant!=0 or any(v!=1 for v in objective.coefficients().values()):
        raise ValueError('ORIGINAL_PRESTART_COUNT_OBJECTIVE_REQUIRED')
    cuts.append(dict(columns=tuple(objective.coefficients()),lower=2,
        proof=dict(kind='PREVIOUS_CERTIFIED_FULL_DOMAIN_LB',new_global_bound_claimed=False,
            source=record(BASELINE/'P2/PRESTART_RELOCATION/GLOBAL_GAP_ACCEPTANCE.json'),
            source_query_sha256=query.fingerprint(),LB=2,objective_integer_count=True)))
    mapping=np.full(query.matrix.shape[1],-1,dtype=np.int64);mapping[reduction.kept_columns]=np.arange(len(reduction.kept_columns))
    strengthened=append_cuts(reduction.compact,cuts,mapping)
    witness=primal_replay(strengthened,ctx['compact_warm'])
    if not witness['PASS']:raise ValueError('PROVED_CUT_REJECTS_ORIGINAL_VALIDATED_UB60')
    with gzip.open(assert_write_path(STATIC/'STRENGTHENED_SNAPSHOT.pkl.gz'),'wb') as stream:
        pickle.dump(strengthened,stream,protocol=5)
    receipt=dict(PASS=True,
        source_query_sha256=query.fingerprint(),actual_window_stats=stats,
        window_cuts=[c for c in cuts[:-1] if c not in covers],shift_integer_cover_cuts=covers,
        inherited_global_LB_cut=cuts[-1],
        UB60_original_point_replay=witness,original_objectives_and_tolerances_preserved=True,
        rows=strengthened.matrix.shape[0],cols=strengthened.matrix.shape[1],nnz=strengthened.matrix.nnz,
        snapshot_sha256=strengthened.fingerprint(),snapshot=record(STATIC/'STRENGTHENED_SNAPSHOT.pkl.gz'),
        preparation_seconds=time.perf_counter()-start,native_optimization_calls=0)
    atomic(assert_write_path(OUT/'VALID_INEQUALITY_VERIFICATION.json'),externalize_cut_vectors(receipt))
    print('ACTUAL_PRESTART_CUTS_VERIFIED',stats,strengthened.matrix.shape,strengthened.matrix.nnz,flush=True)


if __name__=='__main__':run()

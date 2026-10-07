"""Recover original native integrality; never integerize the LP SUM kernel."""
from dataclasses import replace
import numpy as np
from v42_a_stage_phase1 import producer

def typed_block(data,key,graph,axes):
    captured=[];original=producer.snapshot_of
    def capture(model,objectives):
        s=original(model,objectives);captured.append(s.vtypes.copy());return s
    producer.snapshot_of=capture
    try:s,B,c,u=producer.native_block(data,key,graph,axes,averaged=False)
    finally:producer.snapshot_of=original
    if len(captured)!=1 or len(captured[0])!=s.matrix.shape[1]:raise ValueError('ORIGINAL_NATIVE_TYPES_NOT_CAPTURED')
    return replace(s,vtypes=captured[0]),B,c,u

def restore_types(state,global_types):
    ref=state['reference'];types=np.full(ref.matrix.shape[1],'C');types[:state['n']]=global_types
    cursor=len(state['grows']);proofs=[]
    for key,m in sorted(state['metas'].items()):
        uid=state['data'][7]['classes'][key][0]
        s,B,c,u=typed_block(state['data'],key,state['data'][5][uid],tuple(state['axes']))
        cols=m['reference_columns'];rows=list(range(cursor,cursor+s.matrix.shape[0]));cursor+=s.matrix.shape[0]
        delta=s.matrix-ref.matrix[rows][:,cols];delta.eliminate_zeros()
        if delta.nnz or not np.array_equal(s.rhs,ref.rhs[rows]) or not np.array_equal(s.senses,ref.senses[rows]) or not np.array_equal(s.lower,ref.lower[cols]) or not np.array_equal(s.upper,ref.upper[cols]):raise ValueError('INTEGER_RESTORE_CHANGED_ORIGINAL_NATIVE_EQUATIONS')
        types[cols]=s.vtypes;proofs.append(dict(class_id=key,PASS=True,integer_columns=int(np.count_nonzero(s.vtypes!='C')),original_rows=s.matrix.shape[0]))
    if cursor!=ref.matrix.shape[0]:raise ValueError('INTEGER_RESTORE_ROW_COVERAGE_FAIL')
    return replace(ref,vtypes=types).require(),dict(PASS=True,proofs=proofs,original_rows_coefficients_boxes_objectives_preserved=True,
        integer_migration_family='original individual binary migration lanes retained',STAY='original integer histogram counts',
        LP_SUM_kernel_not_integerized=True,integer_columns=int(np.count_nonzero(types!='C')))

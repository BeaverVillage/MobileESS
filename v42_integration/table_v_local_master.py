"""Compose proved complete local projections with every Hybrid Master row."""
from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import gzip,json,pickle
import numpy as np
import scipy.sparse as sp
from .m_engine import _write,file_record
from .table_v_local_reduction import reduce_block,binary64,fold_row
from .table_v_local_reduction_verify import verify
from .table_v_compression_verify import csr_equal


def map_matrix(matrix,mapping,width):
    """Sparse coordinate projection, summing collisions only over rationals."""
    coo=matrix.tocoo();targets=np.asarray(mapping)[coo.col];mask=targets>=0
    rows=coo.row[mask];cols=targets[mask];values=coo.data[mask]
    order=np.lexsort((cols,rows));rows=rows[order];cols=cols[order];values=values[order]
    starts=np.r_[0,np.flatnonzero((rows[1:]!=rows[:-1])|(cols[1:]!=cols[:-1]))+1]
    if len(values)==0:return sp.csr_matrix((matrix.shape[0],width))
    ends=np.r_[starts[1:],len(values)];out=np.empty(len(starts))
    singleton=ends-starts==1;out[singleton]=values[starts[singleton]]
    for k in np.flatnonzero(~singleton):out[k]=binary64(sum((Fraction(float(x)) for x in values[starts[k]:ends[k]]),Fraction(0)))
    nonzero=out!=0
    return sp.csr_matrix((out[nonzero],(rows[starts[nonzero]],cols[starts[nonzero]])),shape=(matrix.shape[0],width))


def lift_compact(state,point):
    info=state.get('_local_reduction')
    if info is None:return np.asarray(point)
    mapping=info['old_to_new'];point=np.asarray(point)
    if point.shape!=(state['compact'].matrix.shape[1],):raise ValueError('LOCAL_MASTER_LIFT_POINT_AXIS')
    result=np.zeros(len(mapping),dtype=point.dtype);used=mapping>=0;result[used]=point[mapping[used]]
    return result


def _verify_global(source,target,mapping,prefix):
    if not csr_equal(source[:,:prefix],target[:,:prefix]):raise ValueError('LOCAL_PROJECTION_GLOBAL_PREFIX_DRIFT')
    old=source[:,prefix:].tocsr();new=target[:,prefix:].tocsr();localmap=mapping[prefix:].copy()
    localmap[localmap>=0]-=prefix
    touched=np.flatnonzero(np.diff(old.indptr)>0)
    if np.any(np.diff(new.indptr)[np.diff(old.indptr)==0]):raise ValueError('INVENTED_GLOBAL_LOCAL_COUPLING')
    for i in touched:
        expected=fold_row(old,int(i),localmap)
        a,b=new.indptr[i:i+2];actual={int(j):Fraction(float(c)) for j,c in zip(new.indices[a:b],new.data[a:b])}
        if expected!=actual:raise ValueError('EVERY_ORIGINAL_GLOBAL_COUPLING_ROW_MUST_LIFT_EXACTLY')
    return dict(PASS=True,global_prefix_all_coefficients_checked=True,
        global_rows=source.shape[0],global_rows_with_local_support=len(touched),
        every_global_local_coefficient_checked=True,RHS_and_senses_unchanged=True)


def reduce_state(state,output):
    from v42_a_stage_compact_rowgen.assembly import partition
    from v42_a_stage_compact_rowgen.prepare import shift
    from v42_a_stage_domain_v2.lexstage import Objective
    from v42_a_stage_phase1.core import primal_replay
    if '_local_reduction' in state:raise ValueError('LOCAL_MASTER_PROJECTION_ALREADY_APPLIED')
    output=Path(output);source=state['compact'];ng=len(state['grows']);prefix=state['n']
    if tuple(state['grows'])!=tuple(range(ng)) or state['reference'].fingerprint()!=source.fingerprint():
        raise ValueError('COMPLETE_CLASS_REFERENCE_AND_GLOBAL_PREFIX_REQUIRED')
    local,_=partition(source,state['metas'],state['grows']);axis_rows=list(state['axes'].values())
    before=json.loads((output/'BLOCK_PRICING_ORACLE_VERIFICATION.json').read_text())
    roster={r['class_id']:r for r in before['records']}
    if set(roster)!=set(state['metas']):raise ValueError('EVERY_COMPLETE_CLASS_REQUIRED_BEFORE_PROJECTION')
    root=output/'REDUCED_FULL_BLOCKS';root.mkdir(exist_ok=False)
    newmap=np.full(source.matrix.shape[1],-2,dtype=np.int64);newmap[:prefix]=np.arange(prefix)
    parts=[];Bs=[];lower=[source.lower[:prefix]];upper=[source.upper[:prefix]];senses=[source.senses[:ng]];rhs=[source.rhs[:ng]]
    newmetas={};newroster=[];certificates=[];newunits=[];selected=list(range(prefix));offset=prefix;covered=set()
    for key,m in sorted(state['metas'].items(),key=lambda pair:pair[1]['offset']):
        want=roster[key];receipt=want['external_full_block_cache']
        if file_record(receipt['path'])!=receipt:raise ValueError('COMPLETE_LOCAL_BLOCK_DRIFT_BEFORE_PROJECTION')
        with gzip.open(receipt['path'],'rb') as stream:block=pickle.load(stream)
        cols=np.arange(m['offset'],m['offset']+m['width']);rows=np.asarray(local[key],dtype=np.int64)
        snap=replace(source,matrix=source.matrix[rows][:,cols].tocsr(),lower=source.lower[cols],upper=source.upper[cols],
            senses=source.senses[rows],rhs=source.rhs[rows],vtypes=source.vtypes[cols],objectives=block['snapshot'].objectives).require()
        if snap.fingerprint()!=block['snapshot'].fingerprint() or not csr_equal(source.matrix[axis_rows][:,cols],block['B']):
            raise ValueError('ACTUAL_MASTER_LOCAL_BLOCK_OR_COUPLING_NOT_EQUAL_TO_COMPLETE_CACHE')
        transformed=reduce_block(snap,block['B'],block['units']);independent=verify(snap,block['B'],transformed,block['units'])
        reduced=transformed['snapshot'];mapping=transformed['mapping'];lifted=mapping.copy();lifted[lifted>=0]+=offset
        newmap[cols]=lifted;selected.extend(cols[transformed['representatives']].tolist());covered.update(map(int,rows))
        parts.append(reduced.matrix);lower.append(reduced.lower);upper.append(reduced.upper);senses.append(reduced.senses);rhs.append(reduced.rhs)
        units=transformed['units'];path=root/(key[:12]+'.pkl.gz')
        with gzip.open(path,'xb',compresslevel=1) as stream:pickle.dump(dict(block,snapshot=reduced,B=transformed['B'],units=units),stream,protocol=5)
        proofpath=root/(key[:12]+'.projection.pkl.gz')
        with gzip.open(proofpath,'xb',compresslevel=1) as stream:pickle.dump(transformed,stream,protocol=5)
        newroster.append(dict(want,external_full_block_cache=file_record(path),complete_local_snapshot_sha256=reduced.fingerprint(),
            exact_original_polytope_projection=file_record(proofpath)))
        newmetas[key]=dict(m,offset=offset,width=reduced.matrix.shape[1],kernel_columns=reduced.matrix.shape[1],
            units=units,reference_units=units,reference_columns=list(range(offset,offset+reduced.matrix.shape[1])),points=[],candidates=[])
        newunits.extend(shift(u,offset) for u in units)
        certificates.append(dict(class_id=key,original_block=receipt,projection=file_record(proofpath),verification=independent,
            before_rows=snap.matrix.shape[0],after_rows=reduced.matrix.shape[0],before_columns=snap.matrix.shape[1],after_columns=reduced.matrix.shape[1]))
        offset+=reduced.matrix.shape[1]
    if np.any(newmap==-2) or covered!=set(range(ng,source.matrix.shape[0])):
        raise ValueError('LOCAL_PROJECTION_MUST_COVER_EVERY_SOURCE_COLUMN_AND_LOCAL_ROW')
    global_part=sp.hstack((source.matrix[:ng,:prefix],map_matrix(source.matrix[:ng,prefix:],
        np.where(newmap[prefix:]>=0,newmap[prefix:]-prefix,-1),offset-prefix)),format='csr')
    global_proof=_verify_global(source.matrix[:ng],global_part,newmap,prefix)
    local_part=sp.block_diag(parts,format='csr')
    matrix=sp.vstack((global_part,sp.hstack((sp.csr_matrix((local_part.shape[0],prefix)),local_part),format='csr')),format='csr')
    objectives=[]
    for objective in source.objectives:
        terms=defaultdict(Fraction)
        for j,c in objective.coefficients().items():
            if newmap[j]>=0:terms[int(newmap[j])]+=c
        for c in terms.values():binary64(c)
        objectives.append(replace(objective,terms=tuple((j,c) for j,c in sorted(terms.items()) if c)))
    reduced=replace(source,matrix=matrix,lower=np.concatenate(lower),upper=np.concatenate(upper),senses=np.concatenate(senses),
        rhs=np.concatenate(rhs),vtypes=np.full(offset,'C'),objectives=tuple(objectives)).require()
    initial=state['prior_compact'][selected]
    lifted_initial=np.zeros(len(newmap));valid=newmap>=0;lifted_initial[valid]=initial[newmap[valid]]
    if not np.array_equal(lifted_initial,state['prior_compact']):raise ValueError('CONSTRUCTED_LOCAL_WITNESS_NOT_EXACTLY_IN_PROVED_SUBSPACE')
    local_snapshot=replace(reduced,matrix=reduced.matrix[ng:].tocsr(),senses=reduced.senses[ng:],rhs=reduced.rhs[ng:])
    witness=primal_replay(local_snapshot,initial)
    if not witness['PASS']:raise ValueError('REDUCED_LOCAL_CANONICAL_WITNESS_REPLAY_FAILED')
    descriptor=dict(state['reference_descriptor'],units=newunits)
    proof=dict(PASS=True,scope='COMPLETE_HYBRID_LP_EXACT_LOCAL_PROJECTIONS',original_snapshot_sha=source.fingerprint(),
        reduced_snapshot_sha=reduced.fingerprint(),before_rows=source.matrix.shape[0],before_columns=source.matrix.shape[1],before_NNZ=source.matrix.nnz,
        after_rows=matrix.shape[0],after_columns=matrix.shape[1],after_NNZ=matrix.nnz,global_projection=global_proof,
        all_global_rows_RHS_senses_and_global_boxes_preserved=True,global_prefix=prefix,global_rows=ng,
        full_pricing_domain_coverage_preserved=True,finite_column_pool_used=False,UIDs=sum(m['N'] for m in state['metas'].values()),
        classes=len(certificates),local_certificates=certificates,local_witness=witness,original_integer_FULL_changed=False,
        physical_domains_changed=False,Global_LB_issued=False,actual_pricing_certificate_required=True,
        production_performance_improvement_claimed=False,Native_calls=0)
    path=output/'LOCAL_POLYTOPE_MASTER_EQUIVALENCE.json';_write(path,proof)
    _write(output/'BLOCK_PRICING_ORACLE_BEFORE_LOCAL_REDUCTION.json',before)
    _write(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json',dict(before,records=newroster,
        producer='EXACT_COMPLETE_LOCAL_POLYTOPE_ZERO_ALIAS_PROJECTION',local_master_equivalence=file_record(path)))
    equivalent=dict(state['_table_v']['equivalent'],class_sum_source_reference_LP_sha=source.fingerprint(),
        source_reference_LP_sha=reduced.fingerprint(),compressed_size=dict(rows=matrix.shape[0],columns=matrix.shape[1],NNZ=matrix.nnz,binary=0),
        local_polytope_projection=file_record(path))
    return dict(state,compact=reduced,reference=reduced,metas=newmetas,reference_descriptor=descriptor,scientific_descriptor=descriptor,
        prior_original=initial,prior_compact=initial,projection_proofs=state['projection_proofs']+[proof],
        _local_reduction=dict(source=source,old_to_new=newmap,selected_columns=np.asarray(selected),proof=proof),
        _table_v=dict(state['_table_v'],equivalent=equivalent))

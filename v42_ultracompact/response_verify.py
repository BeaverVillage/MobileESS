"""Independent exact extension/projection proof for stored affine response rows.

This verifier does not import the producer.  It reconstructs each removed
inequality, all retained rows, the new equality and its exact finite endpoints
from the baseline CSR and metadata.  Bounds on Y imply the old inequalities;
every old feasible x extends by Y=a*x.  All original integer coordinates are
unchanged, so the same two maps prove LP and integer projection equivalence.
"""
from fractions import Fraction
import re
from time import perf_counter

import numpy as np

_SOURCE_VOLTAGE=re.compile(r'voltage_(lower|upper)\[(\d+),(\d+)\]')


def _require(value,reason):
    if not value:raise ValueError(reason)


def _same_values(left,right):
    return np.array_equal(np.asarray(left),np.asarray(right))


def verify_response_reformulation(result):
    began=perf_counter();A=result.original.tocsr(copy=False);d=result.original_data
    B=result.A.tocsr(copy=False);e=result.d;plans=result.plans;n=A.shape[1];count=len(plans)
    _require(A.has_canonical_format and B.has_canonical_format,'RESPONSE_PROOF_NONCANONICAL_CSR')
    _require(np.isfinite(A.data).all() and np.isfinite(B.data).all(), 'RESPONSE_PROOF_NONFINITE_COEFFICIENT')
    _require(set(d)==set(e),'RESPONSE_PROOF_METADATA_KEY_DRIFT')
    for key in ('names','types','lower','upper','objective'):
        _require(len(e[key])==n+count and _same_values(e[key][:n],d[key]),
            'RESPONSE_PROOF_ORIGINAL_COLUMN_METADATA_DRIFT:'+key)
    for key in set(d)-{'names','types','lower','upper','objective','rhs','sense','row_names'}:
        _require(_same_values(d[key],e[key]),'RESPONSE_PROOF_UNCHANGED_METADATA_DRIFT:'+key)
    _require(len(set(map(str,e['names'])))==len(e['names']),'RESPONSE_PROOF_COLUMN_NAME_COLLISION')
    gone=set();references=[];expected_names=[];lower_values=[];upper_values=[]
    for k,p in enumerate(plans):
        _require(p['kind']=='STORED_TWO_SIDED_VOLTAGE_AFFINE_RANGE','RESPONSE_PROOF_UNSUPPORTED_PLAN')
        rows=p['rows']
        _require(len(rows)>=2 and len(set(rows))==len(rows) and not gone.intersection(rows),
            'RESPONSE_PROOF_REMOVED_ROW_WITNESS_REUSED')
        _require(all(type(i) is int and 0<=i<A.shape[0] for i in rows), 'RESPONSE_PROOF_REMOVED_ROW_AXIS')
        reference=p['reference_row'];_require(reference in rows,'RESPONSE_PROOF_REFERENCE_ROW_AXIS')
        a,b=A.indptr[reference:reference+2];columns=A.indices[a:b];weights=A.data[a:b]
        _require(len(columns)>0 and np.all(weights!=0),'RESPONSE_PROOF_EMPTY_OR_EXPLICIT_ZERO_EXPRESSION')
        lows=[];highs=[];slots=set()
        for i in rows:
            match=_SOURCE_VOLTAGE.fullmatch(str(d['row_names'][i]))
            _require(match is not None,'RESPONSE_PROOF_ORIGINAL_ROW_FAMILY')
            slots.add(int(match[2]));side=match[1]
            _require(d['sense'][i]==('>' if side=='lower' else '<'), 'RESPONSE_PROOF_ORIGINAL_SENSE')
            x,y=A.indptr[i:i+2]
            _require(_same_values(A.indices[x:y],columns) and _same_values(A.data[x:y],weights),
                'RESPONSE_PROOF_ORIGINAL_EXPRESSION_NOT_IDENTICAL')
            _require(np.isfinite(d['rhs'][i]),'RESPONSE_PROOF_NONFINITE_ORIGINAL_RHS')
            (lows if side=='lower' else highs).append(i)
        _require(len(slots)==1 and p['slot']==next(iter(slots)) and lows and highs,
            'RESPONSE_PROOF_TWO_SIDED_SINGLE_SLOT_REQUIRED')
        low=max(Fraction(float(d['rhs'][i])) for i in lows)
        high=min(Fraction(float(d['rhs'][i])) for i in highs)
        _require(low<=high,'RESPONSE_PROOF_INFEASIBLE_ORIGINAL_RANGE')
        _require(p['lower_row'] in lows and Fraction(float(d['rhs'][p['lower_row']]))==low
            and p['upper_row'] in highs and Fraction(float(d['rhs'][p['upper_row']]))==high,
            'RESPONSE_PROOF_BOUND_WITNESS_DRIFT')
        column=n+k;name=f'response_voltage_shared[{next(iter(slots))},{reference}]'
        _require(p['column']==column and p['name']==name and p['row_name']==name.replace('[','_binding[',1),
            'RESPONSE_PROOF_NEW_AXIS_IDENTITY')
        _require(str(e['names'][column])==name and e['types'][column]=='C'
            and e['objective'][column]==0,'RESPONSE_PROOF_NEW_HELPER_DOMAIN_OR_OBJECTIVE')
        _require(np.isfinite(e['lower'][column]) and np.isfinite(e['upper'][column])
            and Fraction(float(e['lower'][column]))==low and Fraction(float(e['upper'][column]))==high,
            'RESPONSE_PROOF_STORED_BOUND_NOT_EXACT')
        width=len(columns);before=len(rows)*width;after=width+1
        _require(after<before and (width+1)**2<len(rows)*width**2, 'RESPONSE_PROOF_NONBENEFICIAL_REFORMULATION')
        for key,value in (('expression_nnz',width),('nnz_before',before),('nnz_after',after),
            ('fill_proxy_before',len(rows)*width**2),('fill_proxy_after',(width+1)**2)):
            _require(p[key]==value,'RESPONSE_PROOF_STRUCTURAL_COST_DRIFT:'+key)
        gone.update(rows);references.append(reference);expected_names.append(p['row_name'])
        lower_values.append(low);upper_values.append(high)
    kept=np.asarray([i for i in range(A.shape[0]) if i not in gone],dtype=np.int64)
    _require(B.shape==(len(kept)+count,n+count),'RESPONSE_PROOF_SELECTED_SHAPE_DRIFT')
    _require(_same_values(result.row_ids,np.concatenate((kept,np.full(count,-1,dtype=np.int64))))
        and _same_values(result.col_ids,np.concatenate((np.arange(n),np.full(count,-1,dtype=np.int64)))),
        'RESPONSE_PROOF_TRANSPORT_AXIS_DRIFT')
    # Check retained CSR spans directly, without allocating another matrix
    # containing nearly every original nonzero. Row lengths preserve the
    # segmentation within every consecutive run.
    _require(_same_values(np.diff(B.indptr[:len(kept)+1]),np.diff(A.indptr)[kept]),
        'RESPONSE_PROOF_RETAINED_ROW_COEFFICIENT_DRIFT')
    breaks=np.r_[0,np.flatnonzero(np.diff(kept)!=1)+1,len(kept)]
    for first,last in zip(breaks[:-1],breaks[1:]):
        if first==last:continue
        a=A.indptr[kept[first]];b=A.indptr[kept[last-1]+1]
        c=B.indptr[first];f=B.indptr[last]
        _require(_same_values(B.indices[c:f],A.indices[a:b])
            and _same_values(B.data[c:f],A.data[a:b]),'RESPONSE_PROOF_RETAINED_ROW_COEFFICIENT_DRIFT')
    for key in ('rhs','sense','row_names'):
        _require(len(e[key])==B.shape[0] and _same_values(e[key][:len(kept)],d[key][kept]),
            'RESPONSE_PROOF_RETAINED_ROW_METADATA_DRIFT:'+key)
    for k,reference in enumerate(references):
        i=len(kept)+k;a,b=A.indptr[reference:reference+2];x,y=B.indptr[i:i+2]
        _require(_same_values(B.indices[x:y],np.concatenate((A.indices[a:b],[n+k])))
            and _same_values(B.data[x:y],np.concatenate((-A.data[a:b],[1.]))),
            'RESPONSE_PROOF_NEW_EQUALITY_COEFFICIENT_DRIFT')
        _require(e['sense'][i]=='=' and Fraction(float(e['rhs'][i]))==0
            and str(e['row_names'][i])==expected_names[k], 'RESPONSE_PROOF_NEW_EQUALITY_METADATA_DRIFT')
    expected_nnz=A.nnz-sum(p['nnz_before'] for p in plans)+sum(p['nnz_after'] for p in plans)
    _require(B.nnz==expected_nnz,'RESPONSE_PROOF_TOTAL_NNZ_DRIFT')
    return dict(PASS=True,original_P1_bit_exact=True,integer_and_full_LP_domains_identical=True,
        objective_and_integer_and_full_LP_domains_preserved=True,
        original_variable_projection_equivalent=True,all_original_columns_and_bounds_preserved=True,
        all_removed_rows_reconstructed=True,all_added_helpers_exactly_defined=True,
        original_integer_types_and_bounds_exact=True,objective_exact=True,
        independent_model_proof_replayed=True,fresh_current_matrix_certificates=True,
        mathematical_forward='Y equals the exact stored sparse LHS on the original real coordinates',
        mathematical_inverse='Discard added continuous Y coordinates; preserve all original coordinates',
        deleted_inequalities_checked=len(gone),helper_equalities_checked=count,
        Native_optimize_calls=0,independent_verifier_wall_seconds=perf_counter()-began)

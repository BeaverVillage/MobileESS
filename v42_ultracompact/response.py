"""Reuse F4/FCRA affine sharing on exact, current, stored voltage rows.

The FULL constructor and its coefficients remain untouched.  After its C3A
proof, equal sparse voltage expressions are represented once by a continuous
helper whose box is the actual stored two-sided RHS range.  No substitution
product, recomputed physical constant, small-coefficient test or solver is used.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import re
from time import perf_counter

import numpy as np
from scipy import sparse

from v42_m1_hybrid.blocks import matrix_sha
from v42_pr134_b1.common import digest

SOURCES=('v42_ultracompact/response.py','v42_ultracompact/response_verify.py')
POLICY='EXACT_CURRENT_STORED_VOLTAGE_AFFINE_SHARING'
_VOLTAGE=re.compile(r'voltage_(lower|upper)\[(\d+),(\d+)\]')


def _domain_sha(data):
    h=hashlib.sha256()
    for key in sorted(data):
        value=np.asarray(data[key])
        h.update(key.encode());h.update(value.dtype.str.encode())
        h.update(np.asarray(value.shape,dtype='<i8').tobytes());h.update(value.tobytes())
    return h.hexdigest()


def size(A,d):
    return dict(rows=A.shape[0],columns=A.shape[1],nnz=int(A.nnz),
        binaries=int(np.count_nonzero(d['types']=='B')))


@dataclass
class ReformulationResult:
    original:object
    original_data:dict
    A:object
    d:dict
    row_ids:object
    col_ids:object
    plans:list
    proof:dict

    def forward(self,point):
        point=np.asarray(point,dtype=np.float64)
        if point.shape!=(self.original.shape[1],):
            raise ValueError('RESPONSE_FORWARD_ORIGINAL_POINT_AXIS')
        if not self.plans:return point.copy()
        references=[p['reference_row'] for p in self.plans]
        values=np.asarray(self.original[references]@point).ravel()
        return np.concatenate((point,values))

    def inverse(self,point):
        point=np.asarray(point,dtype=np.float64)
        if point.shape!=(self.A.shape[1],):
            raise ValueError('RESPONSE_INVERSE_SELECTED_POINT_AXIS')
        return point[:self.original.shape[1]].copy()


def state_sha(result):
    """Bind every matrix, domain, axis and row witness used by the proof."""
    return digest(dict(original_matrix=matrix_sha(result.original),
        original_domain=_domain_sha(result.original_data),
        selected_matrix=matrix_sha(result.A),selected_domain=_domain_sha(result.d),
        row_ids=result.row_ids,col_ids=result.col_ids,plans=result.plans))


def reformulate_responses(A,d,progress=None,independent_replay=True):
    """Choose exact two-sided sharing only when NNZ and fill proxy decrease.

    Every original column, bound, type and objective entry is preserved.  A
    selected group must use one slot and byte-identical actual sparse LHSs.
    Its helper equality is ``Y - a*x = 0`` and its finite box uses the maximum
    stored lower RHS and minimum stored upper RHS.  Original constants already
    absorbed into those RHSs are never recomputed.
    """
    if independent_replay is not True:
        raise ValueError('RESPONSE_FRESH_INDEPENDENT_REPLAY_REQUIRED')
    began=perf_counter();A=A.tocsr(copy=False)
    if not A.has_canonical_format or not np.isfinite(A.data).all():
        raise ValueError('RESPONSE_CURRENT_CSR_AUTHORITY_INVALID')
    if np.any(A.data==0):raise ValueError('RESPONSE_CURRENT_CSR_EXPLICIT_ZERO')
    groups=defaultdict(list);audit=Counter()
    for i,name in enumerate(d['row_names']):
        match=_VOLTAGE.fullmatch(str(name))
        if match is None:continue
        side,slot,node=match.groups();expected='>' if side=='lower' else '<'
        if d['sense'][i]!=expected:
            audit['unsupported_voltage_sense']+=1;continue
        start,end=A.indptr[i:i+2]
        if not np.isfinite(d['rhs'][i]):
            audit['nonfinite_voltage_rhs']+=1;continue
        # Full coordinates are part of the signature; no time or site block
        # can be merged merely because its coefficient numbers are similar.
        signature=(int(slot),A.indices[start:end].tobytes(),A.data[start:end].tobytes())
        groups[signature].append((i,side,int(node)))
    plans=[];gone=set();existing=set(map(str,d['names']));n=A.shape[1]
    for group in sorted(groups.values(),key=lambda rows:rows[0][0]):
        lower=[i for i,side,node in group if side=='lower']
        upper=[i for i,side,node in group if side=='upper']
        if not lower or not upper:
            audit['one_sided_expression_groups']+=1;continue
        rows=sorted(i for i,side,node in group);reference=rows[0]
        width=int(A.indptr[reference+1]-A.indptr[reference])
        before=len(rows)*width;after=width+1
        fill_before=len(rows)*width**2;fill_after=(width+1)**2
        if after>=before or fill_after>=fill_before:
            audit['nonbeneficial_expression_groups']+=1;continue
        low=max(lower,key=lambda i:float(d['rhs'][i]))
        high=min(upper,key=lambda i:float(d['rhs'][i]))
        if d['rhs'][low]>d['rhs'][high]:
            raise ValueError('RESPONSE_CURRENT_TWO_SIDED_RANGE_INFEASIBLE')
        slot=int(_VOLTAGE.fullmatch(str(d['row_names'][reference]))[2])
        name=f'response_voltage_shared[{slot},{reference}]'
        if name in existing:raise ValueError('RESPONSE_NEW_HELPER_NAME_COLLISION')
        existing.add(name)
        plans.append(dict(kind='STORED_TWO_SIDED_VOLTAGE_AFFINE_RANGE',rows=rows,
            reference_row=reference,lower_row=int(low),upper_row=int(high),slot=slot,
            column=n+len(plans),name=name,row_name=name.replace('[','_binding[',1),
            expression_nnz=width,nnz_before=before,nnz_after=after,
            fill_proxy_before=fill_before,fill_proxy_after=fill_after))
        gone.update(rows)
    kept=np.asarray([i for i in range(A.shape[0]) if i not in gone],dtype=np.int64)
    count=len(plans)
    if count:
        top=sparse.hstack((A[kept],sparse.csr_matrix((len(kept),count))),format='csr')
        references=[p['reference_row'] for p in plans]
        definitions=sparse.hstack((-A[references],sparse.eye(count,format='csr')),format='csr')
        B=sparse.vstack((top,definitions),format='csr');del top,definitions
        e=dict(d)
        for key in ('rhs','sense','row_names'):
            tail=(np.zeros(count) if key=='rhs' else np.full(count,'=') if key=='sense'
                else np.asarray([p['row_name'] for p in plans]))
            e[key]=np.concatenate((d[key][kept],tail))
        for key in ('names','types','lower','upper','objective'):
            tail=(np.asarray([p['name'] for p in plans]) if key=='names' else
                np.full(count,'C') if key=='types' else np.zeros(count) if key=='objective' else
                np.asarray([d['rhs'][p['lower_row' if key=='lower' else 'upper_row']] for p in plans]))
            e[key]=np.concatenate((d[key],tail))
    else:B,e=A,dict(d)
    result=ReformulationResult(A,d,B,e,np.concatenate((kept,np.full(count,-1,dtype=np.int64))),
        np.concatenate((np.arange(n,dtype=np.int64),np.full(count,-1,dtype=np.int64))),plans,{})
    if progress:progress(dict(phase='M_DENSE_RESPONSE_INDEPENDENT_PROOF',shared_expressions=count))
    from .response_verify import verify_response_reformulation
    proof=verify_response_reformulation(result)
    proof.update(schema='V42_CURRENT_EXACT_RESPONSE_REFORMULATION_V1',policy=POLICY,
        baseline=size(A,d),selected=size(B,e),shared_voltage_expressions=count,
        original_auxiliaries_deleted=0,new_continuous_helpers=count,
        removed_row_families=dict(Counter(str(d['row_names'][i]).split('[',1)[0] for i in gone)),
        nnz_reduction=int(A.nnz-B.nnz),row_reduction=int(A.shape[0]-B.shape[0]),
        structural_improvement=bool(count and B.nnz<A.nnz and B.shape[0]<A.shape[0]),
        selection_audit=dict(audit),coefficient_zeroing_thresholds_used=0,
        stored_RHS_used_without_recomputing_physical_constants=True,
        existing_F4_FCRA_affine_extension_reused=True,
        actual_Gurobi_presolved_improvement_measured=False,
        fill_proxy_is_not_a_solver_runtime_claim=True,wall_seconds=perf_counter()-began)
    result.proof=proof
    return result

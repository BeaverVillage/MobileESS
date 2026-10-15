"""Exact AIDC LP class sums. The original integer matrix is never rewritten.

All input blocks come from a saved, SHA-bound FULL matrix. This module does
not import Gurobi, run a solver, infer forecasts or truncate a physical domain.
It uses the same N*P=sum(P,...,P) continuous-lane argument as the existing
phase1 producer. Binary/integer decomposition is deliberately not asserted.
"""
from collections import defaultdict, Counter
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
import gc
import hashlib
import json
import math
import time

import numpy as np
import scipy.sparse as sp


VERSION = 'AIDC_SEMANTIC_LP_SUM_V1'
EXCLUDED_JOB = frozenset(('uid', 'qos_receipt_sha'))
EXCLUDED_BOUNDARY = frozenset(('window_authority_sha256',))
RUNTIME_FIELDS = ('runtime_authority', 'V10_Q50_total_seconds', 'exact_service_seconds',
                  'nominal_remaining_seconds', 'nominal_slots', 'duration_authority',
                  'overrun_uncertainty', 'synthetic_completion',
                  'risk_nominal_completion_issue_slot', 'reference_end')


def wire(value):
    """Typed canonical values; binary64 values are never rounded for a key."""
    if hasattr(value, '__dataclass_fields__'): value=asdict(value)
    if isinstance(value, np.generic): value=value.item()
    if isinstance(value, np.ndarray):
        return ['ndarray', value.dtype.str, list(value.shape), hashlib.sha256(value.tobytes()).hexdigest()]
    if isinstance(value, dict):
        return ['dict', sorted([[wire(k),wire(v)] for k,v in value.items()],key=lambda v:json.dumps(v[0],sort_keys=True))]
    if isinstance(value, (tuple,list)):
        return ['tuple' if isinstance(value,tuple) else 'list', [wire(v) for v in value]]
    if isinstance(value, float):
        if math.isnan(value): raise ValueError('NAN_SEMANTIC_VALUE')
        return ['binary64',value.hex()]
    if isinstance(value, (str,int,bool)) or value is None: return [type(value).__name__,value]
    raise TypeError('UNSUPPORTED_SEMANTIC_VALUE:'+type(value).__name__)


def digest(value):
    return hashlib.sha256(json.dumps(wire(value),ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def file_record(path):
    path=Path(path); h=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(8*1024*1024),b''):h.update(part)
    return dict(path=str(path.resolve()),sha256=h.hexdigest(),bytes=path.stat().st_size)


def checked_record(record):
    if file_record(record['path'])!=record: raise ValueError('COMPRESSION_INPUT_BYTES_DRIFT')
    return Path(record['path'])


def original_receipt_sha(receipt):
    # Literal existing a_engine.digest authority, including its UID.
    payload=dict(receipt);claimed=payload.pop('receipt_sha',None)
    actual=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if claimed is not None and claimed!=actual:raise ValueError('UID_RECEIPT_SELF_SHA_DRIFT')
    return actual


def semantic_identity(job, boundary, raw, receipt, resources_sha, bundle, graph_sha, retained_flow=False):
    j={k:v for k,v in asdict(job).items() if k not in EXCLUDED_JOB}
    b={k:v for k,v in asdict(boundary).items() if k not in EXCLUDED_BOUNDARY}
    wanted=original_receipt_sha(receipt)
    if (getattr(job,'uid',None)!=receipt.get('uid') or getattr(job,'qos_receipt_sha',None)!=wanted
            or getattr(boundary,'window_authority_sha256',None)!=wanted):
        raise ValueError('UID_RECEIPT_AUTHORITY_DRIFT')
    return dict(version=VERSION,job=j,boundary=b,hard_contract=receipt.get('hard_contract',{}),
                resources_sha=resources_sha,graph_sha=graph_sha,retained_mixed_flow=bool(retained_flow),
                runtime={k:raw.get(k) for k in RUNTIME_FIELDS},
                runtime_gamma=bundle['runtime_reserve_gamma'],runtime_kernel=bundle['runtime_survival_kernel'],
                objectives=dict(P1='ORIGINAL_RHO',migration=1,shift_reference=job.reference_start,
                                placement_reference=job.reference_site),
                integer_scope='UNCHANGED_ORIGINAL_FULL_INTEGER_MODEL')


def semantic_classes(data, domains, receipts):
    bundle,jobs,bounds,resources,raw,graphs,_,prep=data
    resources_sha=digest(asdict(resources));groups=defaultdict(list);identities={};ledger=[]
    retained=set(prep.get('preserve_singleton_mixed_flow',()))
    if set(domains)!=set(jobs) or not set(jobs)<=set(receipts):
        raise ValueError('COMPLETE_UID_DOMAIN_RECEIPT_COVERAGE_REQUIRED')
    for uid,job in sorted(jobs.items()):
        identity=semantic_identity(job,bounds[uid],raw[uid],receipts[uid],resources_sha,bundle,graphs[uid].sha,uid in retained)
        key=digest(identity);members=groups[key]
        if members:
            a,b=domains[members[0]],domains[uid]
            if (a.stays!=b.stays or a.blocks!=b.blocks or a.duration!=b.duration or a.cache.r!=b.cache.r):
                raise ValueError('CANDIDATE_PHYSICAL_DOMAIN_NOT_IDENTICAL:'+uid)
        groups[key].append(uid);identities[key]=identity
        ledger.append(dict(uid=uid,original_receipt_sha=original_receipt_sha(receipts[uid]),
            original_boundary=asdict(bounds[uid]),original_receipt=receipts[uid],
            original_physical_domain_sha=domains[uid].sha,original_graph_sha=graphs[uid].sha,
            mathematical_class=key))
    return dict(groups=dict(groups),identities=identities,uid_ledger=ledger,resources_sha=resources_sha,
                job_count=len(jobs),class_count=len(groups),class_sizes=dict(Counter(map(len,groups.values()))))


def descriptor_ownership(snapshot, descriptor, data, runtime_bindings=None):
    classes=data[7]['classes']
    if any(len(us)!=1 for us in classes.values()):
        raise ValueError('ORIGINAL_SINGLETON_AUDIT_REQUIRED_FOR_THIS_ADAPTER')
    owner={};class_uid={k:us[0] for k,us in classes.items()}
    for unit in descriptor['units']:
        uid=class_uid[unit['class_key']]
        for items in unit['v'].values():
            for e in items.values():
                for j in ((e[1],) if e[0]=='v' else e[2] if e[0]=='e' else ()):
                    j=int(j)
                    if j in owner and owner[j]!=uid:raise ValueError('CROSS_UID_PRIMITIVE_ALIAS')
                    owner[j]=uid
    prefix=min(owner)
    for key,j in (runtime_bindings or {}).items():
        j=int(j);uid=class_uid[key[0]]
        if j in owner and owner[j]!=uid:raise ValueError('RUNTIME_AUXILIARY_ALIAS')
        owner[j]=uid
    if set(owner)!=set(range(prefix,snapshot.matrix.shape[1])):
        raise ValueError('UNOWNED_ORIGINAL_COLUMN')
    by_uid={uid:[] for uid in data[1]}
    for j,uid in sorted(owner.items()):by_uid[uid].append(j)
    return prefix,{u:np.asarray(js,dtype=np.int64) for u,js in by_uid.items()},owner


def partition_rows(snapshot, prefix, by_uid, forced_global=()):
    """One CSR pass; no repeated full coupling extraction per class."""
    uids=sorted(by_uid);labels=np.full(snapshot.matrix.shape[1],-1,dtype=np.int32)
    for i,uid in enumerate(uids):labels[by_uid[uid]]=i
    A=snapshot.matrix;counts=np.diff(A.indptr);nonempty=np.flatnonzero(counts)
    owners=labels[A.indices]
    lo=np.full(A.shape[0],-1,dtype=np.int32);hi=lo.copy()
    # Only nonempty segment starts are reduced, avoiding reduceat's empty-row semantics.
    starts=A.indptr[nonempty]
    if len(starts):
        lo[nonempty]=np.minimum.reduceat(owners,starts)
        hi[nonempty]=np.maximum.reduceat(owners,starts)
    local=(lo>=0)&(lo==hi)
    local[np.asarray(tuple(forced_global),dtype=np.int64)]=False
    global_rows=np.flatnonzero(~local)
    indices=np.flatnonzero(local)
    indices=indices[np.argsort(lo[indices],kind='stable')]
    amounts=np.bincount(lo[indices],minlength=len(uids))
    boundaries=np.r_[0,np.cumsum(amounts)]
    local_rows={uid:indices[boundaries[i]:boundaries[i+1]] for i,uid in enumerate(uids)}
    return global_rows,local_rows


def same_array(a,b):
    a=np.asarray(a);b=np.asarray(b)
    return a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()


def same_sparse(a,b):
    return a.shape==b.shape and all(same_array(getattr(a,k),getattr(b,k)) for k in ('indptr','indices','data'))


def sparse_sha(A):
    h=hashlib.sha256(str(A.shape).encode())
    for x in (A.indptr,A.indices,A.data):
        h.update(str((x.shape,x.dtype.str)).encode());h.update(memoryview(np.ascontiguousarray(x)).cast('B'))
    return h.hexdigest()


def exact_scale(values,N,*,infinity=False):
    values=np.asarray(values,dtype=float);out=values.copy()
    for i,value in enumerate(values):
        if infinity and abs(value)>=1e100:continue
        exact=Fraction(float(value))*N
        new=float(exact)
        if not math.isfinite(new) or Fraction(new)!=exact:
            raise ValueError('NONEXACT_BINARY64_MULTIPLICITY_SCALING')
        out[i]=new
    return out


def local_packet(snapshot,columns,rows,coupling_csc):
    A=snapshot.matrix[rows][:,columns].tocsr();B=coupling_csc[:,columns].tocsc()
    return dict(A=A,B=B,lower=snapshot.lower[columns],upper=snapshot.upper[columns],
                senses=snapshot.senses[rows],rhs=snapshot.rhs[rows],types=snapshot.vtypes[columns])


def packet_equal(a,b):
    return same_sparse(a['A'],b['A']) and same_sparse(a['B'],b['B']) and all(
        same_array(a[k],b[k]) for k in ('lower','upper','senses','rhs','types'))


def packet_sha(p):
    return digest(dict(A=sparse_sha(p['A']),B=sparse_sha(p['B']),**{k:p[k] for k in ('lower','upper','senses','rhs','types')}))


def compress_lp(snapshot,descriptor,data,semantic,*,runtime_bindings=None,forced_global=(),progress=None):
    """Sum entire identical continuous local polytopes, retaining original B.

    This is the existing identical-lane sum proof applied at the whole local
    block boundary. SINGLE mixed-flow blocks are NOT converted to a new STAY
    histogram: their exact original LP rows are retained. Integer lanes stay
    in the separately preserved FULL MILP.
    """
    start=time.perf_counter()
    prefix,columns,_=descriptor_ownership(snapshot,descriptor,data,runtime_bindings)
    global_rows,rows=partition_rows(snapshot,prefix,columns,forced_global)
    coupling=snapshot.matrix[global_rows].tocsc()
    G=coupling[:,:prefix].tocsc()
    parts=[];Bs=[];lower=[];upper=[];senses=[];rhs=[];records=[];offset=prefix
    fold=np.arange(snapshot.matrix.shape[1],dtype=np.int64);scale=np.ones(snapshot.matrix.shape[1],dtype=np.int64)
    seen=[]
    for idx,(key,members) in enumerate(sorted(semantic['groups'].items())):
        uid=members[0];reference=local_packet(snapshot,columns[uid],rows[uid],coupling)
        # Semantic equivalence is necessary, but actual every-UID matrix equality is mandatory.
        for member in members[1:]:
            check=local_packet(snapshot,columns[member],rows[member],coupling)
            if not packet_equal(reference,check):raise ValueError('ACTUAL_LOCAL_OR_COUPLING_MATRIX_DRIFT:'+member)
        N=len(members)
        try:
            group_lower=exact_scale(reference['lower'],N,infinity=True)
            group_upper=exact_scale(reference['upper'],N,infinity=True)
            group_rhs=exact_scale(reference['rhs'],N)
            adopted=[members]
        except ValueError:
            # Exact representability is a gate, not a tolerance. Preserve originals on rejection.
            adopted=[[u] for u in members]
        for subset in adopted:
            N=len(subset);width=reference['A'].shape[1]
            block_key=key if len(adopted)==1 else digest((key,subset[0],'SCALING_FALLBACK'))
            for member in subset:
                fold[columns[member]]=np.arange(offset,offset+width);scale[columns[member]]=N
            # Each sparse coupling has millions of mostly empty global rows.
            # Keep CSC until the one final horizontal concatenation, rather
            # than allocating a full CSR row pointer for every single class.
            parts.append(reference['A']);Bs.append(reference['B'])
            lower.extend(exact_scale(reference['lower'],N,infinity=True))
            upper.extend(exact_scale(reference['upper'],N,infinity=True))
            senses.extend(reference['senses']);rhs.extend(exact_scale(reference['rhs'],N))
            records.append(dict(class_id=block_key,semantic_class=key,members=list(subset),cardinality=N,
                offset=offset,width=width,local_rows=reference['A'].shape[0],
                source_columns={u:columns[u].tolist() for u in subset},
                source_rows={u:rows[u].tolist() for u in subset},
                original_packet_sha=packet_sha(reference),
                local_matrix_sha=sparse_sha(reference['A']),coupling_sha=sparse_sha(reference['B']),
                exact_binary64_multiplicity_scaling=True,integer_compression=False,
                scaling_fallback=len(adopted)>1))
            offset+=width;seen.extend(subset)
        if progress and (idx%10==0 or idx+1==len(semantic['groups'])):
            progress(dict(phase='EXACT_LOCAL_SUM_ASSEMBLY',classes_complete=idx+1,
                          classes_required=len(semantic['groups']),seconds=time.perf_counter()-start))
    if sorted(seen)!=sorted(data[1]) or len(set(seen))!=len(seen):raise ValueError('LOST_OR_DUPLICATED_UID')
    local=sp.block_diag(parts,format='csr')
    A=sp.vstack((sp.hstack([G,*Bs],format='csc').tocsr(),
                 sp.hstack((sp.csr_matrix((local.shape[0],prefix)),local),format='csr')),format='csr')
    A.sum_duplicates();A.sort_indices();A.eliminate_zeros()
    objectives=[]
    for objective in snapshot.objectives:
        co=objective.coefficients();targets=defaultdict(list)
        for j in range(prefix,snapshot.matrix.shape[1]):targets[int(fold[j])].append(co.get(j,Fraction(0)))
        if any(any(v!=xs[0] for v in xs) for xs in targets.values()):raise ValueError('PER_UID_OBJECTIVE_COEFFICIENT_DRIFT')
        terms=[(j,v) for j,v in co.items() if j<prefix]
        terms += [(j,xs[0]) for j,xs in targets.items() if xs[0]]
        objectives.append(replace(objective,terms=tuple(sorted(terms))))
    compressed=replace(snapshot,matrix=A,lower=np.r_[snapshot.lower[:prefix],lower],
        upper=np.r_[snapshot.upper[:prefix],upper],senses=np.r_[snapshot.senses[global_rows],senses],
        rhs=np.r_[snapshot.rhs[global_rows],rhs],vtypes=np.full(A.shape[1],'C'),objectives=tuple(objectives)).require()
    return dict(snapshot=compressed,source_sha=snapshot.fingerprint(),compressed_sha=compressed.fingerprint(),
                prefix=prefix,global_rows=global_rows,records=records,fold=fold,scale=scale,
                original_columns=columns,original_local_rows=rows,
                wall_seconds=time.perf_counter()-start,source_integer_matrix_unchanged=True,
                integer_compression=False,LP_projection='Y=sum(X_uid), inverse X_uid=Y/N')


def lift_rational(result,point):
    """An exact LP inverse. This is not integer disaggregation."""
    if len(point)!=result['snapshot'].matrix.shape[1]:raise ValueError('COMPRESSED_POINT_AXIS')
    return tuple(Fraction(point[int(j)])/int(n) for j,n in zip(result['fold'],result['scale']))


def project_rational(result,point):
    if len(point)!=len(result['fold']):raise ValueError('ORIGINAL_POINT_AXIS')
    out=[Fraction(0)]*result['snapshot'].matrix.shape[1]
    prefix=result['prefix']
    for j,x in enumerate(point):
        if j<prefix:out[j]=Fraction(x)
        else:out[int(result['fold'][j])]+=Fraction(x)
    return tuple(out)


def redundant_rows(snapshot,*,protected_rows=()):
    """Delete only exact duplicate rows or mathematically true constant rows."""
    A=snapshot.matrix;seen={};keep=[];duplicates=[];tautologies=[];protected=set(map(int,protected_rows))
    for i in range(A.shape[0]):
        lo,hi=A.indptr[i:i+2]
        if i in protected:
            keep.append(i)
            continue
        if lo==hi:
            b=float(snapshot.rhs[i]);sense=str(snapshot.senses[i])
            if (sense=='=' and b==0) or (sense=='<' and b>=0) or (sense=='>' and b<=0):
                tautologies.append(i);continue
            raise ValueError('INFEASIBLE_CONSTANT_ROW')
        key=(str(snapshot.senses[i]),np.float64(snapshot.rhs[i]).tobytes(),
             A.indices[lo:hi].tobytes(),A.data[lo:hi].tobytes())
        if key in seen:duplicates.append((i,seen[key]))
        else:seen[key]=i;keep.append(i)
    # This also preserves integer feasibility: columns/boxes/types/objective do not change.
    result=replace(snapshot,matrix=A[keep].tocsr(),senses=snapshot.senses[keep],rhs=snapshot.rhs[keep]).require()
    return result,dict(PASS=True,retained_rows=keep,exact_duplicates=duplicates,
        constant_tautologies=tautologies,integer_rows_equivalent=True,
        named_coupling_rows_preserved=sorted(protected),
        unchanged_bounds_types_objective=True,only_byte_identical_rows_or_true_constants_removed=True)


def size(snapshot):
    return dict(rows=snapshot.matrix.shape[0],columns=snapshot.matrix.shape[1],NNZ=snapshot.matrix.nnz,
                binary=int(np.count_nonzero(snapshot.vtypes=='B')))

"""Exact migration-zero restriction of full native class blocks.

The SUM lane is NEVER integerized. Every optional primitive must be proved
zero. Identical original integer lanes then lift to zero individually. The
unchanged histogram retains original integer counts; singleton native flow
is retained with original native types, including mixed finish semantics.
"""
from dataclasses import replace
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
from v42_a_stage_phase1 import producer
from v42_a_stage_domain_v2.lexstage import Objective,project_migration_zero
from v42_a_stage_compact_rowgen.equivalence import role

def objectives(units,job):
    out=[Objective('rho',())]
    for name in ('migration_count','shift_magnitude','prestart_relocation'):
        terms=[];constant=Fraction(0)
        for u in units:
            for key,e in u['v']['q' if name=='migration_count' else 'y'].items():
                c=1 if name=='migration_count' else abs(key[1]-job.reference_start) if name=='shift_magnitude' else int(key[0]!=job.reference_site)
                if not c:continue
                if e[0]=='v':terms.append((int(e[1]),Fraction(c)))
                elif e[0]=='e':
                    constant+=Fraction(float(e[1]))*c
                    terms.extend((int(j),Fraction(float(v))*c) for j,v in zip(e[2],e[3]))
                else:constant+=Fraction(float(e[1]))*c
        out.append(Objective(name,tuple(terms),constant))
    return tuple(out)

def columns(unit):
    out=set()
    for items in unit['v'].values():
        for e in items.values():out.update((int(e[1]),) if e[0]=='v' else map(int,e[2]) if e[0]=='e' else ())
    return out

def reindex(unit,mapping):
    def entry(e):
        if e[0]=='v':return ('v',int(mapping[e[1]])) if mapping[e[1]]>=0 else ('c',0.)
        if e[0]=='e':
            keep=[i for i,j in enumerate(e[2]) if mapping[j]>=0]
            return ('e',e[1],np.asarray([mapping[e[2][i]] for i in keep],dtype=int),np.asarray([e[3][i] for i in keep])) if keep else ('c',e[1])
        return e
    return dict(unit,v={name:{key:entry(e) for key,e in items.items()} for name,items in unit['v'].items()})

def restrict(data,key,cache,axes):
    captured=[];original=producer.snapshot_of
    def capture(m,objs):
        s=original(m,objs);captured.append(s.vtypes.copy());return s
    producer.snapshot_of=capture
    try:s,B,c,units=producer.native_block(data,key,cache['graph'],tuple(axes),averaged=True)
    finally:producer.snapshot_of=original
    want=cache['snapshot'];delta=s.matrix-want.matrix;delta.eliminate_zeros()
    if delta.nnz or (B-cache['B']).nnz or any(not np.array_equal(getattr(s,a),getattr(want,a)) for a in ('lower','upper','rhs','senses')) or not np.array_equal(c,cache['constant']):raise ValueError('FULL_CACHE_NATIVE_REBUILD_DRIFT')
    uid=data[7]['classes'][key][0];N=len(data[7]['classes'][key]);obj=objectives(units,data[1][uid])
    s=replace(s,objectives=obj,vtypes=captured[0])
    terms=s.objective('migration_count').coefficients()
    row=sp.csr_matrix(([float(v) for v in terms.values()],([0]*len(terms),list(terms))),shape=(1,s.matrix.shape[1]))
    locked=replace(s,matrix=sp.vstack((s.matrix,row),format='csr'),rhs=np.append(s.rhs,0),senses=np.append(s.senses,'='))
    projected,mapping,proof=project_migration_zero(locked,migration_lock_row=s.matrix.shape[0])
    optional=set().union(*(columns(u) for u in units if u['optional'])) if any(u['optional'] for u in units) else set()
    if any(mapping[j]>=0 for j in optional):raise ValueError('NONZERO_OPTIONAL_SUM_CANNOT_BE_INTEGERIZED')
    # All source SUM forcing rows have zero RHS. Multiplication by N leaves
    # these rows unchanged; thus the same zero proof applies to EACH original
    # optional lane. No count-scaled integer migration variable survives.
    if N>1 and optional:
        for i,forced in proof.forcing_steps:
            if not set(forced)<=optional:raise ValueError('OPTIONAL_ZERO_PROOF_TOUCHES_HISTOGRAM')
        hist=next(u for u in units if u['stay_count'])
        if set(hist['v']['y'])!={(site,start) for start,site in data_domain_stays(cache,data,uid)}:raise ValueError('FULL_HISTOGRAM_STAY_COVERAGE_FAIL')
    keep=np.flatnonzero(mapping>=0)
    typed=projected.vtypes
    if N>1 and any(u['optional'] for u in units) and np.any(typed!='I'):raise ValueError('ZERO_MIGRATION_NOT_ORIGINAL_INTEGER_HISTOGRAM')
    receipt=dict(PASS=True,class_id=key,cardinality=N,full_native_sha256=s.fingerprint(),full_graph_sha256=cache['graph'].sha,
        zero_projection=proof.verify(locked),optional_primitives=len(optional),all_optional_primitives_exactly_zero=True,
        original_integer_lanes_lift_to_zero=True,SUM_integerized=False,singleton_native_flow_retained=N==1,
        rows=projected.matrix.shape[0],cols=projected.matrix.shape[1],nnz=projected.matrix.nnz)
    return projected,B[:,keep].tocsr(),c,[reindex(u,mapping) for u in units],dict(source=locked,mapping=mapping,proof=proof),receipt

def data_domain_stays(cache,data,uid):
    # Every valid histogram start was constructed by the original fits rule.
    # The independent complete-domain roster is compared by prepare as well.
    job=data[1][uid]
    from v42_boundary.generator import Generator
    gen=Generator(data[3],max(b.latest_completion for b in data[2].values()))
    return [(start,site) for site,start in cache['graph'].events['y'] if start+job.service_slots<=data[2][uid].latest_completion and gen.fits(site,start,job.service_slots,job.gpu)]

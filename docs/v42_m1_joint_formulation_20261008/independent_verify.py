"""Independent exact row algebra, never calls a production EF constructor."""
from common import *
from functools import lru_cache
@lru_cache(maxsize=None)
def rational(v):return F.from_float(float(v))
def check(A,d,B,e,spec,scientific=True):
    n=A.shape[1];m=A.shape[0];I=spec['source_rows'];J=spec['source_columns'];N=len(J);index={j:q for q,j in enumerate(J)}
    for key in ['names','types','lower','upper','objective']:
        assert np.array_equal(e[key][:n],d[key]),('ORIGINAL_AXIS_FIELD_CHANGED',key)
        if np.issubdtype(d[key].dtype,np.floating):assert e[key][:n].tobytes()==d[key].tobytes()
    for key in ['rhs','sense','row_names']:assert np.array_equal(e[key][:m],d[key])
    assert e['constant'].tobytes()==d['constant'].tobytes();assert not np.any(e['objective'][n:].view(np.uint64))
    assert np.all(e['types'][n:]=='C') and np.isfinite(e['lower']).all() and np.isfinite(e['upper']).all()
    if scientific:objective_identity(A,d)
    row=0
    def expect(terms,sense='=',rhs=0):
        nonlocal row
        expected={};actual={int(j):rational(float(v)) for j,v in zip(B.indices[B.indptr[row]:B.indptr[row+1]],B.data[B.indptr[row]:B.indptr[row+1]]) if v}
        for j,v in terms:
            if v:assert int(j) not in expected;expected[int(j)]=rational(float(v))
        assert actual==expected,('INVALID_EMITTED_COEFFICIENT',row)
        assert e['sense'][m+row]==sense and rational(e['rhs'][m+row])==rational(rhs),('INVALID_EMITTED_RHS_OR_SENSE',row)
        row+=1
    def source_terms(i,offset,sign=1):return [(offset+index[int(j)],sign*float(v)) for j,v in zip(A.indices[A.indptr[i]:A.indptr[i+1]],A.data[A.indptr[i]:A.indptr[i+1]])]
    if spec['kind'].startswith('COMPLETE'):
        groups=spec['groups'];words=spec['words'];expected_words=[list(w) for w in itertools.product(range(len(groups[0])+1),repeat=len(groups))]
        assert all(d['types'][j]=='B' and d['lower'][j]==0 and d['upper'][j]==1 for group in groups for j in group)
        assert words==expected_words,'OMITTED_OR_EXTRA_COUNT_WORD';states=len(words);lams=n+states*N+np.arange(states)
        assert np.array_equal(e['lower'][n:n+states*N],np.tile(np.minimum(0,d['lower'][J]),states))
        assert np.array_equal(e['upper'][n:n+states*N],np.tile(np.maximum(0,d['upper'][J]),states))
        for s,word in enumerate(words):
            lam=int(lams[s]);off=n+s*N
            for i in I:expect(source_terms(i,off)+[(lam,-d['rhs'][i])],str(d['sense'][i]))
            for q,j in enumerate(J):
                expect([(off+q,1),(lam,-d['lower'][j])],'>');expect([(off+q,1),(lam,-d['upper'][j])],'<')
            for t,g in enumerate(groups):expect([(off+index[j],1) for j in g]+[(lam,-word[t])])
        expect([(int(j),1) for j in lams],rhs=1)
        for q,j in enumerate(J):expect([(j,1)]+[(n+s*N+q,-1) for s in range(states)])
    else:
        selectors=spec['selectors'];K=len(selectors);lams=n+K*N+np.arange(K)
        assert np.array_equal(e['lower'][n:n+K*N],np.tile(np.minimum(0,d['lower'][J]),K))
        assert np.array_equal(e['upper'][n:n+K*N],np.tile(np.maximum(0,d['upper'][J]),K))
        for s,b in enumerate(selectors):
            assert d['types'][b]=='B' and d['lower'][b]==0 and d['upper'][b]==1
            off=n+s*N;lam=int(lams[s]);expect([(lam,1),(b,-1)])
            for i in I:
                sense=str(d['sense'][i]);expect(source_terms(i,off)+[(lam,-d['rhs'][i])],sense)
                if sense!='=':
                    original=[(int(j),float(v)) for j,v in zip(A.indices[A.indptr[i]:A.indptr[i+1]],A.data[A.indptr[i]:A.indptr[i+1]])]
                    expect(original+source_terms(i,off,-1)+[(lam,d['rhs'][i])],sense,d['rhs'][i])
            for q,j in enumerate(J):
                y=off+q;lo,hi=d['lower'][j],d['upper'][j]
                expect([(y,1),(lam,-lo)],'>');expect([(y,1),(lam,-hi)],'<')
                expect([(j,1),(y,-1),(lam,lo)],'>',lo);expect([(j,1),(y,-1),(lam,hi)],'<',hi)
            expect([(off+index[b],1),(b,-1)])
        for s,b in enumerate(selectors):
            for t,c in enumerate(selectors[:s]):expect([(n+s*N+index[c],1),(n+t*N+index[b],-1)])
    assert np.all(e['lower'][lams]==0) and np.all(e['upper'][lams]==1)
    assert row==B.shape[0] and B.shape[1]==len(e['names'])
    return dict(PASS=True,checked_added_rows=row,checked_added_nnz=B.nnz,original_axis_bit_identity=True,original_objective_hash=objective_identity(A,d)['source_objective_SHA256'] if scientific else 'BOUNDED_RATIONAL_C3A_TYPE_FIXTURE',every_emitted_coefficient_equals_exact_source_algebra=True,original_integer_projection_unchanged=True,full_96_slot_general_proof='VALIDITY_PROOF_KO.md',production_constructor_called=False,optimize_calls=0)

def run(label):
    gp,old=forbid_optimize()
    try:
        A,d,_=load();B=sparse.load_npz(OUT/f'{label}_ADDED_MATRIX.npz').tocsr()
        with np.load(OUT/f'{label}_DATA.npz') as z:e={k:z[k] for k in z.files}
        spec=read(OUT/f'{label}_SPEC.json');report=check(A,d,B,e,spec)
        # Lifting is independently computed here, not by formulations.lift.
        x=center();J=np.asarray(spec['source_columns']);n=len(x)
        if spec['kind'].startswith('COMPLETE'):
            word=[int(sum(x[j] for j in group)) for group in spec['groups']];s=spec['words'].index(word);weights=np.zeros(len(spec['words']));weights[s]=1;y=np.zeros((len(weights),len(J)));y[s]=x[J]
        else:weights=x[spec['selectors']];assert np.all((weights==0)|(weights==1));y=np.outer(weights,x[J])
        lifted=np.r_[x,y.ravel(),weights];full=sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],B.shape[1]-n))]),B],format='csr')
        replay=hc.replay(full,e,lifted,True);assert replay['PASS'],'ORIGINAL_VERIFIED_UB_EXCLUDED'
        assert np.array_equal(lifted[:n],x)
        save_vector(OUT/f'{label}_LIFTED_CENTER.npz',x=lifted)
        report.update(original_UB_full_physics_replay=read(OUT/'CENTER_FULL_REPLAY.json'),strengthened_center_replay=replay,inverse_lift_original_bits_unchanged=True,matrix_SHA256=sha(OUT/f'{label}_ADDED_MATRIX.npz'),data_SHA256=sha(OUT/f'{label}_DATA.npz'),spec_SHA256=sha(OUT/f'{label}_SPEC.json'))
        assert report['original_UB_full_physics_replay']['PASS'];atomic(OUT/f'{label}_EXACTNESS_VERIFICATION.json',report);print(json.dumps(clean(report)),flush=True)
    finally:gp.Model.optimize=old
if __name__=='__main__':run(sys.argv[1])

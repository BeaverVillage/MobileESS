"""Independent source-row/half-PCS verification of the stored small master."""
from common import *
from fractions import Fraction as F
from collections import defaultdict

def main():
    A,d,_=load();a=Authority();h=read(OUT/'CROSS_MESS_MASTER_AUTHORITY.json')
    M=sparse.load_npz(OUT/'CROSS_MASTER_MATRIX.npz').tocsr()
    with np.load(OUT/'CROSS_MASTER_DATA.npz') as z:e={k:z[k] for k in z.files}
    cols=e['original_columns'];n=len(cols);prefix=h['grid_binding_rows']+h['all_retained_faces'];wanted={}
    def key(indices,data,sense,rhs):return (np.asarray(indices,dtype=np.int64).tobytes(),np.asarray(data,dtype=np.float64).tobytes(),str(sense),float(rhs))
    for i in range(prefix):
        b,f=M.indptr[i:i+2];assert np.all(M.indices[b:f]<n)
        wanted[key(cols[M.indices[b:f]],M.data[b:f],e['sense'][i],e['rhs'][i])]=i
    matched={}
    for i in range(A.shape[0]):
        b,f=A.indptr[i:i+2];signature=key(A.indices[b:f],A.data[b:f],d['sense'][i],d['rhs'][i])
        if signature in wanted:matched[wanted[signature]]=i
    assert len(matched)==prefix
    for field in ('lower','upper','objective'):assert np.array_equal(e[field][:n],d[field][cols])
    row=prefix;power=defaultdict(list);lams=defaultdict(list);index={int(j):k for k,j in enumerate(cols)}
    def check(terms,sense='<',rhs=0):
        nonlocal row
        terms=sorted((int(j),float(w)) for j,w in terms if w);b,f=M.indptr[row:row+2]
        assert np.array_equal(M.indices[b:f],np.array([j for j,w in terms]))
        assert np.array_equal(M.data[b:f],np.array([w for j,w in terms]))
        assert e['sense'][row]==sense and e['rhs'][row]==rhs;row+=1
    units=sorted(a.initial);expected_states={(u,s,b) for u in units for s in a.sites for b in (0,1)}
    assert expected_states=={(s['MESS'],s['site'],s['mode']) for s in h['states']} and len(h['states'])==192
    # Original prefix followed by one complete unit disjunction at a time.
    for unit in units:
        states=[s for s in h['states'] if s['MESS']==unit]
        for state in states:
            site=state['site'];bit=state['mode'];lam,p,q=(state[k] for k in ('lambda_column','p_column','q_column'))
            assert e['types'][lam]=='B' and e['lower'][lam]==0 and e['upper'][lam]==1
            assert (e['lower'][p],e['upper'][p])==(0,300) and (e['lower'][q],e['upper'][q])==(-400,400)
            check([(p,1),(lam,-300)])
            for aa,bb,cap in a.pcs(unit,site,72):check([(p,aa*(1 if bit==0 else -1)),(q,bb),(lam,-cap)])
            lams[unit].append(lam);power[unit,'Pch' if bit else 'Pdis',site].append(p);power[unit,'Q',site].append(q)
            assert a.sites.index(site)*96+69 in a.reachable[unit]
            E=F(760)+a.energy(unit,72)['charge' if bit else 'discharge']*300
            assert 440<=E<=1080
        check([(j,1) for j in lams[unit]],'=',1)
        for site in a.sites:
            for family in ('Pch','Pdis','Q'):
                terms,constant=a.expression(f'{family}[{unit},{site},72]')
                check([(index[j],w) for j,w in terms.items()]+[(j,-1) for j in power[unit,family,site]],'=',-constant)
    assert row==M.shape[0] and sha(OUT/'CROSS_MASTER_MATRIX.npz')==h['matrix_SHA256'] and sha(OUT/'CROSS_MASTER_DATA.npz')==h['data_SHA256']
    # Semantic mutation at the final link, not merely a different file hash.
    old=M.data[M.indptr[-2]:M.indptr[-1]].copy();M.data[M.indptr[-2]:M.indptr[-1]]=-old
    row-=1;rejected=False
    try:check([(index[j],w) for j,w in terms.items()]+[(j,-1) for j in power[unit,family,site]],'=',-constant)
    except AssertionError:rejected=True
    assert rejected
    write('CROSS_MASTER_INDEPENDENT_VERIFICATION.json',dict(PASS=True,optimize_calls=0,production_master_constructor_imported=False,all_original_binding_and_face_rows_matched=matched,all_native_half_PCS_rows_checked=True,all_projection_links_checked=True,complete_state_set_checked=True,one_time_injection_set_extension_to_local_four_slot_proved=True,global96_slot_extension_not_claimed=True,semantic_link_sign_mutation_rejected=True,rows_checked=M.shape[0],columns=M.shape[1],nnz=M.nnz))
    print('CROSS_MASTER_INDEPENDENT_PASS',flush=True)

if __name__=='__main__':main()

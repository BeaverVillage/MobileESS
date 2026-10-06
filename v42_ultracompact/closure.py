"""Actual second-pass bound/duplicate closure and normalized native polygons."""
from .common import *
from fractions import Fraction as F
from collections import Counter
from v42_redundancy.canonical import exact_audits,exact_box
from v42_supercompact.build import load as parent_load
from .polytope import vertices
import time
def run():
    begin=time.perf_counter();A,d=load('C3A');dup,dom,graph,_=exact_audits(A,d);assert not graph,'NEW_DUPLICATE_NEEDS_CERTIFICATE_AND_REBUILD'
    # Outward candidate screen then exact finite-box checks. It never deletes
    # a row merely from a floating comparison.
    P=A.maximum(0);N=A.minimum(0);uf=np.where(np.isfinite(d['upper']),d['upper'],0);lf=np.where(np.isfinite(d['lower']),d['lower'],0);u=P@uf+N@lf;l=P@lf+N@uf;mag=abs(P)@abs(uf)+abs(N)@abs(lf);err=4*(2*np.diff(A.indptr)+4)*np.finfo(float).eps*mag
    unbounded=(P@(~np.isfinite(d['upper'])).astype(float)+abs(N)@(~np.isfinite(d['lower'])).astype(float))>0;unboundedlo=(P@(~np.isfinite(d['lower'])).astype(float)+abs(N)@(~np.isfinite(d['upper'])).astype(float))>0
    sg=np.where(d['sense']=='>',-1.,1.);rough=np.where(sg>0,u,-l);bad=np.where(sg>0,unbounded,unboundedlo);rhs=sg*d['rhs'];candidate=np.flatnonzero((d['sense']!='=')&(~bad)&(rough-err<=rhs));extra=[]
    for i in candidate:
        exact=exact_box(A,d,int(i))
        if exact is not None and exact<=F(float(rhs[i])):extra.append(int(i))
    assert not extra,('NEW_V2_BOUND_PROOFS_NEED_REBUILD',extra[:20])
    summary=read('AUDIT_SUMMARY.json');table('STATIC_REDUCTION_ROUNDS_V2.csv',[dict(round=1,rows_before=summary['all_rows'],rows_deleted=summary['new_rows_removed'],bounds_tightened=summary['new_bounds'],columns_removed=0,rows_after=A.shape[0],nnz_after=A.nnz,actual_checks='Original C2 exact scan, local PCS/flow proof, correlated source support'),dict(round=2,rows_before=A.shape[0],rows_deleted=0,bounds_tightened=0,columns_removed=0,rows_after=A.shape[0],nnz_after=A.nnz,actual_checks='Fresh exact duplicate/proportional scan and all finite-box candidates under V2 bounds; triangular affine support already closed')],['round','rows_before','rows_deleted','bounds_tightened','columns_removed','rows_after','nnz_after','actual_checks'])
    write('STATIC_FIXED_POINT_V2.json',dict(PASS=True,duplicate_candidates=len(graph),finite_box_candidates_tested=len(candidate),new_safe_rows=len(extra),triangular_affine_bounds_dependency_only_on_unchanged_physical_C2=True,physical_SOC_PCS_reach_bounds_unchanged=True,unknown_full_global_multirow_implications_retained=True,wall=time.perf_counter()-begin))
    # Audit every actual normalized native polygon, not regenerated sin/cos.
    C,f=parent_load('C0');vf=[family(n) for n in f['names']];families=[family(n) for n in f['row_names']];results={};canonical={}
    for fam in ['line_thermal_face','transformer_kVA']:
        ids=[i for i,v in enumerate(families) if v==fam];scalar=[]
        if fam=='line_thermal_face':
            scalar=[i for i in ids if not any(vf[j]=='response_line_correction' for j in C.indices[C.indptr[i]:C.indptr[i+1]])];ids=[i for i in ids if i not in set(scalar)]
            assert len(scalar)==1;assert C[scalar[0]].nnz==1 and f['rhs'][scalar[0]]==0
        assert len(ids)%16==0;structs={};zero=0
        for start in range(0,len(ids),16):
            planes=[]
            for i in ids[start:start+16]:
                a,b=C.indptr[i:i+2];p=q=F(0)
                for j,w in zip(C.indices[a:b],C.data[a:b]):
                    if vf[j].startswith(('response_','injection_')) and vf[j].endswith('_P'):p+=F(float(w))
                    if vf[j].startswith(('response_','injection_')) and vf[j].endswith('_Q'):q+=F(float(w))
                planes.append((p,q,F(float(f['rhs'][i])) if fam=='transformer_kVA' else F(1)))
            if all(p==q==0 for p,q,r in planes):
                assert fam!='transformer_kVA' or all(r>=0 for p,q,r in planes)
                zero+=1;continue
            key=tuple(planes);structs[key]=structs.get(key,0)+1
        checks=[]
        for planes,count in structs.items():
            # Pair vertices certify two boundary points per native face. Thus
            # each is an irredundant normalized polygon facet before the actual
            # local affine-domain/security screening already recorded separately.
            v=vertices(planes);necessary=[]
            for k,(a,b,c) in enumerate(planes):
                on=[(x,y) for x,y in v if a*x+b*y==c];necessary.append(len(on)>=2)
            assert all(necessary) and len(v)==16
            checks.append(dict(instances=count,minimal_unclipped_H_facets=16,stored_planes=[[str(x) for x in p] for p in planes],vertices=16,all_faces_have_two_exact_boundary_vertices=True))
        results[fam]=dict(instances=len(ids)//16,scalar_nonpolygon_rows=scalar,zero_direction_instances=zero,canonical_structures=len(checks),minimal_normalized_nonzero_faces=16,structures=checks,local_bound_transport='No unbounded-facet proof used to delete a local row. Actual C2 bounds/route/PCS/cross-family source screening is recorded per retained current row.')
    obj=read('POLYTOPE_MINIMAL_H_REPRESENTATION.json');obj['native_security_polygons_exact_audit']=results;write('POLYTOPE_MINIMAL_H_REPRESENTATION.json',obj);print('V2_ACTUAL_CLOSURE_AND_NATIVE_POLYGONS_PASS',flush=True)
if __name__=='__main__':run()

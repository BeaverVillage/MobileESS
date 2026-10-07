"""Exact solver-free Lagrangian over a valid homogeneous domain relaxation.

No optimized LP value is assumed. Original variables retain finite boxes;
each proved hull's private variables use their perspective boxes, lambda
simplex, and transit-mode mass bounds. SOC/PCS dynamics may be dropped in
this minimization, so the result remains conservative.
"""
from common import *
from fractions import Fraction as F
from collections import defaultdict
import time

def model(labels):
    A,d,_=load();n=A.shape[1];extra=0;bs=[];ds=[];metadata=[]
    assert read(OUT/'CAUSAL_CONTROLS_INDEPENDENT_VERIFICATION.json')['PASS']
    for label in labels:
        h=read(OUT/(label+'_HULL_AUTHORITY.json'))
        assert read(OUT/(label+'_INDEPENDENT_VERIFICATION.json'))['PASS']
        B=sparse.load_npz(OUT/(label+'_EF_MATRIX.npz')).tocoo()
        assert sha(OUT/(label+'_EF_MATRIX.npz'))==h['matrix_SHA256']
        with np.load(OUT/(label+'_EF_DATA.npz')) as z:f={k:z[k] for k in z.files}
        B.col=np.where(B.col>=n,B.col+extra,B.col);bs.append(B);ds.append(f);metadata.append((label,h,f,extra));extra+=len(f['lower'])
    M=sparse.vstack([sparse.hstack([A,sparse.csr_matrix((A.shape[0],extra))],format='csr')]+[sparse.csr_matrix((B.data,(B.row,B.col)),shape=(B.shape[0],n+extra)) for B in bs],format='csr')
    e=dict(lower=np.concatenate([d['lower']]+[f['lower'] for f in ds]),upper=np.concatenate([d['upper']]+[f['upper'] for f in ds]),objective=np.r_[d['objective'],np.zeros(extra)],constant=d['constant'],rhs=np.concatenate([d['rhs']]+[f['rhs'] for f in ds]),sense=np.concatenate([d['sense']]+[f['sense'] for f in ds]))
    return M,e,n,metadata

def certificate(M,d,dual,n,metadata):
    dyadic=exact_bound_module.dyadic;denom=exact_bound_module.denominator_upper
    pi=np.where(d['sense']=='<',np.minimum(dual,0),np.where(d['sense']=='>',np.maximum(dual,0),dual))
    assert np.isfinite(pi).all()
    parts=[dyadic(v) for v in pi];pexp=max(e for v,e in parts if v)
    exponent=max(denom(M.data)+pexp,denom(d['rhs'])+pexp,denom(d['objective']),dyadic(d['constant'])[1])
    bexp=max(denom(d['lower'][:n]),denom(d['upper'][:n]));total_exp=exponent+bexp
    rhs_sum=0
    for (p,pd),rhs in zip(parts,d['rhs']):
        if p and rhs:
            b,bd=dyadic(rhs);rhs_sum+=(p*b)<<(exponent-pd-bd)
    c,cd=dyadic(d['constant']);rhs_sum+=c<<(exponent-cd)
    B=M.tocsc();res=[];products=0
    for j in range(M.shape[1]):
        dot=0
        for k in range(B.indptr[j],B.indptr[j+1]):
            p,pd=parts[int(B.indices[k])]
            if p:
                v,vd=dyadic(B.data[k]);dot+=(p*v)<<(exponent-pd-vd);products+=1
        v,vd=dyadic(d['objective'][j]);res.append((v<<(exponent-vd))-dot)
    original_sum=0
    for j,r in enumerate(res[:n]):
        bound=d['lower'][j] if r>=0 else d['upper'][j];b,bd=dyadic(bound)
        original_sum+=(r*b)<<(bexp-bd)
    a=Authority();blocks=[];private_sum=0
    for label,h,f,offset in metadata:
        assert h['boundary_bounds']==[440,1080]
        catalog=read(OUT/(label+'_INTEGER_TRAJECTORIES.json'))['trajectories'];info={}
        for path in catalog:
            edges=[a.arcs[k] for k in path['arcs']]
            stay={edge[1] for edge in edges if edge[-1] is None}
            departures={edge[1] for edge in edges if edge[-1] is not None and h['start']<=edge[1]<h['end_exclusive']}
            info[path['id']]=(len(stay|departures),stay)
        local_end=n+offset+len(f['lower']);us=list(range(local_end-4,local_end))
        minimum=None;minimum_block=None;count=0;column_cursor=n+offset
        for b in f['blocks']:
            pid,bits,c0,c1,r0,r1=map(int,b);events,stay=info[pid];lam=c0+offset;estate=list(range(c0+1+offset,c0+2+events+offset));first_p=c0+2+events+offset
            assert lam==column_cursor;column_cursor=c1+offset
            assert d['lower'][lam]==0 and d['upper'][lam]==1
            coefficient=res[lam]
            for j in estate:
                assert d['lower'][j]==0 and d['upper'][j]==1080
                coefficient+=res[j]*(440 if res[j]>=0 else 1080)
            assert (c1+offset-first_p)%2==0
            for j in range(first_p,c1+offset,2):
                assert (d['lower'][j],d['upper'][j])==(0,300)
                assert (d['lower'][j+1],d['upper'][j+1])==(-400,400)
                coefficient+=min(0,res[j])*300-abs(res[j+1])*400
            for t,u in zip(range(h['start'],h['end_exclusive']),us):
                assert (d['lower'][u],d['upper'][u])==(0,1)
                if t not in stay:coefficient+=min(0,res[u])
            if minimum is None or coefficient<minimum:minimum,minimum_block=coefficient,dict(pathid=pid,connected_mode_bits=bits)
            count+=1
        assert count==h['blocks'] and column_cursor+4==local_end
        private_sum+=minimum
        blocks.append(dict(label=label,disjuncts=count,minimum_private_residual_cost_exact=str(F(minimum,1<<exponent)),minimizer=minimum_block,all_private_variables_accounted=True))
    total=(rhs_sum<<bexp)+original_sum+(private_sum<<bexp)
    exact=F(total,1<<total_exp);out=float(exact)
    if F.from_float(out)>exact:out=float(np.nextafter(out,-np.inf))
    assert F.from_float(out)<=exact
    return dict(lower_bound=out,exact_rational=str(exact),exact_pi_rhs_and_constant=str(F(rhs_sum,1<<exponent)),exact_original_box_correction=str(F(original_sum,1<<total_exp)),exact_homogeneous_private_correction=str(F(private_sum,1<<exponent)),blocks=blocks,matrix_nonzeros=M.nnz,nonzero_dual_products_evaluated=products,all_arithmetic_exact_dyadic_integer_and_Fraction=True,lower_float_outward_rounded=True,requires_primal_feasibility=False,optimize_calls=0,proof='Clip dual row signs; c*x+c0 >= pi*rhs+c0+r*x. Every hull lift satisfies 440*lambda<=E<=1080*lambda,0<=p<=300*lambda,|Q|<=400*lambda,lambda>=0,sum(lambda)=1 and0<=u_t<=sum(off_t lambda). Thus min r*x over these relaxed perspective boxes equals the minimum disjunct residual cost per block, with min(0,r_u) allocated to off disjuncts. Original variables independently minimize over original finite boxes. Dynamics and PCS may be dropped only in this certificate minimization, never from the model. This relaxed domain contains every original integer lift, so the lower bound is valid.',valid_for_every_original_integer_schedule=True,not_a_formulation_change=True)

def main(stage):
    began=time.perf_counter();labels=['MESS04_69_72'] if stage=='SINGLE_WINDOW_STRENGTHENED_LP' else ['MESS04_69_72','MESS03_69_72']
    M,d,n,metadata=model(labels);bundle=OUT/(stage+'_DUAL_RC_SLACK.npz')
    if bundle.exists():
        with np.load(bundle) as z:pi=z['dual']
    else:
        with np.load(OUT/'MULTIWINDOW_CAPTURE_DUAL.npz') as z:pi=z['dual']
    result=certificate(M,d,pi,n,metadata);result['runtime_seconds']=time.perf_counter()-began
    result['input_dual_array_bytes_SHA256']=hashlib.sha256(pi.tobytes()).hexdigest()
    result['source_hulls']=[dict(label=label,matrix_SHA256=h['matrix_SHA256'],data_SHA256=h['data_SHA256'],independent_verification_SHA256=sha(OUT/(label+'_INDEPENDENT_VERIFICATION.json'))) for label,h,f,offset in metadata]
    write(stage+'_HOMOGENEOUS_VALID_LB_CERTIFICATE.json',result)
    record=read(OUT/(stage+'.json'));previous=record['new_valid_LB'];valid=max(previous,result['lower_bound'])
    record.update(homogeneous_exact_certificate=result,new_valid_LB=valid,delta_LB=valid-LB,percent_required_LB_recovered=100*(valid-LB)/REQUIRED,material=valid-LB>=.001,certificate_domain_tightening_without_new_optimize=True)
    write(stage+'.json',record)
    if stage=='SINGLE_WINDOW_STRENGTHENED_LP':
        old=read(OUT/'SINGLE_WINDOW_VALID_LB_CERTIFICATE.json');old.update(homogeneous_exact_certificate=result,new_valid_LB=valid,delta_LB=valid-LB,percent_required_LB_recovered=100*(valid-LB)/REQUIRED);write('SINGLE_WINDOW_VALID_LB_CERTIFICATE.json',old)
    print('HOMOGENEOUS_EXACT_CERTIFICATE',stage,'lower',result['lower_bound'],'valid',valid,'seconds',result['runtime_seconds'],flush=True)

if __name__=='__main__':
    stage=sys.argv[1] if len(sys.argv)>1 else 'SINGLE_WINDOW_STRENGTHENED_LP';assert stage in ('SINGLE_WINDOW_STRENGTHENED_LP','MULTIWINDOW_STRENGTHENED_LP');main(stage)

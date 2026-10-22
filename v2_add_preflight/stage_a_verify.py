"""Independent original-row proof for the variable AIDC static selection."""
import sys
import numpy as np
import scipy.sparse as sp
from .stage_common import *

def verify(tag):
    with measured(tag+'_VARIABLE_GRID_INDEPENDENT_VERIFICATION.json') as (report,start):
        folder=WORK/tag/'grid';receipt=read(folder/'RECEIPT.json');rows=[]
        for t in range(96):
            guard(start);path=folder/f'{t:02d}';A=sp.load_npz(path/'RAW.npz');H=sp.load_npz(path/'RECONSTRUCTION.npz');c=np.load(path/'CONSTANT.npy')
            with np.load(path/'DOMAIN.npz') as z:d={k:z[k] for k in z.files}
            with np.load(path/'MAP.npz') as z:s={k:z[k] for k in z.files}
            eq=np.flatnonzero(d['sense']=='=');non=np.flatnonzero(d['sense']!='=');E=A[eq,13:]
            assert E.nnz==len(c) and np.array_equal(E.indices,np.arange(len(c)))
            assert (-(sp.diags(E.data)@H)-A[eq,:12]).nnz==0 and np.array_equal(c*E.data,d['rhs'][eq])
            # Independent dense expansion, column-by-column sum rather than
            # the producer's sparse positive/negative interval products.
            helper=A[non,13:];direct=A[non,:12];projected=(direct+helper@H).toarray()
            rhs=d['rhs'][non]-helper@c;rc=A[non,12].toarray().ravel()
            bounds=[];coeff=[projected];right=[rhs];rho=[rc]
            l=d['lower'][:12];u=d['upper'][:12];box=np.maximum(abs(l),abs(u))
            component=abs(direct)@box+abs(helper)@(abs(H)@box+abs(c))+abs(d['rhs'][non]);magnitude=[component]
            for sign,side in ((1,'upper'),(-1,'lower')):
                ids=np.flatnonzero(np.isfinite(d[side][13:]));bounds.extend(ids)
                coeff.append((sign*H[ids]).toarray());right.append(sign*(d[side][13:][ids]-c[ids]));rho.append(np.zeros(len(ids)))
                magnitude.append(abs(H[ids])@box+abs(c[ids])+abs(d[side][13:][ids]))
            C=np.vstack(coeff);r=np.concatenate(right);rc=np.concatenate(rho)
            upper=np.zeros(len(r));lower=np.zeros(len(r))
            for k in range(12):
                a=C[:,k]*l[k];b=C[:,k]*u[k];upper+=np.maximum(a,b);lower+=np.minimum(a,b)
            eps=np.finfo(float).eps;error=120*eps/(1-120*eps)*(1+np.concatenate(magnitude))
            error+=2e-12*(1+np.maximum(abs(lower),abs(upper)));upper=np.nextafter(upper+error,np.inf)
            obj=np.r_[np.char.startswith(d['row_names'][non].astype(str),'parent_line_thermal_face'),np.zeros(len(bounds),dtype=bool)]
            margin=1e-7*(1+abs(r));safe=upper<=r-margin;L=receipt['new_domain_rho_witness']['used']
            assert not np.any(s['safe']&obj)
            assert np.all(safe[s['safe']])
            assert np.all((upper<=r-rc*L-margin)[s['dominant']]) and np.all(obj[s['dominant']])
            n=len(non);kept=non[~(s['safe'][:n]|s['dominant'][:n])];needed=set(map(int,A[kept].indices[A[kept].indices>=13]-13))
            needed.update(map(int,np.array(bounds)[~s['safe'][n:]]))
            assert np.array_equal(s['columns'],np.r_[np.arange(13),13+np.array(sorted(needed),dtype=int)])
            assert np.array_equal(s['rows'],np.sort(np.r_[kept,eq[np.array(sorted(needed),dtype=int)]]))
            B=sp.load_npz(path/'SELECTED.npz');difference=B-A[s['rows']][:,s['columns']];difference.eliminate_zeros();assert difference.nnz==0
            with np.load(path/'SELECTED_DOMAIN.npz') as z:sd={k:z[k] for k in z.files}
            for k in ('rhs','sense','row_names'):assert np.array_equal(sd[k],d[k][s['rows']])
            for k in ('lower','upper','types','objective','names'):assert np.array_equal(sd[k],d[k][s['columns']])
            rows.append(dict(slot=t,all_original_rows=A.shape[0],selected_rows=B.shape[0],selected_nonzeros=B.nnz,
                independent_safety_implication_PASS=True,all_unresolved_rows_retained=True,exact_defining_equations=True))
            if t%12==0:print('INDEPENDENT VARIABLE AIDC GRID',tag,t,flush=True)
        report.update(PASS=True,records=rows,scope='Variable original C1 P box with PF=.95; fixed same-case MESS parameter',
            LP_and_integer_grid_projection_identical=True,new_variable_domain_witness=receipt['new_domain_rho_witness'],
            variable_Source_Job_matrix_acceptance_separate=True,fixed_B0_proof_reused=False)

if __name__=='__main__':verify(sys.argv[1] if len(sys.argv)>1 else 'A1')

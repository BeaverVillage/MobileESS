"""Read-only independent CSC/Fraction reconstruction after root native work."""
from fractions import Fraction as F
import numpy as np
from v42_m_stage.common import ROOT,OUT,SCI,EPS,read,write,sha
from v42_m_stage_root.common import PREVIOUS
from v42_degen.identity import inputs
from v42_dw_root.partition import axes
from v42_disjunctive.certificate import down

def run():
    cp=read(OUT/'DW_CHECKPOINT_LATEST.json')
    assert cp['type']=='TERMINAL' and not (OUT/'DW_INFLIGHT.json').exists()
    final=read(OUT/'DW_CONTINUATION_FINAL_CERTIFICATION.json')
    if final['status']!='COMPLETED' or not final['certificate']['certified']:
        write('ROOT_INDEPENDENT_BOUND_CHECK.json',dict(PASS=True,
            new_corrected_bound_available=False,new_corrected_bound_not_claimed=True,
            inherited_arc_support=read(SCI/'DW_CONTINUATION_BASE_AUDIT.json')['independent_arc']))
        return
    c=final['certificate'];key=c['dual_SHA']
    matching=[r for r in cp['restart_state']['rmps'] if r['status']==2 and r['dual_SHA']==key]
    point=OUT/matching[-1]['point_file'] if matching else SCI/read(SCI/'DW_CHECKPOINT_LATEST.json')['RMP']['point_file']
    with np.load(point) as z:pi=z['pi'].copy();alpha=z['alpha'].copy()
    A,d,B,e,*_=inputs();owner,row_owner=axes()
    cols=np.flatnonzero(owner<0);rows=np.flatnonzero(row_owner<0)
    G=B[rows][:,cols].tocsc();rhs=e['rhs'][rows];senses=e['sense'][rows]
    assert np.all(pi[senses=='<']<=0) and np.all(pi[senses=='>']>=0)
    enclosure=PREVIOUS/'PROVEN_COORDINATE_ENCLOSURES.npz'
    assert sha(enclosure)==read(PREVIOUS/'COORDINATE_ENCLOSURE_PROOF.json')['artifact_SHA']
    with np.load(enclosure) as z:lo=z['lower'][cols];hi=z['upper'][cols]
    # Independent columnwise traversal, unlike the runtime CSR residual dictionary.
    value=F(float(e['constant']))+sum((F(float(p))*F(float(h)) for p,h in zip(pi,rhs) if p),F(0))
    objective=e['objective'][cols]
    for j in range(G.shape[1]):
        q=F(float(objective[j]))
        for k in range(G.indptr[j],G.indptr[j+1]):
            i=G.indices[k]
            if pi[i]:q-=F(float(G.data[k]))*F(float(pi[i]))
        if q:value+=q*F(float(lo[j] if q>=0 else hi[j]))
    p=c['exact_global_proof'];assert value==F(int(p['exact_numerator']),int(p['exact_denominator']))
    pricing=[read(OUT/name) for name in c['pricing_receipts']]
    assert len(pricing)==4 and {r['unit'] for r in pricing}=={0,1,2,3}
    pricing.sort(key=lambda r:r['unit'])
    for r in pricing:
        assert r['valid_bound'] and r['native_status'] in (2,9) and r['type']=='FINAL_CERTIFICATION'
        assert r['full_original_domain'] and not r['stabilized_discovery']
        assert r['dual_SHA']==r['true_dual_SHA']==key
    betas=[F(down(F(float(r['ObjBound']))-F(EPS))) for r in pricing]
    expected=value+sum((F(float(a))+min(F(0),b) for a,b in zip(alpha,betas)),F(0))
    assert expected==F(int(c['exact_numerator']),int(c['exact_denominator']))
    assert c['L_corr']==down(expected) and F(c['L_corr'])<=expected and c['L_corr']<=c['U_RMP']
    write('ROOT_INDEPENDENT_BOUND_CHECK.json',dict(PASS=True,
        method='Independent CSC columnwise Fraction support plus same-dual native global bounds and outward rounding',
        source_SHA=sha(ROOT/'verify_m_stage_closeout.py'),true_dual_SHA=key,
        exact_global_numerator=str(value.numerator),exact_global_denominator=str(value.denominator),
        corrected_numerator=str(expected.numerator),corrected_denominator=str(expected.denominator),
        reconstructed_corrected_LB=down(expected),restricted_LP_upper=c['U_RMP'],
        existing_numerical_authority=EPS,global_optimize_calls=0,
        inherited_arc_support=read(SCI/'DW_CONTINUATION_BASE_AUDIT.json')['independent_arc']))
    print('INDEPENDENT_ROOT_BOUND_PASS',down(expected),flush=True)

if __name__=='__main__':run()

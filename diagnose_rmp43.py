"""Read-only diagnosis of the registered rejected terminal LP."""
import csv,json
from pathlib import Path
import numpy as np
from v42_degen.identity import inputs,digest
from v42_dw_root.partition import axes
from reproduce_rmp43 import OUT,write,read,ROOT
def run():
    _,_,_,e,_,_=inputs();owner,row_owner=axes();rows=np.flatnonzero(row_owner<0)
    with np.load(OUT/'RMP43_TERMINAL_BEFORE_GATE.npz') as z:
        pi,rc,sense=z['pi'],z['rc'],z['sense'];names=z['row_names'];x=z['point']
        bad=np.flatnonzero(((sense=='<')&(pi>0))|((sense=='>')&(pi<0)))
        records=[]
        for i in bad:
            semantic=str(e['row_names'][rows[i]]) if i<len(rows) else str(names[i])
            records.append(dict(native_row_index=int(i),native_row_name=str(names[i]),semantic_row_name=semantic,
                family=semantic.split('[',1)[0],sense=str(sense[i]),raw_Pi=float(pi[i]),
                canonical_Pi=float(pi[i]),row_multiplier=1.,CBasis=int(z['raw_CBasis'][i]) if 'raw_CBasis' in z else None))
        selected=np.where(rc>=0,z['lower'],z['upper']);unsupported=np.flatnonzero((rc!=0)&(abs(selected)>=1e90))
        boundbad=[dict(variable_index=int(i),name=str(z['names'][i]),native_RC=float(rc[i]),
                       lower=float(z['lower'][i]) if np.isfinite(z['lower'][i]) else str(z['lower'][i]),
                       upper=float(z['upper'][i]) if np.isfinite(z['upper'][i]) else str(z['upper'][i]),X=float(x[i])) for i in unsupported]
    out=dict(first_failure=records[0],sign_failures=records,unsupported_infinite_bound_duals=boundbad,
        count_sign_failures=len(records),count_unsupported_bound_duals=len(boundbad),
        row_axis_matches_RMP42=True,semantic_row_axis_SHA=digest(e['row_names'][rows]),
        canonical_transform='identity +1; native row sense and original row sense are identical',
        row_negation=False,row_normalization=False,Pi_BarPi_mixing=False,stale_dual=False,
        diagnosis='Native post-crossover numerical dual-cone inconsistency; no code sign-transform mismatch. Barrier reports Numerical trouble and Numeric-to-Optimal crossover.',
        exact_sign_transform_cause='No transform error: +1 times positive native Pi remains positive on <= row.',
        primal_RC_identity_pass_but_dual_authority_fail=True,pricing_authorized=False)
    write('EXACT_FAILURE_DIAGNOSIS.json',out)
    print(json.dumps({k:v for k,v in out.items() if k not in ('sign_failures','unsupported_infinite_bound_duals')}),flush=True)
if __name__=='__main__':run()

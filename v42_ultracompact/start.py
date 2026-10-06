from .common import *
from v42_degen.identity import inputs
from v42_strengthening.analysis import graph_inputs
from v42_supercompact.formulation import Compact
from v42_supercompact.verify import inverse_map
from v42_supercompact.benchmark import ScientificValidator
def validator():
    full,fd,A,d,identity,_=inputs();sites,initial,arcs,battery,_=graph_inputs();compact=Compact(A,d,arcs,initial,96);_,_,_,_,T,offset,rows,cols,_=inverse_map()
    return ScientificValidator(full,fd,A,d,compact,T,offset,cols),identity
def run():
    with np.load(PARENT/'C2_VALID_START.npz') as z:x=z['point'].copy()
    original,identity=validator();check=original('C2',x);assert check['PASS'];results={}
    for label in ['C2','C3A','C3B','C3C']:
        A,d=load(label);r=residual(A,d,x);r['PASS']=r['max_row_violation']<=1e-8 and r['max_bound_violation']<=1e-8 and r['max_integrality_violation']==0;assert r['PASS'],(label,r);results[label]=r;np.savez_compressed(OUT/(label+'_VALID_START.npz'),point=x)
    result=dict(PASS=True,parent_start_SHA256=sha(PARENT/'C2_VALID_START.npz'),arms=results,original_full_scientific_validation=check,all_C2_columns_copied_identically=True,physical_PQ_SOC_mode_route_repairs=0,auxiliary_repairs=0,maximum_row_residual=max(r['max_row_violation'] for r in results.values()),FeasibilityTol=1e-8)
    write('ULTRACOMPACT_START_VALIDATION.json',result);print('ULTRA_START_PASS',result['maximum_row_residual'],flush=True)
if __name__=='__main__':run()

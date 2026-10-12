"""Reuse Source18r and PR218 validation without modifying predecessor files."""
from pathlib import Path
import hashlib,json,numpy as np
from tools.k32_routefixed1800 import adapter as prior
ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_minimax_beam1800'
BASE='dd283b631e5b88c2f26ca81fde34b2c2cc180a45'
HISTORICAL=.5461621302242249
GLOBAL_LB=.46498486997548166
v,r,n,g=prior.v,prior.r,prior.n,prior.g
OLD=prior.OLD
write,record,read=prior.write,prior.record,prior.read
prior.DOCS=DOCS;prior.base.DOCS=DOCS;prior.base.configure()
r.ORIGINALS['PR218']=(Path('D:/v42_b2_k32_routefixed1800_canary_20261012'),BASE)
guard=prior.guard
cold_spec=prior.cold_spec
stationary_paths=prior.stationary_paths

def route_spec(case,candidate,goal=None):
    spec=prior.route_spec(case,candidate)
    spec.update(stationary_control=bool(candidate.get('stationary_control',False)),improvement_goal=goal,
        numerical_improvement_delta=1e-5,score_role='MINIMAX_PEAK_WITH_SOC_REBOUND_LOOKAHEAD',
        mathematical_model_signature=hashlib.sha256(json.dumps([candidate['paths'],goal],sort_keys=True,separators=(',',':')).encode()).hexdigest())
    return spec

def restriction(case,center,spec):return prior.restriction(case,center,spec)

def audit(case,center,spec,low,high,output=None):
    if spec['method']!='ROUTE_FIXED' or not spec.get('stationary_control'):
        result=prior.audit(case,center,spec,low,high)
    else:
        assert center is None and spec['paths']==stationary_paths(case) and spec['moves']==0
        ids,vals=prior.route_values(case,spec['paths'])
        assert np.array_equal(ids,spec['route_fixed_columns']) and np.array_equal(vals,spec['route_fixed_values'])
        el,eu=case.d['lower'].copy(),case.d['upper'].copy();el[ids]=vals;eu[ids]=vals
        assert np.array_equal(el,low) and np.array_equal(eu,high)
        assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(case.d)==v.DOMAIN_SHA
        result=dict(PASS=True,stationary_control=True,mathematically_original_N1_equivalent=True,
            all384_modes_free=True,original_rows_and_nonroute_bounds_preserved=True,Native_optimize_calls=0)
    if output:write(output,result)
    return result

def current_paths(case,point):
    original=case.lift(point);names={str(n):j for j,n in enumerate(case.original_d['names'])};paths={}
    for u,origin in case.graph[1].items():
        outgoing={}
        for k,a in enumerate(case.graph[2]):
            j=names.get(f'arc[{u},{k}]')
            if j is not None and original[j]==1.:outgoing[a[:2]]=k
        site,t=origin,0;path=[]
        while t<96:
            k=outgoing[site,t];path.append(k);site,t=case.graph[2][k][2:4]
        assert t==96;paths[u]=path
    return paths
